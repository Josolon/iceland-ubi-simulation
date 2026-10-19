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
"""
import numpy as np

from ubisim.abm import params as P


class Automation:
    def __init__(self, p):
        self.p = p
        self.exposure = np.array([p["automation"]["exposure"].get(n, .35) for n in P.OCCUPATIONS])
        self.complement = np.array([p["automation"].get("complementarity", {}).get(n, .3) for n in P.OCCUPATIONS])
        self.automated = np.zeros(len(P.OCCUPATIONS))
        self.augmented = np.zeros(len(P.OCCUPATIONS))   # share of a profession's work made more productive
        self.reinstated = np.zeros(len(P.OCCUPATIONS))  # new tasks, as a share of the profession's base work
        self.weights = None
        self.capability = 1.0
        self.machine_income = 0.0
        self.displaced_fte = 0.0

    def active(self):
        return self.p["automation"]["ai_progress_rate"] > 0

    def update(self, year, real_wage_index, base_fte, price):
        """Take-up per profession, given how capable machines are and what the work costs."""
        a = self.p["automation"]
        self.capability = (1 + a["ai_progress_rate"]) ** year
        # relative cost of doing the work with people rather than machines
        score = self.exposure * np.maximum(real_wage_index, .1) ** a["wage_sensitivity"] * self.capability
        take_up = score ** a["adoption_curvature"] / (a["adoption_midpoint"] ** a["adoption_curvature"]
                                                      + score ** a["adoption_curvature"])
        target = self.exposure * take_up
        # capital takes time to install: move part of the way each year, and never backwards
        self.automated = np.maximum(self.automated, self.automated + a["adoption_speed"] * (target - self.automated))
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

    def income(self, wage_bill_per_fte, price):
        """Machine income: the wage bill no longer paid, less what running the machines costs (bn ISK/yr)."""
        a = self.p["automation"]
        saved = self.displaced_fte * wage_bill_per_fte * 12 / 1e9
        self.machine_income = max(0.0, saved * (1 - a["operating_cost_share"]))
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
                "automation_stake_cost": financing, "machine_income": self.machine_income}

    def productivity_factor(self):
        """Output per hour rises as machines take over part of the work, and as they make people faster."""
        a = self.p["automation"]
        share = float((self.automated * self.exposure).sum() / max(self.exposure.sum(), 1e-9))
        aug = float((self.augmented * self.weights).sum()) if self.weights is not None else 0.0
        return (1 + a["output_gain"] * share) * (1 + a.get("augmentation_gain", 0.0) * aug)

    def snapshot(self):
        return {"automation_capability": self.capability,
                "automated_share": float(self.automated.mean()),
                "automation_displaced_fte": self.displaced_fte,
                "automation_augmented_share": float((self.augmented * self.weights).sum()) if self.weights is not None else 0.0,
                "automation_new_task_fte": float((self.reinstated * self.weights).sum()) if self.weights is not None else 0.0,
                "automation_productivity": self.productivity_factor(),
                "machine_income_bn": self.machine_income,
                **{f"auto_{n.replace(' ', '_')}": float(v) for n, v in zip(P.OCCUPATIONS, self.automated)}}
