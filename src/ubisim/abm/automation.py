"""Automation that responds to wages: machines replace work when the work costs more than the machine.

AI capability improves every year at a rate the scenario sets. Each profession has an exposure: the share of its
tasks a machine could plausibly do. Whether that potential is taken up depends on what the work costs, so rising
real wages pull automation forward — the link the model is meant to test rather than assume.

The wage bill that is no longer paid does not vanish: it becomes machine income. The state can take a share of it
through corporate tax, a levy on machine income, or an ownership stake in the capital.

Exposure figures are EST, informed by the task-content literature (routine clerical and machine work high; care,
teaching and unpredictable physical work low).

v3 adds the two other channels the literature finds (Acemoglu and Restrepo 2019, "Automation and new tasks"):
  augmentation — AI makes the people doing complementary tasks more productive rather than replacing them. The
    complementarity of each profession is EST after Pizzinelli et al. (IMF WP 2023/216), who find professionals
    and managers highly exposed but highly complementary, and clerical work exposed with little complementarity.
    Its take-up follows capability alone, not wages: nobody saves a wage by making a doctor faster.
  reinstatement — new tasks for people appear as old ones go (prompting, checking, integrating, new services).
    A share of the work displaced comes back as new demand, with a lag, where complementarity is high.
Together they are calibrated so that the consensus pace (5% a year) gives about +0.5 points a year of
productivity growth with little change in unemployment — where OECD (2024), Acemoglu (2024), Goldman Sachs (2023)
and Penn Wharton (2025) centre — and a fast pace (15%) displaces faster than new tasks come back.

1.1 splits the technology in two. Office AI (language models and agents) does cognitive tasks: clerical work,
analysis, drafting, code (exposure after Eloundou et al. 2024 and Gmyrek, Berg and Bescond, ILO 2023). Robotics
does physical ones: processing lines, driving, cleaning, kitchens, warehouses (`exposure_physical`). Each has its own
pace — the scenario's, not Iceland's: the country buys the technology the world makes — and its own cost, robots
needing far more capital for each post they fill. Iceland can pay part of what adopting either costs
(`ai_subsidy`, `robot_subsidy`), which brings take-up forward. Office AI takes entry-level work first
(`junior_load_ai`): junior tasks are the codifiable ones, and since 2022 employment of 22-25-year-olds in the most
exposed occupations has fallen against older workers' (Brynjolfsson, Chandar and Chen 2025; Lichtinger and Hosseini
2025). careers.py carries what that does to first jobs and the experience they give.
"""
import numpy as np

from ubisim.abm import params as P


