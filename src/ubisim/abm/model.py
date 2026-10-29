"""The model society: yearly choices, wage clearing, ventures, migration, demography and public accounts."""
import copy

import numpy as np

from ubisim.abm import macro as macromod
from ubisim.abm import policy as pol_rules
from ubisim.abm import automation as automationmod
from ubisim.abm import frontier as frontiermod
from ubisim.abm import housing
from ubisim.abm import careers
from ubisim.abm import familycare
from ubisim.abm import capital
from ubisim.abm import pensions
from ubisim.abm import informal
from ubisim.abm import hours
from ubisim.abm import financial
from ubisim.abm import regions
from ubisim.abm import sectors as sectormod
from ubisim.abm import population as popmod
from ubisim.abm import params as P
from ubisim.abm.params import N_OCC, OCCUPATIONS, deep_merge
from ubisim.abm.population import CHARACTERS, EEA, FULL, INDEP, IS, NON_EEA, NONWORK, PART, VENTURE
from ubisim.models import static_balance as sb

EPS = .05
N_GROUPS = 10  # (16-19, 20-24, 25-54, 55-66, 67-74) x sex


class Society:
    def __init__(self, p):
        self.p = p
        self.rng = np.random.default_rng(p["seed"])
        self.base = popmod.load_baseline(p)
        self.A = popmod.build(p, self.rng)
        self.year = 0
        self.omega = np.ones(N_OCC)
        self.price = 1.0
        self.cons_index = 1.0
        self.demand_level = 1.0   # jobs the economy has room for at base wages; demand equals supply in 2025
        # Calibrated so unemployment matches VIN01104 (4.3%); see _calibrate_separations. The burn-in fits the
        # choice model under whatever rate is set here, so it must start near where calibration ends (1.4-1.5%
        # in two calibrations): a first guess of 4% left it choosing work too readily (part-time 28% against 24%),
        # and none at all left employment at 73% against 78% once churn began.
        self.separation_rate = .015
        self.spend_rate = None      # set from the accounts each year; the base year anchors it
        self.macro = macromod.Macro(p)
        self.sectors = sectormod.Sectors(p)
        self.frontier = frontiermod.Frontier(p)
        self.infra = frontiermod.Infrastructure(p)
        self.automation = automationmod.Automation(p)
        self.firms = {k: np.zeros(0, t) for k, t in
                      [("founder", np.int32), ("age", np.int16), ("alive", bool), ("quality", float), ("jobs", float), ("profit", float)]}
        self.asc = np.zeros((N_GROUPS, 5))
        self.asc_occ = np.zeros(N_OCC)
        self.reference = None      # status quo accounts per year, for real-terms balance
        self.own_history = []      # this run's own accounts, used as the reference path in the status quo
        self.alpha = 1.0
        self.mpc_scale = 1.0
        self.prof_weights = [pr["weight"] or 0 for pr in P.PROFESSIONS]
        self.disamenity = np.array(P.trait(0))
        self.min_edu = np.array(P.trait(2))
        self.consumption_loading = np.array(P.by_group(p["labour"]["consumption_loading"]))
        self.export_loading = np.array(P.by_group(p["labour"]["export_loading"]))
        self.low_value_weights = np.array(P.by_group(p["policy"]["low_value_job_weights"]))
        self.foreign_ratio = np.array(P.by_group(p["migration"]["foreign_wage_ratio"]))
        self.omega_new = np.ones(N_OCC)
        self.public_premium = np.ones(N_OCC)   # what the state pays above the going rate where posts go unfilled
        self.workload = np.ones(N_OCC)         # work per person in post where posts are unfilled
        self.service_unmet = np.zeros(N_OCC)   # the share of the work that simply does not happen
        base_len = sum(k * v for k, v in p["labour"]["contract_lengths_private"].items())
        self.offer_years = np.full(N_OCC, base_len)
        self.needs_elasticity = np.array([P.NEEDS_DRIVEN.get(n, (None, None))[1] for n in OCCUPATIONS], dtype=object)
        self.needs_driver = [P.NEEDS_DRIVEN.get(n, (None, None))[0] for n in OCCUPATIONS]
        self.history = []
        N = len(self.A["age"])
        self.net_now = np.zeros(N)
        self.R0 = np.ones(N)
        self.A["worker0"] = np.isin(self.A["status"], [PART, FULL])
        self.A["fund"] = np.zeros(N)  # start-of-life fund principal (ISK, 2025 prices)

    # ------------------------------------------------------------------ helpers
    @property
    def N(self):
        return len(self.A["age"])

    def contract_rate(self, idx=slice(None)):
        """What a contract pays this year: the rate signed, plus the yearly raises written into it.

        Icelandic agreements schedule nominal raises for each year they run, which is how expected inflation is
        built in; only inflation beyond that is made good at renewal. A contract frozen in krónur until renewal
        left real pay several percent lower on average at 2.5% inflation than at none — which pulled prices below
        the trend, lowered interest rates, raised house prices and profits, all from the inflation rate alone."""
        A = self.A
        years = np.maximum(self.year - A["contract_start"][idx], 0)
        return A["contract_omega"][idx] * (1 + self.p["markets"]["trend_inflation"]) ** years

    def wage_of(self, idx, omega_new):
        """What a person is paid: their contract rate while it runs, otherwise today's rate for new contracts."""
        A = self.A
        under = (A["contract_end"][idx] > self.year) & np.isin(A["status"][idx], [PART, FULL])
        market = np.asarray(omega_new)[A["occupation"][idx]]
        # 1.1: experience gained or lost since the base year (careers.py)
        return A["base_wage"][idx] * np.where(under, self.contract_rate(idx), market) * careers.wage_factor(self, idx)

    def hours_of(self, status, who=None):
        """Hours supplied to employers. Independent work supplies none: there is no employer. `who` (the people
        `status` belongs to) adds each one's week within the job (hours.py, 2.0)."""
        b, pol = self.p["behaviour"], self.p["policy"]
        ft = pol["full_time_hours_factor"] if pol["regime"] == "platform" else 1.0
        h = np.select([status == FULL, status == PART], [ft, b["part_time_hours"] * ft], 0.0)
        return h if who is None else h * hours.factor(self, who)

    def activity_hours(self, status):
        """Hours actually worked, including self-directed work and running a firm."""
        b = self.p["behaviour"]
        return self.hours_of(status) + (status == VENTURE) + b["independent_hours"] * (status == INDEP)

    def group(self, idx):
        age = self.A["age"][idx]
        band = np.select([age <= 19, age <= 24, age <= 54, age <= 66], [0, 1, 2, 3], 4)
        return band * 2 + self.A["sex"][idx]

    def update_peers(self):
        """2.0: the share out of work among each person's peers, people of the same age band and sex, as the year
        starts. A run measured on fixed peers (behaviour.freeze_peers) takes its reference run's, so the income
        effect check measures the individual response alone (DESIGN.md M3)."""
        A = self.A
        ch = np.flatnonzero(A["alive"] & A["chooser"])
        g = self.group(ch)
        out = np.bincount(g, weights=(A["status"][ch] == NONWORK).astype(float), minlength=10)
        share = out / np.maximum(np.bincount(g, minlength=10), 1)
        ref = self.reference
        if self.p["behaviour"].get("freeze_peers") and ref and len(ref) >= self.year \
                and "peer_nonwork" in ref[self.year - 1]:
            share = np.asarray(ref[self.year - 1]["peer_nonwork"], float)
        self.peer_nonwork = share

    def norm_term(self, idx):
        """2.0: what the norm to work adds to the value of not working: the norm's strength times how far the
        share of one's peers out of work has moved from the base year's. Zero in the base year, so it changes
        nothing there; it adds to every move, so a change that takes some out of work takes a few more with them.
        The strength is calibrated (calibrate_norm) to the response measured in Norway: a point more claimants among
        one's peers, a fifth of a point more chance of claiming oneself (Markussen and Røed 2015)."""
        k = getattr(self, "norm_strength", 0.0) * self.p["behaviour"].get("norm_scale", 1.0)
        base = getattr(self, "peer_nonwork0", None)
        if not k or base is None:
            return np.zeros(len(idx))
        g = self.group(idx)
        return k * (getattr(self, "peer_nonwork", base)[g] - base[g])

    def calibrate_norm(self, per_mother):
        """2.0: the norm's strength. For a logit, a change dx in the value of not working moves its probability by
        P(1-P) dx, so a strength of m / mean P(1-P) makes a point more peers out of work raise one's own chance by
        m points on average (behaviour.norm_marginal_effect). Taken on the settled base year, with the norm at
        rest."""
        A = self.A
        ch = np.flatnonzero(A["alive"] & A["chooser"])
        self.update_peers()
        self.peer_nonwork0 = self.peer_nonwork.copy()
        self.norm_strength = 0.0
        P0 = self.probabilities(ch, self.omega, self.price, per_mother)[:, 0]
        m = self.p["behaviour"].get("norm_marginal_effect", 0.0)
        self.norm_strength = float(m / max(np.mean(P0 * (1 - P0)), 1e-6))

    def child_transfers(self):
        """Monthly child transfers per mother, plus totals (usable, invested, gross)."""
        A, p = self.A, self.p
        if p["policy"]["regime"] == "status_quo":
            kids = np.flatnonzero((A["mother"] >= 0) & (A["age"] < 18) & A["alive"])
            # barnabætur are set in krónur and adjusted yearly, like the other benefits net_income indexes
            # barnabætur follow the same indexation as the other benefits: set in krónur each year, with regard
            # to wages and never by less than prices. Indexed to prices alone they fall behind the median every
            # year, which is most of why child poverty climbed through the model's status quo.
            # barnabætur at 2026 law, tested on the household's taxable income: a base amount per child (more for a
            # single parent) and a supplement per child under 7, each withdrawn at 4% of income above the threshold
            b, bx = p["benefits"], self.benefit_index()
            n = np.bincount(A["mother"][kids], minlength=self.N).astype(float)
            n7 = np.bincount(A["mother"][kids[A["age"][kids] < 7]], minlength=self.N).astype(float)
            A["kids_home"] = n
            mothers = np.flatnonzero(n > 0)
            partner = A["partner"][mothers]
            couple = partner >= 0
            own = self.current_gross(mothers)
            theirs = np.where(couple, self.current_gross(np.where(couple, partner, mothers)), 0)
            income = (own + theirs) * 12 / bx                                  # a year, in the thresholds' krónur
            per_child = np.where(couple, b["child_benefit_couple_year"], b["child_benefit_single_year"])
            over = np.maximum(0, income - np.where(couple, b["child_benefit_threshold_couple_year"],
                                                   b["child_benefit_threshold_single_year"]))
            base = np.maximum(0, n[mothers] * per_child - b["child_benefit_withdrawal"] * over)
            young = np.maximum(0, n7[mothers] * (b["child_benefit_under7_year"] - b["child_benefit_withdrawal"] * over))
            per_mother = np.zeros(self.N)
            per_mother[mothers] = (base + young) / 12 * bx
            # v9: the child pension (barnalífeyrir), per child under 18 of an old-age or disability pensioner,
            # untaxed; about 11 ma.kr. a year, missing from v8's status quo (Tryggingastofnun)
            if "child_pension" in b:
                pens = A["disabled"] | (A["age"] >= 67)
                dad = np.where(couple, partner, -1)
                either = pens[mothers] | np.where(dad >= 0, pens[np.maximum(dad, 0)], False)
                cp = np.where(either, n[mothers] * b["child_pension"] * bx, 0.0)
                per_mother[mothers] += cp
                self.child_pension_bn = float(cp.sum() * 12 / 1e9)
            return per_mother, 0.0, per_mother.sum()
        return pol_rules.child_usable_ubi(A, p)

    def household_child(self, idx, per_mother):
        A = self.A
        partner = A["partner"][idx]
        own = per_mother[idx]
        via_partner = np.where(partner >= 0, per_mother[np.where(partner >= 0, partner, 0)], 0)
        return np.where(A["sex"][idx] == 1, own, via_partner)

    def current_vat(self):
        return pol_rules.vat_rate(self.p)

    def employer_rate(self):
        return pol_rules.employer_rate(self.p)

    def wage_cost_index(self, omega):
        er, er0 = pol_rules.employer_rate(self.p), self.p["policy"]["pension_contrib_employer"]
        w = self.D0_pub + self.D0_priv
        return float((omega * w).sum() / w.sum()) * (1 + er) / (1 + er0)

    # ------------------------------------------------------------ a fisheries fund (v8, the counterfactual past)
    def fisheries_fund_start(self):
        """This year's dividend from a fund holding part of the fishery's rent (params `fisheries_fund`; built from
        1984 by scripts/fisheries_history.py). Held abroad: kept in foreign currency, so the króna moves its value in
        krónur. Pays `payout` of its value a year, the same to every adult (policy.citizen_dividend, untaxed)."""
        ff = self.p.get("fisheries_fund") or {}
        pol = self.p["policy"]
        if not (ff.get("assets_bn") or ff.get("capture")):
            pol["citizen_dividend"] = 0.0
            self.ff_paid_fc = 0.0
            return
        if not hasattr(self, "ff_fc"):
            self.ff_fc = float(ff.get("assets_bn", 0.0))     # base-year krónur at the base year's exchange rate
        A = self.A
        adults = max(1, int((A["alive"] & (A["age"] >= 18)).sum()))
        self.ff_paid_fc = ff.get("payout", .03) * self.ff_fc
        pol["citizen_dividend"] = self.ff_paid_fc * self.macro.e * 1e9 / adults / 12

    def fisheries_fund_end(self):
        """The fund at the year's end: its return abroad (real, plus foreign inflation), what it paid, and the rent it
        takes — `capture` of the rent, less the fee the state already takes, so the budget is as it would be."""
        ff = self.p.get("fisheries_fund") or {}
        if not hasattr(self, "ff_fc"):
            return
        st = self.sectors.state
        take = max(0.0, ff.get("capture", 0.0) * max(st.get("fish_rent", 0.0), 0.0) - st.get("fish_fee", 0.0))
        self.ff_take = take
        self.ff_fc = self.ff_fc * (1 + ff.get("return", .04) + ff.get("foreign_inflation", .02)) - self.ff_paid_fc \
            + take / max(self.macro.e, .1)

    def working_age(self):
        A = self.A
        return int((A["alive"] & A["chooser"]).sum())

    def demand(self, omega, supply=None):
        """Labour demand (FTE) by occupation. Scales with the working-age population: new residents consume and
        capital adjusts in the long run."""
        p = self.p
        lab = p["labour"]
        cut = p["policy"]["public_payroll_cut"] if p["policy"]["regime"] == "platform" else 0.0
        er, er0 = pol_rules.employer_rate(p), p["policy"]["pension_contrib_employer"]
        mk = self.macro
        # Every run, reform or status quo, is measured against its own base year — never against its own last year,
        # which makes demand follow its own shocks (a dip in employment cuts demand, which deepens the dip). Until v8 a
        # reform was measured against the status quo's last year instead. That rule was not neutral: the status quo
        # re-run through it, with nothing changed, drifted to output -15%, prices -20% and a budget +209 ma.kr. by
        # 2025 in the backcast (found 2026-10-08), and every reform carried that drift as if it were its own effect.
        # The comparison with the status quo is made on the outputs, as it always was; the rules are the same.
        ext = None
        anchor = ext if ext else self.accounts0
        # How many jobs the economy has room for follows the workforce it could draw on and how much each worker
        # produces — not how many people happened to be working last year.
        if ext:
            growth = self.working_age() / max(ext.get("working_age", self.working_age()), 1.0)
            scale = np.asarray(ext["occ_supply"]) / (self.D0_pub + self.D0_priv) * growth
        else:
            scale = self.working_age() / self.pop0
        # An economy absorbs most of the labour offered to it: people hired produce output, earn, and spend, which
        # is demand for other people's work. Tracking the working-age population alone leaves out the part of supply
        # that comes from people choosing to work more, so demand falls behind by that much every year — and the
        # shortfall has to come out somewhere, as deflation, as unemployment, or as inflation.
        if supply is not None and getattr(self, "supply0", None):
            offered = max(float(np.sum(supply)) / self.supply0, .2)
            theta = lab["supply_absorption"]
            scale = np.asarray(scale, float) ** (1 - theta) * offered ** theta
        cost = mk.relative_wage_cost(omega * (1 + er) / (1 + er0)) / mk.productivity()
        competitiveness = mk.e / np.maximum(cost, .3) / anchor["competitiveness"]
        rate = getattr(self, "spend_rate", None)
        cons_rel = rate / anchor["spend_rate"] if rate and "spend_rate" in anchor else 1.0
        # What firms respond to is the unit labour cost — the wage against what a worker produces — not the wage on
        # its own. Pay that rises with productivity costs no jobs, which is how real wages can grow 1%/yr without
        # employment falling, and is what the Icelandic record shows happening.
        # In real terms: what the wage costs the firm against what its output sells for, and against what a worker
        # produces. This is what makes an erosion of purchasing power self-correcting — prices rise, the real wage
        # falls, hiring becomes worth it again — instead of compounding.
        prod_rel = mk.productivity() / max(anchor.get("productivity", 1.0), .1)
        price_rel = self.price_level(omega) / max(anchor.get("price", 1.0), .2)
        wage_rel = omega / self.reference_wage(anchor) / prod_rel / max(price_rel, .2)
        D = scale * (self.D0_pub * (1 - cut) * self.social_need_factor()
                     + self.D0_priv * wage_rel ** (-lab["demand_elasticity"])
                        * cons_rel ** self.consumption_loading
                        * competitiveness ** (self.export_loading * lab["export_cost_elasticity"])) \
            + self.extra_venture_jobs() * self.D0_priv / self.D0_priv.sum()
        D = self.apply_needs_driven(D, wage_rel, scale) * self.automation.demand_factor()
        D = D + self.sectors.job_change_by_occupation() + self.frontier.state["jobs_by_occ"] \
            + self.infra.state["jobs_by_occ"] + self.tourism_jobs()
        D = D * self.culture_demand_factor()
        # Demand for labour cannot be negative. At extreme corners of the lever space the terms above can drive
        # it below zero, and a negative base to a fractional power in the clearing loop gives NaN rather than an
        # error — which then casts to nonsense further down instead of failing loudly.
        return np.maximum(D * (1 - self.low_value_removal()) * self.demand_level, 0.0)

    def culture_demand_factor(self):
        """Cutting state support for the arts: what is left has to come from ticket sales, which follow spending."""
        p = self.p
        cut = p["policy"]["culture_support_cut"] if p["policy"]["regime"] == "platform" else 0.0
        out = np.ones(N_OCC)
        if not cut:
            return out
        c = p["culture"]
        ref = self.reference_prev()
        # per person on both sides: cons_pc is per head of working age, cons_index is the total
        own_pc = self.cons_index / (self.working_age() / self.pop0)
        cons_rel = (own_pc / (ref["cons_pc"] if ref else 1.0)) ** c["ticket_income_elasticity"]
        i = OCCUPATIONS.index("Artists and writers")
        out[i] = (1 - c["state_support_share"] * cut) * cons_rel
        return out

    def low_value_removal(self):
        """Share of FTE demand removed in each occupation when low-value jobs go (the output-gain lever).
        A gain g means the same output with 1/(1+g) of the hours, concentrated where low-value jobs sit."""
        pol = self.p["policy"]
        g = pol["low_value_jobs_productivity_gain"] if pol["regime"] == "platform" else 0.0
        if g <= 0:
            return np.zeros(N_OCC)
        ramp = min(1.0, self.year / max(1, pol["low_value_jobs_ramp_years"]))
        removed = g / (1 + g) * ramp
        w = self.low_value_weights
        base = self.D0_pub + self.D0_priv
        return np.clip(removed * w / ((w * base).sum() / base.sum()), 0, .6)

    def benefit_index(self, price=None):
        """What benefit levels follow. Lög um almannatryggingar (69. gr.): set each year with regard to how wages
        have moved, and never by less than prices. So benefits keep most of their place against wages, and the
        price level is a floor. Indexing them to prices alone made relative poverty rise in the status quo for
        no reason but the arithmetic.

        Levels are set at the start of the year, to the price level expected for it, as the budget sets them — the
        same rule the borgaralaun follows. Indexed to the year's actual prices, today's benefits could never lose
        value to a price surprise while the payment did: through COVID's fall in the króna and the 2022-23
        inflation the status quo was perfectly protected and the reform was not (found 2026-09-26)."""
        set_at = getattr(self, "price_set", None)
        price = set_at if set_at is not None else (self.price if price is None else price)
        share = self.p["benefits"]["wage_indexation"]
        # the burn-in runs before the base year exists; `scenario` refuses a society without it (BASELINES)
        if not share or getattr(self, "real_wage0", None) is None:
            return price
        w = self.D0_pub + self.D0_priv
        wage = float((self.omega * w).sum() / max(w.sum(), 1e-9))
        real = wage / max(price, .1) / max(self.real_wage0, .1)
        return price * max(real, 1.0) ** share

    def leave_scheme(self):
        """Sick pay and parental leave when the borgaralaun is already the floor.

        Nobody falls to nothing any more, so the state's two schemes — sick pay for its own staff and the parental
        leave fund — are no longer what stands between a household and destitution. They end. What is paid above
        the borgaralaun becomes the employer's: the period law and agreements already give (rising with seniority),
        then mandatory private insurance beyond it, as occupational pensions are mandatory now. Job protection is
        unchanged. The state's saving is real; the employers' cost is real too, and is charged on wages, so it
        shows up in what firms hire rather than being quietly dropped.

        What the state stops paying is measured from the model's own births and wages, not from a fixed figure:
        the parental leave fund pays about 80% of pay under a cap for a year per birth.
        """
        pol = self.p["policy"]
        out = {"state_saved_bn": 0.0, "employer_cost_share": 0.0, "top_up": 0.0, "insured": False}
        if pol["regime"] != "platform" or not pol["state_leave_ended"]:
            return out
        share = float(pol["state_leave_ended"])
        top_up = pol["leave_top_up"]
        if not top_up:   # 0 or None: whatever bargaining is assumed to land on
            top_up = pol["leave_top_up_free_market"] if pol["wage_setting"] == "free_market" \
                else pol["leave_top_up_agreements"]
        A = self.A
        working = A["alive"] & np.isin(A["status"], [PART, FULL])
        n_work = max(int(working.sum()), 1)
        pay = float(np.mean(self.current_gross(np.flatnonzero(working)))) if working.any() else 0.0
        births = float(getattr(self, "births_last", 0.0) or self.p["demography"]["births_per_year"])
        # what the state stops paying: the fund's rule, at this year's pay, capped as today
        capped = min(pay, pol["parental_leave_cap_month"] * self.price)
        parental = births * pol["parental_leave_months"] * .8 * capped / 1e9
        # only the sick pay the older lever (`public_sick_pay_cut`) has not already taken off the state: with both
        # on, the same 39 ma.kr. was saved twice
        sick_public = pol["sick_absence_rate"] * getattr(self, "accounts_cache", {}).get("public_payroll", 0.0) \
            * (1 - pol["public_sick_pay_cut"])
        out["state_saved_bn"] = share * (parental + sick_public)
        # what employers take on: the top-up above the borgaralaun, for sick days and for parental months
        ubi_month = pol["ubi_adult"] * self.price if pol["ubi_indexed"] else pol["ubi_adult"]
        above = max(0.0, top_up - ubi_month / max(pay, 1.0))
        leave_share = pol["sick_absence_rate"] + births * pol["parental_leave_months"] / (12.0 * n_work)
        # the employer's own period is paid directly; the rest is insured, with the insurer's margin on it
        direct = pol["employer_leave_period_share"]
        cost = leave_share * above * (direct + (1 - direct) * pol["leave_insurance_loading"])
        out.update({"employer_cost_share": share * cost, "top_up": top_up, "insured": True})
        return out

    def social_need_factor(self):
        """How much of the state's social work there is to do, against the base year.

        Child protection, home visits, benefit and debt counselling, the police, the courts and the prisons are
        staffed against distress, not against the population. So the staffing the state needs follows hardship,
        child poverty and crime — and a reform that lifts people out of poverty needs fewer of these people, while
        one that does not needs more. The evidence that the link is real: Mincome cut hospital use 8.5% (Forget
        2011), the Cherokee casino payments cut minor crime and behavioural disorders among children (Costello
        2003, Akee 2010), and income support reduces child maltreatment reports (Berger 2017, Raissian and
        Bullinger 2017). The shares below say how much of each profession's public work is of this kind; the
        index moves with a year's lag, as a budget does."""
        p = self.p
        w = p["labour"]["social_need_weights"]
        d = getattr(self, "distress", 1.0)
        share = np.array([p["labour"]["social_need_share"].get(n, 0.0) for n in OCCUPATIONS])
        return 1.0 + share * (np.clip(d, .5, 1.5) - 1.0) if w else np.ones(N_OCC)

    def update_distress(self, inc, crime):
        """Last year's hardship, child poverty and crime, against the base year: what social staffing responds to.

        The burn-in steps the model before the base year exists, so there is nothing to measure against yet."""
        if getattr(self, "hardship0", None) is None or getattr(self, "crime0", None) is None:
            return
        w = self.p["labour"]["social_need_weights"]
        parts = {"hardship": inc.get("hardship_rate", self.hardship0) / max(self.hardship0, 1e-6),
                 "child_poverty": inc.get("child_poverty_rate", self.child_poverty0) / max(self.child_poverty0, 1e-6),
                 "crime": crime / max(self.crime0, 1e-6)}
        total = sum(w.values()) or 1.0
        self.distress = float(sum(w.get(k, 0.0) * v for k, v in parts.items()) / total)

    def apply_needs_driven(self, D, wage_rel, scale):
        """Bins still need emptying and children still need teaching: for these professions demand follows the
        population it serves, with only a weak response to pay.

        `wage_rel` is the real, productivity-adjusted wage the rest of demand uses. This used the nominal wage
        index, so demand for care and teaching fell every year with inflation alone."""
        A, lab = self.A, self.p["labour"]
        alive = A["alive"]
        drivers = {"population": alive.sum() / self.pop_total0 if hasattr(self, "pop_total0") else 1.0,
                   "elderly": (alive & (A["age"] >= 67)).sum() / max(self.driver0["elderly"], 1),
                   "children_1_5": (alive & (A["age"] >= 1) & (A["age"] <= 5)).sum() / max(self.driver0["children_1_5"], 1),
                   "children_1_15": (alive & (A["age"] >= 1) & (A["age"] <= 15)).sum() / max(self.driver0["children_1_15"], 1)}
        base = self.D0_pub + self.D0_priv
        out = D.copy()
        for i, driver in enumerate(self.needs_driver):
            if driver is None:
                continue
            eta = float(self.needs_elasticity[i])
            out[i] = base[i] * drivers[driver] * wage_rel[i] ** (-eta) * (1 - self.low_value_removal()[i])
        # 1.1: care given in the family beyond the status quo's takes the place of part of care assistants' work
        # (familycare.py); never below half of the posts
        self.family_care_replaced = familycare.replaced_fte(self)
        if self.family_care_replaced and "Care assistants" in OCCUPATIONS:
            i = OCCUPATIONS.index("Care assistants")
            out[i] = max(out[i] - self.family_care_replaced, .5 * out[i])
        return out

    def reference_prev(self):
        """Last year's reference-path values: the status-quo run's (for reforms) or this run's own history."""
        hist = self.reference if self.reference else self.own_history
        if self.year >= 2 and len(hist) >= self.year - 1 and "occ_supply" in hist[self.year - 2]:
            return hist[self.year - 2]
        return None

    def reference_wage(self, ref):
        """Wages on the reference path: the status-quo run's for a reform, this run's own last year otherwise."""
        if not ref or "omega" not in ref:
            return np.ones(N_OCC)
        return np.maximum(np.asarray(ref["omega"], float), .3)

    def extra_venture_jobs(self):
        """Venture jobs beyond the status-quo path. Normal start-up churn is already part of baseline demand
        (new firms replace jobs lost elsewhere), so only the difference adds or removes net labour demand."""
        jobs = self.firms["jobs"][self.firms["alive"]].sum()
        if self.reference and self.year >= 2 and len(self.reference) >= self.year - 1:
            return jobs - self.reference[self.year - 2].get("venture_jobs", jobs)
        return 0.0

    def price_level(self, omega):
        return self.macro.cpi_for(self.wage_cost_index(omega), self.current_vat(), self.p["policy"]["vat_effective_status_quo"])

    def update_housing_market(self):
        pop = int(self.A["alive"].sum())
        if not hasattr(self, "pop_total0"):
            self.pop_total0 = pop
        pop_index = pop / self.pop_total0
        self.macro.update_housing(pop_index, max(.3, self.cons_index / pop_index))
        housing.update_segments(self)   # v10: the housing ladder, each size against its own stock
        regions.update_market(self)     # 2.0: each area against its own stock

    def housing_costs(self, idx, pooled=True):
        """The subsistence budget. Property tax is not in it: it is a tax, and comes off income (household_levies).
        pooled=False is the person's own unit, as the choice of work weighs it (policy.household_costs)."""
        rent, mortgage, _ = self.macro.housing_costs()
        return pol_rules.household_costs(self.A, idx, self.p, rent, mortgage, pooled=pooled)

    def household_real_income(self, idx, per_mother=None):
        """Monthly household income after tax and transfers, in 2025 krónur: own and partner's net income and the
        child payments the household receives. cmin is a household budget; set against one member's income it
        counted the low-earning partner of a comfortable couple as living in hardship, and a mother's household as
        poor regardless of her partner's pay or the child payments it receives."""
        A = self.A
        if per_mother is None:
            per_mother, _, _ = self.child_transfers()
        if len(per_mother) < self.N:
            per_mother = np.concatenate([per_mother, np.zeros(self.N - len(per_mother))])
        partner = A["partner"][idx]
        pinc = np.where(partner >= 0, self.net_now[np.maximum(partner, 0)], 0.0)
        own = self.net_now[idx] + pinc + self.household_child(idx, per_mother)
        # v9: an older person living with a younger household pools income with it (policy.household_costs pools
        # the scale and the budget the same way)
        if "host" in A:
            host = A["host"]
            guests = np.flatnonzero((host >= 0) & A["alive"])
            gsum = np.bincount(host[guests], weights=self.net_now[guests], minlength=self.N)
            own = own + gsum[idx] + np.where(partner >= 0, gsum[np.maximum(partner, 0)], 0.0)
            g = host[idx] >= 0
            if g.any():
                own[g] = self.household_real_income(host[idx][g], per_mother) * self.price
        return own / self.price

    def pooled_extra(self, idx):
        """Income this person's household has beyond their own unit's, in current krónur: for someone living in
        another's household, that household's income; for the household itself, what those living with it bring."""
        A = self.A
        out = np.zeros(len(idx))
        if "host" not in A:
            return out
        host = A["host"]
        guests = np.flatnonzero((host >= 0) & A["alive"])
        if not len(guests):
            return out
        gsum = np.bincount(host[guests], weights=self.net_now[guests], minlength=self.N)
        partner = A["partner"][idx]
        out += gsum[idx] + np.where(partner >= 0, gsum[np.maximum(partner, 0)], 0.0)
        g = host[idx] >= 0
        if g.any():
            h = host[idx][g]
            hp = A["partner"][h]
            out[g] = self.net_now[h] + np.where(hp >= 0, self.net_now[np.maximum(hp, 0)], 0.0) \
                + gsum[h] - self.net_now[idx][g]
        return out

    def household_levies(self, idx, price=None):
        """Taxes a household pays that the income tax does not reach, per month in current krónur: the change in
        property tax on its home, charged once per household as the accounts charge it, and any tax on net wealth.

        EU-SILC, which Hagstofa's income statistics follow, takes both off disposable income. The model used to
        leave them out of income altogether — the property tax appeared only as a cost in the subsistence budget and
        the wealth tax nowhere — so raising either made the headline "income after tax and transfers" rise: the
        revenue helped, and no one's bill went up."""
        A, pol = self.A, self.p["policy"]
        _, _, owner_tax = self.macro.housing_costs()
        partner = A["partner"][idx]
        payer = ~A["renter"][idx] & ((partner < 0) | (A["sex"][idx] == 1))
        pr = self.price if price is None else price
        # v9: the extra tax falls on each home by its value (larger homes pay more),
        # not as the average dwelling's on every owner; the total is the same
        levy = np.where(payer, owner_tax * pr * self.home_value_weight(idx), 0.0)
        # v9 option: households with someone 67+ defer the extra until the home is sold or inherited
        levy = np.where(self.property_deferred(idx), 0.0, levy)
        if pol["regime"] == "platform":
            levy = levy + self.heating_bill(idx) * pr
        if pol["regime"] == "platform" and pol["net_wealth_tax_pct"]:
            worth = A["wealth"][idx] + np.maximum(A["home_value"][idx] * housing.price_factor(self, idx)
                                                  - A["mortgage_debt"][idx], 0)
            # worth is in 2025 krónur, and the threshold is read as 2025 krónur too; the tax is paid in today's
            levy = levy + pol["net_wealth_tax_pct"] / 100 * np.maximum(worth - pol["net_wealth_tax_threshold"], 0) \
                / 12 * pr * self.wealth_tax_shrink()
        return levy

    def household_home_value(self, idx):
        """The household's home value (a couple holds half each), for those who own."""
        A = self.A
        partner = A["partner"][idx]
        return A["home_value"][idx] + np.where(partner >= 0, A["home_value"][np.maximum(partner, 0)], 0.0)

    def home_value_weight(self, idx):
        """Each owner household's home value against the average owner household's (cached per year)."""
        A = self.A
        if getattr(self, "_hv_year", None) != (self.year, self.N):
            owners = np.flatnonzero(A["alive"] & ~A["renter"] & ((A["partner"] < 0) | (A["sex"] == 1)))
            hv = self.household_home_value(owners)
            self._hv_mean = float(hv[hv > 0].mean()) if (hv > 0).any() else 1.0
            self._hv_year = (self.year, self.N)
        return self.household_home_value(idx) / max(self._hv_mean, 1.0)

    def property_deferred(self, idx):
        """Owner households with someone 67+ whose extra property tax is deferred (policy.defer_pensioner_property_tax)."""
        A, pol = self.A, self.p["policy"]
        if pol["regime"] != "platform" or not pol.get("defer_pensioner_property_tax", 0.0):
            return np.zeros(len(idx), bool)
        partner = A["partner"][idx]
        old = (A["age"][idx] >= 67) | np.where(partner >= 0, A["age"][np.maximum(partner, 0)] >= 67, False)
        return old & ~A["renter"][idx]

    def deferred_property_tax_bn(self):
        """The extra property tax pensioner households defer this year, ma.kr. of today: a claim on the home from v10
        (housing.accrue_claims), repaid on sale or from the estate; before, it came off revenue and was never
        collected."""
        A = self.A
        if not self.p["policy"].get("defer_pensioner_property_tax", 0.0) or self.p["policy"]["regime"] != "platform":
            return 0.0
        idx = np.flatnonzero(A["alive"] & ~A["renter"] & (A["age"] >= 18) & ((A["partner"] < 0) | (A["sex"] == 1)))
        idx = idx[self.property_deferred(idx)]
        _, _, owner_tax = self.macro.housing_costs()
        return float((owner_tax * self.price * self.home_value_weight(idx)).sum() * 12 / 1e9)

    def cold_area(self, idx):
        """Homes without geothermal heat: a fixed quarter of households outside the capital area (EST), picked by a
        hash of the agent so it does not move from year to year."""
        share = self.p["energy_split"]["cold_area_share_outside_capital"]
        return ~self.A["capital"][idx] & ((np.asarray(idx) * 2654435761 % 1000) < share * 1000)

    def green_heat_share(self):
        """Share of cold-area homes converted to local green heat so far: grants each year, installed by owners."""
        es, pol = self.p["energy_split"], self.p["policy"]
        bn = pol.get("green_heat_bn", 0.0) if pol["regime"] == "platform" else 0.0
        if not bn:
            return 0.0
        A = self.A
        alive = np.flatnonzero(A["alive"] & (A["age"] >= 18))
        head = (A["partner"][alive] < 0) | (A["sex"][alive] == 1)
        n = max(int((head & self.cold_area(alive)).sum()), 1)
        per_year = bn * 1e3 / (es["green_heat_cost_per_home_m"] * es["green_heat_grant_share"])
        return float(min(1.0, self.year * per_year / n))

    def heating_bill(self, idx):
        """What cutting the rural heating support adds to a cold-area household's bill, a month in 2025 krónur,
        charged once per household. It falls on the few homes that get the support, not on everyone."""
        cut = P.energy_cuts(self.p)["heating"]
        if not cut:
            return np.zeros(len(idx))
        A = self.A
        head = lambda j: (A["partner"][j] < 0) | (A["sex"][j] == 1)
        alive = np.flatnonzero(A["alive"] & (A["age"] >= 18))
        n = max(int((head(alive) & self.cold_area(alive)).sum()), 1)
        es = self.p["energy_split"]
        per = cut * es["heating_bn"] * 1e9 / 12 / n * (1 - self.green_heat_share() * es["green_heat_saving"])
        return np.where(head(idx) & self.cold_area(idx), per, 0.0)

    # ------------------------------------------------------------------ incomes
    def public_shortage_premium(self, idx):
        """What the state adds to the going rate where it cannot fill its posts.

        A public employer buys a service it has to provide, so it cannot meet a shortage by doing less of it: when
        nurses or teachers are short, it raises pay until the posts fill. Iceland's own record is of exactly this —
        the nurses' and teachers' settlements followed shortages, not the general round. The premium is carried
        from year to year, grows with the share of the state's own posts left unfilled, and falls back when they
        fill. It applies in both worlds, because the state behaves this way today as well; what the reform changes
        is how big the shortages get. The cost lands in the public payroll like any other pay."""
        return np.asarray(self.public_premium)[self.A["occupation"][idx]] \
            if getattr(self, "public_premium", None) is not None else np.ones(len(idx))

    def public_pay_factor(self, idx):
        """The premium, for the state's own employees only: private pay in the same profession is unchanged."""
        return np.where(self.A["public"][idx], self.public_shortage_premium(idx), 1.0)

    def shortage_pull(self):
        """How much more a profession draws newcomers for its posts standing empty (1 when supply meets demand)."""
        tight = np.clip(np.asarray(getattr(self, "tightness", np.ones(N_OCC)), float), .5, 2.0)
        return tight ** self.p["labour"]["occupation_shortage_pull"]

    def occupation_pull(self):
        """The pull of each profession on someone choosing one: its take-home pay against the base year (for state
        employees, the shortage premium and the reform's pay offset included) and its empty posts. 1 everywhere
        when nothing has changed since the base year."""
        A, lab = self.A, self.p["labour"]
        if getattr(self, "omega0", None) is None:
            return np.ones(N_OCC)
        occ, public = A["occupation"], A["public"]
        pub_share = self.D0_pub / np.maximum(self.D0_pub + self.D0_priv, 1e-9)
        premium = getattr(self, "public_premium", None)
        premium = np.ones(N_OCC) if premium is None else np.asarray(premium, float)
        working = np.flatnonzero(A["alive"] & public & np.isin(A["status"], [PART, FULL]))
        cut = np.bincount(occ[working], weights=self.public_wage_offset(working), minlength=N_OCC) \
            / np.maximum(np.bincount(occ[working], minlength=N_OCC), 1)
        omega = np.asarray(self.omega, float)
        pay = omega * (1 - pub_share + pub_share * premium) - pub_share * cut
        rel = np.clip(pay, 1e-9, None) / np.maximum(self.omega0, 1e-9)
        w0 = self.D0_pub + self.D0_priv
        rel = rel / max(float((rel * w0).sum() / max(w0.sum(), 1e-9)), 1e-9)
        return rel ** lab["occupation_pay_pull"] * self.shortage_pull()

    def step_occupation_change(self):
        """People move between professions when pay and empty posts pull them there.

        Until now nobody ever changed profession, so a pay rise could only be answered by the hours of the people
        already in the job — the own-wage supply elasticity, about 0.2 to 0.4 for nurses — and never by someone
        choosing to become one. That is why shortages closed so slowly and why the reform's case for letting
        people find work that suits them could not show up at all.

        Two rules keep this honest. Moves are driven by how a profession's pay has changed **against the base
        year**, not by its level, so in a world where nothing changes the flows are churn that cancels and the
        profession mix stays where Hagstofa's wage survey put it. And nobody enters a profession whose minimum
        education they do not have, so a shortage of doctors is not solved by relabelling shop assistants.

        Those who move are doing what a basic income is argued to make possible — moving to work that fits them
        better — so they carry a small permanent gain in what they produce (`labour.match_quality_gain`, EST).
        The size is a lever and it can be set to zero; the direction has the better evidence than the magnitude.
        """
        A, lab = self.A, self.p["labour"]
        rate = lab["occupation_mobility"]
        if not rate or getattr(self, "omega0", None) is None:
            return
        rng = self.rng
        # Today's churn is already in the trend the model is calibrated to, so it earns nothing extra. What the
        # reform adds is the moves a secure income makes affordable — trying another line of work without
        # risking the rent — and only those carry the gain from a better fit.
        pol = self.p["policy"]
        extra = lab["occupation_mobility_security"] * min(1.5, max(0.0, pol["ubi_adult"] / 300_000)) \
            if pol["regime"] == "platform" else 0.0
        rate = rate * (1 + extra)
        # public money for retraining makes moves easier for everyone (EST: 25 ma.kr. a year doubles the rate). It
        # lived in the older, pay-only mobility rule, which this one replaces.
        if pol["regime"] == "platform" and pol.get("retraining_bn_per_year"):
            rate *= 1 + pol["retraining_bn_per_year"] / 25.0
        alive = A["alive"] & A["chooser"] & (A["age"] <= lab["occupation_move_max_age"])
        # the young and those out of work move more readily than someone settled in a job
        weight = np.where(A["age"] <= 30, lab["occupation_move_young"], 1.0)
        weight = np.where(A["status"] == NONWORK, weight * lab["occupation_move_idle"], weight)
        movers = np.flatnonzero(alive & (rng.random(len(A["age"])) < rate * weight))
        if not len(movers):
            return
        # What a move would pay against the base year, take-home for state employees, and the empty posts
        occ, public = A["occupation"], A["public"]
        pub_share = self.D0_pub / np.maximum(self.D0_pub + self.D0_priv, 1e-9)
        pull = self.occupation_pull()
        need = np.array(P.trait(2), float)            # the education a profession asks for
        for level in (0, 1, 2):
            who = movers[A["education"][movers] == level]
            if not len(who):
                continue
            # Destinations are weighted by where people *of this education* worked in the base year, not by the
            # profession's overall size. Weighting by size alone let every mover drift toward the big professions
            # regardless of who fills them, so the mix walked away from the wage survey even with nothing
            # changing, and the shortages in health and teaching doubled in the status quo (found 2026-09-25).
            # With pay and tightness where they were, a level's flows now return people where they came from.
            allowed = self.occ_mix0[level] * pull * (need <= level)
            total = allowed.sum()
            if total <= 0:
                continue
            dest = rng.choice(N_OCC, len(who), p=allowed / total)
            move = dest != occ[who]
            changed, dest = who[move], dest[move]
            # pay follows the new profession, as it does for those who retrain: a person keeps their standing
            # within a profession, not the old profession's rate
            med = self.occ_median
            A["base_wage"][changed] *= med[dest] / np.maximum(med[occ[changed]], 1e-9)
            occ[changed] = dest
            # a new job is with the state or a private employer as that profession's jobs are split, so a nurse
            # who leaves for retail does not stay on the state's payroll
            public[changed] = rng.random(len(changed)) < pub_share[occ[changed]]
            # work that fits pays off in what a person produces, once and for good — for the moves beyond today's
            gained = changed[rng.random(len(changed)) < extra / (1 + extra)]
            A["base_wage"][gained] *= 1 + lab["match_quality_gain"]

    def update_workload(self, D, S):
        """How much of a profession's work is left over for the people who stay, and how much is simply not done.

        Where demand exceeds the labour offered, the state cannot recruit its way out within the year. Part of the
        shortfall is absorbed by those in post working harder, part of it is service that does not happen. The
        split is `labour.shortage_absorbed`: at .5, half of an unfilled tenth is carried and half is lost."""
        lab = self.p["labour"]
        short = np.clip(np.asarray(D) - np.asarray(S), 0, None) / np.maximum(np.asarray(D), 1e-9)
        self.workload = 1.0 + lab["shortage_absorbed"] * short
        self.service_unmet = (1 - lab["shortage_absorbed"]) * short

    def update_public_premium(self, D, S):
        """Move the premium after a year's clearing: up by the share of the state's posts left unfilled, down when
        they are filled. Both steps are damped, so a single bad year does not set pay for a decade.

        Where collective agreements set pay, the state cannot answer a shortage in the year it appears: pay moves
        at a settlement, and rounds run a few years apart. So the shortfall is carried until the round comes, and
        what it answers is the shortage built up since the last one — which is how Iceland's nurses' and teachers'
        disputes actually went. Where pay is set job by job, it moves at once."""
        lab = self.p["labour"]
        free = self.p["policy"]["wage_setting"] == "free_market"
        years = 1 if free else lab["agreement_round_years"]
        self.premium_pending = np.maximum(getattr(self, "premium_pending", np.zeros(N_OCC)), 0.0)
        pub_share = self.D0_pub / np.maximum(self.D0_pub + self.D0_priv, 1e-9)
        # the state's own posts, and how many of them the shortfall leaves unfilled
        pub_demand = np.maximum(np.asarray(D) * pub_share, 1e-9)
        unfilled = np.clip((np.asarray(D) - np.asarray(S)) * pub_share, 0, None) / pub_demand
        # the shortage the coming settlement will have to answer: what has built up since the last one
        self.premium_pending = self.premium_pending + unfilled
        if years > 1 and (self.year % years) != 0:
            return                      # no round this year: the posts stay unfilled and the work goes undone
        pressure = self.premium_pending / max(years, 1)
        self.premium_pending = np.zeros(N_OCC)
        prem = np.asarray(self.public_premium, float)
        prem = np.where(pressure > 0, prem * (1 + lab["public_shortage_pay_speed"] * years * pressure),
                        1 + (prem - 1) * (1 - lab["public_shortage_pay_decay"]))
        self.public_premium = np.clip(prem, 1.0, lab["public_shortage_pay_cap"])

    def public_wage_offset(self, idx, omega=None):
        """The state leads on costs: a full-time public job pays, after tax and with the UBI, what it paid before.

        v9: the exact cut. Gross pay falls to what, under the reform's own taxes and contribution, leaves take-home
        pay plus the payment equal to today's take-home pay under today's taxes, contribution and personal credit.
        v8 grossed the payment up at one marginal rate, which ignored that the reform itself lowers take-home pay
        and cut 299.7 ma.kr. at 300 þús. against the exact 233.9 (computed person by person under both tax systems). Where the
        payment exceeds today's take-home pay, the cut takes the whole gross (current_gross keeps a floor of 40%). At
        a share below one, that part of it; part-timers lose it in proportion to their hours."""
        pol = self.p["policy"]
        if pol["regime"] != "platform" or not pol["public_wage_offset_ubi"]:
            return np.zeros(len(idx))
        omega = self.omega if omega is None else omega
        wage = self.wage_of(idx, omega)
        grid, cut = self._offset_table()
        c = np.interp(wage, grid, cut)
        return np.where(self.A["public"][idx], pol["public_wage_offset_ubi"] * c, 0.0)

    def _offset_table(self):
        """Gross monthly full-time pay, and the exact cut at each, for this year's taxes and payment (cached)."""
        pol, p = self.p["policy"], self.p
        key = (self.year, round(float(self.price), 6), float(pol["ubi_adult"]), float(pol["platform_income_tax_scale"]),
               float(pol.get("platform_personal_credit", 0.0)), str(pol.get("platform_income_tax_brackets")))
        if getattr(self, "_offset_key", None) == key:
            return self._offset_cache
        tp = pol_rules.threshold_price(pol, self.price)
        grid = np.linspace(0.0, 6e6 * max(self.price, .1), 1200)
        ee0 = pol["pension_contrib_employee"]
        taxable0 = grid * (1 - ee0)
        today = taxable0 - pol_rules.income_tax(taxable0, [[lo * tp, r] for lo, r in pol["income_tax_brackets"]],
                                                pol["personal_credit"] * tp)
        ee1 = pol_rules.employee_rate(p)
        brackets = pol.get("platform_income_tax_brackets") or pol["income_tax_brackets"]
        taxable1 = grid * (1 - ee1)
        platform = taxable1 - pol_rules.income_tax(taxable1, [[lo * tp, r] for lo, r in brackets],
                                                   pol.get("platform_personal_credit", 0.0) * tp,
                                                   pol["platform_income_tax_scale"])
        want = today - pol["ubi_adult"]                       # take-home pay the new gross must leave
        new_gross = np.where(want > platform[0], np.interp(want, platform, grid), 0.0)
        cut = np.clip(grid - new_gross, 0.0, grid)
        self._offset_key, self._offset_cache = key, (grid, cut)
        return grid, cut

    def top_income_response(self, idx, gross, p=None, price=None, eligible=None, exempt=None):
        """Pay above the second tax threshold against the reform's rates (policy.top_income_response)."""
        A = self.A
        zero = np.zeros(len(idx), bool)
        return pol_rules.top_income_response(A, idx, gross, self.p if p is None else p,
                                             self.price if price is None else price,
                                             zero if eligible is None else eligible, zero if exempt is None else exempt)

    def current_gross(self, idx, omega=None):
        A, p = self.A, self.p
        omega = self.omega if omega is None else omega
        st = A["status"][idx]
        wage = np.maximum(self.wage_of(idx, omega) * self.public_pay_factor(idx) - self.public_wage_offset(idx, omega),
                          .4 * A["base_wage"][idx] * self.price)
        gross = wage * self.hours_of(st, idx)
        # what the choice model priced (option_household_income): the same share, scaled by the creative trait
        gross = np.where(st == INDEP, self.p["policy"]["independent_earnings_share"] * wage * A["creative"][idx], gross)
        founder = st == VENTURE
        if founder.any():
            gross = np.where(founder, self.founder_income(idx, wage), gross)
        return gross

    def founder_income(self, idx, wage):
        A, p, f = self.A, self.p, self.firms
        v = p["ventures"]
        draw = v["founder_draw_share"] * wage
        fid = A["venture"][idx]
        has = fid >= 0
        if not len(f["profit"]):
            return draw
        safe = np.where(has, fid, 0)
        prof = np.where(has, f["profit"][safe], 0)
        age = np.where(has, f["age"][safe], 0)
        quality = np.where(has, f["quality"][safe], 1.0)
        stake = self.venture_stake(v["external_share_typical"])
        share = (1 - stake) * v["dividend_payout"] * np.maximum(prof, 0) / 12 * self.price   # profits: 2025 krónur
        salary = np.where(age >= 2, wage * np.clip(.6 + .4 * quality, .5, 1.6), draw)
        return salary + share

    def deemed_fund(self):
        """The start-of-life fund the state is deemed to have paid into every firm (kr., 2025): what a whole
        childhood's invested payment comes to, from the payment as set."""
        pol = self.p["policy"]
        child = getattr(self, "ubi_real", (pol["ubi_adult"], pol["ubi_child"]))[1]
        share = float(pol_rules.invested_share(pol)[1])
        return float(child * 12 * 18 * share)

    def venture_stake(self, external, at_exit=False):
        """The state's share of a firm. Today's rule: its full stake when the founder lived on the borgaralaun alone,
        falling in proportion to outside funding. Never less than one deemed start-of-life fund
        against what the firm raised — one fund for each round by the time it is sold. None
        outside the reform."""
        p = self.p
        if p["policy"]["regime"] != "platform":
            return 0.0
        v = p["ventures"]
        rule = p["policy"]["state_venture_stake"] * (1 - external)
        fund = self.deemed_fund()
        if at_exit:
            deemed = fund * v.get("rounds_to_exit", 3)
            floor = deemed / max(deemed + v.get("capital_at_exit", 400e6), 1.0)
        else:
            capital = v["capital_reference"] / max(1 - external, .05)
            floor = fund / max(fund + capital, 1.0)
        floor = max(floor, v["stake_floor"]) if fund > 0 else v["stake_floor"]
        return float(min(max(floor, rule), .95)) * p["policy"]["venture_support"]

    def refresh_net_now(self):
        A = self.A
        idx = np.flatnonzero(A["alive"] & (A["age"] >= 16))
        gross = self.current_gross(idx)
        # 1.1: pay above the second threshold answers the reform's rates; what is no longer reported as pay is
        # not paid payroll tax or contributions either, so the accounts take the gross that is left
        st = A["status"][idx]
        gross, top_extra, shifted_tax, top_lost = self.top_income_response(
            idx, gross, eligible=A["self_employed"][idx] | (st == VENTURE),
            exempt=A["public"][idx] & np.isin(st, [PART, FULL]))
        working = np.isin(A["status"][idx], [PART, FULL, VENTURE, INDEP])
        partner = A["partner"][idx]
        pinc = np.where(partner >= 0, self.net_now[np.where(partner >= 0, partner, 0)], 0)
        inc = pol_rules.net_income(A, idx, gross, working, self.p, pinc, self.price, self.benefit_index())
        inc["net"] = inc["net"] + top_extra
        inc["shifted_tax"], inc["top_income_lost"] = shifted_tax, top_lost
        inc["levies"] = self.household_levies(idx)
        inc["gambling"] = self.gambling_change(idx, inc["ubi"])
        inc["free_services"] = self.free_service_benefit(idx)
        inc["net"] = inc["net"] - inc["levies"] - inc["gambling"] + inc["free_services"]
        # 2.0: earnings a reform brings onto the books pay tax, and those it drives off do not (informal.py)
        inc["informal_tax"], inc["hidden"], inc["hidden_sq"] = informal.tax_change(self, idx, gross, working, pinc)
        inc["net"] = inc["net"] - inc["informal_tax"]
        self.net_now = np.zeros(self.N)
        self.net_now[idx] = inc["net"]
        return idx, gross, inc

    def wealth_tax_shrink(self):
        """Taxable wealth against the tax: moved, hidden, revalued. The elasticity is on the net-of-tax return, so
        a 1% tax on wealth earning 3% takes a third of the return. An exit tax and more investigators narrow it."""
        pol, lk, e = self.p["policy"], self.p["links"], self.p["enforcement"]
        rate = pol["net_wealth_tax_pct"] / 100
        if not rate:
            return 1.0
        closed = .3 * min(pol["exit_tax_rate"] / .3, 1) + .3 * min(pol["tax_enforcement_fte"] / 300, 1)
        eps = lk["wealth_tax_elasticity"] * lk["avoidance_scale"] * (1 - closed)
        return float(max(1 - rate / lk["wealth_return"], .05) ** eps)

    def free_service_benefit(self, idx):
        """Monthly value to each person of free health care and free internet: what they no longer pay. Health
        costs fall on the sick and the old; the connection is paid once per household."""
        pol, fs, A = self.p["policy"], self.p["free_services"], self.A
        out = np.zeros(len(idx))
        if pol["regime"] != "platform" or not (pol["free_health_care"] or pol["free_internet"]):
            return out
        adult = A["age"][idx] >= 18
        if pol["free_health_care"]:
            w = np.where(adult, .5 + (1 - A["health"][idx]) + np.maximum(A["age"][idx] - 50, 0) / 40, 0)
            out += pol["free_health_care"] * fs["health_service_copay_bn"] * 1e9 / 12 * w / max(w.sum(), 1)
        if pol["free_internet"]:
            partner = A["partner"][idx]
            payer = adult & ((partner < 0) | (A["sex"][idx] == 1))
            out += np.where(payer, pol["free_internet"] * fs["internet_household_bn"] * fs["internet_free_share_of_bill"]
                            * 1e9 / 12
                            / max(int(payer.sum()), 1), 0)
        return out * self.price

    def at_risk_gamblers(self, idx):
        """A fixed ~2% of adults, the same people every year: drawn from their index, not the model's random stream,
        so adding them changes no other draw."""
        share = self.p["gambling"]["at_risk_share"]
        return ((np.asarray(idx) * 2654435761) % 10007) / 10007 < share

    def gambling_change(self, idx, ubi):
        """What at-risk gamblers lose, a month, against the status quo (today's losses are already in the base).

        A borgaralaun adds liquidity, and some of it goes the way of the rest; more where a lender will lend
        against it. Blocking payments to foreign sites cuts what flows abroad — part of it moves to licensed
        Icelandic games, where it is still lost but stays in the country. Also sets the change in money sent abroad
        to foreign sites (ma.kr. a year, today's krónur), which is an import."""
        g, pol = self.p["gambling"], self.p["policy"]
        out = np.zeros(len(idx))
        self.gambling_abroad_bn = 0.0
        if pol["regime"] != "platform":
            return out
        risk = self.at_risk_gamblers(idx) & (self.A["age"][idx] >= 18)
        n = max(int(risk.sum()), 1)
        extra = g["ubi_extra_loss"] * ubi * (1 + g["pledge_leverage"] * (1 - pol["ubi_protected"]))
        stopped = pol["gambling_payment_block"] * g["block_effect"]
        foreign_now = g["foreign_losses_bn"] * 1e9 / 12 / n * self.price   # per at-risk gambler, today's krónur
        # the block stops part of today's foreign losses and of the new ones; what moves home is still lost
        saved = stopped * (1 - g["displacement"]) * (foreign_now + extra)
        out = np.where(risk, extra - saved, 0.0)
        abroad = -stopped * foreign_now + (1 - stopped) * extra   # new money abroad less what the block stops
        self.gambling_abroad_bn = float(np.where(risk, abroad, 0.0).sum() * 12 / 1e9)
        return out

    def option_household_income(self, idx, omega, per_mother, wage_boost=1.0, price=None):
        """Household monthly disposable income for each option: nonwork, part, full, venture.

        `wage_boost` raises what the person would actually be paid, contract or not. It has to be applied here and
        not to the market index: most people's pay is fixed by their contract, so a boost to the market rate leaves
        their income untouched — which silently flattened the labour-supply elasticity the model is calibrated on.
        """
        A, p = self.A, self.p
        # The price level these options are judged at. Inside the wage solver that is this year's, as the solver
        # estimates it; taxes were indexed to last year's instead, so everyone weighing a job saw a year of fiscal
        # drag that does not exist.
        pr = self.price if price is None else price
        pt = p["behaviour"]["part_time_hours"]
        wage = np.maximum(self.wage_of(idx, omega) * wage_boost * self.public_pay_factor(idx)
                          - self.public_wage_offset(idx, omega),
                          .4 * A["base_wage"][idx] * wage_boost * pr)
        partner = A["partner"][idx]
        pinc = np.where(partner >= 0, self.net_now[np.where(partner >= 0, partner, 0)], 0)
        child = self.household_child(idx, per_mother)
        # v9: the choice is weighed on the person's own unit (probabilities uses housing_costs(pooled=False)); a young
        # adult living with their parents has what the parents give, as v8 had for those under 20
        hosted = A["host"][idx] >= 0 if "host" in A else np.zeros(len(idx), bool)
        young_home = (partner < 0) & ((A["age"][idx] < 20) | (hosted & (A["age"][idx] < 30)))
        child = child + np.where(young_home, p["costs"]["parental_support"] * pr, 0)
        # drawdown of liquid savings (own + partner's) can help finance any option, including not working.
        # Wealth is held in 2025 krónur (update_wealth deflates savings), and H is in today's.
        wealth = np.maximum(A["wealth"][idx], 0) + np.where(partner >= 0, np.maximum(A["wealth"][np.where(partner >= 0, partner, 0)], 0), 0)
        child = child + wealth * p["wealth"]["annuity_rate"] / 12 * pr
        # Six columns: the five options, plus a sixth for self-directed work in a year when the work does not sell.
        # Creative earnings are a lottery, not a salary, and that is the whole point — it is the risk, not the
        # average, that keeps people with a vocation in a regular job today, and a floor under the bad year is
        # exactly what a basic income provides.
        H = np.empty((len(idx), 6))
        levy = self.household_levies(idx, pr)   # the same whichever option is chosen
        has_firm = A["venture"][idx] >= 0
        venture_gross = np.where(has_firm, self.founder_income(idx, wage), p["ventures"]["founder_draw_share"] * wage)
        sells = p["behaviour"]["independent_sale_probability"]
        # the same expected earnings, concentrated into the years the work does sell
        indep_gross = p["policy"]["independent_earnings_share"] * wage * A["creative"][idx] / max(sells, .05)
        # Part of what a job pays today is a pension. Where the funds are not folded into the UBI, the job still
        # carries it, at what people think a future pension is worth.
        polp = p["policy"]
        fold = polp.get("pension_fold", 1.0) if polp["regime"] == "platform" else 0.0
        accrual = p["links"]["pension_accrual_value"] * (1 - fold) \
            * (polp["pension_contrib_employee"] + polp["pension_contrib_employer"])
        for j, (gross, working) in enumerate([(0 * wage, False), (wage * pt, True), (wage, True),
                                              (venture_gross, True), (indep_gross, True),
                                              (p["behaviour"]["independent_floor_share"] * indep_gross, True)]):
            # 1.1: the pay above the second threshold as it would be reported, the same as refresh_net_now books it
            extra = 0.0
            if j in (1, 2, 3):
                gross, extra, _, _ = self.top_income_response(
                    idx, gross, p, pr, eligible=A["self_employed"][idx] | (j == 3),
                    exempt=A["public"][idx] & (j in (1, 2)))
            inc = pol_rules.net_income(A, idx, gross, np.full(len(idx), working), p, pinc, pr,
                                       self.benefit_index(pr))
            # v9: capital income is left out of the choice. Every option already carries a draw on savings
            # (wealth x annuity_rate, above), which is how wealth finances not working; its return on top counted
            # the same savings twice, and the response to unearned income fell below the lottery evidence.
            cap = inc.get("capital_income", 0.0) - inc.get("capital_tax", 0.0)
            H[:, j] = inc["net"] + extra - cap - levy + pinc + child + (accrual * gross if j in (1, 2) else 0.0)
        return H

    # ------------------------------------------------------------------ choice model
    def idea_prob(self, idx):
        """Probability that a re-thinking agent has a venture idea worth considering this year."""
        A, p = self.A, self.p
        age = A["age"][idx]
        can = (age >= 20) & (age <= 64) & ~A["disabled"][idx] & (A["venture"][idx] < 0)
        v = p["ventures"]
        # Time spent learning is where ideas come from. A degree raises both the chance of having one worth acting
        # on and what it turns into — the link that makes a longer education pay off for the country, not only for
        # the person holding it.
        schooled = 1 + v["education_idea_bonus"] * (A["education"][idx] == 2)
        q = v["idea_rate"] * p["behaviour"]["entrepreneurial_spirit"] * A["enterprise"][idx] * schooled
        # Premises. Nearly everyone with an idea worth acting on acts on it, so what rent does is decide how many
        # ideas are worth acting on: cheaper space, and a high street owned by many rather than a few, make more
        # small ventures viable. Applied to the idea rate, where it bites; in the choice alone it changed nothing.
        po = p["property_ownership"]
        com = getattr(self.macro, "commercial_rent", 1.0) / (1 + po["commercial_markup"])
        q = q * max(.5, 1 - po["commercial_rent_share_of_costs"] * (com - 1) * 4) \
            * (1 + po["variety_venture_boost"] * getattr(self.macro, "variety", 0.0))
        if p["policy"]["regime"] == "platform":   # fewer firms started without the innovation support
            q = q * (1 - p["links"]["innovation_ideas_at_full_cut"] * p["policy"]["subsidy_cut_innovation"])
        # existing founders always have the option of carrying on with their firm
        return np.where(A["venture"][idx] >= 0, 1.0, np.where(can, np.clip(q, 0, .6), 0.0))

    def probabilities(self, idx, omega, price, per_mother, wage_boost=1.0, idea=None):
        """Choice probabilities over (nonwork, part, full, venture). idea=None returns the expectation over
        idea arrival; a boolean array conditions on who has an idea."""
        A, p = self.A, self.p
        b, v = p["behaviour"], p["ventures"]
        H = self.option_household_income(idx, omega, per_mother, wage_boost, price=price)
        cmin, equiv = self.housing_costs(idx, pooled=False)
        s = p["costs"]["subsistence_share"]
        # Below a small margin over the essentials (EPS of what they cost at the base year's rents) utility keeps
        # falling with each króna short: a whole budget of essentials short costs one step of the logarithm. Until
        # 1.1 it was clipped there: where neither working nor not working covered the essentials, both sat on the
        # same floor, income stopped counting and the constants alone decided. Low-paid young renters fall there,
        # and as their share and rents rose through the status quo their chance of choosing not to work tripled.
        # The floor was also taken at this year's rents, so dearer rents raised it.
        cmin0, _ = pol_rules.household_costs(A, idx, p, 1.0, 1.0, pooled=False, base_rents=True)
        f = (EPS * cmin0)[:, None]
        y = H / price - s * cmin[:, None]
        short = np.clip((y - f) / (s * cmin0[:, None]), -20, 0)
        x = np.where(y >= f, y, f * np.exp(short)) / equiv[:, None]
        U = self.alpha * np.log(x / 1e5)
        # Self-directed work is judged on the expected utility across a year that sells and one that does not, not
        # on the average income of the two. Because utility is logarithmic, a bad year hurts far more than a good
        # year helps, which is why people with a vocation take a salary instead — and why a floor under the bad
        # year changes the decision. This is the mechanism a basic income acts on.
        sells = b["independent_sale_probability"]
        U[:, 4] = sells * U[:, 4] + (1 - sells) * U[:, 5]
        U = U[:, :5]
        hours = np.array([0, b["part_time_hours"], 1.0, 1.0, b["independent_hours"]])
        # Posts the state cannot fill do not simply disappear: part of the work is not done, and the rest falls on
        # the people who stay (pay rises, the service shrinks, and workload rises, all three).
        # A profession carrying unfilled posts is worse to work in, so more of its staff go part time or leave,
        # which widens the gap again. EST: at a tenth of posts unfilled the job is as unpleasant as one step of
        # the disamenity scale, anchored on nurse burnout and intention-to-leave studies.
        load = np.asarray(getattr(self, "workload", np.ones(N_OCC)))[A["occupation"][idx]] - 1.0
        dis = self.disamenity[A["occupation"][idx]] * (1 + 1.5 * A["disabled"][idx]) \
            + p["labour"]["workload_disamenity"] * np.clip(load, 0, 1.0)
        nonpec = b["gamma_meaning"] * A["meaning"][idx] - b["gamma_disamenity"] * dis
        venture_meaning = b["gamma_meaning"] * np.minimum(A["enterprise"][idx], 3.0) / 2
        U[:, :3] += hours[None, :3] * nonpec[:, None]
        U[:, 3] += venture_meaning
        # Self-directed work: no employer, uncertain money from selling the work, and the work itself is part of
        # the reward. The pull is kept to the creative trait; loading the full meaning term here as well made the
        # option so attractive that its calibration constant pinned at -12 and took the elasticity down with it.
        U[:, 4] += b["gamma_creative"] * A["creative"][idx] * b["independent_hours"]
        # Time given to work costs leisure — but self-directed work is chosen for its own sake, so its hours are
        # not given up in the same way a shift is. Without this a UBI pushes people who would paint, write or study
        # into "not working" rather than into doing it.
        time_cost = np.array([1., 1., 1., 1., b["independent_leisure_cost"]])
        U -= A["leisure"][idx][:, None] * hours[None, :] ** 1.5 * time_cost[None, :]
        U += self.asc[self.group(idx)]
        U[:, 1:3] += self.asc_occ[A["occupation"][idx]][:, None]
        # 2.0: the norm to work. Not working weighs less the more of one's peers are out of work too (social_norms)
        U[:, 0] += self.norm_term(idx)
        # security is worth something: people trade pay for a contract that lasts
        remaining = np.maximum(A["contract_end"][idx] - self.year, 0)
        secure = np.where(remaining > 0, remaining, self.offer_years[A["occupation"][idx]])
        U[:, 1:3] += (p["labour"]["stability_value"] * np.minimum(secure, 5) / 5)[:, None]
        U[:, 1:4] += b["work_ethic"]
        # a course to keep up with makes full-time work and running a firm much harder to hold
        studying = A["studying"][idx] > 0
        U[:, 2] -= b["study_full_time_cost"] * studying
        U[:, 3] -= b["study_full_time_cost"] * studying
        # and any work at all competes with the course: a constant fitted so that the share of students without a
        # paid job is EUROSTUDENT's (calibrate: fit_asc, _settle_student_work). Without it the choice model put 95%
        # of students in work, against 76% in the survey.
        U[:, 1:5] -= getattr(self, "student_work_cost", 0.0) * studying[:, None]
        # v9: a disability pension is for reduced capacity to work: part-time or self-directed work, not a full-time
        # job or a firm. v8 let calibration move disabled people into full-time work (52% working at 723k a month),
        # and the earnings test then took most of their pension (found in an external review of v8, 2026-10).
        U[:, 2:4] -= 50.0 * A["disabled"][idx][:, None]
        # and part-time or self-directed work costs them more than others, by as much as makes about a fifth of
        # recipients work (calibrated in calibrate.fit_asc to disability_working_share)
        U[:, [1, 4]] -= getattr(self, "disabled_work_cost", 0.0) * A["disabled"][idx][:, None]
        access = v["capital_access_status_quo"]
        if p["policy"]["regime"] == "platform":
            access += (v["capital_access_platform"] - access) * p["policy"]["venture_support"]
        # money of your own to start with, from the start-of-life fund
        seed = A["seed_capital"][idx] / max(v["capital_reference"], 1.0)
        access = access * (1 + v["seed_capital_effect"] * np.clip(seed, 0, 3))
        # rent on premises is a fixed cost that decides whether a small business in Reykjavík is viable at all
        po = p["property_ownership"]
        com = getattr(self.macro, "commercial_rent", 1.0) / (1 + po["commercial_markup"])
        access = access * (1 - po["commercial_rent_share_of_costs"] * (com - 1) * 4)
        U[:, 3] += np.log(access)
        q = self.idea_prob(idx)
        U -= U.max(1, keepdims=True)
        E = np.exp(U)
        P_with = E / E.sum(1, keepdims=True)
        E[:, 3] = 0
        P_without = E / E.sum(1, keepdims=True)
        if idea is None:
            return q[:, None] * P_with + (1 - q[:, None]) * P_without
        return np.where((idea & (q > 0))[:, None], P_with, P_without)

    def choosers(self):
        A = self.A
        return np.flatnonzero(A["alive"] & A["chooser"])

    def calibrate(self, verbose=True):
        """Status quo calibration: ASCs reproduce 2025 activity shares, alpha matches the target elasticity."""
        A, p = self.A, self.p
        assert p["policy"]["regime"] == "status_quo"
        self._seed_firm_stock()
        # 1.1: the schooling the young leave upper-secondary school with, as the population has it (leave_school)
        y = A["alive"] & (A["age"] >= 20) & (A["age"] <= 24) & ~A["immigrant"]
        self.compulsory_only_20_24 = float((A["education"][y] == 0).mean()) if y.any() else 0.0
        idx = self.choosers()
        st = A["status"][idx]
        g = self.group(idx)
        hours = self.hours_of(A["status"])
        self.D0_pub = np.bincount(A["occupation"], weights=hours * A["public"], minlength=N_OCC)
        self.D0_priv = np.bincount(A["occupation"], weights=hours * ~A["public"], minlength=N_OCC)
        self.pop0 = self.working_age()
        A2, alive = self.A, self.A["alive"]
        self.pop_total0 = int(alive.sum())
        # provisional: schooling is costed during burn-in; the final baseline is taken once calibration ends
        self.children0 = int((alive & (A2["age"] < 18)).sum())
        self.driver0 = {"elderly": int((alive & (A2["age"] >= 67)).sum()),
                        "children_1_5": int((alive & (A2["age"] >= 1) & (A2["age"] <= 5)).sum()),
                        "children_1_15": int((alive & (A2["age"] >= 1) & (A2["age"] <= 15)).sum())}
        self.occ_median = np.array([np.median(A["base_wage"][A["occupation"] == o]) for o in range(N_OCC)])
        for _ in range(3):
            self.refresh_net_now()
        per_mother, _, _ = self.child_transfers()
        v = p["ventures"]
        target_founders = v["baseline_founders_per_year"] / p["behaviour"]["reoptimise_rate"]
        occ = A["occupation"][idx]
        pt = p["behaviour"]["part_time_hours"]
        fte_obs = np.bincount(occ, weights=self.hours_of(st), minlength=N_OCC)
        indep_target = p["behaviour"]["baseline_independent_share"]
        target = np.zeros((N_GROUPS, 5))
        for gi in range(N_GROUPS):
            m = g == gi
            if m.any():
                target[gi, :3] = np.array([np.mean(st[m] == NONWORK), np.mean(st[m] == PART),
                                           np.mean(np.isin(st[m], [FULL, VENTURE]))]) * (1 - indep_target)
        target[:, 4] = indep_target
        target = np.clip(target, 1e-4, None)

        def fit_asc():
            for it in range(60):
                P = self.probabilities(idx, self.omega, 1.0, per_mother)
                sim = np.zeros((N_GROUPS, 5))
                for gi in range(N_GROUPS):
                    m = g == gi
                    if m.any():
                        sim[gi] = P[m].mean(0)
                # the target's third column is "full-time or running a firm", because that is how the labour force
                # survey counts the self-employed. Fitting it against full-time alone leaves founders to be added on
                # top, which puts the employment rate several points above the published one.
                work = np.stack([sim[:, 0], sim[:, 1], sim[:, 2] + sim[:, 3]], axis=1)
                work_sim = np.clip(work / work.sum(1, keepdims=True), 1e-9, None)
                step = np.log(np.clip(target[:, :3], 1e-9, None) / work_sim)
                step -= step[:, :1]  # nonwork is the reference
                self.asc[:, 1:3] += .8 * step[:, 1:3]
                no_firm = A["venture"][idx] < 0  # new founding only; existing founders' carry-on choices excluded
                self.asc[:, 3] += .8 * np.log(target_founders / max(P[no_firm, 3].sum(), 1e-9))
                self.asc[:, 4] += .8 * np.log(indep_target / max(P[:, 4].mean(), 1e-9))
                dis = A["disabled"][idx]
                if dis.any():   # v9: about a fifth of disability recipients work (params disability_working_share)
                    t = p["benefits"].get("disability_working_share", .2)
                    s_ = float(np.clip(P[dis][:, 1:5].sum(1).mean(), 1e-4, 1 - 1e-4))
                    self.disabled_work_cost = getattr(self, "disabled_work_cost", 0.0) \
                        + .8 * (np.log(s_ / (1 - s_)) - np.log(t / (1 - t)))
                stu = A["studying"][idx] > 0
                if stu.any():   # 1.1: students without a paid job as EUROSTUDENT has them (student_nonwork_share)
                    t = 1 - p["behaviour"]["student_nonwork_share"]
                    s_ = float(np.clip(P[stu][:, 1:5].sum(1).mean(), 1e-4, 1 - 1e-4))
                    self.student_work_cost = getattr(self, "student_work_cost", 0.0) \
                        + .8 * (np.log(s_ / (1 - s_)) - np.log(t / (1 - t)))
                fte_sim = np.bincount(occ, weights=P[:, 1] * pt + P[:, 2], minlength=N_OCC)
                occ_step = np.log(fte_obs / np.maximum(fte_sim, 1e-9))
                self.asc_occ += .8 * occ_step
                if max(np.abs(step[:, 1:]).max(), np.abs(occ_step).max()) < 2e-3:
                    break
            return P

        def elasticity(alpha):
            self.alpha = alpha
            P = fit_asc()
            w0 = P[:, 1:4].sum()
            P1 = self.probabilities(idx, self.omega, 1.0, per_mother, wage_boost=1.10)
            return (P1[:, 1:4].sum() / w0 - 1) / .10

        lo, hi = .02, 40.0   # wide: a search that stops at its bound silently misses the target elasticity
        target_e = p["behaviour"]["target_extensive_elasticity"]
        for _ in range(14):
            mid = (lo * hi) ** .5
            e = elasticity(mid)
            lo, hi = (mid, hi) if e < target_e else (lo, mid)
        self.alpha = (lo * hi) ** .5
        fit_asc()
        e = elasticity(self.alpha)
        self._targets = (target, fte_obs, len(idx))
        # emigration base hazards and baseline income ratios
        self._calibrate_migration()
        self._calibrate_demography()
        self.accounts0 = self.accounts()
        income_part, wealth_part, income_sum = self._cons_parts
        target = p["wealth"]["target_consumption_ratio"] * income_sum
        self.mpc_scale = float(np.clip((target - wealth_part) / max(income_part, 1), .5, 1.5))
        self.accounts0 = self.accounts()
        self.dynamic_recalibration(verbose=verbose)
        self._calibrate_separations(verbose=verbose)
        self._reseed_firms_to_steady_state()
        self._settle_initial_statuses()
        self._calibrate_employment_level(verbose=verbose)
        self._net_capital_income_of_dividends()
        self.enforce_disability_limits()
        self._settle_disabled_work()
        self._settle_student_work()
        self.calibrate_norm(self.child_transfers()[0])
        self.accounts0 = self.accounts()
        self.median0 = float(self.welfare_snapshot()["real_income_median"])
        self.welfare_snapshot()          # recompute with median0 set
        self.wellbeing0 = self._wellbeing_raw
        self.children0 = int((self.A["alive"] & (self.A["age"] < 18)).sum())
        self.per_child0, self.hh_income0 = self._fertility_reference()
        # Migration once more, on the population scenarios actually start from: solved on the pre-burn-in one, the
        # first year overshot Hagstofa's emigration by a quarter, and its income references were a burn-in stale.
        self._calibrate_migration()
        self._seed_childhood_poverty()
        w0 = self.D0_pub + self.D0_priv
        self.real_wage0 = float((self.omega * w0).sum() / max(w0.sum(), 1e-9)) / max(self.price, .1)
        self.guaranteed_share0 = float(getattr(self, "guaranteed_share_now", 0.0))
        self.omega0 = np.array(self.omega, float)     # what each profession paid before anything moved
        self.birth_penalty0 = float(getattr(self, "_birth_pen_seen", self.p["demography"]["birth_career_penalty"]))
        # where people of each education worked, so profession moves leave the mix alone when nothing changes
        who = self.A["alive"] & self.A["chooser"]
        self.occ_mix0 = np.stack([np.bincount(self.A["occupation"][who & (self.A["education"] == e)],
                                              minlength=N_OCC).astype(float) for e in (0, 1, 2)])
        self.crime0 = float(self.crime_snapshot()["crime_pressure"]) or 1e-6
        # what the state's social services are staffed against today: hardship, child poverty and crime
        # Measured on a simulated year, not on the settled starting state: the two are not the same footing, and
        # a baseline taken here read 2.2% hardship where the first simulated year reads 3.6%, which alone put the
        # distress index 30% above 1 before anything had happened.
        careers.ensure(self)                 # 1.1: experience, and the base year's rates of gaining it
        probe = copy.deepcopy(self)
        probe.history, probe.own_history, probe.year = [], [], 0
        probe.hardship0 = probe.child_poverty0 = 1.0      # the probe itself needs no index
        inc0 = probe.step()
        # 1.1: the rates of gaining experience as the status quo's first five years have them (careers.rates); measured
        # on the first alone, the young fell 8-11% of a year a year behind them in the years after
        probe.p["careers"]["return_per_year"] = 0.0
        measured = [careers.rates(probe)]
        for _ in range(4):
            probe.step()
            measured.append(careers.rates(probe))
        self.exp_rate0 = np.mean(measured, 0)
        self.hardship0 = float(inc0["hardship_rate"]) or 1e-6
        self.child_poverty0 = float(inc0["child_poverty_rate"]) or 1e-6
        self.distress = 1.0
        self.health0 = float(np.mean((1 - self.A["health"][self.A["alive"]])
                                     ** self.p["health"]["cost_elasticity"]))
        if verbose:
            print(f"calibrated alpha={self.alpha:.3f}, extensive elasticity={e:.3f}, "
                  f"founder firms {int(self.firms['alive'].sum()):,}")
        return self

    def dynamic_recalibration(self, rounds=14, years=12, verbose=True):
        """Adjust constants so activity shares stay at their 2025 levels over time in the status quo, given
        inertia (only some agents re-think each year) and ageing. Migration is switched off during burn-in."""
        target, fte_obs, n0 = self._targets
        p = self.p
        for r in range(rounds):
            sim = copy.deepcopy(self)
            sim.step_immigration = lambda: ({"eea_workers": 0, "eea_nonworkers": 0, "non_eea": 0,
                                              "returning_icelanders": 0, "families": 0}, 0)
            sim.step_emigration = lambda: {"total": 0, "icelandic": 0, "foreign": 0, "young_graduates": 0,
                                           "children": 0}
            shares, ftes, founders, indep, unemp = [], [], [], [], []
            for _ in range(years):
                h = sim.step()
                A = sim.A
                idx = np.flatnonzero(A["alive"] & A["chooser"])
                st, g = A["status"][idx], sim.group(idx)
                sh = np.zeros((N_GROUPS, 3))
                for gi in range(N_GROUPS):  # founders count as full-time workers
                    m = (g == gi) & (st != INDEP)
                    if m.any():
                        sh[gi] = [np.mean(st[m] == NONWORK), np.mean(st[m] == PART), np.mean(np.isin(st[m], [FULL, VENTURE]))]
                shares.append(sh)
                indep.append(float(np.mean(st == INDEP)))
                unemp.append(float(h["unemployment_rate"]))
                w = sim.hours_of(st)
                ftes.append(np.bincount(A["occupation"][idx], weights=w, minlength=N_OCC) * n0 / len(idx))
                founders.append(h["new_ventures"])
            late = slice(years // 2, None)  # measure once the founder stock has built up
            sh = np.clip(np.mean(shares[late], 0), 1e-6, None)
            step = np.log(np.clip(target[:, :3], 1e-6, None) / sh)
            step -= step[:, :1]
            occ_step = np.log(fte_obs / np.maximum(np.mean(ftes[late], 0), 1e-9))
            occ_step -= np.average(occ_step, weights=fte_obs)
            v_step = np.log(p["ventures"]["baseline_founders_per_year"] / max(np.mean(founders[late]), 1))
            i_step = np.log(p["behaviour"]["baseline_independent_share"] / max(np.mean(indep[late]), 1e-6))
            # How many jobs there are is a calibrated quantity too. Without this the fit can only push people to
            # want more work, which against short demand just turns into more involuntary unemployment.
            u_target = popmod.load_baseline(self.p)["labour_rates_2025"]["Total"]["Unemployment rate"] / 100
            damp = .5 if r < 4 else .3  # small steps once close: the response lags by several years
            self.asc[:, 1:3] += damp * step[:, 1:3]
            self.asc_occ += damp * occ_step
            self.asc[:, 3] += damp * v_step
            self.asc[:, 4] += damp * float(np.clip(i_step, -2, 2))
            self._steady_firms = (int(sim.firms["alive"].sum()), sim.firms["age"][sim.firms["alive"]].copy(),
                                  sim.firms["quality"][sim.firms["alive"]].copy(), sim.firms["jobs"][sim.firms["alive"]].copy())
            if verbose:
                emp = [float((1 - s_[:, 0]).mean()) for s_ in shares]
                print(f"  burn-in round {r + 1}: max group gap {np.abs(step[:, 1:]).max():.3f}, "
                      f"occupation gap {np.abs(occ_step).max():.3f}, founders {np.mean(founders[late]):.0f}, "
                      f"employment path {emp[0]:.3f}->{emp[-1]:.3f}, "
                      f"unemployment without migration {np.mean(unemp[late]):.3f}")

    def _calibrate_separations(self, rounds=12, years=8, verbose=True):
        """How often jobs end for frictional reasons, set so unemployment comes out at the published rate.

        This has to be measured with migration running. The burn-in above deliberately switches it off to isolate
        ageing and inertia, but migration is precisely what drives the workforce.

        It replaces calibrating the demand level. That reached the same unemployment rate by holding demand about
        7% below supply for good, and a standing surplus does two things at once: it lays people off, and it pushes
        every new contract to the bottom of its range. The status quo's real wages then fell about 0.9% a year.
        """
        target = popmod.load_baseline(self.p)["labour_rates_2025"]["Total"]["Unemployment rate"] / 100
        self.separation_rate = self.separation_rate or .015
        for r in range(rounds):
            sim = copy.deepcopy(self)
            unemp = [sim.step()["unemployment_rate"] for _ in range(years)]
            # the whole window, not its second half: mismatch between professions builds up over the first years
            # from a base year that has none, and fitted to the settled years alone the first forward year came out
            # near 2% against the published 4% (2026-09-29)
            got = float(np.mean(unemp))
            gap = got - target
            if verbose:
                print(f"  separations round {r + 1}: unemployment {got:.3f} (target {target:.3f}), "
                      f"rate {self.separation_rate:.3f}", flush=True)
            # 1.1: within 0.15 points, not 0.3. At 0.3 the 2015 calibration settled high in the band, and its floor
            # held the backcast's boom years 0.4-0.8 points above the record whatever demand was given
            if abs(gap) < .0015:
                break
            self.separation_rate *= float(np.clip(target / max(got, 1e-3), .6, 1.6))

    def _calibrate_employment_level(self, rounds=6, years=4, verbose=True):
        """The employment rate the status quo actually settles at, with migration and separations running.

        The burn-in fits activity shares with migration off, and separations are then fitted to unemployment with
        it on; nothing checked the employment rate after both. It settled about three points below the published
        rate from the first year, at the 2025 base (78.0% calibrated, 75.2% in year one against 77.8%) and at a
        2015 base alike — the backcast found it. Here the whole model runs, the willingness to work shifts by the
        gap in the odds of working, and separations are refitted, until the settled rate matches."""
        target = popmod.load_baseline(self.p)["labour_rates_2025"]["Total"]["Employment rate"] / 100
        odds = lambda e: e / max(1 - e, 1e-6)
        for r in range(rounds):
            sim = copy.deepcopy(self)
            got = float(np.mean([sim.step()["employment_rate_16_74"] for _ in range(years)]))
            if verbose:
                print(f"  employment round {r + 1}: settled {got:.3f} (target {target:.3f})", flush=True)
            if abs(got - target) < .003:
                break
            self.asc[:, 1:3] += .8 * np.log(odds(target) / odds(got))
            self._calibrate_separations(rounds=4, years=6, verbose=False)
            self._settle_initial_statuses()   # the start a scenario runs from, drawn with the new willingness

    def founder_dividends_bn(self):
        """Dividends founders draw from their firms this year, ma.kr. of today (part of founder_income)."""
        A, p, f = self.A, self.p, self.firms
        idx = np.flatnonzero(A["alive"] & (A["status"] == VENTURE) & (A["venture"] >= 0))
        if not len(idx) or not len(f["profit"]):
            return 0.0
        v = p["ventures"]
        prof = f["profit"][A["venture"][idx]]
        return float(((1 - self.venture_stake(v["external_share_typical"])) * v["dividend_payout"]
                      * np.maximum(prof, 0)).sum() * self.price / 1e9)

    def _settle_disabled_work(self, rounds=8):
        """After the employment level is set, disabled people's work cost is fitted again — the later calibration
        steps move the constants it was fitted with — and their statuses settled to it (v9)."""
        A, p = self.A, self.p
        dis = np.flatnonzero(A["alive"] & A["chooser"] & A["disabled"] & (A["age"] < 67))
        if not len(dis):
            return
        t = p["benefits"].get("disability_working_share", .325)
        pm, _, _ = self.child_transfers()
        for _ in range(rounds):
            P = self.probabilities(dis, self.omega, self.price, pm)
            s_ = float(np.clip(P[:, 1:5].sum(1).mean(), 1e-4, 1 - 1e-4))
            self.disabled_work_cost = getattr(self, "disabled_work_cost", 0.0) \
                + (np.log(s_ / (1 - s_)) - np.log(t / (1 - t)))
        working = dis[np.isin(A["status"][dis], [PART, INDEP])]
        idle = dis[A["status"][dis] == NONWORK]
        want = int(round(t * len(dis)))
        if len(working) > want:
            A["status"][self.rng.choice(working, len(working) - want, replace=False)] = NONWORK
        elif len(working) < want and len(idle):
            A["status"][self.rng.choice(idle, min(len(idle), want - len(working)), replace=False)] = PART

    def _settle_student_work(self, rounds=8):
        """Students' constant fitted again once the others are final, and their statuses settled to it (1.1), as
        for disability above."""
        A, p = self.A, self.p
        stu = np.flatnonzero(A["alive"] & A["chooser"] & (A["studying"] > 0) & ~A["disabled"] & (A["venture"] < 0))
        if not len(stu):
            return
        t = 1 - p["behaviour"]["student_nonwork_share"]
        pm, _, _ = self.child_transfers()
        for _ in range(rounds):
            P = self.probabilities(stu, self.omega, self.price, pm)
            s_ = float(np.clip(P[:, 1:5].sum(1).mean(), 1e-4, 1 - 1e-4))
            self.student_work_cost = getattr(self, "student_work_cost", 0.0) \
                + (np.log(s_ / (1 - s_)) - np.log(t / (1 - t)))
        working = stu[np.isin(A["status"][stu], [PART, FULL, INDEP])]
        idle = stu[A["status"][stu] == NONWORK]
        want = int(round(t * len(stu)))
        if len(working) > want:
            A["status"][self.rng.choice(working, len(working) - want, replace=False)] = NONWORK
        elif len(working) < want and len(idle):
            A["status"][self.rng.choice(idle, min(len(idle), want - len(working)), replace=False)] = PART
        self.refresh_net_now()

    def _net_capital_income_of_dividends(self):
        """The tax returns' capital income (355 ma.kr., population.assign_capital_income) includes the dividends
        founders draw, which the model pays as part of their income (founder_income). Once founders are settled, the
        capital income of everyone else under 67 is scaled down by those dividends, so the total is the record's
        and nothing is counted twice (v9; an external review of v8, 2026-10 found founders' income counted on top of the wage bill)."""
        A, p = self.A, self.p
        if "capital_income_rate" not in A:
            return
        idx = np.flatnonzero(A["alive"] & (A["status"] == VENTURE) & (A["venture"] >= 0))
        if not len(idx) or not len(self.firms["profit"]):
            return
        v, f = p["ventures"], self.firms
        prof = f["profit"][A["venture"][idx]]
        div = float(((1 - self.venture_stake(v["external_share_typical"])) * v["dividend_payout"]
                     * np.maximum(prof, 0)).sum())                       # a year, base-year krónur
        young = A["alive"] & (A["age"] >= 18) & (A["age"] < 67)
        ci = float((A["wealth"][young] * A["capital_income_rate"][young]).sum())
        if ci > 0:
            A["capital_income_rate"][young] *= max(0.0, 1 - div / ci)
        self.founder_dividends0 = div / 1e9

    def _settle_initial_statuses(self):
        """Draw the 2025 statuses from the calibrated choice model itself, so the base year is the model's own
        equilibrium rather than a set of published marginals it then drifts away from. Baseline labour demand is
        rebuilt from the result, so demand equals supply at unchanged wages."""
        A, rng = self.A, self.rng
        # Those studying keep the status they were drawn with; _settle_student_work fits their constant at the end.
        # Redrawn here before 1.1, when the choice model had no student constant, they went into work: 0.4% of
        # 20-24 year olds out of work against the survey's 16.5%, and a part-time share of 28% against 24.3% (found
        # 2026-10-05).
        idx = np.flatnonzero(A["alive"] & A["chooser"] & (A["venture"] < 0) & (A["studying"] == 0))
        per_mother, _, _ = self.child_transfers()
        for _ in range(3):
            P = self.probabilities(idx, self.omega, 1.0, per_mother, idea=np.zeros(len(idx), bool))
            P[:, 3] = 0
            P = P / P.sum(1, keepdims=True)
            u = rng.random(len(idx))
            A["status"][idx] = np.minimum((u[:, None] > np.cumsum(P, 1)).sum(1), 4).astype(np.int8)
            self.refresh_net_now()
        hours = self.hours_of(A["status"])
        self.D0_pub = np.bincount(A["occupation"], weights=hours * A["public"], minlength=N_OCC)
        self.D0_priv = np.bincount(A["occupation"], weights=hours * ~A["public"], minlength=N_OCC)
        A["worker0"] = np.isin(A["status"], [PART, FULL, VENTURE])
        self.supply0 = float((self.D0_pub + self.D0_priv).sum())
        self.sectors.base = dict(self.sectors.state)

    def _reseed_firms_to_steady_state(self):
        """Start from the founder stock the model itself settles on, so the 2025 base year is not below it."""
        A, rng = self.A, self.rng
        target, ages, quality, jobs = getattr(self, "_steady_firms", (None, None, None, None))
        if not target:
            return
        current = np.flatnonzero(self.firms["alive"])
        founders = self.firms["founder"][current]
        A["venture"][founders[founders >= 0]] = -1
        A["status"][founders[founders >= 0]] = FULL
        self.enforce_disability_limits()
        for k in self.firms:
            self.firms[k] = self.firms[k][:0]
        cand = np.flatnonzero(A["self_employed"] & (A["age"] >= 25) & (A["age"] <= 66) & np.isin(A["status"], [PART, FULL]))
        n = min(target, len(cand))
        w = A["enterprise"][cand]
        who = rng.choice(cand, n, replace=False, p=w / w.sum())
        pick = rng.integers(0, len(ages), n)
        v = self.p["ventures"]
        vals = {"founder": who, "age": ages[pick], "alive": np.ones(n, bool), "quality": quality[pick], "jobs": jobs[pick],
                "profit": np.minimum((rng.pareto(v["profit_pareto_alpha"], n) + 1) * v["profit_scale"] * quality[pick], v["profit_cap"])}
        for k, val in vals.items():
            self.firms[k] = np.asarray(val).astype(self.firms[k].dtype)
        A["venture"][who] = np.arange(n)
        A["status"][who] = VENTURE

    def _seed_firm_stock(self):
        """Start from a steady-state stock of founder-run firms, drawn from today's self-employed."""
        A, p, rng, f = self.A, self.p, self.rng, self.firms
        v = p["ventures"]
        n = int(v["baseline_founders_per_year"] * v["initial_founder_stock_years"])
        cand = np.flatnonzero(A["self_employed"] & (A["age"] >= 25) & (A["age"] <= 66) & np.isin(A["status"], [PART, FULL]))
        w = A["enterprise"][cand]
        who = rng.choice(cand, min(n, len(cand)), replace=False, p=w / w.sum())
        n = len(who)
        age = np.minimum(rng.geometric(.2, n), 30).astype(np.int16)
        q = rng.lognormal(-.125, .5, n)
        # grown year by year by the same rule the firms follow (step), ceiling included
        jobs = np.full(n, float(v["jobs_at_birth"]))
        cap = v.get("size_per_quality", 50.0) * q
        for year in range(int(age.max()) if n else 0):
            grow = age > year
            jobs[grow] *= 1 + v["job_growth_survivors"] * q[grow] * np.clip(1 - jobs[grow] / cap[grow], 0, 1)
        prof = np.minimum((rng.pareto(v["profit_pareto_alpha"], n) + 1) * v["profit_scale"] * q, v["profit_cap"])
        for k, val in [("founder", who), ("age", age), ("alive", np.ones(n, bool)), ("quality", q), ("jobs", jobs),
                       ("profit", prof)]:
            f[k] = np.concatenate([f[k], np.asarray(val).astype(f[k].dtype)])
        A["venture"][who] = np.arange(len(f["alive"]) - n, len(f["alive"]))
        A["status"][who] = VENTURE

    def _calibrate_migration(self):
        A, p, base = self.A, self.p, self.base
        mig = base["migration_2025"]
        foreign = A["citizenship"] != IS
        self.emig_hazard = np.zeros((2, 111))
        for c, lab in [(0, "Icelandic citizens"), (1, "Foreign citizens")]:
            counts = np.bincount(A["age"][(foreign == bool(c)) & A["alive"]], minlength=111)
            for a, n in mig[lab]["Emigration"].items():
                a = int(a)
                if a < 111 and counts[a] > 0:
                    self.emig_hazard[c, a] = min(.3, n / counts[a])
        # Hazards apply to adults; a partner goes along 80% of the time, and a mother takes her children. Two
        # things are fixed from Hagstofa 2025: how many leave, and how many of those are children. Solving for both
        # gives an overall scale and how much less readily a household with children moves — which is what the
        # evidence on family migration shows. The earlier version assumed half a child per adult and let the
        # children leave at four to six times the recorded rate, draining the child population.
        adults = np.flatnonzero(A["alive"] & (A["age"] >= 18))
        b = self.emig_hazard[(A["citizenship"][adults] != IS).astype(int), np.minimum(A["age"][adults], 110)] \
            * self.recent_multiplier(adults)
        own = np.zeros(self.N)
        own[adults] = b
        partner = A["partner"][adults]
        leaves = b + .8 * np.where(partner >= 0, own[np.maximum(partner, 0)], 0.0)
        family = A["n_kids"][adults] > 0
        young = A["alive"] & (A["age"] < 18) & (A["mother"] >= 0)
        children_of = np.bincount(A["mother"][young], minlength=self.N)[adults]
        K = float((leaves * children_of).sum())
        F, S = float(leaves[family].sum()), float(leaves[~family].sum())
        labs = ["Icelandic citizens", "Foreign citizens"]
        total = sum(sum(mig[lab]["Emigration"].values()) for lab in labs)
        children = sum(v for lab in labs for a, v in mig[lab]["Emigration"].items() if int(a) < 18)
        scale_family = children / K                       # overall scale × family factor
        scale = (total - scale_family * (F + K)) / S
        if scale <= 0:
            raise RuntimeError("emigration cannot be calibrated: children alone exceed the recorded total")
        self.emig_hazard *= scale
        self.family_mobility = scale_family / scale
        self.R0 = self.income_ratio(np.arange(self.N))
        mob = A["mobility"][A["alive"] & A["chooser"]]
        self.mobility_norm = 1.0 / mob.mean() if mob.mean() > 0 else 1.0
        self.mobility_norm = 1.0
        self.imm_age = {c: np.array([mig[lab]["Immigration"].get(str(a), 0) for a in range(111)], float)
                        for c, lab in [(0, "Icelandic citizens"), (1, "Foreign citizens")]}
        # children per adult arrival, as Hagstofa records it: 0.15 for returning Icelanders, 0.08 for others
        self.imm_children_per_adult = {c: float(a[:18].sum() / max(a[18:].sum(), 1)) for c, a in self.imm_age.items()}
        self.Y0 = self.arrival_income()

    def recent_multiplier(self, idx):
        A = self.A
        recent = A["immigrant"][idx] & (A["years_in_iceland"][idx] < 3)
        return np.where(recent, self.p["migration"]["recent_arrival_emigration_multiplier"], 1.0)

    def income_ratio(self, idx):
        A, p = self.A, self.p
        # pay abroad grows with productivity as pay here does; held flat, staying looked better every year
        growth = (1 + p["markets"]["productivity_growth"]) ** self.year
        abroad = self.foreign_ratio[A["occupation"][idx]] * A["base_wage"][idx] * .68 * growth
        home = np.maximum(self.net_now[idx] / self.price, 100_000 * (self.p.get("base") or {}).get("krona_scale", 1.0))
        return abroad / home

    def arrival_income(self):
        """Expected real monthly net income for a typical arrival in each pool (EEA worker, non-EEA worker, returning Icelander)."""
        A, p = self.A, self.p
        mix = np.array(P.expand_mix(p["migration"]["immigrant_occupation_mix"], self.prof_weights))
        med = np.array([np.median(A["base_wage"][(A["occupation"] == o) & A["immigrant"]])
                        if ((A["occupation"] == o) & A["immigrant"]).any() else 0.0 for o in range(N_OCC)])
        gross = med * self.omega
        polp = p["policy"]
        pr = pol_rules.threshold_price(p["policy"], self.price)
        # Brackets and credit indexed as net_income indexes them. Unindexed, an arrival's expected income shrank
        # with every year of inflation and immigration drifted down for no reason.
        if polp["regime"] == "status_quo":
            taxable = gross * (1 - polp["pension_contrib_employee"])
            net = taxable - pol_rules.income_tax(taxable, [[lo * pr, r] for lo, r in polp["income_tax_brackets"]],
                                                 polp["personal_credit"] * pr)
            ubi = 0.0
        else:
            taxable = gross * (1 - pol_rules.employee_rate(p))
            brackets = polp.get("platform_income_tax_brackets") or polp["income_tax_brackets"]
            net = taxable - pol_rules.income_tax(taxable, [[lo * pr, r] for lo, r in brackets],
                                                 polp.get("platform_personal_credit", 0.0) * pr,
                                                 polp["platform_income_tax_scale"])
            ubi = polp["ubi_adult"]
        eea = (mix * (net + ubi)).sum() / self.price
        non = (mix * net).sum() / self.price
        natives = A["alive"] & ~A["immigrant"] & (A["age"] >= 25) & (A["age"] <= 44)
        ice = self.net_now[natives].mean() / self.price
        return np.array([eea, non, ice])

    def _calibrate_demography(self):
        A, d = self.A, self.p["demography"]
        age = A["age"][A["alive"]].astype(float)
        b = .095
        self.gompertz_a = d["deaths_per_year"] / np.exp(b * age).sum()
        self.gompertz_b = b

    # ------------------------------------------------------------------ yearly step
    def set_policy(self, overrides):
        old_trend = self.p["markets"]["trend_inflation"]
        self.p = deep_merge(self.p, overrides)
        # the second status quo: prices, the króna and rents as the last decade went, for both runs alike
        h = self.p["markets"]["history_like"]
        if h:
            mk = self.p["markets"]
            mk["trend_inflation"] = mk["trend_inflation"] + h * (mk["history_inflation"] - mk["trend_inflation"])
        # a scenario with a different trend pays a different inflation premium on the debt from its first year
        m = self.p["markets"]
        self.macro.coupon_n += m["trend_inflation"] - old_trend
        self.macro.r_debt += (1 - m["debt_indexed_share"]) * (m["trend_inflation"] - old_trend)
        self.macro.inflation += m["trend_inflation"] - old_trend
        self.macro.p = self.p
        self.sectors.p = self.p
        self.frontier.p = self.p
        self.infra.p = self.p
        self.automation.p = self.p

    def solve_market(self, reopt, per_mother):
        A, p = self.A, self.p
        lab, b = p["labour"], p["behaviour"]
        stay = np.setdiff1d(np.flatnonzero(A["alive"] & A["chooser"]), reopt, assume_unique=True)
        stay_fte = np.bincount(A["occupation"][stay], weights=self.hours_of(A["status"][stay], stay), minlength=N_OCC)
        free = p["policy"]["wage_setting"] == "free_market"
        # The market sets the rate for new contracts. Start from last year's, grown by the inflation expected this
        # year: started in last year's krónur, the solver began a trend's width below where it had to go and, with
        # its steps bounded, did not always get there.
        omega = self.omega_new * (1 + p["markets"]["trend_inflation"])
        # The offer is kept within reach of what the job pays (the window below), so the search stays inside it, and
        # a profession at its edge has nowhere further to go: the search ends when every profession has either
        # cleared or reached its edge. Searching past the edge, as it did, every year ran all 80 rounds — three
        # quarters of a model-year's time — to a point the window then threw away (found 2026-10-03).
        bound = lab["safety_wage_bound"]
        going0 = self.omega * (1 + p["markets"]["trend_inflation"])
        w_lo, w_hi = going0 * (1 - bound), going0 * (1 + bound)
        omega = np.clip(omega, w_lo, w_hi)
        prev = None     # last round's (log wage, log gap) per profession, for the secant step
        done = np.zeros(N_OCC, bool)
        rounds = lab["clearing_iterations"]
        for it in range(rounds):
            price = self.price_level(omega)
            P = self.probabilities(reopt, omega, price, per_mother)
            fte = (P[:, 1] * b["part_time_hours"] + P[:, 2]) * hours.factor(self, reopt)
            S = stay_fte + np.bincount(A["occupation"][reopt], weights=fte, minlength=N_OCC)
            # firms weigh the wage they actually pay — mostly contracted — not just the new-hire rate
            D = self.demand(self.implied_paid_index(omega, free), supply=S)
            floor = self.minimum_wage_floor()
            omega = np.maximum(omega, floor)
            # Each profession's search steps towards where its gap closes. The fixed step, (D/S) ** 0.15, closed a
            # 3% gap by about 0.35% a round and never finished in 80; from the second round, the secant — how the gap
            # moved with the wage last round — says how far to go, damped and bounded (10% a round), with the fixed
            # step kept wherever the slope is not a falling one (2026-10-03).
            gap = np.log(np.maximum(D, 1e-9) / np.maximum(S, 1))
            lw = np.log(np.maximum(omega, 1e-9))
            fixed = np.clip(lab["clearing_step"] * gap, np.log(.8), np.log(1.25))
            move = fixed
            if prev is not None:
                dw, dg = lw - prev[0], gap - prev[1]
                slope = np.where(np.abs(dw) > 1e-7, dg / np.where(np.abs(dw) > 1e-7, dw, 1.0), np.nan)
                ok = np.isfinite(slope) & (slope < -.05)
                move = np.where(ok, np.clip(-.8 * gap / np.where(ok, slope, -1.0), -.1, .1), fixed)
                # A profession whose gap does not answer its offer at all — in a year with no renewals the offer
                # reaches only new hires, whom demand does not see — was pushed by the fixed step for every round
                # left, usually to the edge of its window. It is given that whole push at once, and is then done.
                deaf = np.isfinite(slope) & (np.abs(slope) < .05) & ~done
                move = np.where(deaf, fixed * (rounds - it), move)
                move = np.where(done, 0.0, move)
                done |= deaf
            prev = (lw, gap)
            step = np.exp(move)
            # small markets overshoot without a leash. The bounds are real: as fixed nominal numbers, the top one
            # bound once prices had roughly quadrupled — from about 2050 in the status quo, sooner with more
            # inflation — and real pay then fell year after year while vacancies climbed to a third of all posts
            # (found 2026-10-01).
            level = self.price * self.macro.productivity()
            new = np.clip(np.clip(omega * np.where(done, step, np.clip(step, .8, 1.25)), .3 * self.price, 4.0 * level),
                          w_lo, w_hi)
            # A profession held at the statutory minimum with more people than posts is at a bound too: the search
            # lowered it, the floor raised it back, and it never counted as done — every year at a high minimum wage
            # ran all 80 rounds, five times a model-year's time (found 2026-10-05)
            at_floor = (floor > 0) & (omega <= floor * (1 + 1e-6)) & (new <= omega)
            done |= at_floor
            new = np.where(at_floor, omega, new)
            moving = (new > w_lo * (1 + 1e-6)) & (new < w_hi * (1 - 1e-6)) & ~done
            # cleared: every profession that can still move has supply and demand within half a per cent
            if not moving.any() or np.abs(new / omega - 1)[moving].max() < 1e-3 or np.abs(gap)[moving].max() < .005:
                omega = new
                break
            omega = new
        # Diagnostic (markets.freeze_wages): the rate for new contracts is the reference run's of the same year, as a
        # lottery winner's pay rate is the market's, untouched by what they do. scripts/income_effect_check.py uses it
        # to measure the income effect alone; with everyone paid, the market's answer to fewer hours offered — wages
        # bid up — otherwise offset most of the response (v9, 2026-10-12).
        if p["markets"].get("freeze_wages") and self.reference and len(self.reference) >= self.year \
                and "omega_new" in self.reference[self.year - 1]:
            omega = np.asarray(self.reference[self.year - 1]["omega_new"], float)
            price = self.price_level(omega)
            P = self.probabilities(reopt, omega, price, per_mother)
            fte = P[:, 1] * b["part_time_hours"] + P[:, 2]
            S = stay_fte + np.bincount(A["occupation"][reopt], weights=fte, minlength=N_OCC)
            D = self.demand(self.implied_paid_index(omega, free), supply=S)
        # `omega` is the rate for contracts signed now; what most people are paid follows their own contract
        # The offer has to stay within reach of what the job already pays. The solver would otherwise push it far
        # below the going rate — a big lever is needed when only a few contracts renew — and then a renewal wave
        # hands that rate to most of the profession at once, walking the whole wage level down.
        b = lab["safety_wage_bound"]
        # the window sits around what the job pays now, grown by the inflation expected this year — around last
        # year's krónur it was a trend's width lower in real terms, and a large shock pressing on its ceiling cleared
        # real wages lower the higher the trend
        going = self.omega * (1 + p["markets"]["trend_inflation"])
        self.omega_new = np.clip(omega, going * (1 - b), going * (1 + b))
        tightness = D / np.maximum(S, 1)
        self.job_tightness = float(D.sum() / max(S.sum(), 1))   # jobs on offer against people offering, overall
        # jobs per person of working age: demand grows with the workforce, so counted in total, arrivals would
        # create the jobs that draw more arrivals
        self.labour_demand_pc = float(D.sum()) / max(self.working_age(), 1)
        base_len = sum(k * v for k, v in lab["contract_lengths_private"].items())
        # tightness can come back as NaN at extreme corners of the lever space, and a NaN contract length casts
        # to garbage rather than failing, which would quietly poison the run
        tightness = np.nan_to_num(tightness, nan=1.0, posinf=2.0, neginf=0.5)
        self.offer_years = np.clip(base_len + lab["offer_length_sensitivity"] * (tightness - 1), 1, lab["max_contract_years"])
        self.update_public_premium(D, S)
        self.update_workload(D, S)
        self.tightness = np.asarray(D) / np.maximum(np.asarray(S), 1.0)
        # each year's place on the wage curve, so an agreement can be set against where it was signed
        if not hasattr(self, "curve_hist") or self.curve_hist is None:
            self.curve_hist = {}
        self.curve_hist[int(self.year)] = self.wage_curve()
        self.renew_contracts(free)
        self.omega = self.paid_wage_index()
        self.price = self.price_level(self.omega)
        return P, S, D

    def bargaining_cpi(self):
        """The price index agreements compensate. Today, the CPI. Under the reform the parties can agree to
        compensate prices net of the tax switch — the VAT that pays for the borgaralaun — as Denmark's agreements
        use the nettoprisindeks; `policy.indexation_net_of_tax` is the share of the tax effect left out. The
        Scottish micro-macro study of a basic income (Connolly et al. 2021, 2023) found this "social contract"
        decides whether the tax rise feeds a wage-price spiral, more than any other single response."""
        mk = self.macro
        s = self.p["policy"].get("indexation_net_of_tax", 0.0) if self.p["policy"]["regime"] == "platform" else 0.0
        net = getattr(mk, "cpi_net", mk.cpi)
        return float(mk.cpi * (net / max(mk.cpi, 1e-9)) ** s)

    def minimum_wage_floor(self):
        """A statutory monthly minimum, expressed as the wage index each profession needs to clear it."""
        mw = self.p["policy"]["minimum_wage"] if self.p["policy"]["regime"] == "platform" else 0
        if not mw:
            return np.zeros(N_OCC)
        # occ_median is in 2025 krónur and the wage index carries prices, so the minimum must too
        return np.clip(mw * self.price / np.maximum(self.occ_median, 1e-6), 0, 4.0 * self.price)

    def renewal_weight(self, free_market):
        """How far a renegotiated contract moves towards today's rate. Collective agreements move less."""
        w = self.p["labour"]["renewal_bargaining"]
        return w if free_market else w * .6

    def renewal_wage(self, due, omega_new, free_market):
        """What a contract coming up for renewal will actually be signed at.

        The market solver and the renewal itself must both use this. If the solver assumes something else — that a
        renewal adopts the new rate in full, or that there is no negotiated floor — it clears the market at a wage
        nobody is paid, and the difference comes out as unemployment.
        """
        A = self.A
        w = self.renewal_weight(free_market)
        market = np.asarray(omega_new)[A["occupation"][due]]
        signed = np.maximum(self.contract_rate(due), 1e-6)       # including the raises already paid
        agreed = signed ** (1 - w) * market ** w
        if not free_market:
            # An Icelandic kjarasamningur compensates the price rises since the last round and passes through a share
            # of productivity growth: real wages (LAU04800) rose 2.1%/yr over 2005-2025 and never fell over any
            # ten-year window since 1989.
            lab, mk = self.p["labour"], self.macro
            years_since = np.maximum(self.year - A["contract_start"][due], 1)
            # only the inflation the scheduled raises did not already cover
            scheduled = (1 + self.p["markets"]["trend_inflation"]) ** years_since
            prices = (self.bargaining_cpi() / np.maximum(A["contract_cpi"][due], .2) / scheduled) \
                ** lab["inflation_compensation"]
            # What output per hour actually did since the contract was signed — the trend, AI, and anything else
            # that moved it — not the trend alone. Passing through only the assumed trend kept real pay flat through
            # the 2016-18 boom while measured productivity rose 6% and real wages 9% (found 2026-09-26), and
            # left every productivity gain under the reform out of pay. `contract_ai` holds the level at signing.
            prod = (mk.productivity() / np.maximum(A["contract_ai"][due], .2)) ** lab["productivity_passthrough"]
            # a share of what better terms of trade brought since the contract was signed, and a real premium
            tot = (mk.terms_of_trade() / np.maximum(A["contract_tot"][due], .2)) ** lab.get("tot_passthrough", 0.0)
            premium = (1 + lab.get("agreement_real_premium", 0.0)) ** years_since
            # the wage curve, as a level: the profession's slack now against its slack when the contract was signed
            curve = self.wage_curve()
            occ = A["occupation"][due]
            then = np.ones(len(due))
            if getattr(self, "curve_hist", None):
                ys = A["contract_start"][due].astype(int)
                for y in np.unique(ys):
                    m = ys == y
                    then[m] = self.curve_hist.get(int(y), curve)[occ[m]]
            agreed = np.maximum(agreed, signed * prices * prod * tot * premium * curve[occ] / np.maximum(then, 1e-6))
        return agreed

    def wage_curve(self):
        """Where each profession's pay stands on the wage curve: (u / u_frictional) ** -elasticity, with u its
        frictional rate plus its excess supply. 1 where supply meets demand or falls short of it."""
        lab = self.p["labour"]
        eps = lab.get("wage_curve_elasticity", 0.0)
        if not eps:
            return np.ones(N_OCC)
        raw = np.asarray(getattr(self, "tightness", np.ones(N_OCC)), float)
        tight = np.clip(raw, .3, 1.0)
        uf = lab.get("frictional_unemployment", .035)
        # 1.1: the tight side as well. Where posts outnumber people, fewer of those whose job ends are out of work
        # (the refill in step), and the curve reads that lower unemployment; until 1.1 it stopped at 1, so pay in a
        # profession short of people rose only as far as one year's search window allowed
        vac = np.clip(1 - 1 / np.maximum(raw, 1e-9), 0, None)
        refill = lab.get("refill_max", 0.0) * vac / (vac + lab.get("refill_half", .05))
        return ((uf + (1 - tight)) * (1 - refill) / uf) ** -eps

    def implied_paid_index(self, omega_new, free_market=True):
        """Average wage per profession once this year's renewals have happened at `omega_new`.

        This has to renew contracts exactly the way `renew_contracts` does. If it assumes a renewal adopts the new
        rate in full while renewals actually move only part of the way, the solver keeps pushing the new-hire rate
        further to close a gap that never closes — a ratchet that walks the whole wage level down."""
        A = self.A
        employed = A["alive"] & np.isin(A["status"], [PART, FULL])
        hours = self.hours_of(A["status"], slice(None)) * employed
        locked = (A["contract_end"] > self.year) & employed
        rate = self.contract_rate().astype(float)
        due = np.flatnonzero(employed & ~locked)
        if len(due):
            rate[due] = self.renewal_wage(due, omega_new, free_market)
        paid = np.bincount(A["occupation"], weights=hours * rate, minlength=N_OCC)
        total = np.bincount(A["occupation"], weights=hours, minlength=N_OCC)
        return np.where(total > 0, paid / np.maximum(total, 1e-9), omega_new)

    def paid_wage_index(self):
        """Average wage actually paid in each profession, across contract vintages."""
        A = self.A
        employed = A["alive"] & np.isin(A["status"], [PART, FULL])
        hours = self.hours_of(A["status"], slice(None)) * employed
        paid = np.bincount(A["occupation"], weights=hours * np.where(A["contract_end"] > self.year,
                                                                     self.contract_rate(), self.omega_new[A["occupation"]]),
                           minlength=N_OCC)
        total = np.bincount(A["occupation"], weights=hours, minlength=N_OCC)
        return np.where(total > 0, paid / np.maximum(total, 1e-9), self.omega_new)

    def renew_contracts(self, free_market):
        """Contracts that have run out are renegotiated at today's rate; new hires sign at it too."""
        A, lab, rng = self.A, self.p["labour"], self.rng
        employed = np.flatnonzero(A["alive"] & np.isin(A["status"], [PART, FULL]))
        if not len(employed):
            return
        due = employed[(A["contract_end"][employed] <= self.year)]
        if not len(due):
            return
        A["contract_omega"][due] = self.renewal_wage(due, self.omega_new, free_market)
        A["contract_start"][due] = self.year
        A["contract_cpi"][due] = self.bargaining_cpi()
        A["contract_tot"][due] = self.macro.terms_of_trade()
        A["contract_ai"][due] = self.macro.productivity()
        table = lab["contract_lengths_public"], lab["contract_lengths_private"]
        for is_public, lengths in zip((True, False), table):
            who = due[A["public"][due] == is_public]
            if not len(who):
                continue
            offer = self.offer_years[A["occupation"][who]] * (1.15 if is_public else 1.0)
            jitter = np.nan_to_num(offer + rng.normal(0, 1.2, len(who)), nan=2.0)
            drawn = np.maximum(1, np.round(jitter)).astype(int)   # stagger renewals
            if not free_market:   # collective agreements: everyone renews together on a fixed cycle
                drawn = np.full(len(who), lab["agreement_cycle_years"])
            A["contract_end"][who] = (self.year + drawn).astype(np.int16)

    def market_balance(self, reopt, P):
        """Supply and demand at the solved wages, given realised choice probabilities."""
        A, p = self.A, self.p
        lab = p["labour"]
        stay = np.setdiff1d(np.flatnonzero(A["alive"] & A["chooser"]), reopt, assume_unique=True)
        S = np.bincount(A["occupation"][stay], weights=self.hours_of(A["status"][stay], stay), minlength=N_OCC) \
            + np.bincount(A["occupation"][reopt], weights=(P[:, 1] * p["behaviour"]["part_time_hours"] + P[:, 2])
                          * hours.factor(self, reopt), minlength=N_OCC)
        # the wage the market cleared at, which is what demand was solved against
        return None, S, self.demand(self.implied_paid_index(self.omega_new,
                                    p["policy"]["wage_setting"] == "free_market"), supply=S)

    def step(self):
        # Employers carry leave above the borgaralaun, so the cost has to be on wages before the market prices
        # labour this year. It is read from last year's pay and births, as an insurer would set a premium.
        leave = self.leave_scheme()
        self.p["policy"]["employer_leave_cost_share"] = leave["employer_cost_share"]
        self.leave_now = leave
        A, p = self.A, self.p
        rng = self.rng
        self.year += 1
        # the backcast's identified demand shock: jobs the economy had room for that year beyond what the model
        # generates — construction, the investment boom, the collapse — applied to every run alike
        # A run measured against the status quo's path already has that shock in its demand (demand() scales to
        # the reference's employment), so it is applied only to runs that stand on their own.
        hist = p.get("history") or {}
        if "demand_level" in hist:   # every run alike (v8: the same rules for reform and status quo, demand())
            self.demand_level = float(hist["demand_level"])
        self.macro.year = self.year   # trend productivity is dated
        capital.set_factor(self, self.macro)   # 2.0: capital per worker against the reference's
        b = p["behaviour"]
        platform = p["policy"]["regime"] == "platform"
        # the price level payments are set to for the year: expected at its start, for benefits and the payment alike
        self.price_set = self.price * (1 + p["markets"]["trend_inflation"])
        # tax thresholds and the personal credit rise with the CPI and, by law, 1% a year more (policy.threshold_price)
        p["policy"]["threshold_index"] = p["policy"].get("threshold_index", 1.0) \
            * (1 + p["policy"].get("threshold_real_growth", 0.0))
        if platform:
            pol = p["policy"]
            if not hasattr(self, "ubi_real"):
                self.ubi_real = (pol["ubi_adult"], pol["ubi_child"])
            indexation = pol.get("ubi_indexation", 1.0 if pol.get("ubi_indexed", True) else 0.0)
            phase = min(1.0, self.year / max(1, pol.get("ubi_phase_in_years", 1)))
            # Set at the start of the year, so to the price level expected for it — as Iceland sets benefits — not to
            # last year's, which cost the payment a year's inflation in real value, every year.
            expected = self.price_set
            # Optionally, a share of real wage growth as well, the rule today's benefits follow (benefit_index).
            # Indexed to prices alone, a payment falls behind pay by a third over thirty-five years of 1% real
            # growth — a design choice, but one the long view must show as such, not as a budget surplus.
            follow = pol.get("ubi_wage_indexation", 0.0)
            real = 1.0
            if follow and getattr(self, "real_wage0", None) is not None:
                w = self.D0_pub + self.D0_priv
                wage = float((self.omega * w).sum() / max(w.sum(), 1e-9))
                real = max(wage / max(expected, .1) / max(self.real_wage0, .1), 1.0) ** follow
            pol["ubi_adult"], pol["ubi_child"] = (u * expected ** indexation * real * phase for u in self.ubi_real)
            # The reform's pace (v8). Taxes and the payment start on day one, as legislated; the public payroll cut and
            # the folding-in of the pension funds advance linearly over `transition_years` (a 20% cut takes about three
            # years at the public sector's 5-7% yearly turnover), and those on today's benefits are protected for the
            # share not yet phased in (policy.net_income). One year is v7's switch: everything at once.
            T = max(1, int(round(pol.get("transition_years", 1))))
            s = min(1.0, self.year / T)
            if not hasattr(self, "transition_targets"):
                self.transition_targets = {k: pol.get(k, 0.0) for k in ("public_payroll_cut", "pension_fold")}
            for k, v in self.transition_targets.items():
                pol[k] = v * s
            pol["transition_share"] = s
        self.fisheries_fund_start()
        self.step_occupation_change()
        base_fte = self.D0_pub + self.D0_priv
        self.automation.update(self.year, self.omega / max(self.price, .1), base_fte, self.price)
        careers.reset_year(self)
        self.update_peers()                  # 2.0: last year's statuses, before anyone chooses
        self.update_housing_market()
        hours.update(self)                   # 2.0: the week within the job, at last year's pay
        self.refresh_net_now()
        fresh = np.flatnonzero(np.isnan(self.R0) & A["alive"])
        if len(fresh):
            self.R0[fresh] = self.income_ratio(fresh)
        per_mother, invested, child_gross = self.child_transfers()
        self.per_mother_now = per_mother   # the snapshot's incentive measures reprice the same choices

        # --- who re-thinks this year
        cand = self.choosers()
        rate = b["reoptimise_rate_first_year"] if (self.year == 1 and platform) else b["reoptimise_rate"]
        # Some moments make everyone decide again: coming of working age, leaving upper-secondary school (20), the
        # pension age, arrival, and a course begun or ended last year. Until 1.1 those studying never re-chose and
        # those leaving study kept the status they had as students until a yearly draw reached them, so school
        # leavers and graduates piled up out of work: 17% of 20-29 year olds after ten years of the status quo,
        # against about 5% neither working nor studying in the survey (Eurostat edat_lfse_20).
        forced = A["involuntary"][cand] | A["underemployed"][cand] | np.isin(A["age"][cand], [16, 20, 67]) \
            | (A["origin_year"][cand] == self.year - 1) & (self.year > 1) \
            | np.isin(cand, getattr(self, "study_changed", np.zeros(0, int)))
        reopt = cand[(rng.random(len(cand)) < rate) | forced]

        self.solve_market(reopt, per_mother)
        idea = rng.random(len(reopt)) < self.idea_prob(reopt)
        P = self.probabilities(reopt, self.omega, self.price, per_mother, idea=idea)
        u = rng.random(len(reopt))
        choice = np.minimum((u[:, None] > np.cumsum(P, 1)).sum(1), 4).astype(np.int8)
        _, S, D = self.market_balance(reopt, P)
        leavers = reopt[(A["venture"][reopt] >= 0) & (choice != VENTURE)]
        self.founder_leaves(leavers)
        took_job = reopt[np.isin(choice, [PART, FULL]) & (A["contract_end"][reopt] <= self.year)]
        A["status"][reopt] = choice
        A["involuntary"][reopt] = False
        A["underemployed"][reopt] = False
        # 1.1: juniors turned away where machines took the entry-level work; they look again next year (careers.py)
        away = careers.ration_first_jobs(self, took_job)
        if len(away):
            A["status"][away] = NONWORK
            A["involuntary"][away] = True
            took_job = np.setdiff1d(took_job, away)
        self._start_contracts(took_job)

        # --- when the agreed wage does not clear the market, who absorbs it?
        # In Iceland the answer has been pay, not jobs: the króna slides, inflation runs ahead of the last
        # settlement, real wages fall, and people keep working. Unemployment stayed near 4% even through 2008
        # (VIN01104), while real wages (LAU04800) swung hard. So most of a shortfall is taken as an erosion of real
        # pay, and only what is left over is taken as lost jobs.
        shortfall = np.clip(1 - D / np.maximum(S, 1), 0, 1)
        absorbed = p["labour"]["real_wage_absorption"]
        self.wage_erosion = float(min(np.average(shortfall, weights=np.maximum(S, 1)) * absorbed,
                                      p["labour"]["max_yearly_erosion"]))
        excess = shortfall * (1 - absorbed) * p["labour"]["dismissal_speed"]
        self.vacancy_rate = float(np.clip(D - S, 0, None).sum() / max(D.sum(), 1))
        if self.wage_erosion > 1e-6:
            # the erosion lands on the price level: pay keeps its krónur and buys less
            self.macro.absorbed *= 1 + self.wage_erosion
            self.price = self.price_level(self.omega)
        workers = np.flatnonzero(A["alive"] & np.isin(A["status"], [PART, FULL]))
        lose = rng.random(len(workers)) < excess[A["occupation"][workers]] if excess.max() > 1e-3 \
            else np.zeros(len(workers), bool)
        hit = workers[lose]
        # some of those a shortfall reaches keep the job on fewer hours — the other way a firm sheds labour
        cut = (A["status"][hit] == FULL) & (rng.random(len(hit)) < p["labour"]["hours_cut_share"])
        A["status"][hit[cut]] = PART
        A["underemployed"][hit[cut]] = True
        dismissed = hit[~cut]
        # Frictional separations: jobs end for reasons that have nothing to do with the level of demand — a firm
        # closes, a project ends, a move — and the next takes time to find. This is what gives the economy its
        # unemployment at the going wage. It used to come from holding demand 7% below supply, which bought the
        # right unemployment rate with a surplus that pushed every new hire's pay to its floor, year after year,
        # and made the status quo's real wages fall.
        rest = workers[~lose]
        separated = rest[rng.random(len(rest)) < self.separation_rate]
        # 1.1: where a profession has open posts, some of those whose job ends move straight to another
        vac = np.clip(D - S, 0, None) / np.maximum(D, 1)
        refill = p["labour"].get("refill_max", 0.0) * vac / (vac + p["labour"].get("refill_half", .05))
        separated = separated[rng.random(len(separated)) >= refill[A["occupation"][separated]]]
        let_go = np.union1d(dismissed, separated)
        A["status"][let_go] = NONWORK
        A["involuntary"][let_go] = True
        A["contract_end"][let_go] = 0
        # notice period on a dismissal: the wage keeps being paid for a few months after the job ends
        self.severance_bn = float((self.wage_of(dismissed, self.omega_new) * p["labour"]["notice_months"]).sum() / 1e9)

        self.step_health()
        self.step_childhood()
        self.step_education()
        self.step_tenure()
        careers.accrue(self)                # 1.1: a year's experience
        self.step_home_purchase()
        housing.step_moves(self)            # v10: older owners downsizing, families moving up
        regions.step_moves(self)            # 2.0: moves between the capital area and the rest
        self.step_occupational_mobility()
        founders_new = self.step_ventures(reopt[(choice == VENTURE) & (A["venture"][reopt] < 0)])
        emig = self.step_emigration()
        imm, self.imm_children = self.step_immigration()
        self.arrivals_choose()
        births, deaths = self.step_demography()
        self.step_partnerships()
        self.births_last = float(births)
        self.step_funds()
        self.step_public_equity()
        self.apply_childcare_constraint()
        self.enforce_disability_limits()
        self.frontier.update(self.year)
        self.infra.update(self.year)
        self.macro.infra_gain = self.infra.state["productivity_gain"]
        self.sectors.update(self.year, self.macro.e, self.omega / self.macro.trend(), self.macro.P_N, self.macro.r,
                            self.frontier.state)
        self.fisheries_fund_end()
        acc = self.accounts()
        # 2.0: the pension funds' year; the state's cover for a cut is spent, special payments ended are saved
        support, saved = pensions.update(self, acc)
        acc["pension_fund_support"], acc["pension_special_saved"] = support * self.price, saved * self.price
        acc["expenditure"] += (support - saved) * self.price
        housing.accrue_claims(self)         # v10: lending against homes, booked once a year
        self.update_wealth()
        self.adult_savings = getattr(self, "adult_savings", 0.0) + acc["ubi_saved"] / max(self.price, .1)
        self.cons_index = acc["consumption_real"] / self.accounts0["consumption_real"] if hasattr(self, "accounts0") else 1.0
        # how much of what households earn they actually spend. This, not the income level, is the demand channel a
        # reform opens: paying the same total to people who spend more of it raises demand. The level is already in
        # the wage term, and counting it twice makes any wage fall feed back on itself.
        self.spend_rate = acc["consumption_real"] / max(acc["labour_income_real"], 1.0)
        pre, change, static = self.balance(acc)
        # interest against the base year's, in every run (see balance)
        interest_ref = self.macro.interest0
        if hasattr(self, "accounts0"):
            bal = self.macro.update_end_of_year(self, acc, S, D, pre, interest_ref)
            self.price = self.macro.cpi
        else:
            bal = pre
        self.accounts_cache = acc
        acc["interest"] = self.macro.interest
        for k in ("raw_gap", "export_capacity", "competitiveness_x", "rel_price", "output", "rent"):
            acc[k] = float(getattr(self.macro, k, 1.0))
        # 1.1: what a reform's family care is set against
        acc["family_care_hours"], acc["family_carers"] = familycare.hours(self), int(familycare.ties(self).sum())
        acc.update(regions.accounts(self))
        self.own_history.append(acc)
        self.history.append(self.snapshot(acc, founders_new, emig, imm, births, deaths, bal, change, static))
        # what next year's social staffing is set against: this year's hardship, child poverty and crime
        self.update_distress(self.history[-1],
                             self.history[-1].get("crime_index", 1.0) * getattr(self, "crime0", 0.0))
        return self.history[-1]

    def step_funds(self):
        """Start-of-life funds: invested child UBI accumulates (principal, CPI-indexed) and is paid out at 25.

        The money lands with the person, which matters: it is a deposit on somewhere to live and capital to start
        something with, at the age when both decisions are actually made. Before this the payout only nudged
        aggregate housing demand and never reached a household at all.
        """
        A, p = self.A, self.p
        pol, f = p["policy"], p["markets"]
        payout = A["alive"] & (A["age"] == pol["fund_payout_age"]) & (A["fund"] > 0)
        money = A["fund"][payout]
        self.macro.fund_payout = float(money.sum() / 1e9)
        # The payout lands as savings. Whether it buys a home is the same decision anyone's savings face
        # (step_home_purchase): a deposit, and payments the household can carry. Booked straight into home equity,
        # as it was, every payout made its holder an owner of a fraction of a dwelling.
        A["wealth"][payout] += money
        # money in hand to start something with, if they choose to, for as long as it lasts
        A["seed_capital"][payout] = money
        A["fund"][payout] = 0.0
        A["seed_capital"][A["alive"]] *= (1 - pol["fund_venture_decay"])
        if p["policy"]["regime"] != "platform":
            return
        kids = np.flatnonzero(A["alive"] & (A["age"] < 18) & (A["mother"] >= 0))
        kids = kids[~pol_rules.moved_out(A, kids, p)]    # paid in full to themselves; the fund stops growing
        inv = pol_rules.invested_share(p["policy"])
        real_ubi = p["policy"]["ubi_child"] / max(self.price, .1)
        A["fund"][kids] += inv[np.clip(A["birth_order"][kids], 1, 7)] * real_ubi * 12

    def tourism_jobs(self):
        """Tourism is Iceland's largest export earner and was not a sector at all. Employment follows what it
        earns, and lands where those jobs actually are — service, sales and food."""
        tr = self.p["trade"]
        rel = (tr["price"]["tourism"] * self.macro.tourism_vat_factor()) ** tr["tourism_labour_elasticity"]
        change = tr["tourism_fte"] * (rel - 1)
        # a job-retention scheme (hlutabætur, 2020-21) keeps part of the jobs a collapse would end on the payroll
        hist = self.p.get("history") or {}
        # shielding fills empty hotels with those it protects: rent the state pays, which tourism earns
        housing = float(hist.get("shield_housing_bn", 0.0))
        if housing:
            change += tr["tourism_fte"] * housing / max(tr.get("tourism_revenue_bn", 600.0), 1.0)
        keep = float(hist.get("job_retention", 0.0))
        if change < 0 and keep:
            change *= 1 - keep
        if abs(change) < 1 and not hist.get("shield_carers"):
            return np.zeros(N_OCC)
        where = {"Waiters and bar staff": .18, "Cooks": .14, "Retail and other service": .34,
                 "Cleaners": .12, "Bus and truck drivers": .09, "Other elementary": .13}
        jobs = np.zeros(N_OCC)
        for name, share in where.items():
            if name in OCCUPATIONS:
                jobs[OCCUPATIONS.index(name)] = change * share
        # and the young carers it hires, on call in the shielded areas, as care work for the months it runs
        carers = float(hist.get("shield_carers", 0.0)) * float(hist.get("shield_months", 0.0)) / 12
        if carers and "Care assistants" in OCCUPATIONS:
            jobs[OCCUPATIONS.index("Care assistants")] += carers
        return jobs

    def schooling_cost(self):
        """Compulsory and upper-secondary schooling: a cost that follows how many children there are."""
        A, sc = self.A, self.p["schooling"]
        kids = int((A["alive"] & (A["age"] < 18)).sum())
        return sc["spending_bn"] * kids / max(self.children0, 1)

    def emissions_snapshot(self):
        """Territorial emissions. Electricity here is already clean, so industry dominates and the smelters are
        most of it — which makes ending their contracts a large emissions decision, not only a fiscal one."""
        em, mk = self.p["emissions"], self.macro
        running = mk.smelter_share if hasattr(mk, "smelter_share") else self.sectors.state.get("smelter_twh", 12.9) / 12.9
        smelter = em["smelter_mt"] * max(0.0, running)
        rest = (em["total_mt"] - em["smelter_mt"]) * (int(self.A["alive"].sum()) / max(getattr(self, "pop_total0", 1), 1))
        transition = mk.transition_delay()   # slower electrification of road transport, and fewer buses
        total = smelter + rest + transition
        return {"emissions_mt": float(total),
                "emissions_smelter_mt": float(smelter),
                "emissions_transition_mt": float(transition),
                "fuel_imports_extra_bn": float(self.p["energy_split"]["fuel_imports_bn_per_mt"] * transition),
                # the extra heating bill of a cold-area household, a month in 2025 krónur
                "green_heat_share": float(self.green_heat_share()),
                "cold_area_heating_bill": float(self.heating_bill(np.flatnonzero(self.A["alive"])).max(initial=0.0)),
                "emissions_vs_2025": float(total / max(em["total_mt"], .1)),
                "emissions_value_bn": float((em["total_mt"] - total) * em["carbon_price_isk_per_t"] * 1e6 / 1e9)}

    def crime_now(self):
        """Crime for this year, computed once. It was being computed twice at different points in the step, so
        the index and the cost it implied disagreed with each other."""
        if getattr(self, "_crime_year", None) != self.year:
            self._crime_year, self._crime = self.year, self.crime_snapshot()
        return self._crime

    def crime_snapshot(self):
        """Offending, and what it costs the state.

        Built from what the evidence says drives acquisitive crime — hardship, idleness among the young, and a
        childhood spent poor — and carrying the finding that cuts the other way: Alaska's dividend reduced
        property crime slightly while raising substance-related incidents right after payment. Both terms are
        live, so a large payment does not automatically read as less crime.

        Reported as an index against the base year, because the level of crime in Iceland is not something this
        model can predict; how it moves is.
        """
        A, p = self.A, self.p
        c = p["crime"]
        alive = A["alive"]
        adults = np.flatnonzero(alive & (A["age"] >= 16))
        cmin, equiv = self.housing_costs(adults)
        hardship = self.household_real_income(adults) < p["costs"]["subsistence_share"] * cmin
        idle = A["involuntary"][adults] & (A["status"][adults] == NONWORK)
        young = A["age"][adults] < 30
        childhood = np.minimum(A["poverty_years"][adults], 18)
        pressure = (c["hardship_weight"] * hardship
                    + c["youth_idle_weight"] * (idle & young)
                    + c["childhood_weight"] * childhood)
        ubi = p["policy"]["ubi_adult"] if p["policy"]["regime"] == "platform" else 0.0
        k = (p.get("base") or {}).get("krona_scale", 1.0)
        over = max(0.0, ubi / max(self.price, .1) - c["substance_threshold"] * k) / (300_000 * k)
        now = float(np.mean(pressure))
        base = getattr(self, "crime0", None)
        # The Alaska finding is a proportional one — substance incidents rise by a share after a payment — so it
        # scales offending rather than adding a fixed amount to every adult's pressure. Added, its size depended on
        # how large the other terms happened to be, and once hardship was measured on household income it
        # outweighed all of them.
        index = (now / base if base else 1.0) * (1 + c["substance_weight"] * over)
        # a payment withheld in prison makes a sentence dearer; severity deters little
        withheld = p["policy"]["prison_ubi_withheld"] if p["policy"]["regime"] == "platform" else 0.0
        index *= 1 - c["forfeit_deterrence"] * withheld * min(ubi / max(self.price, .1) / (300_000 * k), 1.5)
        return {"crime_index": float(index), "prisoners": float(c["prisoners0"] * index),
                "crime_pressure": now,
                "crime_cost_bn": float(c["responsive_spending_bn"] * index ** c["cost_elasticity"])}

    def _seed_childhood_poverty(self):
        """Give the 2025 population the childhood-poverty histories it actually has.

        Everyone started at zero, so the childhood term in crime was nil in the base year and grew as each new
        cohort reached 16 carrying years counted in the run — offending in the status quo rose by half again
        every couple of years for no reason. Children get the years they have lived in their household's current
        state; adults a draw at the rate children are poor today."""
        A, p, rng = self.A, self.p, self.rng
        kids = np.flatnonzero(A["alive"] & (A["age"] < 18) & (A["mother"] >= 0))
        if not len(kids):
            return
        mothers = A["mother"][kids]
        cmin, _ = self.housing_costs(mothers)
        poor = self.household_real_income(mothers) < p["costs"]["subsistence_share"] * cmin * 1.6
        A["poverty_years"][kids] = np.where(poor, A["age"][kids], 0).astype(A["poverty_years"].dtype)
        rate = float(poor.mean())
        adults = np.flatnonzero(A["alive"] & (A["age"] >= 18))
        A["poverty_years"][adults] = rng.binomial(p["childhood"]["max_years"], rate, len(adults))

    def step_health(self):
        """Health responds to how people are living, and what that costs the state.

        The evidence here is unusually direct. Manitoba's Mincome cut hospital use 8.5%, concentrated in
        accidents and mental health (Forget 2011); Finland's basic income trial found clearly better mental
        wellbeing with no employment effect at all. What does the damage is hardship and involuntary idleness
        rather than low income as such, so those are what the model responds to.
        """
        A, p, rng = self.A, self.p, self.rng
        hp = p["health"]
        alive = A["alive"]
        adults = np.flatnonzero(alive & (A["age"] >= 18))
        cmin, equiv = self.housing_costs(adults)
        hardship = self.household_real_income(adults) < p["costs"]["subsistence_share"] * cmin
        idle = A["involuntary"][adults] & (A["status"][adults] == NONWORK)
        pol = p["policy"]
        # sick pay withdrawn: whoever falls ill without private cover loses income while ill, and the model
        # carries that the same way it carries any other hardship
        uncovered = 0.0
        if pol["regime"] == "platform" and pol["public_sick_pay_cut"]:
            exposed = A["public"][adults] & np.isin(A["status"][adults], [PART, FULL])
            # where the leave scheme makes cover compulsory, nobody is left uninsured, so the penalty goes with it
            insured = pol["state_leave_ended"]
            uncovered = (hp["hardship_penalty"] * pol["public_sick_pay_cut"] * pol["sick_absence_rate"]
                         * (1 - pol["private_sickness_uptake"]) * (1 - insured) * exposed)
        ceiling = np.clip(1.0 - hp["age_gradient"] * np.maximum(A["age"][adults] - 40, 0)
                          - hp["disability_penalty"] * A["disabled"][adults] + A["health_offset"][adults]
                          - hp["hardship_penalty"] * hardship - hp["unemployment_penalty"] * idle
                          - uncovered, .05, 1.0)
        now = A["health"][adults]
        A["health"][adults] = now + hp["recovery_rate"] * (ceiling - now)
        # ill health is also how people leave the workforce
        working = np.isin(A["status"][adults], [PART, FULL, VENTURE])
        risk = hp["disability_onset"] * np.clip(1.5 - A["health"][adults], 0, 2)
        struck = adults[working & (rng.random(len(adults)) < risk)]
        A["disabled"][struck] = True
        # v9: reduced capacity to work is what the pension is for; a full-time job becomes a part-time one
        A["status"][struck[A["status"][struck] == FULL]] = PART
        self.new_disabled = int(len(struck))

    def health_cost(self):
        """Public health spending: the 2025 level, scaled by how many people there are and how well they are."""
        A, hp = self.A, self.p["health"]
        alive = A["alive"]
        if not hasattr(self, "health0"):
            return hp["public_spending_bn"]
        morbidity = float(np.mean((1 - A["health"][alive]) ** hp["cost_elasticity"]))
        pop = int(alive.sum()) / max(getattr(self, "pop_total0", int(alive.sum())), 1)
        return hp["public_spending_bn"] * pop * (morbidity / max(self.health0, 1e-6))

    def step_childhood(self):
        """A childhood year spent in a poor household, counted so it can be carried into adult life."""
        A, p = self.A, self.p
        kids = np.flatnonzero(A["alive"] & (A["age"] < 18) & (A["mother"] >= 0))
        if not len(kids):
            return
        mothers = A["mother"][kids]
        cmin, equiv = self.housing_costs(mothers)
        poor = self.household_real_income(mothers) < p["costs"]["subsistence_share"] * cmin * 1.6
        A["poverty_years"][kids[poor]] += 1

    def education_return_index(self):
        """What a degree is expected to be worth against the base year: the pay of work that asks for one, times the
        chance of a post (a shortage is a post waiting, a queue a smaller chance), against work that does not."""
        omega0 = getattr(self, "omega0", None)
        if omega0 is None:
            return 1.0
        w0 = self.D0_pub + self.D0_priv
        hi = self.min_edu >= 2
        tight = np.clip(np.asarray(getattr(self, "tightness", np.ones(N_OCC)), float), .5, 2.0)
        expected = np.asarray(self.omega, float) * np.minimum(tight, 1.0)
        # 1.1: and the chance of a first job in it, where machines take entry-level work (careers.py)
        if "experience" in self.A:
            expected = expected * careers.junior_hiring(self) ** self.p["careers"]["first_job_weight"]
        avg = lambda v, m: float((v * w0)[m].sum() / max(w0[m].sum(), 1e-9))
        now = avg(expected, hi) / max(avg(expected, ~hi), 1e-9)
        base = avg(np.asarray(omega0, float), hi) / max(avg(np.asarray(omega0, float), ~hi), 1e-9)
        return float(np.clip(now / max(base, 1e-9), .5, 3.0))

    def step_education(self):
        """Who goes and studies, and what it is worth.

        Studying means years of little or no earnings, so whether a person can afford it turns on what income
        they have while they are not working. That is exactly what a basic income changes, and it is the channel
        the US negative income tax experiments found: school attendance and completion rose. Without this the
        model can only ever show a basic income costing output, never building any.
        """
        A, p, rng = self.A, self.p, self.rng
        e = p["education"]
        course_events = []   # who began or ended a course this year: they decide about work again next year
        enrolled = np.flatnonzero(A["alive"] & (A["studying"] > 0))
        if len(enrolled):
            # A course goes at the speed the rest of life allows. Someone who does not have to work gets through
            # it in the nominal time; someone holding down a full-time job takes far longer and many never finish.
            # This is where a basic income buys completion rather than only enrolment.
            h = self.hours_of(A["status"][enrolled])
            speed = np.where(h <= 0, 1.0, np.where(h < 1.0, e["progress_part_time"], e["progress_full_time"]))
            # a mother of a child under two gets through a course more slowly
            infant = np.zeros(len(A["age"]), bool)
            small = A["alive"] & (A["age"] <= 1) & (A["mother"] >= 0)
            infant[A["mother"][small]] = True
            speed = speed * np.where(infant[enrolled], e["progress_with_infant"], 1.0)
            A["studying"][enrolled] -= speed
            A["study_years"][enrolled] += 1
            gave_up = enrolled[A["study_years"][enrolled] >= e["max_years"]]
            A["studying"][gave_up] = 0                 # years spent, no degree at the end of them
            A["student"][gave_up] = False
            self.dropouts = int(len(gave_up))
            done = enrolled[(A["studying"][enrolled] <= 0) & (A["study_years"][enrolled] < e["max_years"])]
            A["studying"][done] = 0
            if len(done):
                moved = done[A["education"][done] < 2]
                A["education"][moved] += 1
                # most take work that asks for what they studied: a profession drawn as anyone of their new level
                # is placed, weighted by where the posts and the pay are, at that profession's pay; the rest stay
                # in their old one, paid the premium. Kept in the old profession, as all were until v6, graduates
                # added nothing to the professions short of graduates.
                switch = moved[rng.random(len(moved)) < e.get("graduate_switch_share", 0.0)]
                stay = np.setdiff1d(moved, switch, assume_unique=True)
                A["base_wage"][stay] *= e["wage_premium"]
                if len(switch) and getattr(self, "occ_mix0", None) is not None:
                    pull = self.occupation_pull()
                    pub_share = self.D0_pub / np.maximum(self.D0_pub + self.D0_priv, 1e-9)
                    for level in (1, 2):
                        who = switch[A["education"][switch] == level]
                        allowed = self.occ_mix0[level] * pull * (self.min_edu <= level)
                        if not len(who) or allowed.sum() <= 0:
                            continue
                        dest = rng.choice(N_OCC, len(who), p=allowed / allowed.sum())
                        old_occ = A["occupation"][who]
                        A["base_wage"][who] *= np.where(dest != old_occ, self.occ_median[dest]
                                                        / np.maximum(self.occ_median[old_occ], 1e-9), e["wage_premium"])
                        A["occupation"][who] = dest
                        changed = who[dest != old_occ]
                        A["public"][changed] = rng.random(len(changed)) < pub_share[dest[dest != old_occ]]
                        A["tenure"][changed] = 0
                elif len(switch):
                    A["base_wage"][switch] *= e["wage_premium"]
                A["student"][done] = False
            self.graduates = int(len(done))
            course_events += [gave_up, done]
        else:
            self.graduates = 0
            self.dropouts = 0
        ch_p = p["childhood"]
        cand = np.flatnonzero(A["alive"] & A["chooser"] & (A["studying"] == 0) & ~A["disabled"]
                              & (A["age"] >= 18) & (A["age"] <= e["max_age"]) & (A["education"] < 2)
                              & (A["venture"] < 0))
        if not len(cand):
            self.new_students = 0
            self.study_changed = np.concatenate(course_events) if course_events else np.zeros(0, int)
            return
        # What a student would have to live on. Studying here means part-time work alongside it, which is what
        # Icelandic students actually do and how the labour force survey counts them — so the cost of studying is
        # the full-time earnings given up, and the question is whether what is left covers the cost of living.
        pt = p["behaviour"]["part_time_hours"]
        wage = np.maximum(self.wage_of(cand, self.omega_new) * self.public_pay_factor(cand)
                          - self.public_wage_offset(cand, self.omega_new),
                          .4 * A["base_wage"][cand] * self.price)
        partner = A["partner"][cand]
        pinc = np.where(partner >= 0, self.net_now[np.where(partner >= 0, partner, 0)], 0)
        per_mother, _, _ = self.child_transfers()
        while_studying = pol_rules.net_income(A, cand, wage * pt, np.ones(len(cand), bool), p, pinc,
                                      self.price, self.benefit_index())["net"] - self.household_levies(cand) + pinc \
            + self.household_child(cand, per_mother)
        cmin, equiv = self.housing_costs(cand)
        afford = np.clip(while_studying / self.price / np.maximum(cmin, 1), .05, 4.0)
        # childhood poverty shows up here, decades later: the Cherokee payments raised educational attainment
        # and Baby's First Years found cash to poor mothers changed infant brain activity
        scar = np.clip(1 - ch_p["study_penalty_per_year"] * A["poverty_years"][cand], .2, 1.0)
        rate = e["enrolment_base"] * afford ** e["affordability_elasticity"] * scar \
            * self.education_return_index() ** e.get("return_elasticity", 0.0)
        take = cand[rng.random(len(cand)) < np.clip(rate, 0, .5)]
        A["studying"][take] = float(e["years"])
        A["study_years"][take] = 0
        A["student"][take] = True
        A["involuntary"][take] = False      # studying is a choice, not idleness
        self.new_students = int(len(take))
        self.study_changed = np.concatenate(course_events + [take])
        # What studying costs is handled in the choice model, not forced here: a course makes a full-time job much
        # harder to hold, and people weigh that like anything else. Overriding someone's status from outside is
        # something the calibration cannot absorb — it reads as a preference it never chose.

    def dwelling_price(self):
        """What an average dwelling costs this year, in current krónur."""
        m = self.p["markets"]
        return self.macro.PROPERTY_VALUE0 * 1e9 * m["residential_share"] / m["dwellings0"] * self.macro.house_price

    def step_home_purchase(self):
        """Renters who can buy, do. Until 2026-09-26 nobody ever bought a home: owners were those the population
        was drawn with, so each new cohort rented for life and home ownership under 35 fell to nothing by 2040 in
        the status quo — and the start-of-life fund, the only route to owning, looked like the only thing standing
        between the young and renting for ever.

        A household buys a first home when it has the deposit (`markets.first_home_deposit` of a smaller-than-average
        dwelling, 15% for first-time buyers under Seðlabanki's rules) and the payments fit within the central
        bank's debt-service limit for first-time buyers (`markets.first_home_dsti`, 40% of net income). Those who
        qualify buy at `markets.first_home_rate` a year — not everyone who could buy wants to. Couples decide
        together and hold the home half each, as the population was drawn."""
        A, m, rng = self.A, self.p["markets"], self.rng
        rate = m.get("first_home_rate", 0.0)
        if not rate:
            self.first_homes = 0
            return
        cand = np.flatnonzero(A["alive"] & A["renter"] & (A["age"] >= 22) & (A["age"] <= 60)
                              & (A["home_value"] <= 0))
        partner = A["partner"][cand]
        lead = cand[(partner < 0) | (cand < partner)]       # one decision per household
        if not len(lead):
            self.first_homes = 0
            return
        pa = A["partner"][lead]
        has = pa >= 0
        pidx = np.where(has, pa, 0)
        savings = np.maximum(A["wealth"][lead], 0) + np.where(has, np.maximum(A["wealth"][pidx], 0), 0)
        income = self.net_now[lead] + np.where(has, self.net_now[pidx], 0)
        # v10: a first home is bought in the size the household rents, at that size's price on the ladder
        if "hclass" in A:
            f_size = housing.factors(self)[np.maximum(A["hclass"][lead], 0)] * regions.factor(self, lead)
        else:
            f_size = np.ones(len(lead))
        price = self.dwelling_price() * f_size * m["first_home_price_share"] * np.where(has, 1.0, .75)
        deposit = m["first_home_deposit"] * price
        payment = (price - deposit) * m["mortgage_payment_rate"]
        able = (savings >= deposit) & (payment <= m["first_home_dsti"] * income)
        buy = able & (rng.random(len(lead)) < rate)
        b, bp, bh = lead[buy], pidx[buy], has[buy]
        share = np.where(bh, .5, 1.0)
        # the deposit comes out of savings, the lead's first
        from_lead = np.minimum(np.maximum(A["wealth"][b], 0), deposit[buy])
        A["wealth"][b] -= from_lead
        A["wealth"][bp[bh]] -= (deposit[buy] - from_lead)[bh]
        for who, part in ((b, np.ones(len(b), bool)), (bp, bh)):
            w = who[part]
            A["home_value"][w] = (price[buy] / (self.macro.house_price * f_size[buy]) * share)[part]
            A["mortgage_debt"][w] = ((price[buy] - deposit[buy]) * share)[part]
            A["renter"][w] = False
            A["mortgage"][w] = True
        self.first_homes = int(buy.sum())

    def step_tenure(self):
        """A year in the same job adds a year of tenure; anyone out of work starts again from zero."""
        A = self.A
        held = A["alive"] & np.isin(A["status"], [PART, FULL])
        A["tenure"] = np.where(held, A["tenure"] + 1, 0).astype(np.float32)

    def step_occupational_mobility(self):
        """Workers drift towards occupations whose pay has risen relative to their own, within education limits."""
        A, p, rng = self.A, self.p, self.rng
        self.occupation_moves = 0
        rate = p["labour"]["occupational_mobility"]
        if p["policy"]["regime"] == "platform" and p["policy"]["retraining_bn_per_year"]:
            rate *= 1 + p["policy"]["retraining_bn_per_year"] / 25.0   # EST: 25 bn doubles the rate of moves
        if rate <= 0:
            return
        # people move towards professions whose pay has risen relative to their own; the pay differences that
        # already compensate for hard or dirty work are in the data, so only changes drive moves
        lw = np.log(self.omega)
        gap = np.maximum(0, lw[None, :] - lw[:, None])
        min_edu = self.min_edu
        workers = np.flatnonzero(A["alive"] & np.isin(A["status"], [PART, FULL]) & (A["age"] < 60) & (A["venture"] < 0))
        if not len(workers):
            return
        o, e = A["occupation"][workers], A["education"][workers]
        G = gap[o] * (e[:, None] >= min_edu[None, :])
        strength = G.max(1)
        move = rng.random(len(workers)) < rate * np.minimum(1.0, strength * 4)
        if not move.any():
            return
        idx, G = workers[move], G[move]
        dest = (rng.random(len(idx))[:, None] > np.cumsum(G / G.sum(1, keepdims=True), 1)).sum(1)
        dest = np.minimum(dest, N_OCC - 1)
        # a profession cannot double overnight: entry is limited to a share of the people already in it
        size = np.bincount(A["occupation"][A["alive"]], minlength=N_OCC)
        allowed = np.maximum(p["labour"]["max_entry_share"] * size, 25)
        keep = np.ones(len(idx), bool)
        for d in np.unique(dest):
            k = np.flatnonzero(dest == d)
            if len(k) > allowed[d]:
                keep[rng.permutation(k)[int(allowed[d]):]] = False
        idx, dest = idx[keep], dest[keep]
        if not len(idx):
            return
        med = self.occ_median
        A["base_wage"][idx] *= med[dest] / med[A["occupation"][idx]]
        traits = np.array(P.trait(1))
        A["meaning"][idx] = np.clip(A["meaning"][idx] + traits[dest] - traits[A["occupation"][idx]], 0, 1)
        A["occupation"][idx] = dest
        A["public"][idx] = False
        A["tenure"][idx] = 0        # a move starts the clock again
        self.occupation_moves = len(idx)

    # ------------------------------------------------------------------ ventures
    def founder_leaves(self, idx):
        """Founder stops running the firm: young firms close, established ones carry on without them."""
        if not len(idx):
            return
        A, f = self.A, self.firms
        fid = A["venture"][idx]
        young = f["age"][fid] < 2
        f["alive"][fid[young]] = False
        f["founder"][fid[~young]] = -1
        A["venture"][idx] = -1

    def step_ventures(self, new_founders):
        A, p, f, rng = self.A, self.p, self.firms, self.rng
        v = p["ventures"]
        # existing firms
        alive = np.flatnonzero(f["alive"])
        if len(alive):
            surv = np.where(f["age"][alive] == 0, v["survival_year1"], v["survival_later"])
            dies = rng.random(len(alive)) > surv
            dead = alive[dies]
            f["alive"][dead] = False
            fd = f["founder"][dead]
            fd = fd[fd >= 0]
            A["venture"][fd] = -1
            A["status"][fd] = NONWORK
            A["involuntary"][fd] = True
            live = alive[~dies]
            f["age"][live] += 1
            # Growth slows as a firm nears the size its idea can carry. Grown by a fixed share every year for as long
            # as it survived, a firm of the best quality multiplied its staff by 1.7 a year; in thirty-five-year runs
            # a handful reached hundreds of thousands of jobs and then closed, and labour demand swung with them —
            # unemployment 3% one year and 20% the next (2026-09-29). The ceiling scales with quality: about 60 jobs
            # for an average firm, a few hundred for the best, where Iceland's successful start-ups of the last
            # twenty years sit. EST.
            q = f["quality"][live]
            room = np.clip(1 - f["jobs"][live] / (v.get("size_per_quality", 50.0) * q), 0, 1)
            f["jobs"][live] *= 1 + v["job_growth_survivors"] * q * room
            # A firm's profits persist from one year to the next. Redrawn from a heavy-tailed distribution every
            # year, the ventures' total swung by a fifth from year to year, and with it the economy-wide corporate
            # tax it is netted out of — enough to fail the inflation-neutrality check on noise alone (2026-09-26).
            draw = np.minimum((rng.pareto(v["profit_pareto_alpha"], len(live)) + 1) * v["profit_scale"]
                              * f["quality"][live], v["profit_cap"])
            keep = v.get("profit_persistence", .7)
            f["profit"][live] = keep * f["profit"][live] + (1 - keep) * draw
            self.exits = live[rng.random(len(live)) < v["exit_probability"]]
        else:
            self.exits = np.zeros(0, int)
        # new firms
        n = len(new_founders)
        if n:
            sel = (max(n, 1) / v["baseline_founders_per_year"]) ** (-v["entry_selection_elasticity"])
            q = rng.lognormal(-.125, .5, n) * min(sel, 1.5)
            q = q * (1 + v["education_quality_bonus"] * (A["education"][new_founders] == 2))
            start = len(f["alive"])
            for k, val in [("founder", new_founders), ("age", np.zeros(n)), ("alive", np.ones(n, bool)),
                           ("quality", q), ("jobs", v["jobs_at_birth"] * np.ones(n)),
                           ("profit", np.minimum((rng.pareto(v["profit_pareto_alpha"], n) + 1) * v["profit_scale"] * q * .3, v["profit_cap"]))]:
                f[k] = np.concatenate([f[k], val.astype(f[k].dtype)])
            A["venture"][new_founders] = np.arange(start, start + n)
            A["status"][new_founders] = VENTURE
        self.new_firms = n
        return n

    # ------------------------------------------------------------------ migration
    def step_emigration(self):
        A, p, rng = self.A, self.p, self.rng
        adults = np.flatnonzero(A["alive"] & (A["age"] >= 18))
        c = (A["citizenship"][adults] != IS).astype(int)
        base = self.emig_hazard[c, np.minimum(A["age"][adults], 110)] * self.recent_multiplier(adults) \
            * np.where(A["n_kids"][adults] > 0, self.family_mobility, 1.0)
        R = self.income_ratio(adults)
        beta = p["migration"]["emigration_income_elasticity"] * p["behaviour"]["mobility_scale"] * A["mobility"][adults]
        R0 = np.nan_to_num(self.R0[adults], nan=1.0)
        h = base * np.clip((R / np.where(np.isnan(self.R0[adults]), R, R0)) ** beta, .25, 4.0)
        # a year's identified or imposed shock to leaving (the backcast; a scenario's disaster), in every run alike
        h = h * float((p.get("history") or {}).get("emigration_scale", 1.0))
        leave = adults[rng.random(len(adults)) < h]
        partners = A["partner"][leave]
        partners = partners[(partners >= 0)]
        partners = partners[rng.random(len(partners)) < .8]
        movers = np.union1d(leave, partners)
        kids = np.flatnonzero(A["alive"] & (A["age"] < 18) & np.isin(A["mother"], movers))
        movers = np.union1d(movers, kids)
        pol = self.p["policy"]
        self.exit_tax_bn = 0.0
        if pol["regime"] == "platform" and pol["exit_tax_rate"]:
            above = np.maximum(A["wealth"][movers] - pol["exit_tax_threshold"], 0)
            tax = pol["exit_tax_rate"] * self.p["inheritance"]["unrealised_gain_share"] * above
            A["wealth"][movers] -= tax
            self.exit_tax_bn = float(tax.sum() / 1e9)
        self._remove(movers)
        young_skilled = movers[(A["age"][movers] >= 22) & (A["age"][movers] < 40) & (A["education"][movers] == 2)]
        return {"total": len(movers), "icelandic": int((A["citizenship"][movers] == IS).sum()),
                "foreign": int((A["citizenship"][movers] != IS).sum()),
                "young_graduates": int(len(young_skilled)),
                "children": int((A["age"][movers] < 18).sum())}

    def _remove(self, idx):
        A = self.A
        housing.write_off_leavers(self, idx)   # an estate has settled its claim already; emigrants' is written off
        A["alive"][idx] = False
        A["status"][idx] = NONWORK
        p_of = A["partner"][idx]
        A["partner"][p_of[p_of >= 0]] = -1
        A["partner"][idx] = -1
        # v9: whoever is left on their own — a widow or widower, an older person whose household is gone — finds a
        # new living arrangement; the gone hold none
        if "host" in A:
            left = np.r_[p_of[p_of >= 0], np.flatnonzero(np.isin(A["host"], idx))]
            A["host"][idx] = -1
            A["lives_alone"][idx] = False
            left = left[A["alive"][left]]
            if len(left):
                popmod.assign_living_arrangements(A, self.p, self.rng, only=np.unique(left))
        self.founder_leaves(idx[A["venture"][idx] >= 0])

    def step_immigration(self):
        A, p, rng = self.A, self.p, self.rng
        mig, polp = p["migration"], p["policy"]
        Y = self.arrival_income()
        ratio = Y / self.Y0
        mix = np.array(P.expand_mix(mig["immigrant_occupation_mix"], self.prof_weights))
        demand = float((mix * self.omega).sum() / self.price) ** mig["immigration_demand_elasticity"]
        m25 = self.base["migration_2025"]
        base_foreign = sum(m25["Foreign citizens"]["Immigration"].values())
        base_ice = sum(m25["Icelandic citizens"]["Immigration"].values())
        # Hagstofa's totals count everyone who moves. The draws here are adults arriving on their own account; a
        # share bring a partner and children follow (add_arriving_families), so the totals come out as recorded.
        per_draw = 1 + mig["arrival_partner_share"]
        base_foreign /= (1 + self.imm_children_per_adult[1]) * per_draw
        base_ice /= (1 + self.imm_children_per_adult[0]) * per_draw
        n_before = self.N
        eea_share = mig["eea_share_of_immigrants"]
        beta = mig["immigration_income_elasticity"]
        strict = polp["residence_rules_strictness"] if polp["regime"] == "platform" else 0.0
        nonworker_share = .25
        # Iceland's immigration follows jobs: EEA workers come when there are vacancies to fill. At 0 only pay
        # draws them, as before; the backcast tunes it.
        pull = max(getattr(self, "job_tightness", 1.0), .5) ** mig.get("immigration_tightness_elasticity", 0.0)
        demand = demand * pull
        n_eea_w = base_foreign * eea_share * (1 - nonworker_share) * ratio[0] ** beta * demand
        # arrivals for the jobs the economy added this year: the tourism boom's workers came for jobs, not pay
        now = getattr(self, "labour_demand_pc", None)
        prev = getattr(self, "labour_demand_pc_prev", now)
        if now is not None and prev is not None and mig.get("new_job_fill_share", 0.0):
            added = (now - prev) * self.working_age()          # jobs added beyond what a larger workforce brings
            n_eea_w += mig["new_job_fill_share"] * max(added, 0.0) / per_draw
        self.labour_demand_pc_prev = now
        # EEA arrivals who do not work get no borgaralaun until permanent residence, so it is no pull for them:
        # their income is what an arrival earns without it (ratio[1]), not with it
        n_eea_nw = base_foreign * eea_share * nonworker_share * (1 - .8 * strict) * ratio[1] ** beta
        n_non = base_foreign * (1 - eea_share) * ratio[1] ** beta * demand
        n_ice = base_ice * ratio[2] ** beta
        cap = polp.get("immigration_cap_multiple") if polp["regime"] == "platform" else None
        if cap is not None:  # "closed experiment": foreign inflow held at cap x 2025 level
            scale = min(1.0, cap * base_foreign / max(n_eea_w + n_eea_nw + n_non, 1))
            n_eea_w, n_eea_nw, n_non = n_eea_w * scale, n_eea_nw * scale, n_non * scale
        # A diagnostic: arrivals held at a given path (the status quo's), so a reform's other effects can be seen
        # without the change in who comes. The four streams keep their mix; only the total is set.
        fixed = getattr(self, "fixed_arrivals", None)
        if fixed is not None and self.year - 1 < len(fixed):
            per_person = (1 + mig["arrival_partner_share"]) * (1 + self.imm_children_per_adult[1])
            total = n_eea_w + n_eea_nw + n_non + n_ice
            k = fixed[self.year - 1] / per_person / max(total, 1e-9)
            n_eea_w, n_eea_nw, n_non, n_ice = n_eea_w * k, n_eea_nw * k, n_non * k, n_ice * k
        # Housing is Iceland's brake on arrivals: more people push rents up, and dearer rents deter the next
        # arrivals. Without it the pull terms — tuned on the status quo's small movements — compounded under a
        # large payment into a runaway: 64,000 arrivals a year by 2025 in the counterfactual past, against 18,800
        # (found 2026-09-26). Measured against the status quo's rents where there is a reference path, against the
        # base year where there is not. Elasticity EST ~1 (studies of housing costs and migration: 0.5-1).
        # against the base year in every run, as in demand() (v8): a reform's dearer rents then deter arrivals against
        # the status quo's by exactly the difference in rents
        rent_ref = 1.0
        housing = (self.macro.rent / max(rent_ref, .3)) ** (-mig.get("arrival_rent_elasticity", 0.0))
        # the backcast's identified arrival shock (refugees, the boom's recruitment), a multiplier on every stream
        k_hist = float((p.get("history") or {}).get("arrival_scale", 1.0)) * housing
        # A ceiling on how many can arrive in a year, as a share of the population: there are only so many
        # dwellings, school places and people abroad ready to move. The pull terms and the jobs arrivals create
        # feed each other, and with the housing brake saturated (rents are bounded) a run could compound — in a
        # thirty-five-year run with a fish-stock collapse under the reform, 600,000 arrivals a year by 2051, and
        # a tenth of the surface runs grew their population over 5% in a year (2026-09-28), where Iceland's record
        # since 1990 is about 3%. The ceiling is soft: a twentieth of a percent below it at today's arrivals,
        # about 8% at it, and it cannot be exceeded. EST 7% of the population a year, above any year on record.
        raw = np.array([n_eea_w, n_eea_nw, n_non, n_ice]) * k_hist
        persons = per_draw * ((raw[:3].sum()) * (1 + self.imm_children_per_adult[1])
                              + raw[3] * (1 + self.imm_children_per_adult[0]))
        ceiling = mig.get("max_arrival_rate", 0.0) * float(A["alive"].sum())
        if ceiling > 0:
            raw = raw * (1 + (persons / ceiling) ** 8) ** (-1 / 8)
        counts = rng.poisson(raw)
        donors_f = np.flatnonzero(A["alive"] & A["immigrant"] & (A["age"] >= 20) & (A["age"] <= 50))
        donors_i = np.flatnonzero(A["alive"] & ~A["immigrant"] & (A["age"] >= 20) & (A["age"] <= 50))
        pools = [(counts[0], EEA, FULL, 1), (counts[1], EEA, NONWORK, 1), (counts[2], NON_EEA, FULL, 1),
                 (counts[3], IS, None, 0)]
        for n, cit, status, c in pools:
            if n == 0:
                continue
            if cit == IS:
                donor = rng.choice(donors_i, n)
            else:  # pick donors to match the immigrant occupation mix, tilted towards occupations paying more
                # and towards where the posts are empty: labour migration to Iceland follows vacancies (the 2016-19
                # and 2022-24 waves filled construction, tourism and care); with pay alone, arrivals kept coming
                # into professions automation was emptying while the long view's vacancies went unfilled
                tilt = mix * (self.omega / self.price) ** mig["arrival_occupation_wage_response"] \
                    * self.shortage_pull()
                occ = rng.choice(N_OCC, n, p=tilt / tilt.sum())
                # donors grouped by profession once: filtering the pool for each arrival cost 3 s a year
                occ_f = A["occupation"][donors_f]
                occ_i = A["occupation"][donors_i]
                donor = np.empty(n, int)
                for o in np.unique(occ):
                    at = np.flatnonzero(occ == o)
                    # a profession can hold no immigrant of working age in a long run that empties it (a surface
                    # run crashed on this, 2026-10-12): copy a native in it, and failing that any immigrant
                    pool = donors_f[occ_f == o]
                    if len(pool) == 0:
                        pool = donors_i[occ_i == o]
                    if len(pool) == 0:
                        pool = donors_f
                    donor[at] = rng.choice(pool, len(at))
            new = self._clone(donor)
            regions.settle_arrivals(self, new)     # 2.0: in the record's shares, not the donors'
            ages = self.imm_age[c][18:67]
            A["age"][new] = rng.choice(np.arange(18, 67), n, p=ages / ages.sum())
            A["citizenship"][new] = cit
            A["immigrant"][new] = cit != IS
            A["years_in_iceland"][new] = 0 if cit != IS else A["age"][new]
            if status is not None:
                A["status"][new] = status
            A["renter"][new] = True
            A["mortgage"][new] = False
            # arrivals bring modest savings; non-working EEA arrivals must show resources (~EUR 30k)
            k = (self.p.get("base") or {}).get("krona_scale", 1.0)   # base-year krónur
            A["wealth"][new] = k * (3e6 if cit == IS else (4.4e6 if status == NONWORK else 1e6))
            if cit != IS:
                A["mobility"][new] = rng.lognormal(-.125, .5, n) * 1.8 * np.where(A["age"][new] < 35, 1.5, 1.0) \
                    / self.mobility_norm
        self.add_arriving_families()
        self.R0 = np.r_[self.R0, np.full(self.N - len(self.R0), np.nan)]
        # everyone who arrived, as Hagstofa counts it: the draws, and the partners and children with them
        return {"eea_workers": int(counts[0]), "eea_nonworkers": int(counts[1]), "non_eea": int(counts[2]),
                "returning_icelanders": int(counts[3]),
                "families": int(self.N - n_before - counts.sum())}, int(
                    (A["alive"][n_before:] & (A["age"][n_before:] < 18)).sum())

    def add_arriving_families(self):
        """Arrivals are not all single workers: some bring a partner, some a child. Without this the arriving
        cohort is far more employed than the population it joins, and the status quo drifts."""
        A, p, rng = self.A, self.p, self.rng
        mig = p["migration"]
        arrivals = np.flatnonzero((A["origin_year"] == self.year) & A["alive"] & (A["age"] >= 18) & (A["partner"] < 0))
        if not len(arrivals):
            return
        with_partner = arrivals[rng.random(len(arrivals)) < mig["arrival_partner_share"]]
        if len(with_partner):
            partners = self._clone(with_partner)
            A["sex"][partners] = 1 - A["sex"][with_partner]
            A["age"][partners] = np.clip(A["age"][with_partner] + rng.integers(-4, 5, len(partners)), 18, 66)
            A["partner"][with_partner], A["partner"][partners] = partners, with_partner
            A["status"][partners] = np.where(rng.random(len(partners)) < mig["arrival_partner_employment"], FULL, NONWORK)
            A["wealth"][partners] = 0.0
        # Children, at Hagstofa's rate per adult arrival and with its age profile, each with an arriving mother —
        # single or partnered. Before, only couples could bring a child, and too few children arrived.
        adults = np.flatnonzero((A["origin_year"] == self.year) & A["alive"] & (A["age"] >= 18))
        foreign = A["citizenship"][adults] != IS
        added = False
        for c in (0, 1):
            group = adults[foreign == bool(c)]
            women = group[(A["sex"][group] == 1) & (A["age"][group] >= 20) & (A["age"][group] <= 50)]
            n = int(rng.poisson(len(group) * self.imm_children_per_adult[c]))
            if not n or not len(women):
                continue
            mothers = rng.choice(women, n)
            kids = self._clone(mothers)
            profile = self.imm_age[c][:18]
            A["age"][kids] = np.minimum(rng.choice(18, n, p=profile / profile.sum()), A["age"][mothers] - 18)
            A["sex"][kids] = rng.integers(0, 2, n)
            A["mother"][kids] = mothers
            A["status"][kids] = NONWORK
            A["chooser"][kids] = False
            A["partner"][kids] = -1
            A["wealth"][kids] = 0.0
            added = True
        if added:
            popmod.recompute_birth_order(A)

    def _clone(self, donor):
        A = self.A
        n = len(donor)
        start = self.N
        for k in A:
            A[k] = np.concatenate([A[k], A[k][donor]])
        new = np.arange(start, start + n)
        A["partner"][new] = -1
        A["mother"][new] = -1
        A["venture"][new] = -1
        A["occ_pension"][new] = 0
        A["tenure"][new] = 0
        A["studying"][new] = 0
        A["seed_capital"][new] = 0.0
        A["study_years"][new] = 0
        A["poverty_years"][new] = 0
        A["contract_start"][new] = self.year
        A["contract_cpi"][new] = self.bargaining_cpi()
        A["contract_tot"][new] = self.macro.terms_of_trade()
        A["contract_ai"][new] = self.macro.productivity()
        A["alive"][new] = True
        A["involuntary"][new] = False
        A["underemployed"][new] = False
        A["worker0"][new] = False
        A["origin_year"][new] = self.year
        A["self_employed"][new] = False
        A["fund"][new] = 0.0
        if "hours_scale" in A:
            A["hours_scale"][new] = 1.0
        if "host" in A:
            A["host"][new] = -1
            A["lives_alone"][new] = False
        A["wealth"][new] = 0.0
        A["home_value"][new] = 0.0
        A["mortgage_debt"][new] = 0.0
        if "exp_gap" in A:
            A["exp_gap"][new] = 0.0          # 1.1: measured from arrival
        if "lien" in A:
            A["hclass"][new] = -1               # placed on the housing ladder next year (housing._place_new)
            A["equity_annuity"][new] = 0.0
            A["lien"][new] = 0.0
            A["widowed_at"][new] = -99
            if "home_lock" in A:
                A["home_lock"][new] = -99
        self.net_now = np.r_[self.net_now, np.zeros(n)]
        return new

    # ------------------------------------------------------------------ demography
    def _fertility_reference(self):
        """Usable child income per child, in 2025 prices, and the net income of people of child-bearing age."""
        A = self.A
        per_mother, _, _ = self.child_transfers()
        kids = np.flatnonzero(A["alive"] & (A["age"] < 18) & (A["mother"] >= 0))
        per_child = float(per_mother.sum() / max(len(kids), 1) / self.price)
        return per_child, float(self.net_now[A["alive"] & (A["age"] >= 25) & (A["age"] <= 45)].mean())

    def estate_values(self, idx):
        """What each person would leave, in 2025 krónur: savings and the equity in their home."""
        A = self.A
        return np.maximum(A["wealth"][idx], 0) + np.maximum(A["home_value"][idx] * housing.price_factor(self, idx)
                                                             - A["mortgage_debt"][idx], 0)

    def inheritance_rules(self):
        """(estate rate, tax-free amount, gift rate, exit tax rate), today's under the status quo."""
        inh, pol = self.p["inheritance"], self.p["policy"]
        if pol["regime"] == "platform":
            return (min(max(float(pol["inheritance_tax_rate"]), 0.0), .99), float(pol["inheritance_tax_floor"]),
                    float(pol["gift_tax_rate"]), float(pol["exit_tax_rate"]))
        return inh["rate_today"], inh["floor_today"], inh["rate_today"], 0.0

    def avoidance_routes(self):
        """How strongly taxable estates answer the rate, by route. Gifts avoid only the part of the rate they are
        not taxed at; moving wealth abroad only the part an exit tax does not catch; enforcement narrows the rest.
        Returns (gifts, abroad, other) elasticities."""
        inh, e = self.p["inheritance"], self.p["enforcement"]
        rate, _, gift, exit_ = self.inheritance_rules()
        gap = lambda other: float(np.clip((rate - other) / rate, 0, 1)) if rate > 0 else 0.0
        n = float(self.p["policy"]["tax_enforcement_fte"]) if self.p["policy"]["regime"] == "platform" else 0.0
        other = inh["avoidance_other"] * (1 - e["avoidance_cut_at_300"] * min(n / 300, 1.0))
        k = self.p["links"]["avoidance_scale"]
        return k * inh["avoidance_gifts"] * gap(gift), k * inh["avoidance_abroad"] * gap(exit_), k * other

    def home_exemption(self, idx=None):
        """1.1, as in Germany (§ 13 Abs. 1 Nr. 4c ErbStG): the home the deceased lived in passes free of tax to a
        child who lives in it for ten years, up to 200 m²; everything else is taxed. Returns the chance that an heir
        moves in — some do anyway, more the more tax it saves (inheritance.home_occupy_*) — and, for the people in
        idx, the equity it would exempt: all of it, but for the part of the largest homes above the size limit.
        Nothing under the status quo or with the rule off."""
        pol, inh, A = self.p["policy"], self.p["inheritance"], self.A
        n = 0 if idx is None else len(idx)
        if pol["regime"] != "platform" or not pol.get("inheritance_home_exempt", 0.0):
            return 0.0, np.zeros(n)
        rate = self.inheritance_rules()[0]
        p_occ = min(inh["home_occupy_max"], inh["home_occupy_base"]
                    + inh["home_occupy_response"] * rate * inh["valuation_share"])
        if idx is None:
            return p_occ, np.zeros(0)
        eq = np.maximum(A["home_value"][idx] * housing.price_factor(self, idx) - A["mortgage_debt"][idx], 0)
        if "hclass" in A:
            cls = A["hclass"][idx]
            share = np.asarray(inh["home_exempt_share_by_size"], float)
            eq = eq * np.where(cls >= 0, share[np.maximum(cls, 0)], 1.0)
        return p_occ, eq

    def estate_tax(self, estate, exempt=0.0):
        """Inheritance tax on estates passing to someone other than a spouse, in 2025 krónur, and what the
        heirs keep. Taxable estates shrink as the rate rises — gifts, moving abroad, trusts, spending it first —
        by an elasticity against the net-of-tax rate; what is avoided stays with the heirs, less any gift or exit
        tax on the route it took. `exempt` is taken off before the tax (1.1: a home an heir lives in)."""
        inh = self.p["inheritance"]
        rate, floor, gift, exit_ = self.inheritance_rules()
        eg, ea, eo = self.avoidance_routes()
        eps = eg + ea + eo
        shrink = ((1 - rate) / (1 - inh["rate_today"])) ** eps
        base = np.maximum((estate - exempt) * inh["valuation_share"] - floor, 0)
        avoided = base * (1 - shrink)
        side = (gift * eg + exit_ * ea) / eps * avoided if eps > 0 else 0.0   # taxed on the way round
        tax = rate * base * shrink + side
        return tax, estate - tax

    def expected_inheritance_tax(self):
        """This year's inheritance tax, in today's krónur and billions: every living person's chance of dying
        times the tax on what they would leave to someone other than a spouse, plus advance inheritance, taxed
        alike. An expectation rather than the year's actual deaths, so the budget line is not a lottery."""
        A = self.A
        alive = np.flatnonzero(A["alive"] & (A["partner"] < 0) & (A["age"] >= 18))
        if not len(alive) or not hasattr(self, "gompertz_a"):
            return 0.0
        better = (1 - self.p["demography"].get("mortality_improvement", 0.0)) ** self.year
        q = np.minimum(1, self.gompertz_a * better * np.exp(self.gompertz_b * A["age"][alive]))
        p_occ, eq = self.home_exemption(alive)
        tax, _ = self.estate_tax(self.estate_values(alive), p_occ * eq)
        # advance inheritance: taxed at the gift rate, on a base in today's proportion to estates
        rate, floor, gift, _ = self.inheritance_rules()
        base = np.maximum(self.estate_values(alive) * self.p["inheritance"]["valuation_share"] - floor, 0)
        advance = gift * (q * base).sum() * self.p["inheritance"]["advance_ratio"]
        return float(((q * tax).sum() + advance) * self.price / 1e9)

    def enforcement_yield(self, n):
        """What n more tax investigators recover a year, ma.kr. in 2025 krónur: each finds less than the one
        before, out of what enforcement can reach at all, after a training period."""
        e = self.p["enforcement"]
        pool = e["evasion_bn"] * e["recoverable_share"]
        ramp = min(1.0, self.year / max(e["ramp_years"], 1))
        return pool * (1 - np.exp(-n * e["yield_per_fte_m"] / 1000 / pool)) * ramp

    def pass_estates(self, dead):
        """An estate with no spouse to take it passes to the dead person's children if they are in the model,
        otherwise to adults of the next generation, net of inheritance tax. It used to vanish: savings and home
        equity of everyone who died alone left the economy."""
        A, rng = self.A, self.rng
        alone = dead[A["partner"][dead] < 0]
        alone = alone[A["age"][alone] >= 18]
        if not len(alone):
            return
        # v10: the state's claim on the home is repaid before the estate is taxed and passed on
        estate = housing.recover_from_estates(self, alone, self.estate_values(alone))
        # 1.1: where the home is exempt if an heir lives in it, some heirs move in (home_exemption)
        p_occ, eq = self.home_exemption(alone)
        moves_in = (rng.random(len(alone)) < p_occ) & (eq > 0) if p_occ > 0 else np.zeros(len(alone), bool)
        _, net = self.estate_tax(estate, np.where(moves_in, np.minimum(eq, np.maximum(estate, 0)), 0.0))
        adults = np.flatnonzero(A["alive"] & (A["age"] >= 25) & (A["age"] <= 70))
        adults = adults[~np.isin(adults, dead)]
        if not len(adults):
            return
        k = self.p["inheritance"]["heirs"]
        # each estate's children, and the next generation by age, indexed once: scanning every agent for each
        # estate cost 3 s a year
        grown = np.flatnonzero(np.isin(A["mother"], alone) & A["alive"] & (A["age"] >= 18))
        grown = grown[~np.isin(grown, dead)]
        grown = grown[np.argsort(A["mother"][grown], kind="stable")]
        mothers = A["mother"][grown]
        by_age = adults[np.argsort(A["age"][adults], kind="stable")]
        ages = A["age"][by_age]
        for person, amount, home in zip(alone, net, moves_in):
            if amount <= 0 and not home:
                continue
            lo, hi = np.searchsorted(mothers, person), np.searchsorted(mothers, person, side="right")
            kids = grown[lo:hi]
            if len(kids):
                heirs = kids[:k]
            else:
                # the next generation: about thirty years younger
                target = A["age"][person] - 30
                lo, hi = np.searchsorted(ages, target - 8), np.searchsorted(ages, target + 8, side="right")
                pool = by_age[lo:hi] if hi > lo else adults
                heirs = rng.choice(pool, min(k, len(pool)), replace=False)
            if home:
                amount = amount - self.heir_moves_in(person, heirs[0])
            A["wealth"][heirs] += amount / len(heirs)

    def heir_moves_in(self, person, heir):
        """1.1: an heir takes over the home of the deceased and must live in it for ten years
        (inheritance.home_lock_years), selling their own; returns the equity taken as the home, which the other heirs
        are paid out of the rest of the estate. The dwelling the heir leaves goes back on the market."""
        A = self.A
        if "home_lock" not in A:
            A["home_lock"] = np.full(len(A["alive"]), -99, np.int16)
        pf = housing.price_factor(self, np.array([person]))[0]
        equity = max(A["home_value"][person] * pf - A["mortgage_debt"][person], 0.0)
        mate = A["partner"][heir]
        house = [heir] + ([mate] if mate >= 0 else [])
        for w in house:
            if A["home_value"][w] > 0:
                A["wealth"][w] += max(A["home_value"][w] * housing.price_factor(self, np.array([w]))[0]
                                      - A["mortgage_debt"][w], 0.0)
                A["home_value"][w], A["mortgage_debt"][w], A["mortgage"][w] = 0.0, 0.0, False
            A["renter"][w] = False
            if "host" in A:
                A["host"][w] = -1
            if "lien" in A:
                A["lien"][w] = 0.0
        if "hclass" in A:
            housing._set_home(self, np.array([heir]), np.array([A["home_value"][person]]),
                              np.array([A["mortgage_debt"][person]]), np.array([A["hclass"][person]], np.int8))
        else:
            A["home_value"][heir], A["mortgage_debt"][heir] = A["home_value"][person], A["mortgage_debt"][person]
            A["mortgage"][heir] = A["mortgage_debt"][heir] > 0
        A["home_lock"][house] = self.year + self.p["inheritance"]["home_lock_years"]
        self.heirs_moved_in = getattr(self, "heirs_moved_in", 0) + 1
        return equity

    def birth_timing(self):
        """How many years earlier births come this year, and the extra births the move itself brings.

        Under the reform, a secure income lets people study and raise a small child at the same time, so births
        move earlier — `demography.birth_timing_shift` years at a 300 þús. payment, in proportion to the payment,
        reached over `birth_timing_years`. While the mean age is falling, births of two cohorts overlap: in
        Bongaarts and Feeney's (1998) terms, observed births run at 1/(1 - r) of the underlying rate, where r is
        the yearly change in mean age. That is a tempo effect and it ends when the shift does; any lasting change
        in how many children people have comes only through the income channel above it."""
        d, pol = self.p["demography"], self.p["policy"]
        if pol["regime"] != "platform" or not d["birth_timing_shift"]:
            return 0.0, 1.0
        full = d["birth_timing_shift"] * min(1.5, max(0.0, pol["ubi_adult"] / 300_000))
        years = max(d["birth_timing_years"], 1)
        now, before = full * min(1.0, self.year / years), full * min(1.0, max(self.year - 1, 0) / years)
        return now, 1.0 / max(1.0 - (now - before), .5)

    def birth_career_cost(self, mothers):
        """What a birth does to a mother's pay for good, measured against the cost at today's timing.

        A birth in the early career costs `birth_career_penalty` of the wage rate; one while studying or before 25
        costs `birth_before_career_share` of that. The status quo's average cost is already in the wage survey
        the population is drawn from, so what is applied is each birth's cost relative to that average: in the
        status quo the adjustments cancel, and only a change in *when* births come moves anyone's pay."""
        A, d = self.A, self.p["demography"]
        if not len(mothers) or not d["birth_career_penalty"]:
            return
        before = (A["studying"][mothers] > 0) | (A["age"][mothers] < 25)
        pen = d["birth_career_penalty"] * np.where(before, d["birth_before_career_share"], 1.0)
        ref = getattr(self, "birth_penalty0", None)
        if ref is None:
            # burn-in: learn today's average cost per birth, apply nothing
            self._birth_pen_seen = .8 * getattr(self, "_birth_pen_seen", float(pen.mean())) + .2 * float(pen.mean())
            return
        A["base_wage"][mothers] *= (1 - pen) / (1 - ref)

    def newborns_come_of_age(self, idx):
        """A child born in the run is made by copying its mother, so at 16 it still carries her profession,
        education and pay. Harmless within ten years; wrong beyond, where it makes pay perfectly hereditary. At 16
        such a child takes the profession, schooling and pay of a young person drawn at random from those the
        population was built with — which is how every child already in the population was drawn — and keeps a
        share of its mother's standing: intergenerational persistence of earnings in the Nordic countries is about
        0.2-0.3 (Bratsberg et al. 2007; Corak 2013), `childhood.earnings_persistence`."""
        A, rng = self.A, self.rng
        born = idx[(A["origin_year"][idx] > 0) & ~A["immigrant"][idx]]
        if not len(born):
            return
        donors = np.flatnonzero(A["alive"] & (A["origin_year"] == 0) & (A["age"] >= 16) & (A["age"] <= 19)
                                & ~A["immigrant"])
        if not len(donors):
            return
        # Young people choose a line of work where the posts are and the pay has risen: donors weighted by the pull
        # of their profession, which is 1 everywhere when nothing has changed, so the mix the population was built
        # with is kept. Copied from 2025's teenagers unweighted, every cohort to 2060 entered the professions in
        # 2025's proportions, however far automation or a shortage had moved the jobs.
        w = self.occupation_pull()[A["occupation"][donors]]
        pick = rng.choice(donors, len(born), p=w / w.sum())
        for k in ("occupation", "education", "public", "meaning", "creative", "export_loading"):
            if k in A:
                A[k][born] = A[k][pick]
        young = popmod.age_wage_factor(16) / popmod.age_wage_factor(A["age"][pick])
        wage = A["base_wage"][pick] * young
        mother = A["mother"][born]
        known = mother >= 0
        adults = A["alive"] & (A["age"] >= 25) & (A["age"] <= 60)
        med = float(np.median(A["base_wage"][adults])) if adults.any() else 1.0
        standing = np.ones(len(born))
        standing[known] = np.clip(A["base_wage"][mother[known]] / max(med, 1e-9), .25, 4.0)
        A["base_wage"][born] = wage * standing ** self.p["childhood"]["earnings_persistence"]

    def _start_contracts(self, took_job):
        """A new job means a new contract at today's rate."""
        A, rng = self.A, self.rng
        if not len(took_job):
            return
        A["contract_omega"][took_job] = self.omega_new[A["occupation"][took_job]]
        # the contract starts now: its raises, and what its renewal makes good, count from today
        A["contract_start"][took_job] = self.year
        A["contract_cpi"][took_job] = self.bargaining_cpi()
        A["contract_tot"][took_job] = self.macro.terms_of_trade()
        A["contract_ai"][took_job] = self.macro.productivity()
        offer = self.offer_years[A["occupation"][took_job]]
        j = np.nan_to_num(offer + rng.normal(0, 1.2, len(took_job)), nan=2.0)
        A["contract_end"][took_job] = (self.year + np.maximum(1, np.round(j))).astype(np.int16)

    def arrivals_choose(self):
        """Arrivals who come out of work weigh work in the year they arrive (1.1). Until then they waited for the
        next year's choice, and the year's arrivals were a stock out of work all year: 7-8% of foreign-born 20-34
        year olds idle on arrival alone, where the survey has the foreign-born at 8.5% neither working nor studying
        in all, against 5.2% for those born here (Eurostat edat_lfse_28, 2025). No new firms on arrival."""
        A = self.A
        new = np.flatnonzero(A["alive"] & (A["origin_year"] == self.year) & (A["age"] >= 16) & (A["age"] <= 74)
                             & (A["status"] == NONWORK) & ~A["disabled"])
        if not len(new):
            return
        per_mother, _, _ = self.child_transfers()
        P = self.probabilities(new, self.omega, self.price, per_mother, idea=np.zeros(len(new), bool))
        u = self.rng.random(len(new))
        choice = np.minimum((u[:, None] > np.cumsum(P, 1)).sum(1), 4).astype(np.int8)
        A["status"][new] = choice
        self._start_contracts(new[np.isin(choice, [PART, FULL])])

    def leave_school(self, idx):
        """Leaving upper-secondary school, at 20. The population gives everyone under 20 compulsory schooling only,
        and until 1.1 only a course of tertiary length moved anyone on, so the cohorts who were teenagers in the base
        year reached their twenties with compulsory schooling (85% of them, against 21% of 20-29 year olds as
        drawn), a teenager's profession and pay, and three times the others' chance of not working. Now, of those
        turning 20 with compulsory schooling and not studying, as many complete upper-secondary school as leave the
        cohort with the base year's share of 20-24 year olds on compulsory schooling (`compulsory_only_20_24`).
        They take the profession and pay of a young adult of that schooling, as children born in the run do at 16
        (newborns_come_of_age), keeping a share of their own standing (`childhood.earnings_persistence`)."""
        A, rng = self.A, self.rng
        target = getattr(self, "compulsory_only_20_24", None)
        low = idx[(A["education"][idx] == 0) & (A["studying"][idx] <= 0)]
        if target is None or not len(low):
            return
        share_low = len(low) / max(len(idx), 1)
        q = float(np.clip(1 - target / max(share_low, 1e-9), 0, 1))
        done = low[rng.random(len(low)) < q]
        donors = np.flatnonzero(A["alive"] & ~A["immigrant"] & (A["age"] >= 21) & (A["age"] <= 29)
                                & (A["education"] == 1) & (A["studying"] <= 0))
        if not len(done) or not len(donors):
            return
        w = self.occupation_pull()[A["occupation"][donors]]
        pick = rng.choice(donors, len(done), p=w / w.sum())
        teen = A["alive"] & (A["age"] >= 16) & (A["age"] <= 20) & (A["education"] == 0)
        med = float(np.median(A["base_wage"][teen])) if teen.any() else 1.0
        standing = np.clip(A["base_wage"][done] / max(med, 1e-9), .25, 4.0)
        wage = A["base_wage"][pick] * popmod.age_wage_factor(20) / popmod.age_wage_factor(A["age"][pick])
        moved = done[A["occupation"][pick] != A["occupation"][done]]
        A["base_wage"][done] = wage * standing ** self.p["childhood"]["earnings_persistence"]
        for k in ("occupation", "public", "export_loading"):
            if k in A:
                A[k][done] = A[k][pick]
        A["education"][done] = 1
        A["tenure"][moved] = 0
        A["contract_end"][moved] = self.year   # a new line of work is a new contract, taken when they choose at 20

    def step_partnerships(self):
        """New couples. Partnerships used to end only — by a death, by emigration — and none ever began: arrivals came
        single, the young never paired, and the share of adults living as a couple fell from 48% to 23% in the status
        quo by 2060, which tripled single-person households and with them the demand for small homes (found
        2026-10-14, building the housing ladder). Each year singles pair up within five-year age bands (a man up to
        one band older), closing `couple_catch_up` of each band's shortfall from the share it had at the start. A
        couple sets up one home: if both own, the second home is sold into savings; they take their place on the
        housing ladder the next year (housing._place_new)."""
        A, rng = self.A, self.rng
        d = self.p["demography"]
        adults = A["alive"] & (A["age"] >= 20) & (A["age"] < 80)
        bins = np.minimum(A["age"] // 5, 15)
        if not hasattr(self, "couple_share0"):
            self.couple_share0 = {int(b): float(np.mean(A["partner"][adults & (bins == b)] >= 0))
                                  for b in np.unique(bins[adults])}
        single = adults & (A["partner"] < 0)
        made = 0
        for b, target in self.couple_share0.items():
            here = adults & (bins == b)
            short = target * here.sum() - (A["partner"][here] >= 0).sum()
            n = int(d.get("couple_catch_up", .3) * max(short, 0) / 2)
            if n <= 0:
                continue
            women = np.flatnonzero(single & here & (A["sex"] == 1) & (A["partner"] < 0))
            men = np.flatnonzero(single & (A["sex"] == 0) & (A["partner"] < 0) & (bins >= b) & (bins <= b + 1))
            k = min(n, len(women), len(men))
            if k <= 0:
                continue
            w, m = rng.choice(women, k, replace=False), rng.choice(men, k, replace=False)
            A["partner"][w], A["partner"][m] = m, w
            single[w] = single[m] = False
            made += k
            # one home: if both own, the man's is sold and its equity goes to savings; if one owns, both live in it
            both = (A["home_value"][w] > 0) & (A["home_value"][m] > 0)
            sold = m[both]
            if len(sold):
                A["wealth"][sold] += np.maximum(A["home_value"][sold] * housing.price_factor(self, sold)
                                                - A["mortgage_debt"][sold], 0)
                A["home_value"][sold] = 0.0
                A["mortgage_debt"][sold] = 0.0
                A["mortgage"][sold] = False
            owns = (A["home_value"][w] > 0) | (A["home_value"][m] > 0)
            A["renter"][w] = A["renter"][m] = ~owns
            if "host" in A:
                A["host"][w] = A["host"][m] = -1
                A["lives_alone"][w] = A["lives_alone"][m] = False
            if "hclass" in A:
                A["hclass"][w] = A["hclass"][m] = -1
            if "n_kids" in A:
                A["n_kids"][m] = A["n_kids"][m] + A["n_kids"][w]
        self.couples_formed = made

    def step_demography(self):
        A, p, rng = self.A, self.p, self.rng
        d = p["demography"]
        alive = np.flatnonzero(A["alive"])
        # Death rates keep falling, as they have for a century: held at the base year's, the thirty-year view had
        # life expectancy frozen at 2025's and the over-67s levelling off at 67 thousand by 2040, where Hagstofa's
        # projection has them still rising. EST 1.2% a year, about a year of life expectancy a decade.
        better = (1 - d.get("mortality_improvement", 0.0)) ** self.year
        q = np.minimum(1, self.gompertz_a * better * np.exp(self.gompertz_b * A["age"][alive]))
        dead = alive[rng.random(len(alive)) < q]
        orphans = np.flatnonzero(np.isin(A["mother"], dead))
        A["mother"][orphans] = -1
        heirs = A["partner"][dead]
        has = heirs >= 0
        np.add.at(A["wealth"], heirs[has], A["wealth"][dead[has]])
        np.add.at(A["home_value"], heirs[has], A["home_value"][dead[has]])
        np.add.at(A["mortgage_debt"], heirs[has], A["mortgage_debt"][dead[has]])
        housing.settle_estates(self, dead)
        self.pass_estates(dead)
        self._remove(dead)
        # births respond to the change in usable child income relative to household income — change against
        # the status quo, which is why the reference is taken at calibration and not in a scenario's first year
        # Burn-in runs before the reference exists, and runs the status quo, so there is no change to respond to.
        # A scenario cannot start without the reference: scenario() refuses one that lacks it.
        if getattr(self, "per_child0", None) is None:
            rel = 0.0
        else:
            per_child, _ = self._fertility_reference()
            rel = (per_child - self.per_child0) / self.hh_income0
        shift, tempo = self.birth_timing()
        n_births = rng.poisson(d["births_per_year"] * max(.2, 1 + d["fertility_income_elasticity"] * rel) * tempo)
        women = np.flatnonzero(A["alive"] & (A["sex"] == 1) & (A["age"] >= 18) & (A["age"] <= 44))
        w = np.exp(-((A["age"][women] - (d["birth_age_mean"] - shift)) / 6) ** 2)
        mothers = rng.choice(women, n_births, p=w / w.sum())
        self.mean_birth_age = float(A["age"][mothers].mean()) if len(mothers) else float("nan")
        new = self._clone(mothers)
        self.birth_career_cost(mothers)      # after the child is made, so the cost stays the mother's own
        A["age"][new] = -1  # becomes 0 after ageing below
        A["mother"][new] = mothers
        A["immigrant"][new] = False
        A["status"][new] = NONWORK
        A["chooser"][new] = False
        A["disabled"][new] = False
        A["student"][new] = False
        A["retired"][new] = False
        A["character"][new] = -1
        A["sex"][new] = rng.integers(0, 2, len(new))
        # ageing
        A["age"][A["alive"]] += 1
        A["years_in_iceland"][A["alive"]] += 1
        A["retired"] = A["age"] >= 67
        new_pensioners = np.flatnonzero(A["alive"] & (A["age"] == 67))
        A["occ_pension"][new_pensioners] = popmod.occupational_pension(A, new_pensioners, p, rng)
        A["occ_pension"][new_pensioners] *= pensions.new_pension_factor(self)   # 2.0: rights cut or raised so far
        # v9: where the funds keep paying earned pensions but take no more contributions, those retiring now earned
        # only the years before the reform (a career from 25 to 67)
        pol_ = p["policy"]
        if pol_["regime"] == "platform" and pol_.get("pension_keep_earned", 0.0) and pol_.get("pension_fold", 0.0):
            earned = np.clip((42 - self.year) / 42, 0, 1)
            A["occ_pension"][new_pensioners] *= 1 - pol_["pension_fold"] * (1 - earned)
        if "host" in A:   # turning 67 on one's own: living alone or with family, as those 67+ do (v9)
            popmod.assign_living_arrangements(A, p, rng, only=new_pensioners)
            popmod.update_young(A, p, rng, housing.leave_home_multiplier(self))
        # pay grows (and eases) with age, as the wage survey's age profile says: applied as people cross into the
        # next band, after the new pensioners' pensions are set on their working pay
        grown = np.flatnonzero(A["alive"] & (A["age"] > 0))
        A["base_wage"][grown] *= popmod.age_wage_factor(A["age"][grown]) / popmod.age_wage_factor(A["age"][grown] - 1)
        turned16 = A["alive"] & (A["age"] == 16) & ~A["chooser"]
        self.newborns_come_of_age(np.flatnonzero(turned16))
        self.leave_school(np.flatnonzero(A["alive"] & (A["age"] == 20) & ~A["immigrant"]))
        if turned16.any():
            ch_p = self.p["childhood"]
            years = np.minimum(A["poverty_years"][turned16], ch_p["max_years"])
            A["base_wage"][turned16] *= np.clip(1 - ch_p["wage_penalty_per_year"] * years, .5, 1.0)
        A["chooser"] = (A["age"] >= 16) & (A["age"] <= 74)
        old = A["alive"] & (A["age"] > 74)
        self.founder_leaves(np.flatnonzero(old & (A["venture"] >= 0)))
        A["status"][old] = NONWORK
        A["student"] &= A["age"] <= 24
        popmod.recompute_birth_order(A)
        self.R0 = np.r_[self.R0, np.full(self.N - len(self.R0), np.nan)]
        return len(new), len(dead)

    # ------------------------------------------------------------------ household savings and wealth
    def housing_equity(self):
        A = self.A
        return np.maximum(A["home_value"] * housing.price_factor(self, np.arange(len(A["home_value"])))
                          - A["mortgage_debt"], 0)

    def household_consumption(self, idx, net, per_mother, guaranteed=None):
        """Monthly household consumption (ISK): income-rank MPC plus consumption out of liquid and housing wealth.
        Stores per-agent income and consumption for the wealth update."""
        A, w = self.A, self.p["wealth"]
        income = net + per_mother[idx]           # net is already after property and wealth tax
        # v9: capital income is in net income now (policy.net_income), as the return on savings. It is kept out of
        # the saving that builds wealth — wealth already earns its return (update_wealth), and saving a yield tied to
        # wealth compounds it at that yield, far above any real return for the wealthiest — and out of the income
        # the consumption ratio is calibrated on; a share of it is spent (wealth.mpc_capital_income).
        ci = pol_rules.capital_income(A, idx, self.p, self.price)
        if ci is not None:
            ben = self.p["benefits"]
            ci_net = ci - ben["capital_income_tax"] * np.maximum(0.0, ci - ben["capital_income_allowance_year"] / 12 * self.price)
        else:
            ci_net = np.zeros(len(idx))
        income = income - ci_net
        rank = np.argsort(np.argsort(income)) / max(1, len(income) - 1)
        mpc = w["mpc_bottom"] + (w["mpc_top"] - w["mpc_bottom"]) * rank
        mpc = mpc * self.security_factor(idx, income, guaranteed)
        liquid = A["wealth"][idx]
        # higher real interest rates make households save more (the channel monetary policy works through)
        mk, m = self.macro, self.p["markets"]
        s0 = 1 - m["mortgage_indexed_share0"]
        transmission = 1 + m["indexation_transmission_gain"] * (mk.nonindexed_share() - s0) / (1 - s0)
        rate_effect = float(np.clip(1 - w["consumption_rate_sensitivity"] * transmission * (mk.r - m["real_rate0"]),
                                    .75, 1.15))
        income_part = mpc * np.maximum(income, 0)
        # wealth is held in 2025 krónur and income is in today's
        wealth_part = (w["mpc_liquid_wealth"] * np.maximum(liquid, 0)
                       + w["mpc_housing_wealth"] * self.housing_equity()[idx]) / 12 * self.price
        wealth_part = wealth_part + w.get("mpc_capital_income", 0.0) * np.maximum(ci_net, 0)
        cons = rate_effect * (self.mpc_scale * income_part + wealth_part)
        self._cons_parts = (float(income_part.sum()), float(wealth_part.sum()), float(np.maximum(income, 0).sum()))
        if guaranteed is not None:
            self.guaranteed_share_now = float(np.mean(np.clip(np.asarray(guaranteed)
                                                              / np.maximum(income, 1.0), 0, 1)))
        # borrowing limit: households cannot run liquid wealth below a few months of income
        floor = -w["borrowing_limit_months"] * np.maximum(income, 0)
        cons = np.minimum(cons, np.maximum(income, 0) + np.maximum(liquid * self.price - floor, 0) / 12)
        # what the wealth update sees: income and spending without the capital-income flow and its share spent
        cap_cons = np.minimum(rate_effect * self.p["wealth"].get("mpc_capital_income", 0.0) * np.maximum(ci_net, 0), cons)
        self._household = (idx, income, cons - cap_cons)
        return cons.sum()

    def security_factor(self, idx, income, guaranteed):
        """How much more of their income people spend once it stops being uncertain.

        Buffer-stock saving is saving against a bad year. The size of the buffer follows the risk, not the level
        of income (Carroll 1997; Carroll and Samwick 1998 put precautionary wealth at roughly a tenth to a fifth
        of household wealth), so an income that cannot fall away should be spent more freely than the same income
        that can. This is a claim made for a basic income that the model otherwise had no way to express: the
        MPC here varied by how much a household had and never by how safe it was.

        The measure is the share of a household's income that is guaranteed — the borgaralaun, or the benefits
        that play that part today — against the share guaranteed in the base year. `wealth.security_mpc_gain` is
        what a move from nothing guaranteed to everything guaranteed is worth, and at 0 the channel is off.

        EST, and a lever, because the size is not settled: the direction is well evidenced, the magnitude for a
        permanent floor is not.
        """
        w = self.p["wealth"]
        gain = w["security_mpc_gain"]
        if not gain or guaranteed is None:
            return 1.0
        share = np.clip(np.asarray(guaranteed) / np.maximum(income, 1.0), 0, 1)
        base = getattr(self, "guaranteed_share0", None)
        if base is None:
            return 1.0
        return np.clip(1 + gain * (share - base), .9, 1 + gain)

    def venture_equity_return(self, profits, exits, f):
        """What the state's stake in new firms earns.

        The stake is not a seed-money scheme and it does not pay into the start-of-life fund. Two separate things are going on. People start firms at 25 with
        *their own* fund money, which is theirs to use as they like.
        And the state holds a share of what is built, because it underwrites everyone's living through the
        borgaralaun, health care and schooling — so tax and a shareholding are the public's return on what it
        puts into its people, not a subsidy handed to founders. The return is ordinary revenue."""
        v = self.p["ventures"]
        return (self.venture_stake(v["external_share_typical"]) * v["dividend_payout"] * profits
                + self.venture_stake(v["external_share_at_exit"], at_exit=True) * v["exit_multiple"]
                * f["profit"][exits].clip(0).sum()) / 1e9

    def update_wealth(self):
        A, w = self.A, self.p["wealth"]
        if not hasattr(self, "_household"):
            return
        idx, income, cons = self._household
        A["wealth"][idx] = A["wealth"][idx] * (1 + self.wealth_returns(A["wealth"][idx])) \
            + 12 * (income - cons) / max(self.price, .1)
        # Amortisation only. Inflation does wear down non-indexed debt faster, but the higher payments that do it
        # are not taken out of what households spend, so eroding the debt here built equity out of nothing — and
        # through the housing-wealth effect raised prices with the inflation rate. The reform acts through
        # payments (Macro.mortgage_payment_factor) and through how spending answers interest rates.
        A["mortgage_debt"] *= .97

    def wealth_returns(self, wealth):
        """2.0: the real return on savings and other assets, rising with one's rank in them.

        In Norway's tax records the return on financial wealth rises 1.6 points from the 10th to the 90th
        percentile, and on net worth far more at the top, where private business dominates: a krone at the 75th
        percentile grew to 1.5 over 2005-15, one in the top 0.1% to 2.4 — about 3.8% and 8.3% a year (Fagereng,
        Guiso, Malacrino and Pistaferri 2020, Econometrica; Bach, Calvet and Sodini 2020, AER, find the same in
        Sweden). The extra return by rank is set from that, and the whole is shifted so that the return on all
        savings together stays `liquid_return`: the gradient moves wealth between families, not into the economy.
        Debts pay the base rate."""
        w = self.p["wealth"]
        base = w["liquid_return"]
        g = w.get("return_gradient")
        scale = w.get("return_gradient_scale", 1.0)
        pos = wealth > 0
        if not g or not scale or pos.sum() < 2:
            return np.full(len(wealth), base)
        rank = np.zeros(len(wealth))
        order = np.argsort(wealth[pos], kind="stable")
        rank[np.flatnonzero(pos)[order]] = (np.arange(pos.sum()) + .5) / pos.sum() * 100
        extra = scale * np.interp(rank, g["percentile"], g["extra"])
        mean = float((extra[pos] * wealth[pos]).sum() / wealth[pos].sum())
        return np.where(pos, base + extra - mean, base)

    def wealth_snapshot(self):
        A = self.A
        adults = A["alive"] & (A["age"] >= 20)
        liquid = A["wealth"][adults]
        net = liquid + self.housing_equity()[adults]
        income = np.maximum(self.net_now[adults], 1)
        s = np.sort(net)
        n = len(s)
        gini = float((2 * np.arange(1, n + 1) - n - 1).dot(s) / (n * s.sum())) if n and s.sum() > 0 else 0.0
        return {"wealth_median_liquid": float(np.median(liquid)), "wealth_gini": gini,
                "wealth_low_buffer_share": float((liquid * self.price < 3 * income).mean())}

    def extra_policy_accounts(self):
        """The newer levers that cost or raise money, plus the services whose cost the model now drives.

        Health, schooling and public order are always present — they are what the state spends money on whatever
        regime it is in, and the model moves them. Only the reform's own levers switch off outside it.
        """
        A, p = self.A, self.p
        pol = p["policy"]
        platform = pol["regime"] == "platform"
        # present in both regimes: the services the model drives
        out = {
            "education_cost": float((A["alive"] & (A["studying"] > 0)).sum() * p["education"]["cost_per_student_bn"]),
            "health_cost": float(self.health_cost()),
            "crime_cost": float(self.crime_snapshot()["crime_cost_bn"]),
            "schooling_cost": float(self.schooling_cost()),
        }
        if not platform:
            out.update({"wealth_tax": 0.0, "retraining_cost": 0.0, "childcare_cost": 0.0,
                        "public_housing_cost": 0.0, "sick_pay_saved": 0.0, "leave_saved": 0.0})
            return out
        net_worth = A["wealth"] + self.housing_equity()
        taxable = np.maximum(net_worth[A["alive"] & (A["age"] >= 18)] - pol["net_wealth_tax_threshold"], 0)
        out.update({
            "wealth_tax": float(pol["net_wealth_tax_pct"] / 100 * taxable.sum() / 1e9 * self.wealth_tax_shrink()),
            "retraining_cost": float(pol["retraining_bn_per_year"]),
            "childcare_cost": float(self.childcare_places_built() * p["childcare"]["cost_per_place_bn"]),
            "public_housing_cost": float(pol["public_dwellings_per_year"] * pol["public_dwelling_cost_m_isk"] / 1000),
            # the public wage bill of the year being built, which on the first pass does not exist yet
            "sick_pay_saved": float(pol["public_sick_pay_cut"] * pol["sick_absence_rate"]
                                    * getattr(self, "accounts_cache", {}).get("public_payroll", 0.0)),
            # the state's own sick pay and the parental leave fund, once employers and insurers carry them
            "leave_saved": float(getattr(self, "leave_now", {}).get("state_saved_bn", 0.0)),
        })
        return out

    def pay_machine_dividends(self, a):
        """1.1: what machines earn after tax and any levy, less the state's share, reaches households as their owners:
        the domestic share of it (automation.domestic_ownership), paid out as dividends, in proportion to financial
        wealth, as other capital income is. Until 1.1 it went nowhere. Today's krónur, ma.kr."""
        A, au = self.A, self.p["automation"]
        platform = self.p["policy"]["regime"] == "platform"
        rate = self.p["policy"]["corporate_tax_rate"] if platform else .20
        levy = au["levy_rate"] if platform else 0.0
        stake = au["state_capital_share"] if platform else 0.0
        after = max(a["machine_income"] * (1 - rate - levy), 0.0) * (1 - stake)
        paid = after * au.get("domestic_ownership", 0.0) * au["dividend_payout"]
        holders = np.flatnonzero(A["alive"] & (A["wealth"] > 0))
        if paid <= 0 or not len(holders):
            return 0.0
        w = A["wealth"][holders]
        A["wealth"][holders] += w / w.sum() * paid * 1e9 / self.price     # wealth is held in 2025 krónur
        return float(paid)

    def corporate_profits(self):
        """Taxable profits of the corporate sector beyond the model's own ventures (bn, 2025 krónur): 740 in 2025
        (148 bn of tax at 20%, THJ05132), growing with output and squeezed when wage costs outrun prices."""
        p, mk = self.p, self.macro
        base = 148.0 / .20
        venture_profits = self.firms["profit"][self.firms["alive"]].clip(0).sum() / 1e9
        return max(0.0, base * self.profit_index() - venture_profits)

    def profit_index(self):
        """The corporate sector's profits against the base year's: output, and the margin prices leave over wage
        costs."""
        p, mk = self.p, self.macro
        ulc = mk.relative_wage_cost(self.wage_cost_index(self.omega)) / mk.productivity()
        margin = float(np.clip((mk.P_N / max(ulc, .2)) ** p["markets"]["profit_margin_elasticity"], .2, 2.0))
        # 1.1: on the output of people's work; machines' earnings are taxed apart (automation.fiscal)
        return margin * getattr(mk, "output_labour", mk.output)

    def corporate_tax_economy(self):
        """Economy-wide corporate income tax. Under the reform, firms the state holds a deemed stake in pay the
        share of it the reform chooses (`staked_corporate_tax_share`)."""
        p = self.p
        platform = p["policy"]["regime"] == "platform"
        rate = p["policy"]["corporate_tax_rate"] if platform else .20
        covered = getattr(self, "public_equity", {}).get("coverage", 0.0) if platform else 0.0
        kept = p["policy"].get("staked_corporate_tax_share", 1.0)
        return rate * self.corporate_profits() * (1 - covered * (1 - kept))

    def step_public_equity(self):
        """The state's deemed stake in every company that raises capital (params "public_equity").

        Each round issues the state shares worth one deemed start-of-life fund. The state's share S of the corporate
        sector grows as rounds dilute the other owners; `coverage` is the share of profits earned by firms that have
        raised capital since the reform began, and so carry a stake. Firms answer by raising less equity — fewer
        rounds, in proportion to what a round gives away — and the investment that goes with it falls a little,
        which costs output per worker over a decade."""
        p = self.p
        pe = p.get("public_equity") or P.DEFAULTS["public_equity"]
        st = getattr(self, "public_equity", None)
        if st is None:
            st = self.public_equity = {"share": 0.0, "coverage": 0.0, "drag": 0.0, "rounds": 0.0, "dividends": 0.0}
        if p["policy"]["regime"] != "platform" or not pe["enabled"] or not p["policy"]["venture_support"]:
            st["dividends"] = 0.0
            return
        fund = self.deemed_fund() / 1e9
        size = pe["round_size"] / 1e9
        given = fund / max(fund + size, 1e-9)               # what one round gives the state
        rounds = pe["rounds_per_year"] * (1 - given) ** pe["avoidance_elasticity"]
        new = rounds * fund
        value = pe["equity_value_bn"] * self.macro.output
        st["share"] += (1 - st["share"]) * new / max(value + new, 1e-9)
        st["coverage"] += (1 - st["coverage"]) * pe["raising_share"] * rounds / max(pe["rounds_per_year"], 1)
        target = pe["productivity_cost"] * new / max(new + rounds * size, 1e-9)
        st["drag"] += (target - st["drag"]) / max(pe["cost_years"], 1)
        st["rounds"] = rounds
        self.macro.equity_drag = st["drag"]
        rate = p["policy"]["corporate_tax_rate"]
        kept = p["policy"].get("staked_corporate_tax_share", 1.0)
        after_tax = self.corporate_profits() * (1 - rate * (1 - st["coverage"] * (1 - kept)))
        st["dividends"] = st["share"] * pe["payout"] * after_tax

    def profession_snapshot(self):
        """Numbers and pay by profession: who grows, who shrinks, who gets a raise."""
        A = self.A
        ch = A["alive"] & A["chooser"]
        work = ch & np.isin(A["status"], [PART, FULL, VENTURE])
        hours = self.hours_of(A["status"], slice(None)) + (A["status"] == VENTURE)
        out = {}
        for i, name in enumerate(OCCUPATIONS):
            m = work & (A["occupation"] == i)
            key = name.replace(" ", "_")
            out[f"prof_n_{key}"] = int(m.sum())
            out[f"prof_fte_{key}"] = float((hours * m).sum())
            out[f"prof_pay_{key}"] = float(self.omega[i] / self.price)   # real wage index for this profession
            out[f"prof_earn_{key}"] = float(np.median(A["base_wage"][m]) * self.omega[i]) if m.any() else np.nan
            out[f"prof_part_{key}"] = float((A["status"][m] == PART).mean()) if m.any() else np.nan
            out[f"prof_contract_{key}"] = float(np.mean(np.maximum(A["contract_end"][m] - self.year, 0))) if m.any() else np.nan
        return out

    def family_snapshot(self):
        """Time with children, and the demand for kindergarten places that follows from it."""
        A, p = self.A, self.p
        alive = A["alive"]
        kids_small = np.flatnonzero(alive & (A["age"] >= 1) & (A["age"] <= 5) & (A["mother"] >= 0))
        mothers = A["mother"][kids_small]
        partners = A["partner"][mothers]
        hours = self.hours_of(A["status"]) + (A["status"] == VENTURE)
        mother_h = hours[mothers]
        partner_h = np.where(partners >= 0, hours[np.where(partners >= 0, partners, 0)], 0.0)
        working_parent = (mother_h > 0) | (partner_h > 0)
        full_day = (mother_h >= .9) | ((partners >= 0) & (partner_h >= .9) & (mother_h >= .55))
        ages = A["age"][kids_small]
        teens = np.flatnonzero(alive & (A["age"] >= 16) & (A["age"] < 18))
        away = pol_rules.moved_out(A, teens, p)
        return {"teens_moved_out": int(away.sum()),
                # what a teenager living alone has a month, in 2025 krónur: the whole payment
                "teen_moved_out_income": float(p["policy"]["ubi_child"] / max(self.price, .1)) if away.any() else 0.0,
                "children_1_5": int(len(kids_small)),
                "kindergarten_demand": int(working_parent.sum()),
                "kindergarten_full_day_demand": int(full_day.sum()),
                "kindergarten_demand_under_2": int((working_parent & (ages <= 2)).sum()),
                "kindergarten_gap": int(working_parent.sum() - p["childcare"]["places_full_time"]),
                
                "parent_hours_index": float(np.mean(hours[np.unique(mothers)])) if len(mothers) else np.nan,
                "parents_not_working_share": float(np.mean(hours[np.unique(mothers)] == 0)) if len(mothers) else np.nan}

    def childcare_places_built(self):
        """Places the state pays for: what the lever asks for, or what parents actually want, whichever is less.

        The lever used to add its places whether or not there were children to fill them, so a generous setting
        bought empty rooms and charged the budget for them every year. `needed` is set each
        year by apply_childcare_constraint from the parents who want a place and cannot get one."""
        p = self.p
        if p["policy"]["regime"] != "platform":
            return 0.0
        return min(float(p["policy"]["childcare_places_added"]), float(getattr(self, "childcare_needed", 1e9)))

    def enforce_disability_limits(self):
        """No one on a disability pension holds a full-time job (v9): wherever a status is set — a firm reseeded,
        a health shock, a contract — full-time becomes part-time for them."""
        A = self.A
        full = np.flatnonzero(A["alive"] & A["disabled"] & (A["status"] == FULL))
        if len(full):
            A["status"][full] = PART

    def apply_childcare_constraint(self):
        """Parents of small children who cannot get a place cannot hold a full-time job."""
        A, p, rng = self.A, self.p, self.rng
        places = p["childcare"]["places_full_time"] + p["childcare"]["childminder_places"] \
            + (p["policy"]["childcare_places_added"] if p["policy"]["regime"] == "platform" else 0)
        kids = np.flatnonzero(A["alive"] & (A["age"] >= 1) & (A["age"] <= 5) & (A["mother"] >= 0))
        if not len(kids):
            self.childcare_shortfall = 0
            return
        mothers = A["mother"][kids]
        wanting = np.unique(mothers[np.isin(A["status"][mothers], [PART, FULL, VENTURE])])
        # places wanted beyond what exists without the lever: what the lever can usefully pay for
        base = p["childcare"]["places_full_time"] + p["childcare"]["childminder_places"]
        self.childcare_needed = max(0, len(wanting) - base)
        shortfall = max(0, len(wanting) - places)
        self.childcare_shortfall = shortfall
        if shortfall > 0:
            unlucky = rng.choice(wanting, min(shortfall, len(wanting)), replace=False)
            full_time = unlucky[A["status"][unlucky] == FULL]
            A["status"][full_time] = PART   # a place-less parent drops to part time
            A["underemployed"][full_time] = True

    def welfare_snapshot(self):
        """How people actually live: income, poverty (overall, children, pensioners), hardship, security."""
        A, p = self.A, self.p
        adults = np.flatnonzero(A["alive"] & (A["age"] >= 18))
        cmin, equiv = self.housing_costs(adults)
        per_mother, _, _ = self.child_transfers()
        household = self.household_real_income(adults, per_mother)
        equivalised = household / equiv
        median = float(np.median(equivalised))
        line = .6 * median
        self.poverty_line_last = line    # v10: how far below it a household is moves older owners (housing.py)
        poor = equivalised < line
        ch = A["alive"] & A["chooser"]
        st = A["status"]
        kids = A["alive"] & (A["age"] < 18) & (A["mother"] >= 0)
        mother_poor = dict(zip(adults, poor))
        child_poor = np.mean([mother_poor.get(m, False) for m in A["mother"][kids]]) if kids.any() else 0.0
        pensioners = A["age"][adults] >= 67
        working = np.isin(st, [PART, FULL, VENTURE])
        secure = np.maximum(A["contract_end"] - self.year, 0)
        wellbeing = self.life_satisfaction(adults, equivalised, cmin, equiv)
        wellbeing.update(self.security_snapshot(adults, equivalised))
        # The comparison that matters is not the wage but what a household is left with: pay less tax plus
        # everything the state pays out. A UBI economy is meant to have lower wages and higher transfers, so a wage
        # comparison alone reads the reform backwards.
        by_decile = np.sort(equivalised)
        n = len(by_decile)
        deciles = {f"net_income_d{i + 1}": float(by_decile[int(n * i / 10):int(n * (i + 1) / 10)].mean())
                   for i in range(10)} if n >= 10 else {}
        work_income = self.net_now[adults] / self.price
        anchored = getattr(self, "median0", None)
        # Who gains and who loses, by what people are: a reform that replaces targeted benefits with a flat payment
        # moves money between groups, and a national median hides it. The household's income per equivalent adult,
        # after prices, at the group's median.
        age_a, dis_a, st_a = A["age"][adults], A["disabled"][adults], st[adults]
        studying = A["studying"][adults] > 0
        groups = {"pensioners": age_a >= 67, "disabled": (age_a < 67) & dis_a,
                  "students": (age_a < 67) & ~dis_a & studying,
                  "out_of_work": (age_a < 67) & ~dis_a & ~studying & (st_a == NONWORK),
                  "in_work": (age_a < 67) & ~dis_a & ~studying & (st_a != NONWORK)}
        by_group = {f"income_{g}": float(np.median(equivalised[m])) if m.any() else np.nan for g, m in groups.items()}
        return {"real_income_median": median,
                # Poverty against the 2025 median held fixed in real terms. The relative line above moves with the
                # median, so a payment that lifts everyone can leave it unchanged; this says whether people actually
                # climbed above what counted as poverty before the reform.
                "poverty_rate_anchored": float(np.mean(equivalised < .6 * anchored)) if anchored else np.nan,
                "net_income_mean_real": float(np.mean(equivalised)),
                "net_income_sd": float(np.std(equivalised)),
                "net_income_cv": float(np.std(equivalised) / max(np.mean(equivalised), 1)),
                "net_income_p10": float(np.percentile(equivalised, 10)),
                "net_income_p90": float(np.percentile(equivalised, 90)),
                "own_net_income_median": float(np.median(work_income)),
                **deciles, **by_group,
                # v9: over persons, children included, as EU-SILC and Hagstofa measure it; the
                # adults-only rate v8 reported as "poverty" is kept under its own name
                "poverty_rate": float((poor.sum() + child_poor * kids.sum()) / max(len(poor) + kids.sum(), 1)),
                "poverty_rate_adults": float(np.mean(poor)),
                "poverty_gap": float(np.mean(np.clip((line - equivalised[poor]) / line, 0, 1))) if poor.any() else 0.0,
                "child_poverty_rate": float(child_poor),
                "pensioner_poverty_rate": float(np.mean(poor[pensioners])) if pensioners.any() else np.nan,
                "hardship_rate": float(np.mean(household < p["costs"]["subsistence_share"] * cmin)),
                "forced_idle_share": float((ch & A["involuntary"]).sum() / max(ch.sum(), 1)),
                "involuntary_part_time": float(np.mean((st[ch] == PART) & A["underemployed"][ch])),
                **housing.snapshot(self),
                **wellbeing}

    def structure_snapshot(self):
        """Structural measures: shortages in essential services, output, ownership, mobility and the tax mix."""
        A, p, mk = self.A, self.p, self.macro
        alive = A["alive"]
        S = np.bincount(A["occupation"][alive & A["chooser"]],
                        weights=self.hours_of(A["status"][alive & A["chooser"]]), minlength=N_OCC)
        D = self.demand(self.implied_paid_index(self.omega_new, self.p["policy"]["wage_setting"] == "free_market"),
                        supply=S)
        gaps = np.clip(D - S, 0, None)
        essential = {"Nurses and midwives": "nurse", "Doctors": "doctor", "Primary and pre-school teachers": "teacher",
                     "Care assistants": "care", "Child-care workers": "childcare_staff"}
        out = {f"shortfall_{tag}": float(gaps[OCCUPATIONS.index(n)]) for n, tag in essential.items() if n in OCCUPATIONS}
        out["essential_services_gap"] = float(sum(out.values()))
        out["social_distress_index"] = float(getattr(self, "distress", 1.0))
        # what the state is paying above the going rate to fill those posts, and what that costs it in a year
        prem = np.asarray(self.public_premium, float)
        ess_idx = [OCCUPATIONS.index(n) for n in essential if n in OCCUPATIONS]
        weight = self.D0_pub[ess_idx]
        out["mean_birth_age"] = float(getattr(self, "mean_birth_age", float("nan")))
        out["childcare_places_short"] = float(getattr(self, "childcare_needed", 0))
        out["public_shortage_premium"] = float((prem[ess_idx] * weight).sum() / max(weight.sum(), 1e-9))
        # the three ways a shortage shows up: pay, work not done, and load on the people who stay
        unmet = np.asarray(self.service_unmet)
        load = np.asarray(self.workload)
        out["essential_service_unmet"] = float((unmet[ess_idx] * weight).sum() / max(weight.sum(), 1e-9))
        out["essential_workload"] = float((load[ess_idx] * weight).sum() / max(weight.sum(), 1e-9))
        out["health_service_unmet"] = float(np.mean([unmet[OCCUPATIONS.index(n)] for n in
                                                     ("Doctors", "Nurses and midwives", "Care assistants")
                                                     if n in OCCUPATIONS]))
        out["teaching_service_unmet"] = float(np.mean([unmet[OCCUPATIONS.index(n)] for n in
                                                       ("Primary and pre-school teachers", "Secondary teachers",
                                                        "Child-care workers") if n in OCCUPATIONS]))
        base = np.bincount(A["occupation"][alive & A["chooser"] & A["public"]],
                           weights=(self.hours_of(A["status"][alive & A["chooser"] & A["public"]])
                                    * self.A["base_wage"][alive & A["chooser"] & A["public"]]), minlength=N_OCC)
        out["public_shortage_pay_bn"] = float((base * self.omega * (prem - 1)).sum() * 12 / 1e9)
        pop = max(int(alive.sum()), 1)
        hours = self.activity_hours(A["status"])[alive & A["chooser"]]
        out["gdp_per_capita_index"] = float(mk.output * self.pop_total0 / pop) if hasattr(self, "pop_total0") else float(mk.output)
        out["productivity_per_hour"] = float(mk.output / max(hours.sum() / max(len(hours), 1), .01))
        young = alive & (A["age"] >= 25) & (A["age"] < 35)
        out["first_home_purchases"] = int(getattr(self, "first_homes", 0))
        out["home_ownership_under_35"] = float(np.mean(A["home_value"][young] > 0)) if young.any() else np.nan
        out["weekly_hours_per_adult"] = float(np.mean(hours) * 40)
        tax = {"labour": self.accounts_cache.get("income_tax", 0) + self.accounts_cache.get("payroll_tax", 0)
               + self.accounts_cache.get("social_security", 0),
               "consumption": self.accounts_cache.get("vat", 0),
               "capital": self.accounts_cache.get("corporate_tax_economy", 0) + self.accounts_cache.get("property_tax", 0)
               + self.accounts_cache.get("wealth_tax", 0) + self.accounts_cache.get("automation_levy", 0),
               "resource": self.accounts_cache.get("fisheries_fee", 0) + self.accounts_cache.get("energy_dividend_change", 0)
                           + self.accounts_cache.get("windfall_take", 0)}
        total = sum(tax.values()) or 1.0
        out.update({f"tax_share_{k}": v / total for k, v in tax.items()})
        out["net_foreign_assets_pct_gdp"] = float(getattr(mk, "niip", 0.0))
        return out

    def incentive_snapshot(self, per_mother):
        """What working is actually worth. The participation tax rate is the share of gross full-time pay that a
        household never sees, because tax rises and support falls when someone takes the job; the marginal rate is
        the same question for the step from part-time to full-time. High rates are the trap a UBI is meant to avoid."""
        A = self.A
        idx = np.flatnonzero(A["alive"] & A["chooser"] & (A["age"] < 67))
        if not len(idx):
            return {}
        # medians off an even sample: pricing every option for everyone would roughly double the run time, and a
        # fixed stride keeps the main random stream untouched so runs stay comparable
        idx = idx[:: max(1, len(idx) // 20_000)]
        # births and arrivals joined after per_mother was built, so it has to be padded out to today's population
        if len(per_mother) < self.N:
            per_mother = np.concatenate([per_mother, np.zeros(self.N - len(per_mother))])
        H = self.option_household_income(idx, self.omega_new, per_mother)
        wage = np.maximum(self.wage_of(idx, self.omega_new) * self.public_pay_factor(idx)
                          - self.public_wage_offset(idx, self.omega_new),
                          .4 * A["base_wage"][idx] * self.price)
        pt = self.p["behaviour"]["part_time_hours"]
        keep_full = (H[:, 2] - H[:, 0]) / np.maximum(wage, 1)                     # kept per króna of full-time pay
        keep_step = (H[:, 2] - H[:, 1]) / np.maximum(wage * (1 - pt), 1)          # kept on the extra hours
        ubi = self.p["policy"]["ubi_adult"] if self.p["policy"]["regime"] == "platform" else 0.0
        median_net = float(np.median(self.net_now[A["alive"] & (A["age"] >= 18)]))
        return {"participation_tax_rate": float(np.median(1 - keep_full)),
                "marginal_tax_rate_to_full_time": float(np.median(1 - keep_step)),
                "share_facing_over_70pct_ptr": float(np.mean(1 - keep_full > .70)),
                "gain_from_full_time_isk": float(np.median(H[:, 2] - H[:, 0]) / self.price),
                "ubi_replacement_rate": float(ubi / max(median_net, 1))}

    def housing_burden(self, adults):
        """Housing cost as a share of the household's income after tax, both in 2025 krónur.

        It used to divide a rent *index* (about 1.0) by monthly income in krónur, which put the median burden at
        0.000002 and meant nobody ever paid over 40% — so neither that figure nor the housing term in life
        satisfaction ever moved. Property tax is not added to the cost: it is already off the income."""
        A = self.A
        rent, mortgage, _ = self.macro.housing_costs()
        cost = pol_rules.housing_cost(A, adults, self.p, rent, mortgage)
        partner = A["partner"][adults]
        household = (self.net_now[adults] + np.where(partner >= 0, self.net_now[np.maximum(partner, 0)], 0)) / self.price
        return cost / np.maximum(household, 1e4)

    def housing_snapshot(self):
        """Whether housing is affordable, not just what it costs: the price of a home against a year's earnings,
        and how much of their income renters and owners actually hand over."""
        A, mk = self.A, self.macro
        adults = np.flatnonzero(A["alive"] & (A["age"] >= 18))
        burden = self.housing_burden(adults)
        median_year_income = float(np.median(self.net_now[A["alive"] & (A["age"] >= 18)]) * 12 / self.price)
        dwelling_value = (self.macro.PROPERTY_VALUE0 * 1e9 * self.p["markets"]["residential_share"]
                          / self.p["markets"]["dwellings0"] * mk.house_price)
        return {"house_price_to_income": float(dwelling_value / max(median_year_income, 1)),
                "housing_cost_burden": float(np.median(burden)),
                "share_housing_over_40pct": float(np.mean(burden > .40)),
                "renter_share": float(np.mean(A["renter"][adults]))}

    def churn_snapshot(self):
        """How settled working life is: how many contracts come up each year, and how long people have been in post."""
        A = self.A
        employed = A["alive"] & np.isin(A["status"], [PART, FULL])
        if not employed.any():
            return {"contracts_expiring_share": 0.0, "mean_tenure_years": 0.0, "job_changes": 0}
        remaining = np.maximum(A["contract_end"][employed] - self.year, 0)
        return {"contracts_expiring_share": float(np.mean(remaining <= 0)),
                "mean_tenure_years": float(np.mean(A["tenure"][employed])) if "tenure" in A else float("nan"),
                "job_changes": int(getattr(self, "occupation_moves", 0))}

    def security_snapshot(self, adults, equivalised):
        """Insecurity: how many people had the floor move under them this year.

        A basic income is argued for as a floor more than as an amount, and a floor is about variance rather
        than the mean. None of the other measures here capture that — a population can have a rising average
        income while a fifth of it is knocked sideways every year.
        """
        A = self.A
        prev = getattr(self, "_income_last", None)
        out = {}
        now = np.zeros(self.N)
        now[adults] = equivalised
        # the population grows during a year, so last year's array is shorter than this year's indices: pad it
        # rather than compare its length to a count, which is the same mistake in a different place
        if prev is not None:
            if len(prev) < self.N:
                prev = np.concatenate([prev, np.zeros(self.N - len(prev))])
            old_inc = prev[adults]
            both = (old_inc > 1e3) & (equivalised > 0)
            if both.any():
                change = equivalised[both] / old_inc[both] - 1
                out["income_fell_20pct"] = float(np.mean(change < -.20))
                out["income_fell_40pct"] = float(np.mean(change < -.40))
                out["income_volatility"] = float(np.mean(np.abs(change)))
        self._income_last = now
        cushion = A["wealth"][adults] * self.price / np.maximum(self.net_now[adults], 1)
        out["under_3_months_savings"] = float(np.mean(cushion < 3))
        out["cannot_meet_emergency"] = float(np.mean(cushion < 1))
        return out

    def life_satisfaction(self, adults, equivalised, cmin, equiv):
        """Life satisfaction per adult on a 0-10 scale, built from what the evidence says moves it.

        Weights are EST but their signs and rough sizes follow the life-satisfaction literature: involuntary
        unemployment costs far more than the income it takes away (Clark & Oswald), health and partnership are
        large, income enters logarithmically and against what others have rather than absolutely, and job quality,
        security, housing costs and time pressure each carry a measurable amount.

        The model cannot predict how happy Icelanders are. What it can do is say how much a reform moves this, so
        the scale is anchored on the published figure for Iceland (about 7.5 on the 0-10 Cantril ladder, World
        Happiness Report / Eurostat) in the base year, and every scenario is read as a difference from that.
        """
        A, p, w = self.A, self.p, self.p["wellbeing"]
        st, hours = A["status"][adults], self.activity_hours(A["status"])[adults]
        working = np.isin(st, [PART, FULL, VENTURE, INDEP])
        ref = getattr(self, "median0", None) or float(np.median(equivalised))
        s = np.zeros(len(adults))
        parts = {}
        parts["income"] = w["income"] * np.log(np.maximum(equivalised, 1e3) / max(ref, 1e3))
        parts["unemployment"] = -w["unemployment"] * (A["involuntary"][adults] & ~working)
        parts["health"] = -w["ill_health"] * (1 - A["health"][adults])
        parts["partner"] = w["partner"] * (A["partner"][adults] >= 0)
        quality = A["meaning"][adults] - self.disamenity[A["occupation"][adults]]
        parts["work_quality"] = w["work_quality"] * quality * hours
        secure = np.minimum(np.maximum(A["contract_end"][adults] - self.year, 0), 5) / 5
        parts["security"] = w["security"] * secure * np.isin(st, [PART, FULL])
        burden = self.housing_burden(adults)
        parts["housing"] = -w["housing_burden"] * np.clip((burden - .4) / .3, 0, 1)
        parts["hardship"] = -w["hardship"] * (equivalised * equiv < p["costs"]["subsistence_share"] * cmin)
        squeezed = (A["n_young_kids"][adults] > 0) & (hours >= 1.0)
        parts["time_squeeze"] = -w["time_squeeze"] * squeezed
        # towns with more kinds of shop, owned by more people: worth something in itself, and as a consumer gain
        po = p["property_ownership"]
        variety = getattr(self.macro, "variety", 0.0)
        parts["variety"] = np.full(len(hours), variety * (po["variety_wellbeing"]
                                                          + w["income"] * np.log1p(po["variety_consumption_gain"])))
        for v in parts.values():
            s = s + v
        # anchored so the base year sits at the published level; a scenario is the difference from there
        # Before the base year is fixed (during calibration) centre on this run's own mean, so the score is still
        # a per-person array rather than collapsing to the anchor.
        base = getattr(self, "wellbeing0", None)
        if base is None:
            base = float(np.mean(s))
        score = np.clip(w["anchor"] + (s - base), 0, 10)
        out = {"wellbeing_index": float(np.mean(score)),
               "wellbeing_p10": float(np.percentile(score, 10)),
               "wellbeing_struggling": float(np.mean(score < 5)),
               "wellbeing_thriving": float(np.mean(score >= 7)),
               **{f"wb_{k}": float(np.mean(v)) for k, v in parts.items()}}
        for tag, mask in [("worker", np.isin(st, [PART, FULL])), ("independent", st == INDEP),
                          ("idle", A["involuntary"][adults] & ~working), ("pensioner", A["age"][adults] >= 67),
                          ("parent", A["n_kids"][adults] > 0)]:
            out[f"wellbeing_{tag}"] = float(np.mean(score[mask])) if mask.any() else np.nan
        self._wellbeing_raw = float(np.mean(s))
        return out

    def distribution_snapshot(self):
        """Who gains and who loses: the wage ladder and the spread of real disposable income."""
        A, mk = self.A, self.macro
        harsh = [OCCUPATIONS.index(n) for n in P.HARSH]      # by profession, not by the 9 occupation groups
        top = [OCCUPATIONS.index(n) for n in P.TOP_PAID]
        adults = A["alive"] & (A["age"] >= 18)
        inc = np.sort(self.net_now[adults] / self.price)
        n = len(inc)
        q = [float(inc[int(n * a):int(n * b)].mean()) for a, b in [(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1)]]
        pos = inc[inc > 0]
        gini = float((2 * np.arange(1, len(pos) + 1) - len(pos) - 1).dot(pos) / (len(pos) * pos.sum())) if len(pos) else 0.0
        return {"wage_ratio_harsh_to_top": float(self.omega[harsh].mean() / self.omega[top].mean()),
                "income_gini": gini, "income_top_decile_share": float(inc[int(n * .9):].sum() / max(inc.sum(), 1)),
                "income_p90_p10": float(inc[int(n * .9)] / max(inc[int(n * .1)], 1)),
                **{f"income_q{i + 1}": v for i, v in enumerate(q)}}

    # ------------------------------------------------------------------ accounts
    def accounts(self):
        """Annual public accounts (bn ISK) computed from agents, plus real consumption."""
        A, p = self.A, self.p
        idx, gross, inc = self.refresh_net_now()
        per_mother, invested, child_gross = self.child_transfers()
        er = pol_rules.employer_rate(p)
        platform = p["policy"]["regime"] == "platform"
        vat = pol_rules.vat_rate(p)
        f = self.firms
        profits = f["profit"][f["alive"]].clip(0).sum()
        v = p["ventures"]
        exits = getattr(self, "exits", np.zeros(0, int))
        public = A["public"][idx] & np.isin(A["status"][idx], [PART, FULL])
        usable_child = per_mother.sum()
        # what the state guarantees this person a month, whatever happens to their work: the floor their
        # spending can rely on
        guaranteed = np.asarray(inc["benefits"]) + np.asarray(inc.get("ubi", 0.0))
        consumption = self.household_consumption(idx, inc["net"], per_mother, guaranteed)
        bn = 12 / 1e9
        # v10: the top-up lent against homes (policy.floor_loan) is lending, not spending; booked by accrue_claims
        lend_j, lend = housing.floor_lending(self, idx, inc["benefits"])
        self._lending = (lend_j, lend)
        self._gross_by_agent = np.zeros(len(A["alive"]))
        self._gross_by_agent[idx] = gross
        self.junior_subsidy_bn = careers.subsidy_cost(self, idx, gross)
        hidden_sq = inc["hidden_sq"] if platform else informal.status_quo_hidden(self, idx, gross, np.isin(
            A["status"][idx], [PART, FULL, VENTURE, INDEP]), np.where(A["partner"][idx] >= 0,
            self.net_now[np.maximum(A["partner"][idx], 0)], 0))
        a = {
            "income_tax": inc["tax"].sum() * bn,
            # 2.0: tax on earnings the reform brings onto the books (informal.py); the earnings hidden, both ways
            "informal_tax_change": float(np.sum(inc["informal_tax"]) * bn),
            "hidden_earnings": float(np.sum(inc["hidden"] if platform else hidden_sq) * bn),
            "hidden_earnings_sq": float(np.sum(hidden_sq) * bn),
            # v9: capital income tax on the capital income now in people's incomes (it was in the unmodelled part of
            # revenue, which shrinks by as much at the base year: macro.unmodelled_bn)
            "capital_income_tax": float(inc["capital_tax"].sum() * bn) if "capital_tax" in inc else 0.0,
            "capital_income": float(inc["capital_income"].sum() * bn) if "capital_income" in inc else 0.0,
            # 1.1: corporate and dividend tax on pay taken as dividends, and the pay above the second threshold no
            # longer reported (policy.top_income_response)
            "income_shifted_tax": float(inc["shifted_tax"].sum() * bn),
            "top_income_lost": float(inc["top_income_lost"].sum() * bn),
            # 1.1: the state's share of juniors' wages where machines take entry-level work (careers.py)
            "junior_subsidy": self.junior_subsidy_bn,
            "child_pension": float(getattr(self, "child_pension_bn", 0.0)) if p["policy"]["regime"] == "status_quo" else 0.0,
            "founder_dividends": self.founder_dividends_bn(),
            "social_security": (inc["employee_contrib"].sum() + (gross * er).sum()) * bn
                               * pol_rules.state_contribution_share(p) if platform else 0.0,
            "payroll_tax": (gross * p["policy"]["payroll_tax"]).sum() * bn,
            "vat": consumption * vat / (1 + vat) * bn,
            "corporate_tax": v["corporate_tax"] * profits / 1e9,
            "state_equity": self.venture_equity_return(profits, exits, f) if platform else 0.0,
            "public_equity_dividends": getattr(self, "public_equity", {}).get("dividends", 0.0) if platform else 0.0,
            "benefits": inc["benefits"].sum() * bn,
            # the status quo's benefits one by one, to check each against the 2025 record
            **{f"benefit_{k}": float(v.sum() * bn) for k, v in (inc.get("parts") or {}).items()},
            # 1.1: people paid social assistance, against the record's (the claim share is fitted to it)
            "recipients_social_assistance": float((np.asarray((inc.get("parts") or {}).get("social_assistance", 0.0)) > 0).sum()),
            "child_payments": child_gross * bn,
            "ubi_adult": inc["ubi"].sum() * bn,
            "pension_topup": inc["topup"].sum() * bn,
            "public_payroll": (gross[public] * (1 + er + p["policy"]["payroll_tax"])).sum() * bn,
            "seed_money": p["policy"]["state_seed_money"] * p["policy"]["venture_support"]
                          * getattr(self, "new_firms", 0) / 1e9 if platform else 0.0,
            "child_invested": invested * bn,
            "consumption_real": consumption * bn / self.price,
            "labour_income_real": gross.sum() * bn / self.price,
            "occupational_pensions": inc["occ_pension"].sum() * bn,
            "venture_jobs": float(f["jobs"][f["alive"]].sum()),
            # v10: deferred property tax is still due — a claim on the home, repaid on sale or from the estate
            # (housing.py) — so it stays in revenue, as accrual accounts book it; property_tax_deferred is the cash
            # not collected this year
            "property_tax": self.macro.property_tax_rate() * self.macro.house_price * self.macro.stock * self.macro.PROPERTY_VALUE0,
            "property_tax_deferred": self.deferred_property_tax_bn(),
            "floor_loans": float(lend.sum() * self.price / 1e9),
            "claims_written_off": float(getattr(self, "claims_written_off", 0.0) * self.price / 1e9),
            "fund_returns": (A["fund"][A["alive"]].sum() / 1e9 + getattr(self, "adult_savings", 0.0))
                            * sb.P["pension_real_return"] if platform else 0.0,
            "ubi_saved": inc["ubi_saved"].sum() * bn,
            "adult_savings_assets": getattr(self, "adult_savings", 0.0),
            "fund_assets": A["fund"][A["alive"]].sum() / 1e9,
            **self.sectors.fiscal(),
            **self.automation.fiscal(),
            **self.extra_policy_accounts(),
            "frontier_capex": self.frontier.state["capex_bn"],
            "infrastructure_capex": self.infra.state["capex_bn"],
            "frontier_return": self.frontier.state["state_return_bn"],
            "corporate_tax_economy": self.corporate_tax_economy(),
            "sovereign_fund_return": self.macro.sovereign_fund * self.p["markets"]["sovereign_fund_return"],
            "household_liquid_wealth": A["wealth"][A["alive"]].sum() / 1e9,
            "household_housing_equity": self.housing_equity()[A["alive"]].sum() / 1e9,
            "low_value_fte_removed": float((self.low_value_removal() * (self.D0_pub + self.D0_priv)).sum()),
        }
        ch = A["alive"] & A["chooser"]
        a["working_age"] = float(self.working_age())
        a["productivity"] = float(self.macro.productivity())
        a["spend_rate"] = a["consumption_real"] / max(a["labour_income_real"], 1.0)
        a["omega"] = self.omega.tolist()   # the wage each profession is actually paid, for the reference path
        a["omega_new"] = np.asarray(getattr(self, "omega_new", self.omega)).tolist()   # and the rate for new contracts
        a["peer_nonwork"] = np.asarray(getattr(self, "peer_nonwork", np.zeros(10))).tolist()   # 2.0: the norm's peers
        a["occ_supply"] = np.bincount(A["occupation"][ch], weights=self.hours_of(A["status"][ch], ch), minlength=N_OCC).tolist()
        a["cons_pc"] = a["consumption_real"] / (self.accounts0["consumption_real"] if hasattr(self, "accounts0") else a["consumption_real"]) \
            / (self.working_age() / getattr(self, "pop0", self.working_age()))
        er0 = p["policy"]["pension_contrib_employer"]
        a["competitiveness"] = self.macro.e / max(.3, self.macro.relative_wage_cost(self.wage_cost_index(self.omega))
                                                   / self.macro.productivity())
        wage_per_fte = gross.sum() / max(self.hours_of(A["status"][idx], idx).sum(), 1)
        self.automation.income(wage_per_fte, self.price)
        a.update(self.automation.fiscal())
        a["machine_dividends"] = self.pay_machine_dividends(a)
        # One currency for every flow: today's krónur. Items built from incomes and spending are already in it; the
        # ones below were built in 2025 krónur, and balance() deflates everything by the price level, so they were
        # deflated twice and shrank about 2.5% a year for no reason.
        for k in REAL_FLOWS:
            a[k] = a[k] * self.price
        a["price"] = self.price
        a["inheritance_tax"] = self.expected_inheritance_tax()   # already in today's krónur
        a["revenue"] = a["income_tax"] + a["informal_tax_change"] + a["capital_income_tax"] + a["income_shifted_tax"] + a["social_security"] + a["payroll_tax"] + a["vat"] + a["corporate_tax"] \
            + a["state_equity"] + a["public_equity_dividends"] + a["property_tax"] + a["fund_returns"] + a["fisheries_fee"] \
            + a["energy_dividend_change"] + a["windfall_take"] + a["corporate_tax_economy"] + a["frontier_return"] \
            + a["automation_tax"] + a["automation_levy"] + a["automation_dividends"] + a["wealth_tax"] \
            + a["sovereign_fund_return"] + a["sick_pay_saved"] + a["inheritance_tax"] + a["leave_saved"]
        a["expenditure"] = (a["benefits"] - a["floor_loans"] + a["claims_written_off"] + a["child_payments"] + a["ubi_adult"] + a["pension_topup"]
                            + a["public_payroll"] + a["seed_money"] + a["contract_compensation"] + a["frontier_capex"]
                            + a["automation_subsidy"] + a["junior_subsidy"]
                            + a["retraining_cost"] + a["childcare_cost"] + a["public_housing_cost"]
                            + a["education_cost"] + a["infrastructure_capex"]
                            + a["health_cost"] - p["health"]["public_spending_bn"] * self.price
                            + a["crime_cost"] - p["crime"]["responsive_spending_bn"] * self.price
                            + a["schooling_cost"] - p["schooling"]["spending_bn"] * self.price)
        return a

    def balance(self, a):
        """General government balance (bn ISK): 2025 deficit + agent-modelled change + static platform items."""
        p = self.p
        # Every run is measured from the base year's accounts, a reform included. Measured from the status quo's
        # own path, a reform's balance was the base-year deficit plus the policy's effect and nothing else: the
        # status quo's own drift — ageing, pay, interest — never reached it, so the page's "against the status
        # quo" credited the reform with the whole of that drift (found 2026-09-26: +200 ma.kr. a year by 2035).
        ref = self.accounts0
        real = lambda acc, k: acc[k] / acc.get("price", 1.0)
        change = (real(a, "revenue") - real(ref, "revenue")) - (real(a, "expenditure") - real(ref, "expenditure"))
        static = {}
        if p["policy"]["regime"] == "platform":
            s = sb.P
            g = p["policy"]["governance_cut"]
            items, _, _ = sb.run({**s, "public_payroll_cut": 0.0, "pension_contribution_mode": "none",
                                  "parliament_cut": s["parliament_cut"] * g, "mp_pay_cut": s["mp_pay_cut"] * g,
                                  "minister_pay_cut": s["minister_pay_cut"] * g,
                                  "party_funding_cut": s["party_funding_cut"] * g,
                                  "rural_travel_cut": s["rural_travel_cut"] * g,
                                  "foreign_service_cut": s["foreign_service_cut"] * g,
                                  "presidency_cut": p["policy"]["presidency_cut"],
                                  "church_funding_cut": p["policy"]["church_funding_cut"],
                                  "agriculture_subsidy_cut": p["policy"]["agriculture_subsidy_cut"],
                                  "other_subsidies_cut": 0.0,
                                  "subsidy_cut_innovation": p["policy"]["subsidy_cut_innovation"],
                                  **{f"subsidy_cut_{k}": v for k, v in P.energy_cuts(p).items()},
                                  "subsidy_cut_other": p["policy"]["subsidy_cut_other"],
                                  "customs_kept": p["policy"]["customs_kept"],
                                  "vat_input_restriction_gain": p["policy"]["vat_input_restriction_gain"],
                                  "pension_real_return": p["policy"]["pension_fund_real_return"],
                                  # kept earned pensions: the funds keep their returns to pay them
                                  "pension_return_share": p["policy"]["pension_fold"]
                                  * (1 - p["policy"].get("pension_keep_earned", 0.0)),
                                  "per_diem_abolished": True,
                                  "ministers_outside_parliament": g > 0})
            keep = ["Pension-fund returns", *[f"Subsidies cut: {n}" for _, n, _ in sb.SUBSIDY_GROUPS],
                    "Alþingi, smaller and cheaper", "þingfararkaup reduced", "Ministers' pay reduced",
                    "Presidency made formulaic", "Party funding ended", "Rural travel support ended",
                    "Foreign service reduced", "Ministers seated outside parliament",
                    "Church and religious funding ended",
                    "Agriculture subsidies cut", "Customs abolished", "VAT input credit restricted (EST)",
                    "Per diems abolished (EST)"]
            # the static lines are 2025 figures; another base year takes them in proportion to its economy
            scale = (p.get("base") or {}).get("static_scale", 1.0)
            static = {k: items[k] * scale for k in keep}
            static["Pension-fund returns"] *= self.macro.pension_asset_ratio()
            static["Per diems abolished (EST)"] *= p["policy"]["per_diem_cut"]
            # 2.0: the part of the restricted input VAT that falls on capital goods is paid on what firms invest
            sk = p["capital"]["vat_capital_share"] if p.get("capital") else 0.0
            static["VAT input credit restricted (EST)"] *= 1 - sk + sk * capital.investment_against_reference(self)
            static["Benefit administration wound down (EST)"] = p["enforcement"]["benefit_admin_saved_bn"]
            # VAT on what tourists buy, at the reform's rate against today's, on what they still buy
            lk, tr = p["links"], p["trade"]
            v, v0 = p["policy"]["vat_platform"], lk["tourism_vat_today"]
            spend = self.macro.X0 * tr["shares"]["tourism"] * tr["price"]["tourism"] * self.macro.tourism_vat_factor()
            static["VAT on tourists"] = spend * lk["tourism_vatable_share"] * (v / (1 + v) - v0 / (1 + v0))
            fs = p["free_services"]
            if p["policy"]["free_health_care"]:
                h = p["policy"]["free_health_care"]
                ramp = min(1.0, self.year / fs["gatekeeping_years"])
                static["Free health care, GP first (Danish model): visits free"] = -h * fs["health_service_copay_bn"] \
                    * (1 + fs["health_demand_response"])
                static["Free health care, GP first (Danish model): GP referral"] = h * ramp * fs["specialist_bn"] \
                    * fs["gatekeeping_specialist_cut"] * (1 - fs["gatekeeping_gp_cost_share"])
            if p["policy"]["agriculture_subsidy_cut"]:
                static["Agricultural start-ups (RANNÍS)"] = -p["agriculture"]["startup_bn"] \
                    * min(1.0, p["policy"]["agriculture_subsidy_cut"] / .5)
            if p["policy"].get("green_heat_bn"):
                es = p["energy_split"]
                kept = 1 - P.energy_cuts(p)["heating"]      # the support still paid, now needed less
                static["Local green heat for cold areas"] = -p["policy"]["green_heat_bn"] \
                    + es["heating_bn"] * kept * self.green_heat_share() * es["green_heat_saving"]
            if p["policy"]["free_internet"]:
                static["Internet as infrastructure"] = -p["policy"]["free_internet"] * fs["internet_state_cost_bn"]
            # the borgaralaun of people in prison, where it is withheld (2025 krónur)
            real_ubi = p["policy"]["ubi_adult"] / max(self.price, .1)
            static["Borgaralaun withheld in prison"] = self.crime_now()["prisoners"] * real_ubi * 12 \
                * p["policy"]["prison_ubi_withheld"] / 1e9
            n = float(p["policy"]["tax_enforcement_fte"])
            if n:
                static["Tax enforcement"] = self.enforcement_yield(n) - n * p["enforcement"]["cost_per_fte_m"] / 1000
            if getattr(self, "exit_tax_bn", 0.0):
                static["Exit tax"] = self.exit_tax_bn
            cust = self.macro.custodianship()
            if cust:
                static["Custodianship assessments"] = -cust * p["property_ownership"]["custodian_admin_bn"]
            # The national-accounts total of social benefits includes the parental leave fund's payments, and the
            # leave lever saves those again from the model's own births and wages. Counted here as well, they were
            # saved twice with the lever on — and once with it off, when the reform is meant to keep paying them
            # (found 2026-09-25). They are left to the leave lever alone.
            static["Other social benefits replaced"] = max(0.0, (sb.SOCIAL_BENEFITS_2025
                                                                 - p["policy"]["parental_leave_fund_bn"]) * scale
                                                           - self.accounts0["benefits"] - self.accounts0["child_payments"])
        # support in a crisis the model does not generate itself (COVID 2020-21, in the backcast): spending
        hist = p.get("history") or {}
        crisis = float(hist.get("crisis_support_bn", 0.0))
        if crisis and p["policy"]["regime"] == "platform" and self.reference:
            # the wage-linked part follows the reform's pay against the status quo's (params "crisis")
            ref = self.reference[min(self.year, len(self.reference)) - 1]
            w = self.D0_pub + self.D0_priv
            own = float((np.asarray(self.omega) * w).sum() / w.sum()) / max(self.price, .1)
            theirs = float((np.asarray(ref["omega"]) * w).sum() / w.sum()) / max(ref.get("price", 1.0), .1)
            share = p["crisis"]["wage_linked_share"]
            crisis *= 1 - share + share * float(np.clip(own / max(theirs, 1e-9), .3, 1.5))
        if crisis:
            static["Crisis support"] = -crisis
        # shielding: the top-ups, the carers' pay and the rooms, for the months it runs (params "crisis")
        months = float(hist.get("shield_months", 0.0))
        if months:
            c = p["crisis"]
            static["Shielding: top-ups"] = -c["shield_people"] * c["shield_topup"] * months / 1e9
            static["Shielding: carers"] = -c["shield_carers"] * c["shield_carer_pay"] * months / 1e9
            static["Shielding: rooms"] = -float(hist.get("shield_housing_bn", 0.0))
        # what the budget recorded that the model does not produce — one-offs, programmes, revenue it does not
        # carry — identified in the backcast so the status quo matches the record, and the same in every run
        residual = float((p.get("history") or {}).get("fiscal_residual_bn", 0.0))
        if residual:
            static["Unmodelled items (identified)"] = residual
        deficit0 = (p.get("base") or {}).get("DEFICIT0", sb.DEFICIT_2025)
        return deficit0 + change + sum(static.values()), change, static

    def snapshot(self, acc, founders_new, emig, imm, births, deaths, bal, change, static):
        A = self.A
        alive = A["alive"]
        ch = alive & A["chooser"]
        st = A["status"]
        working = np.isin(st, [PART, FULL, VENTURE])
        independent = st == INDEP
        creative_prof = A["creative"] >= 1.0   # stronger-than-average pull towards making, writing, studying
        w0 = alive & A["worker0"] & A["chooser"]
        out = {
            "year": self.year,
            "population": int(alive.sum()),
            "children_under_18": int((alive & (A["age"] < 18)).sum()),
            "employment_rate_16_74": float(working[ch].mean()),
            "fte": float((self.hours_of(st, slice(None)) * alive).sum() + (st == VENTURE).sum()),
            "fte_per_adult_16_74": float(((self.hours_of(st, slice(None)) + (st == VENTURE)) * ch).sum() / ch.sum()),
            # FTE is measured in 2025 full-time weeks, so a shorter standard week lowers it by design. This one
            # counts a standard week as 1.0 whatever the week currently is, which is what "is everyone working?"
            # actually asks.
            "standard_weeks_per_adult": float(((self.hours_of(st) + (st == VENTURE)) * ch).sum() / ch.sum()
                                              / max(self.p["policy"]["full_time_hours_factor"]
                                                    if self.p["policy"]["regime"] == "platform" else 1.0, .1)),
            "dropouts": int(getattr(self, "dropouts", 0)),
            "health_mean": float(A["health"][alive].mean()),
            "health_p10": float(np.percentile(A["health"][alive], 10)),
            "poor_health_share": float((A["health"][alive] < .6).mean()),
            "new_disabled": int(getattr(self, "new_disabled", 0)),
            "childhood_poverty_years": float(A["poverty_years"][alive & (A["age"] < 18)].mean())
                                       if (alive & (A["age"] < 18)).any() else 0.0,
            "unemployment_rate": float((A["involuntary"] & ch & (st == NONWORK)).sum()
                                       / max(1, (ch & (working | A["involuntary"])).sum())),
            "voluntary_nonwork_share": float((ch & (st == NONWORK) & ~A["involuntary"]).sum() / ch.sum()),
            "independent_workers": int((ch & independent).sum()),
            "students": int((alive & (A["studying"] > 0)).sum()),
            "students_full_time": int((alive & (A["studying"] > 0) & (st == NONWORK)).sum()),
            "new_students": int(getattr(self, "new_students", 0)),
            "graduates": int(getattr(self, "graduates", 0)),
            "tertiary_share_16_74": float((A["education"][ch] == 2).mean()),
            "independent_share": float((ch & independent).sum() / ch.sum()),
            "independent_creative": int((ch & independent & creative_prof).sum()),
            "activity_rate_16_74": float(((working | independent)[ch]).mean()),
            "part_time_share": float((st[ch] == PART).sum() / max(1, np.isin(st[ch], [PART, FULL]).sum())),
            "baseline_workers_stopped": float((st[w0] == NONWORK).mean()) if w0.any() else 0.0,
            "involuntary_unemployed": int((A["involuntary"] & alive).sum()),
            "new_ventures": int(founders_new),
            "gambling_abroad_bn": float(getattr(self, "gambling_abroad_bn", 0.0)) / max(self.price, .1),
            "firms_alive": int(self.firms["alive"].sum()),
            "venture_jobs": float(self.firms["jobs"][self.firms["alive"]].sum()),
            "emigrants": emig["total"], "emigrants_children": emig["children"],
            "immigrants_children": self.imm_children, "emigrants_icelandic": emig["icelandic"],
            "emigrants_young_graduates": emig.get("young_graduates", 0),
            "immigrants": sum(imm.values()), **{f"imm_{k}": v for k, v in imm.items()},
            "births": births, "deaths": deaths,
            "price_level": float(self.price),
            "vacancy_rate": float(getattr(self, "vacancy_rate", 0.0)),
            "severance_bn": float(getattr(self, "severance_bn", 0.0)),
            "contract_years_mean": float(np.mean(np.maximum(A["contract_end"][alive & np.isin(st, [PART, FULL])] - self.year, 0)))
                                   if (alive & np.isin(st, [PART, FULL])).any() else 0.0,
            "short_contract_share": float(np.mean(np.maximum(A["contract_end"][alive & np.isin(st, [PART, FULL])] - self.year, 0) <= 1))
                                    if (alive & np.isin(st, [PART, FULL])).any() else 0.0,
            "new_contract_wage_index": float((self.omega_new * (self.D0_pub + self.D0_priv)).sum()
                                             / (self.D0_pub + self.D0_priv).sum()),
            **{f"newpay_{OCCUPATIONS[o]}": float(self.omega_new[o] / self.price) for o in range(N_OCC)},
            **{f"sector_{k}": float(v) for k, v in self.sectors.state.items()},
            "fisheries_fund_real_bn": getattr(self, "ff_fc", 0.0) * self.macro.e / max(self.price, .1),
            "fisheries_dividend_bn": getattr(self, "ff_paid_fc", 0.0) * self.macro.e,
            "transition_share": float(self.p["policy"].get("transition_share", 1.0)),
            **self.wealth_snapshot(),
            **self.automation.snapshot(),
            **careers.snapshot(self),
            **familycare.snapshot(self),
            **pensions.snapshot(self), **capital.snapshot(self.macro), **hours.snapshot(self), **financial.snapshot(self), **regions.snapshot(self),
            **{f"public_equity_{k}": float(v) for k, v in getattr(self, "public_equity", {}).items()},
            "deemed_fund_m": self.deemed_fund() / 1e6 if self.p["policy"]["regime"] == "platform" else 0.0,
            "machine_income_bn": float(self.automation.machine_income / max(self.price, .1)),   # 2025 krónur
            **self.welfare_snapshot(),
            **self.crime_now(),
            **self.emissions_snapshot(),
            **self.structure_snapshot(),
            **self.distribution_snapshot(),
            **self.incentive_snapshot(self.per_mother_now),
            **self.housing_snapshot(),
            **self.churn_snapshot(),
            **self.profession_snapshot(),
            **self.family_snapshot(),
            **{f"frontier_{k}": float(v) for k, v in self.frontier.state.items() if isinstance(v, (int, float))},
            **{f"infra_{k}": float(v) for k, v in self.infra.state.items() if isinstance(v, (int, float))},
            "infra_projects_running": len(self.infra.state["active"]),
            "infra_projects_open": len(self.infra.state["finished"]),
            **{k: float(v) for k, v in self.macro.snapshot().items()},
            "balance_bn": float(bal), "agent_change_bn": float(change),
            "static_total_bn": float(sum(static.values())) if static else 0.0,
            **{f"static_{k}": float(v) for k, v in (static or {}).items()},
            # the balance once inflation's erosion of the non-indexed debt is counted: interest carries the
            # inflation premium, so the conventional balance depends on the inflation rate and this one does not
            "balance_operational_bn": float(bal + self.macro.erosion_bn),
            **{f"acc_{k}": float(v / acc["price"] if k in NOMINAL_FLOWS else v)
               for k, v in acc.items() if not isinstance(v, list)},
            **{f"supply_{OCCUPATIONS[o]}": float(acc["occ_supply"][o]) for o in range(N_OCC)},
            **{f"wage_{OCCUPATIONS[o]}": float(self.omega[o]) for o in range(N_OCC)},
        }
        for ci, name in enumerate(CHARACTERS):
            m = alive & (A["character"] == ci) & A["worker0"] & A["chooser"]
            out[f"stopped_{name}"] = float((st[m] == NONWORK).mean()) if m.any() else np.nan
        return out

    def run(self, years=None):
        for _ in range(years or self.p["years"]):
            self.step()
        return self.history


# Account flows built in 2025 krónur; accounts() converts them to today's.
REAL_FLOWS = ("corporate_tax", "state_equity", "public_equity_dividends", "seed_money", "property_tax", "fund_returns", "fisheries_fee",
              "energy_dividend_change", "windfall_take", "contract_compensation", "education_cost", "health_cost", "crime_cost",
              "schooling_cost", "wealth_tax", "retraining_cost", "childcare_cost", "public_housing_cost",
              "frontier_capex", "infrastructure_capex", "frontier_return", "corporate_tax_economy",
              "sovereign_fund_return")
# Every flow, all in today's krónur once accounts() is done; snapshots report them in 2025 krónur.
NOMINAL_FLOWS = set(REAL_FLOWS) | {
    "income_tax", "social_security", "payroll_tax", "vat", "benefits", "child_payments", "ubi_adult",
    "pension_topup", "public_payroll", "child_invested", "occupational_pensions", "ubi_saved", "sick_pay_saved",
    "leave_saved",
    "benefit_old_age", "benefit_disability", "benefit_unemployment",
    "benefit_social_assistance", "benefit_housing_benefit", "benefit_fund_disability",
    "automation_tax", "automation_levy", "automation_dividends", "automation_stake_cost", "machine_income", "revenue", "expenditure",
    "inheritance_tax", "capital_income_tax", "income_shifted_tax", "top_income_lost", "automation_subsidy",
    "junior_subsidy", "machine_dividends", "pension_fund_support", "pension_special_saved",
    "informal_tax_change", "hidden_earnings", "hidden_earnings_sq"}

# Everything calibrate() fixes as a year-0 reference. Several are read with a fallback while calibration is still
# running, which is right there and wrong afterwards: a society cached before one of these was added would carry
# on without it, quietly using the current value as its own baseline. That froze the schooling bill for a whole
# build. So a scenario refuses to start unless every one is present.
BASELINES = ("accounts0", "median0", "wellbeing0", "children0", "crime0", "health0", "hardship0", "child_poverty0",
             "real_wage0", "guaranteed_share0", "omega0", "occ_mix0", "birth_penalty0",
             "pop0", "pop_total0", "supply0", "per_child0", "hh_income0", "family_mobility",
             "separation_rate", "exp_rate0")


def scenario(base_society, overrides):
    """Copy a calibrated status-quo society and apply scenario overrides."""
    missing = [b for b in BASELINES if getattr(base_society, b, None) is None]
    if missing:
        raise RuntimeError(f"calibrated society lacks {', '.join(missing)} — it predates the code; recalibrate")
    soc = copy.deepcopy(base_society)
    soc.set_policy(overrides)
    soc.history = []
    soc.own_history = []
    soc.year = 0
    return soc
