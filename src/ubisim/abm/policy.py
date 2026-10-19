"""Tax-benefit rules, vectorised. Monthly ISK. Two regimes: status_quo (2026 rules) and platform."""
import numpy as np

from ubisim.abm.population import EEA, NON_EEA


def income_tax(taxable, brackets, credit=0.0, scale=1.0):
    tax = np.zeros_like(taxable, dtype=float)
    for (lo, rate), nxt in zip(brackets, [b[0] for b in brackets[1:]] + [np.inf]):
        tax += rate * scale * np.clip(taxable - lo, 0, nxt - lo)
    return np.maximum(tax - credit, 0.0)


def threshold_price(pol, price):
    """What the tax thresholds and the personal credit are multiplied by. Since 2022 both move each January with
    the CPI plus an estimate of long-run productivity growth, set at 1% (lög nr. 90/2003, as amended; reviewed
    every five years). Indexed to prices alone, real growth pushed everyone up the brackets year after year and
    the thirty-year budget ran into a surplus the law does not produce (found 2026-10-01)."""
    return price * pol.get("threshold_index", 1.0)


def housing_benefit(A, idx, taxable, partner_income, ben, bx):
    """Húsnæðisbætur for a renting household (law 75/2016): the base amount for its size less 9% of the household's
    income above the limit for that size, paid once per household — to a woman in a couple or to anyone living
    alone — and not taxed. At these amounts the 75%-of-rent cap rarely binds, so rents are not needed for it."""
    if "renter" not in A or "partner" not in A:
        return np.zeros(len(idx))
    partner = A["partner"][idx]
    payee = A["renter"][idx] & ((partner < 0) | (A["sex"][idx] == 1)) & (A["age"][idx] >= 18)
    kids = A["kids_home"][idx] if "kids_home" in A else np.zeros(len(idx))
    size = np.clip(1 + (partner >= 0) + kids, 1, 6).astype(int) - 1
    base = np.array(ben["housing_benefit_base_year"], float)[size] * bx / 12
    limit = np.array(ben["housing_benefit_limit_year"], float)[size] * bx / 12
    income = taxable + np.where(partner >= 0, partner_income, 0)
    amount = np.maximum(0, base - ben["housing_benefit_reduction"] * np.maximum(0, income - limit))
    # assets above the limit cut the benefit in proportion, to nothing at a quarter above it (Húsnæðis- og mannvirkjastofnun / ráðuneyti 2026)
    over = np.maximum(0, A["wealth"][idx] * bx / ben["housing_benefit_asset_limit"] - 1)
    amount = amount * np.clip(1 - 4 * over, 0, 1)
    # The model's renters are people, not dwellings: young adults who live with their parents or share a flat are
    # renters here, where one benefit is paid per dwelling against every adult's income, and some who could claim do
    # not. A fixed share of renters claims, the same people every year (golden-ratio draw on the agent's index).
    claims = (idx * 0.6180339887498949) % 1.0 < ben["housing_benefit_claim_share"]
    return np.where(payee & claims, amount, 0)


def ubi_eligible(A, idx, working, pol):
    """Adult UBI eligibility. EEA arrivals need worker status until permanent residence (Danish SU model)."""
    cit, yrs, age = A["citizenship"][idx], A["years_in_iceland"][idx], A["age"][idx]
    ok = age >= 18
    eea_new = (cit == EEA) & (yrs < pol["eea_years_to_permanent"])
    ok &= ~eea_new | working | A["involuntary"][idx]
    ok &= ~((cit == NON_EEA) & (yrs < pol["non_eea_years_to_ubi"]))
    return ok


def invested_share(pol):
    """How much of each child's payment goes into their fund rather than to the household, by birth order.

    Two ways of setting it. The graduated schedule invests more of each additional child's payment, which is a
    guard against a household living off its children. A flat share treats every child alike, which removes that
    guard deliberately: at 50% invested, five children bring in five times 225,000 a month with nothing taken
    back. The fertility response to that is the model's to answer, not an assumption to bury in a schedule.
    """
    flat = pol.get("child_invested_flat")
    if flat is not None and flat >= 0:
        return np.full(8, float(flat))
    return np.array([pol["child_invested"].get(k, pol["child_invested"][7]) for k in range(0, 8)])