class Automation:
    def __init__(self, p):
        self.p = p
        a = p["automation"]
        self.exposure_ai = np.array([a["exposure"].get(n, .35) for n in P.OCCUPATIONS])
        self.exposure_robot = np.array([a.get("exposure_physical", {}).get(n, 0.0) for n in P.OCCUPATIONS])
        self.exposure = np.minimum(self.exposure_ai + self.exposure_robot, .95)
        self.complement = np.array([a.get("complementarity", {}).get(n, .3) for n in P.OCCUPATIONS])
        self.automated_ai = np.zeros(len(P.OCCUPATIONS))
        self.automated_robot = np.zeros(len(P.OCCUPATIONS))
        self.automated = np.zeros(len(P.OCCUPATIONS))
        self.robot_capability = 1.0
        self.new_capex = (0.0, 0.0)          # FTE newly displaced this year, by office AI and by robots
        self.subsidy_cost = 0.0
        self.augmented = np.zeros(len(P.OCCUPATIONS))   # share of a profession's work made more productive
        self.reinstated = np.zeros(len(P.OCCUPATIONS))  # new tasks, as a share of the profession's base work
        self.weights = None
        self.capability = 1.0
        self.machine_income = 0.0
        self.displaced_fte = 0.0

    def active(self):
        a = self.p["automation"]
        return a["ai_progress_rate"] > 0 or a.get("robot_progress_rate", 0.0) > 0

    def subsidies(self):
        """Share of what adopting office AI and robots costs that the state pays (under the reform only)."""
        a, pol = self.p["automation"], self.p["policy"]
        if pol["regime"] != "platform":
            return 0.0, 0.0
        return min(a.get("ai_subsidy", 0.0), .9), min(a.get("robot_subsidy", 0.0), .9)

    def _take_up(self, exposure, wage, capability, midpoint, subsidy):
        a = self.p["automation"]
        # relative cost of doing the work with people rather than machines; a subsidy makes the machine cheaper
        score = exposure * np.maximum(wage, .1) ** a["wage_sensitivity"] * capability / (1 - subsidy)
        c = a["adoption_curvature"]
        return exposure * score ** c / (midpoint ** c + score ** c)

    def update(self, year, real_wage_index, base_fte, price):
        """Take-up per profession, given how capable machines are and what the work costs."""
        a = self.p["automation"]
        self.capability = (1 + a["ai_progress_rate"]) ** year
        self.robot_capability = (1 + a.get("robot_progress_rate", 0.0)) ** year
        s_ai, s_robot = self.subsidies()
        t_ai = self._take_up(self.exposure_ai, real_wage_index, self.capability, a["adoption_midpoint"], s_ai)
        t_robot = self._take_up(self.exposure_robot, real_wage_index, self.robot_capability,
                                a.get("robot_adoption_midpoint", a["adoption_midpoint"]), s_robot)
        # capital takes time to install: move part of the way each year, and never backwards
        before = self.automated_ai.copy(), self.automated_robot.copy()
        self.automated_ai = np.maximum(self.automated_ai, self.automated_ai + a["adoption_speed"] * (t_ai - self.automated_ai))
        self.automated_robot = np.maximum(self.automated_robot, self.automated_robot
                                          + a.get("robot_adoption_speed", a["adoption_speed"]) * (t_robot - self.automated_robot))
        self.automated = np.minimum(self.automated_ai + self.automated_robot, .95)
        self.new_capex = (float(((self.automated_ai - before[0]) * base_fte).sum()),
                          float(((self.automated_robot - before[1]) * base_fte).sum()))
        self.displaced_fte = float((self.automated * base_fte).sum())
        # augmentation: take-up by capability alone
        c = a.get("augmentation_curvature", 2.0)
        aug_take = (self.capability - 1) ** c / (a.get("augmentation_midpoint", .6) ** c + (self.capability - 1) ** c)
        aug_target = self.complement * aug_take
        self.augmented = np.maximum(self.augmented, self.augmented + a["adoption_speed"] * (aug_target - self.augmented))
        # reinstatement: a share of the displaced work returns as new tasks, placed where complementarity is high
        w = self.complement * base_fte
        self.weights = base_fte / max(base_fte.sum(), 1e-9)
        want = a.get("reinstatement_share", 0.0) * self.displaced_fte * w / max(w.sum(), 1e-9) / np.maximum(base_fte, 1e-9)
        self.reinstated += a.get("reinstatement_speed", .2) * (want - self.reinstated)
        return self.automated

    def demand_factor(self):
        """Work left to people, against the base: what machines took is gone, the new tasks come on top. Both are
        shares of the profession's base work, so they add. Multiplied, as they were, the new tasks shrank with the
        automation of the profession they landed in — a cross term too small to see in ten years, but by the 2050s
        at 5% a year it had taken 4-5% of all jobs that the calibrated reinstatement meant to give back (found
        2026-10-01, the long view's unemployment climbing to 9-13% with no shock)."""
        return np.maximum(1 - self.automated + self.reinstated, 0.0)

    def entry_cut(self):
        """Share of each profession's entry-level work the machines have taken: office AI takes it first."""
        a = self.p["automation"]
        return np.minimum(a.get("junior_load_ai", 1.0) * self.automated_ai
                          + a.get("junior_load_robot", 1.0) * self.automated_robot, .95)

    def junior_hiring(self):
        """How many juniors a profession takes on against what its work left to people would suggest: below 1
        where machines took entry-level tasks faster than the rest."""
        overall = np.maximum(1 - self.automated + self.reinstated, .05)
        return np.clip((1 - self.entry_cut() + self.reinstated) / overall, 0.0, 1.0)

    def income(self, wage_bill_per_fte, price):
        """Machine income: the wage bill no longer paid, less what running the machines costs (bn ISK/yr). And
        what the state pays towards adopting them this year, from the machines' cost: years of the wages they
        replace (capex_years_*)."""
        a = self.p["automation"]
        saved = self.displaced_fte * wage_bill_per_fte * 12 / 1e9
        self.machine_income = max(0.0, saved * (1 - a["operating_cost_share"]))
        s_ai, s_robot = self.subsidies()
        year_pay = wage_bill_per_fte * 12 / 1e9
        self.subsidy_cost = year_pay * (s_ai * max(self.new_capex[0], 0.0) * a.get("capex_years_ai", .5)
                                        + s_robot * max(self.new_capex[1], 0.0) * a.get("capex_years_robot", 2.0))
        return self.machine_income

    def fiscal(self):
        """What the state takes from machine income: corporate tax, a levy, and dividends on any public stake."""
        a, pol = self.p["automation"], self.p["policy"]
        platform = pol["regime"] == "platform"
        rate = pol["corporate_tax_rate"] if platform else .20
        levy = a["levy_rate"] if platform else 0.0
        stake = a["state_capital_share"] if platform else 0.0
        taxed = self.machine_income * rate
        levied = self.machine_income * levy
        after_tax = self.machine_income * (1 - rate - levy)
        # A stake is bought, not given: at a fair price the capital is worth its after-tax earnings over the return
        # investors ask of it, and the state pays interest on what it borrowed to buy it. What is left is the
        # equity premium, not the machines' whole income — owning the robots is a way of taking risk for a return,
        # not a free source of revenue. Before 2026-10-01 the dividends came with no purchase.
        value = after_tax / max(a.get("stake_required_return", .07), .01)
        financing = stake * value * a.get("stake_financing_rate", .03)
        dividends = after_tax * stake * a["dividend_payout"] - financing
        return {"automation_tax": taxed, "automation_levy": levied, "automation_dividends": dividends,
                "automation_stake_cost": financing, "machine_income": self.machine_income,
                "automation_subsidy": self.subsidy_cost}

    def productivity_factor(self):
        """Output per hour rises as machines take over part of the work, and as they make people faster."""
        a = self.p["automation"]
        # the same gain per task taken over, by either technology, as before the split
        share = float((self.automated * self.exposure).sum() / max(self.exposure.sum(), 1e-9))
        aug = float((self.augmented * self.weights).sum()) if self.weights is not None else 0.0
        return (1 + a["output_gain"] * share) * (1 + a.get("augmentation_gain", 0.0) * aug)

    def snapshot(self):
        return {"automation_capability": self.capability,
                "automated_share": float(self.automated.mean()),
                "automation_displaced_fte": self.displaced_fte,
                "automation_ai_share": float((self.automated_ai * self.weights).sum()) if self.weights is not None else 0.0,
                "automation_robot_share": float((self.automated_robot * self.weights).sum()) if self.weights is not None else 0.0,
                "robot_capability": self.robot_capability,
                "automation_subsidy_bn": self.subsidy_cost,
                "automation_augmented_share": float((self.augmented * self.weights).sum()) if self.weights is not None else 0.0,
                "automation_new_task_fte": float((self.reinstated * self.weights).sum()) if self.weights is not None else 0.0,
                "automation_productivity": self.productivity_factor(),
                "machine_income_bn": self.machine_income,
                **{f"auto_{n.replace(' ', '_')}": float(v) for n, v in zip(P.OCCUPATIONS, self.automated)}}