def moved_out(A, idx, p):
    """16- and 17-year-olds living on their own (a reform option): they are paid their whole borgaralaun
    themselves, nothing more goes into their fund, and they still get what is in it at 25.

    Who moves out is a fixed share of each cohort (EST), picked by a hash of the agent so it takes no draw from the
    model's random stream. Today few do; the share is a scenario setting, not a finding."""
    pol = p["policy"]
    if pol["regime"] != "platform":
        return np.zeros(len(idx), bool)
    age = A["age"][idx]
    return (age >= 16) & (age < 18) & ((np.asarray(idx) * 40503 % 1000) < pol.get("teen_moveout_share", 0.0) * 1000)


def child_usable_ubi(A, p):
    """Monthly usable child UBI per mother (platform). Teenagers who have moved out are paid their own."""
    pol = p["policy"]
    kids = np.flatnonzero((A["mother"] >= 0) & (A["age"] < 18) & A["alive"])
    away = moved_out(A, kids, p)
    inv = invested_share(pol)
    order = np.clip(A["birth_order"][kids], 1, 7)
    inv_k = np.where(away, 0.0, inv[order])
    usable = (1 - inv_k) * pol["ubi_child"]
    home = ~away
    out = np.bincount(A["mother"][kids[home]], weights=usable[home], minlength=len(A["age"]))
    invested = (inv_k * pol["ubi_child"]).sum()
    return out, invested, len(kids) * pol["ubi_child"]


def net_income(A, idx, gross_wage, working, p, partner_income=None, price=1.0, benefit_index=None):
    """Net monthly income, with any dividend from a resource fund (`policy.citizen_dividend`, set each year by
    model.fisheries_fund_start): the same untaxed amount to every adult, under either system."""
    out = _net_income(A, idx, gross_wage, working, p, partner_income, price, benefit_index)
    # Capital income, under either system, after the 22% capital income tax above the yearly allowance (v9). It
    # was left out of net income and entered only Tryggingastofnun's tests (found in an external review of v8, 2026-10).
    ci = capital_income(A, idx, p, price)
    if ci is not None:
        ben = p["benefits"]
        ctax = ben["capital_income_tax"] * np.maximum(0.0, ci - ben["capital_income_allowance_year"] / 12 * price)
        out["net"] = out["net"] + ci - ctax
        out["capital_income"], out["capital_tax"] = ci, ctax
    # v10: the lifetime income from equity released by selling a home and buying a cheaper one (housing.py); held in
    # 2025 krónur. Mostly a return of the buyer's own capital, so untaxed (EST), and outside the benefit tests
    if "equity_annuity" in A:
        ea = A["equity_annuity"][idx] * price
        out["net"] = out["net"] + ea
        out["equity_annuity"] = ea
    div = p["policy"].get("citizen_dividend", 0.0)
    if div:
        paid = np.where(A["age"][idx] >= 18, div, 0.0)
        out["net"] = out["net"] + paid
        out["dividend"] = paid
    return out


def capital_income(A, idx, p, price):
    """Monthly capital income: each person's savings at the yield the tax returns give them (population.py,
    assign_capital_income). None for a population built before v9."""
    if "capital_income_rate" not in A:
        return None
    return A["wealth"][idx] * A["capital_income_rate"][idx] * price / 12


def interest_rebate(A, idx, taxable, ci, ben, bx):
    """Vaxtabætur (lög 90/2003, 68. gr. B), per person; a couple holds half the debt and has half the caps: eligible
    interest is the least of what is paid, 7% of the housing debt and the cap, less 8.5% of income including capital
    income; withdrawn as net wealth passes its limit, gone at 60% above it. About 1.1-1.6 ma.kr. a year."""
    if "mortgage_debt" not in A:
        return np.zeros(len(idx))
    debt = A["mortgage_debt"][idx] * bx
    couple = A["partner"][idx] >= 0
    half = np.where(couple, .5, 1.0)
    interest = debt * ben["mortgage_interest_rate"]
    eligible = np.minimum(np.minimum(interest, ben["interest_rebate_debt_share"] * debt),
                          np.where(couple, ben["interest_rebate_max_interest_couple"] * half,
                                   ben["interest_rebate_max_interest_single"]))
    year_income = (taxable + (ci if ci is not None else 0.0)) * 12
    rebate = np.minimum(np.maximum(0.0, eligible - ben["interest_rebate_income_rate"] * year_income),
                        np.where(couple, ben["interest_rebate_max_couple"] * half, ben["interest_rebate_max_single"]))
    net_worth = (A["wealth"][idx] + A["home_value"][idx] - A["mortgage_debt"][idx]) * bx
    limit = np.where(couple, ben["interest_rebate_asset_limit_couple"] * half, ben["interest_rebate_asset_limit_single"])
    phase = np.clip(1 - np.maximum(0.0, net_worth - limit) / (.6 * limit), 0, 1)
    return np.where(debt > 0, rebate * phase / 12, 0.0)


def _net_income(A, idx, gross_wage, working, p, partner_income=None, price=1.0, benefit_index=None):
    """Net monthly income. `price` indexes everything set in krónur — tax thresholds, the personal credit, benefit
    levels and the UBI — because Iceland adjusts all of them annually. Leaving them fixed while prices rise is
    fiscal drag the country does not actually have, and it quietly erodes every benefit in the model.
    """
    """Own monthly net income (after tax and transfers, excluding child transfers) for agents idx
    earning gross_wage. Returns dict of components (arrays)."""
    pol, ben = p["policy"], p["benefits"]
    # Benefits are not indexed to prices alone. Lög um almannatryggingar (69. gr.) says they shall be set each
    # year with regard to how wages have moved, and never by less than prices — and in practice they have
    # followed wages. Indexing them to prices only makes relative poverty climb in the status quo for no reason
    # but the arithmetic, which flatters any reform compared against it (found 2026-09-20: hardship nearly
    # doubled and child poverty rose 5 points over ten years with no policy change at all).
    # set at the start of the year (model.benefit_index), never below the price level expected then
    bx = price if benefit_index is None else benefit_index
    ben = {k: (v * bx if isinstance(v, (int, float)) and abs(v) > 1000 else v) for k, v in ben.items()}
    age, disabled = A["age"][idx], A["disabled"][idx]
    # set at retirement in 2025 krónur; Icelandic pension-fund pensions are CPI-indexed, so pay them in today's
    # krónur. Left unindexed, every pensioner lost the inflation rate in real income every year.
    occ_pen = A["occ_pension"][idx] * price
    zero = np.zeros(len(idx))
    if pol["regime"] == "status_quo":
        contrib = gross_wage * pol["pension_contrib_employee"]
        retired = age >= 67
        single = (A["partner"][idx] < 0) if "partner" in A else np.zeros(len(idx), bool)
        # the household supplement goes to those LIVING alone (law 99/2007, 8. gr.), not to everyone without a
        # partner: v8 paid it to 52% of those 67+, about 7 ma.kr. too much (found in an external review of v8, 2026-10)
        alone = A["lives_alone"][idx] if "lives_alone" in A else single
        pinc = partner_income if partner_income is not None else zero
        # old age: Tryggingastofnun's pension against pension-fund and other income above the general disregard and
        # earnings above the earnings disregard; the household supplement for those living alone
        # Capital income counts in full in both tests (law 100/2007, 16. gr.): from v9 as the tax returns have it.
        ci = capital_income(A, idx, p, price)
        capital_inc = ci if ci is not None else A["wealth"][idx] * price * ben["tr_capital_return"] / 12
        countable_oa = np.maximum(0, occ_pen + capital_inc - ben["tr_general_exemption"]) \
            + np.maximum(0, gross_wage - ben["tr_work_exemption"])
        # the pension is earned by residence, 16-67: full after 40 years, pro rata for those who came later
        resid = np.where(A["immigrant"][idx], np.clip(A["years_in_iceland"][idx] / ben["tr_full_residence_years"],
                                                       0, 1), 1.0)
        tr = np.where(retired, np.maximum(0, ben["tr_old_age_full"] * resid - ben["tr_clawback"] * countable_oa), 0)
        hs_oa = np.where(retired & alone, np.maximum(0, ben["household_supplement_old_age"] * resid
                                                     - ben["household_supplement_old_age_withdrawal"] * countable_oa), 0)
        # disability (the new system): a full pension, or a partial one for those who also work; the pension funds'
        # disability pensions on top; one general disregard on all income and an earnings disregard for the partial
        dis = disabled & ~retired
        fund_dis = np.where(dis, A["base_wage"][idx] * price * ben["fund_disability_replacement"]
                            * np.where(working, .5, 1.0), 0)
        partial = dis & working
        amount = np.where(partial, ben["disability_partial"], ben["disability_pension"])
        earned = np.maximum(0, gross_wage - np.where(partial, ben["disability_earned_disregard"], 0))
        countable_d = np.maximum(0, earned + fund_dis + capital_inc - ben["disability_general_disregard"])
        dp = np.where(dis, np.maximum(0, amount - ben["tr_clawback"] * countable_d), 0)
        hs_dis = np.where(dis & alone, np.maximum(0, ben["household_supplement_disability"] - np.maximum(
            0, ben["household_supplement_disability_withdrawal"] * countable_d - amount)), 0)
        # Working age, not working: those who lost a job and seek another have unemployment benefit — individual,
        # and at 70% of prior pay (capped) for the first three months; everyone else has only the municipalities'
        # social assistance, residual and tested on the household's income. Studying is not covered by either.
        prime = (~working) & ~retired & ~disabled & (age >= 18)
        studying = (A["studying"][idx] > 0) if "studying" in A else np.zeros(len(idx), bool)
        seeking = A["involuntary"][idx] if "involuntary" in A else np.zeros(len(idx), bool)
        prior = np.clip(ben["unemployment_replacement"] * A["base_wage"][idx] * price,
                        ben["unemployment_basic"], ben["unemployment_income_related_cap"])
        ub = np.where(prime & seeking, ben["unemployment_basic"] + ben["unemployment_income_related_share"]
                      * (prior - ben["unemployment_basic"]), 0)
        # Someone who stops working by choice: the assistance is means-tested on savings, switched off as before
        # (nonwork_asset_limit_months; the choice model has no drawing on savings), and on the household's income.
        limit = ben.get("nonwork_asset_limit_months", 0.0) * ben["social_assistance_single"]
        means = (A["wealth"][idx] * price <= limit) if limit > 0 else np.ones(len(idx), bool)
        spread = A["support_factor"][idx] if "support_factor" in A else 1.0
        has_partner = ~single
        couple_left = np.maximum(0, ben["social_assistance_couple"] - pinc)
        # a couple both out of work share the couple's amount; with a partner earning, what the couple's amount
        # leaves after the partner's income
        # someone living with their parents (here, as for their costs, under 20 with no partner) has half the single
        # amount (Reykjavík's rules, 11. gr.); the parents' home is not a household of their own
        at_home = (age < 20) & ~has_partner
        sa_amount = np.where(has_partner, np.where(pinc > 0, couple_left, ben["social_assistance_couple"] / 2),
                             ben["social_assistance_single"] * np.where(at_home, .5, 1.0)) * spread
        # It is conditional on seeking work: someone able to work who turns work down has it cut to half (Reykjavík's
        # rules, 4. gr.). In the model everyone it reaches has stopped working by choice. Paid in full, it was a
        # 260,000 basic income for leaving work: the young left work at 1.5 points a year and the bill doubled in six
        # years, where the record has some 2,700 recipients (PAYE 2023) and no such drift (found 2026-10-04).
        sa = np.where(prime & ~seeking & ~studying & means, sa_amount * (1 - ben["social_assistance_refusal_cut"]), 0)
        support = ub + sa
        occ = np.where(retired, occ_pen, 0) + fund_dis
        hs = hs_oa + hs_dis
        taxable = gross_wage - contrib + tr + dp + hs + support + occ
        tp = threshold_price(pol, price)
        tax = income_tax(taxable, [[lo * tp, r] for lo, r in pol["income_tax_brackets"]],
                         pol["personal_credit"] * tp)
        hb = housing_benefit(A, idx, taxable, pinc, ben, bx)
        ir = interest_rebate(A, idx, taxable, capital_inc, ben, bx) if "interest_rebate_max_single" in ben else zero
        hb = hb + ir      # paid with housing support in the accounts; reported apart in parts
        return {"net": taxable - tax + hb, "tax": tax, "employee_contrib": contrib,
                "benefits": tr + dp + hs + support + hb, "ubi": zero, "ubi_saved": zero, "occ_pension": occ,
                "topup": zero, "parts": {"old_age": tr + hs_oa, "disability": dp + hs_dis,
                                         "unemployment": ub, "social_assistance": sa, "housing_benefit": hb - ir, "interest_rebate": ir,
                                         "fund_disability": fund_dis}}
    # the reform
    fold = pol.get("pension_fold", 1.0)
    contrib = gross_wage * employee_rate(p)
    ubi = np.where(ubi_eligible(A, idx, working, pol), pol["ubi_adult"], 0.0)   # already nominal
    if pol.get("ubi_taper_rate", 0) > 0:   # withdraw the UBI above an earnings threshold
        ubi = np.maximum(0.0, ubi - pol["ubi_taper_rate"] * np.maximum(0.0, gross_wage - pol["ubi_taper_start"] * price))
    # optional forced saving: part of working-age adults' UBI goes to a personal account instead of spending
    saved = ubi * np.where((age >= 18) & (age < 67), pol.get("adult_ubi_invested", 0.0), 0.0)
    # folded: the funds stop paying and the state tops up anyone whose pension beat the UBI; not folded: the
    # funds keep paying occupational pensions, on top of the UBI
    # v9 option: contributions become social security, but the funds go on paying the pensions
    # already earned, out of their assets — no top-up, no rights cancelled (policy.pension_keep_earned)
    keep = pol.get("pension_keep_earned", 0.0)
    topup = np.where(age >= 67, np.maximum(0, occ_pen - pol["ubi_adult"]) * pol["pension_topup_share"], 0) * fold \
        * (1 - keep)
    occ = np.where(age >= 67, occ_pen, 0) * (1 - fold * (1 - keep))
    # the pension funds' disability pensions continue as far as the funds are not folded into the scheme
    dis_young = disabled & (age < 67)
    occ = occ + np.where(dis_young, A["base_wage"][idx] * price * ben["fund_disability_replacement"]
                         * np.where(working, .5, 1.0), 0) * (1 - fold * (1 - keep))
    taxable = gross_wage - contrib + topup + occ
    brackets = pol.get("platform_income_tax_brackets") or pol["income_tax_brackets"]
    tp = threshold_price(pol, price)
    tax = income_tax(taxable, [[lo * tp, r] for lo, r in brackets],
                     pol.get("platform_personal_credit", 0.0) * tp, pol["platform_income_tax_scale"])
    net = taxable - tax + ubi - saved
    # Nobody on a disability or old-age pension below what today's system pays them: a 300 þús. payment is less
    # than the disability pension (430 þús. taxed, about 370 net) and a little less than a full Tryggingastofnun
    # pension, so without this the people least able to work are the ones the reform leaves worse off. The
    # top-up is the gap to today's net income for the same person on the same earnings, untaxed like the payment;
    # `benefit_floor_topup` is the share of the gap closed. It withdraws as earnings rise, as today's pensions do.
    floor = pol.get("benefit_floor_topup", 0.0)
    # While the reform phases in (policy.transition_years), anyone today's system pays a benefit keeps the share of
    # their loss not yet phased in: 2/3 of it in the first year of three, 1/3 in the second.
    protect = 1.0 - pol.get("transition_share", 1.0)
    floor_paid = zero
    if floor or protect > 0:
        covered = disabled | (age >= 67)
        if covered.any() or protect > 0:
            today = {**p, "policy": {**pol, "regime": "status_quo"}}
            sq = _net_income(A, idx, gross_wage, working, today, partner_income, price, benefit_index)
            share = np.where(covered, max(floor, protect), protect)
            floor_paid = np.where(sq["benefits"] > 0, share * np.maximum(0.0, sq["net"] - net), 0.0)
            net = net + floor_paid
    return {"net": net, "tax": tax, "employee_contrib": contrib, "benefits": floor_paid,
            "ubi": ubi, "ubi_saved": saved, "occ_pension": occ, "topup": topup}


def employer_rate(p):
    """What employers pay on wages besides payroll tax: pension contributions today, social security under the
    platform, and a blend as far as the pension system is folded in."""
    pol = p["policy"]
    if pol["regime"] == "status_quo":
        return pol["pension_contrib_employer"]
    f = pol.get("pension_fold", 1.0)
    return f * pol["social_security_employer"] + (1 - f) * pol["pension_contrib_employer"] \
        + pol.get("employer_leave_cost_share", 0.0)


def employee_rate(p):
    pol = p["policy"]
    if pol["regime"] == "status_quo":
        return pol["pension_contrib_employee"]
    f = pol.get("pension_fold", 1.0)
    return f * pol["social_security_employee"] + (1 - f) * pol["pension_contrib_employee"]


def state_contribution_share(p):
    """Share of wage contributions that reach the state as social security; the rest go to the pension funds."""
    pol = p["policy"]
    if pol["regime"] == "status_quo":
        return 0.0
    f = pol.get("pension_fold", 1.0)
    ss = pol["social_security_employee"] + pol["social_security_employer"]
    total = employee_rate(p) + employer_rate(p)
    return f * ss / total if total else 0.0


def vat_rate(p):
    pol = p["policy"]
    # The reform's rate is the statutory one; it reaches less than all of consumption (vat_platform_capture)
    return pol["vat_effective_status_quo"] if pol["regime"] == "status_quo" \
        else pol["vat_platform"] * pol.get("vat_platform_capture", 1.0)


def housing_cost(A, idx, p, rent_index=1.0, mortgage_factor=None, owner_tax=0.0):
    """Monthly housing cost of the household of each agent in idx, in 2025 krónur: rent, or the mortgage and
    upkeep, plus any change in property tax when it is asked for."""
    c = p["costs"]
    kids = A["n_kids"][idx]
    housing = np.where(A["renter"][idx], np.where(A["capital"][idx], c["housing_renter_capital"], c["housing_renter_other"]),
                       np.where(A["mortgage"][idx], c["housing_owner_mortgage"], c["housing_owner_outright"]))
    # renters pay market rents; mortgage holders feel part of it (indexed loans, refinancing)
    mortgage_factor = 1 + .3 * (rent_index - 1) if mortgage_factor is None else mortgage_factor
    # v10: a renter pays the rent of the size it lives in on the housing ladder (housing.update_segments)
    rf = p.get("housing_segments", {}).get("_rent_factor")
    if rf is not None and "hclass" in A:
        cls = A["hclass"][idx]
        rent_index = rent_index * np.where(cls >= 0, np.asarray(rf)[np.maximum(cls, 0)], 1.0)
    housing = housing * (1 + .15 * kids) * np.where(A["renter"][idx], rent_index,
                                                    np.where(A["mortgage"][idx], mortgage_factor, 1.0))
    return housing + np.where(A["renter"][idx], 0.0, owner_tax)


def household_costs(A, idx, p, rent_index=1.0, mortgage_factor=None, owner_tax=0.0, pooled=True):
    """Monthly essential costs c_min and equivalence scale for the household of each agent in idx."""
    c = p["costs"]
    age, partner = A["age"][idx], A["partner"][idx]
    kids = A["n_kids"][idx]
    has_p = partner >= 0
    # the modified OECD scale, as Eurostat's poverty rates use it: .5 for each person 14 or over, .3 under 14.
    # At .3 for every child the needs of families with teenagers were understated, and child poverty with them.
    teens = A["n_teens"][idx] if "n_teens" in A else 0
    equiv = 1 + .5 * has_p + .3 * (kids - teens) + .5 * teens
    basic = c["basic_single"] * equiv
    housing = housing_cost(A, idx, p, rent_index, mortgage_factor, owner_tax)
    at_home = (age < 20) & ~has_p
    cmin = np.where(at_home, c["living_with_parents"], basic + housing)
    equiv = np.where(at_home, 1.0, equiv)
    # v9: a single person of 67+ living with a younger household, or a young adult living with their parents
    # (population.assign_living_arrangements), is part of it for poverty and hardship: half an adult more in its
    # scale and its budget, and the guest has the household's scale and budget. For the choice of work (pooled=False)
    # each weighs their own unit: a young adult at home what living with parents costs, an older guest their own
    # basic costs without rent (pooling the choice as well took the labour-supply calibration to
    # its bound, 2026-10-12).
    if "host" in A and not pooled:
        g = A["host"][idx] >= 0
        if g.any():
            cmin = np.where(g, np.where(age < 30, c["living_with_parents"], c["basic_single"]), cmin)
            equiv = np.where(g, 1.0, equiv)
        return cmin, equiv
    if "host" in A:
        host = A["host"]
        N = len(host)
        guests = np.flatnonzero(host >= 0)
        n_g = np.bincount(host[guests], minlength=N).astype(float)
        mine = n_g[idx] + np.where(has_p, n_g[np.where(has_p, partner, 0)], 0.0)
        equiv = equiv + .5 * mine
        cmin = cmin + .5 * c["basic_single"] * mine
        g = host[idx] >= 0
        if g.any():
            cm_h, eq_h = household_costs(A, host[idx][g], p, rent_index, mortgage_factor, owner_tax)
            cmin[g], equiv[g] = cm_h, eq_h
    return cmin, equiv
