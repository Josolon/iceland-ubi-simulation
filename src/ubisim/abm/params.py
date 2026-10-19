"""Default parameters for the agent-based model. Scenario YAML files override any subset.

Amounts are ISK per month unless noted. EST marks an estimate awaiting better data.
"""
import copy
import json
import pathlib

import yaml

GROUPS = ["Managers", "Professionals", "Associate professionals", "Clerks", "Service and sales",
          "Agriculture and fishery", "Craft and trades", "Plant and machine operators", "Elementary"]

# The labour market clears profession by profession. Professions, their pay and their size come from the wage
# survey (VIN02001, 2025) via data_prep; how pleasant and how meaningful the work is are EST judgements here.
PROFESSION_TRAITS = {                     # name: (disamenity, meaning, minimum education 0-2)
    "Managers":                         (.25, .60, 1),
    "Doctors":                          (.45, .80, 2),
    "Nurses and midwives":              (.55, .80, 2),
    "Primary and pre-school teachers":  (.45, .75, 2),
    "Secondary teachers":               (.35, .70, 2),
    "Academics":                        (.20, .80, 2),
    "Lawyers":                          (.30, .45, 2),
    "Engineers and IT":                 (.20, .60, 2),
    "Artists and writers":              (.20, .90, 0),
    "Business professionals":           (.25, .45, 1),
    "Other professionals":              (.25, .60, 2),
    "Pilots, officers and controllers": (.45, .65, 1),
    "Other associate professionals":    (.25, .50, 1),
    "Clerks":                           (.40, .35, 0),
    "Child-care workers":               (.45, .75, 0),
    "Care assistants":                  (.60, .75, 0),
    "Cooks":                            (.55, .55, 0),
    "Waiters and bar staff":            (.55, .40, 0),
    "Retail and other service":         (.45, .40, 0),
    "Fishers and farm workers":         (.70, .55, 0),
    "Fish processing workers":          (.75, .35, 0),
    "Other craft and trades":           (.35, .60, 0),
    "Bus and truck drivers":            (.50, .40, 0),
    "Other machine operators":          (.60, .30, 0),
    "Cleaners":                         (.75, .25, 0),
    "Refuse collectors":                (.90, .30, 0),
    "Other elementary":                 (.70, .30, 0),
}
_BASELINE = pathlib.Path(__file__).resolve().parents[3] / "data/processed/baseline_2025.json"
PROFESSIONS = json.loads(_BASELINE.read_text())["professions_2025"] if _BASELINE.exists() else []
OCCUPATIONS = [pr["name"] for pr in PROFESSIONS]
PROF_GROUP = [pr["group"] for pr in PROFESSIONS]
N_OCC = len(OCCUPATIONS)


_pay_by_name = {pr["name"]: (pr["median_earnings"] or 0) for pr in PROFESSIONS}
_median_pay = sorted(v for v in _pay_by_name.values() if v)[len([v for v in _pay_by_name.values() if v]) // 2] if PROFESSIONS else 0
# "unpleasant work": rated hard or dirty AND paid below the middle of the pay ladder
HARSH = [n for n in OCCUPATIONS
         if PROFESSION_TRAITS.get(n, (0, 0, 0))[0] >= .55 and _pay_by_name.get(n, 0) <= _median_pay]
_pay = sorted((pr["median_earnings"] or 0) for pr in PROFESSIONS)
TOP_PAID = [pr["name"] for pr in PROFESSIONS
            if (pr["median_earnings"] or 0) >= (_pay[int(len(_pay) * .75)] if _pay else 0)]


def by_group(group_values):
    """Expand a 9-long group array to one value per profession."""
    return [group_values[g] for g in PROF_GROUP]


def by_name(mapping, default=0.0):
    """Build a profession-length vector from {profession name: value}."""
    return [mapping.get(name, default) for name in OCCUPATIONS]


def expand_mix(group_mix, weights):
    """Spread a 9-group mix across professions in proportion to how many people work in each."""
    out = []
    for i, g in enumerate(PROF_GROUP):
        same = [j for j, gg in enumerate(PROF_GROUP) if gg == g]
        total = sum(weights[j] for j in same) or 1.0
        out.append(group_mix[g] * weights[i] / total)
    total = sum(out) or 1.0
    return [v / total for v in out]


CREATIVE_PROFESSIONS = ["Artists and writers", "Academics", "Other professionals", "Secondary teachers"]

# Work society needs a certain amount of, whatever it pays: bins emptied, buses driven, children taught and
# nursed. Demand follows the driver, not the wage, so cheap labour does not create extra jobs out of nothing.
NEEDS_DRIVEN = {
    "Refuse collectors":               ("population", .05),
    "Cleaners":                        ("population", .25),
    "Bus and truck drivers":           ("population", .15),
    "Nurses and midwives":             ("elderly", .05),
    "Doctors":                         ("elderly", .05),
    "Care assistants":                 ("elderly", .10),
    "Child-care workers":              ("children_1_5", .05),
    "Primary and pre-school teachers": ("children_1_15", .05),
    "Secondary teachers":              ("children_1_15", .10),
    "Other elementary":                ("population", .35),
}

PUBLIC_SHARE_OVERRIDE = {                 # EST: professions that are overwhelmingly public or private
    "Doctors": .85, "Nurses and midwives": .85, "Primary and pre-school teachers": .95, "Secondary teachers": .90,
    "Academics": .90, "Care assistants": .80, "Child-care workers": .90, "Artists and writers": .35,
    "Lawyers": .25, "Engineers and IT": .15, "Business professionals": .10, "Pilots, officers and controllers": .10,
}


def trait(index):
    return [PROFESSION_TRAITS.get(name, (.4, .5, 0))[index] for name in OCCUPATIONS]

DEFAULTS = {
    "seed": 1,
    "years": 10,
    # The base year. Empty means 2025, the model's own. The backcast sets it to 2015 (history/base_2015.json):
    # year (which baseline_<year>.json to build the population from), the national figures the macro block starts
    # from (GDP0, C0, X0, M0, CA0, DEBT0, INTEREST0, PROPERTY_VALUE0, PROPERTY_TAX0, TARIFF0), the wage bill and
    # public payroll the population is scaled to, krona_scale (that year's price level against 2025, for the few
    # amounts written in krónur in the code) and static_scale (the reform's static budget lines, in proportion).
    "base": {},
    # A year in the past being walked through (the backcast): support in a crisis, in ma.kr. of the base year.
    "history": {},

    # ---------------------------------------------------------------- policy
    "policy": {
        "regime": "platform",            # "status_quo" | "platform"
        "ubi_adult": 300_000,
        "ubi_child": 300_000,
        "ubi_indexed": True,             # UBI follows consumer prices (lagged one year)
        "ubi_indexation": 1.0,           # share of price increases passed into the UBI (0 = fixed in krónur)
        "ubi_wage_indexation": 0.0,      # share of real wage growth passed into the UBI too (benefits: .8)
        "ubi_phase_in_years": 1,         # UBI rises linearly to its full level over this many years
        "transition_years": 3,           # v8: the payroll cut, pension fold and benefit protection phase over this
        "adult_ubi_invested": 0.0,       # share of working-age adults' UBI paid into a personal savings account
        "independent_earnings_share": .25,  # EST: what self-directed work earns, as a share of the person's wage
        "platform_personal_credit": 0.0, # monthly personal tax credit under the reform (persónuafsláttur abolished = 0)
        "platform_income_tax_brackets": None,  # [[threshold, rate], ...]; None = same brackets as today
        # The graduated schedule below invests more of each additional child's payment — a guard against a
        # household living off its children. Setting child_invested_flat overrides it with one share for every
        # child, which removes that guard on purpose: at .5, five children bring in 5 x 225,000 a month with
        # nothing taken back. Whether people then have children for a living is for the model to answer.
        "child_invested": {1: .5, 2: .5, 3: .6, 4: .7, 5: .7, 6: .8, 7: .9},
        "child_invested_flat": .5,
        # The fund is paid out at 25, to a home or to starting something — the age both decisions are made.
        "fund_payout_age": 25,
        # 16-17-year-olds living on their own, paid their borgaralaun in full (policy.moved_out). EST: about 3% of
        # the cohort; Hagstofa does not publish it directly. A scenario setting.
        "teen_moveout_share": .05,      # EST: 3% today, from troubled homes; a little more once the payment is theirs
        # The payout is the person's own money, to use as they like. Having it in hand makes
        # starting something easier, as a windfall does (Blanchflower and Oswald 1998: inheritances raise
        # self-employment); `fund_venture_decay` is how fast that advantage wears off as the money is used.
        "fund_venture_decay": .20,        # EST
        "fund_deposit_share": .15,        # a payout worth this much of a dwelling buys a way in
        "wage_setting": "free_market",   # "free_market" | "status_quo" (downward-rigid agreed wages)
        "income_tax_brackets": [[0, .3149], [498_122, .3799], [1_398_450, .4629]],
        "platform_income_tax_scale": 1.0,  # multiply bracket rates under the reform
        "personal_credit": 72_492,       # status quo only; abolished under the reform
        # Thresholds and the credit move each January with the CPI plus the law's estimate of productivity growth
        # (1%, lög nr. 90/2003 as amended 2019; stjornarradid.is, "Breytingar á staðgreiðslu um áramótin", 2025).
        "threshold_real_growth": .01,
        "threshold_index": 1.0,          # where the thresholds stand against the base year's, beyond prices (model-kept)
        "pension_contrib_employee": .04, "pension_contrib_employer": .115,   # status quo
        "social_security_employee": .0775, "social_security_employer": .0775,  # reform
        "payroll_tax": .0635,            # tryggingagjald, both regimes
        "vat_effective_status_quo": .18,  # EST: effective VAT on household consumption (24%/11%/exempt mix)
        "vat_platform": .25,
        # EST: the share of household consumption (housing excluded) a flat rate actually reaches. Across the OECD
        # consumption taxes raise 58% of what they would with no carve-outs and no evasion (OECD Consumption Tax
        # Trends, the VAT revenue ratio). A single rate ends the 11% band but not the exemptions every VAT keeps —
        # health, education, financial services, ~10% of this base — nor evasion. Today's 18% effective on a 24/11
        # mix (~65/25, the rest exempt) implies ~.88: a flat 25% raises ~22% effective, not 25%.
        "vat_platform_capture": .88,
        # A reform option that treats the state as an investor in its citizens: it pays for their upbringing,
        # schooling, health and the borgaralaun, and in return takes a share of the firms they found. The share follows
        # where the money came from: half if the founder lived on the borgaralaun alone, falling in proportion to
        # outside funding — 25% at half outside money, 10% at 80% — with a floor of 5% (ventures.stake_floor).
        # There is no seed money per firm; RANNÍS goes on funding ventures as it does now.
        "state_venture_stake": .50,      # the stake in a firm funded by the borgaralaun alone
        # The premise of the option: everyone who founds or funds a firm has had schooling, health
        # care and the payment, so the state is deemed to have paid at least one start-of-life fund into every
        # company, each time it raises capital — the premise of a corporate tax, held as ownership instead. A
        # firm's stake is today's rule or one deemed fund's share of it, whichever is larger (ventures,
        # `public_equity`). Whether corporate tax is still due on what the state partly owns is a choice:
        "staked_corporate_tax_share": 1.0,   # share of corporate tax still paid by firms with a stake (lever)
        "state_seed_money": 0,           # v3: none. Was 3 m kr. a firm, a cost the reform does not intend
        "public_payroll_cut": .20,
        "pension_topup_share": 1.0,      # transition top-up max(0, occupational pension - UBI), share paid
        # Eligibility follows EEA law. An EEA citizen who works — 10-12 hours a week, judged
        # month by month — has worker status and equal treatment, the borgaralaun included; one who is involuntarily
        # unemployed keeps it. Otherwise EEA citizens qualify with the permanent right of residence after five years
        # (Directive 2004/38, art. 16). Every part-time job in the model is over that threshold.
        "eea_years_to_permanent": 5,
        # Non-EEA citizens qualify with permanent residence: four years of residence under the Foreign Nationals Act
        # (útlendingalög, 58. gr.), with conditions on income and conduct; citizenship takes seven. EST: 5, allowing
        # for the time the conditions take to meet.
        "non_eea_years_to_ubi": 5,
        "immigration_cap_multiple": None,  # e.g. 1.0 caps foreign inflow at the 2025 level ("closed experiment")
        "residence_rules_strictness": .5,
        "prop_tax_extra_pp": 1.0,        # extra recurrent property tax, percentage points of market value
        # v9 option: households with someone 67+ defer the extra until sale or inheritance (~29 ma.kr.
        # in year 1); 0 = off
        "defer_pensioner_property_tax": 0.0,
        # v10 option: the top-up (benefit_floor_topup) paid to owners 67+ is a loan secured on
        # the home, up to `floor_loan_ltv` of its equity, repaid on sale or from the estate (housing.py); 0 = off
        "floor_loan": 0.0,
        "floor_loan_ltv": .5,             # EST: lenders of lifetime mortgages lend 20-55% of value by age
        # Taking CPI indexation out of household lending (verðtrygging). The government plans to cut its weight in
        # stages from 2026-27, starting with minimum principal payments on indexed mortgages, to strengthen how
        # interest rates reach demand; the IMF (2025 Article IV) asks that it be timed with care. Government bonds
        # and pension-fund assets — the long-term securities — keep their indexation here. 0 = today, 1 = none.
        "indexation_phaseout": 0.0,
        "indexation_phase_years": 5,
        "abolish_tariffs": True,
        # share of today's customs duties kept (7.7 ma.kr., THJ05132). The reform abolishes them ("afnema tolla").
        "customs_kept": 0.0,
        # Budget lines the reform cuts, as shares. Farm support is 19.7 ma.kr. and all other subsidies 55.3
        # (THJ05161, 2024). The reform asks that farm support go to innovation rather than to established
        # production, and that there be no subsidies at all; the model carries the first as the share cut.
        "agriculture_subsidy_cut": 1.0,
        # The other 55.3 ma.kr. of subsidies (THJ05161, 2024), in three groups:
        #   innovation and film, 21.7: R&D tax credits paid out (11.1, Rannís), film reimbursements (~6.1) and
        #     R&D grants (4.5);
        #   energy and transport, 17.7: road transport (6.0: buses and regional routes), electricity (4.5: rural
        #     heating and distribution), and the rest of "economic affairs n.e.c." (7.2: mostly the electric-car
        #     grants, EST);
        #   everything else, 15.9: culture, sport and private media (5.7), waste handling (4.7), education (1.6),
        #     labour-market and business support (3.0), tourism (0.8) and small items.
        # v3: RANNÍS continues in the reform, so the innovation support is kept
        "subsidy_cut_innovation": 0.0,
        "subsidy_cut_energy_transport": 1.0,
        # v3: the energy-and-transport line in its three parts, each with its own effects (energy_split below).
        # None = follow subsidy_cut_energy_transport, as before.
        "subsidy_cut_heating": None,      # rural heating support for the "cold areas", 4.5 ma.kr.
        "subsidy_cut_transition": None,   # electric-car and energy-transition grants, 7.2 ma.kr. (EST)
        "subsidy_cut_transport": None,    # buses and regional routes, 6.0 ma.kr.
        # Local green heat for the cold areas (a reform option): grants towards heat pumps, small hydro and wind
        # that a household or landowner installs, so remote homes need less expensive heat and less support.
        "green_heat_bn": 0.0,
        "subsidy_cut_other": 1.0,
        # Input VAT reclaimable only on inputs to the value chain. v9: from the input VAT firms claimed in 2025 (about
        # 997 ma.kr.), the full restriction yields 459.5 ma.kr. net of dearer government purchases and corporate tax
        # (509 gross, range 385-574; EST from Skatturinn's input VAT and Hagstofa's supply-use tables). v8 assumed 200 (EST, 100-350). The lever
        # sets how much of it is applied. It also raises exporters' costs (markets.vat_input_export_burden_bn).
        "vat_input_restriction_gain": 459.5,
        "vat_input_restriction_full_bn": 459.5,
        # The real return on pension-fund assets (187% of GDP) paid to the UBI instead of to pensions. EST 3%.
        "pension_fund_real_return": .0381,   # 1997-2025 (pension_funds_returns_1997_2025.csv); was .03 EST
        # How far the pension system is folded into the UBI. 1 = the reform: contributions (15.5%) go to the state
        # as social security, the funds' returns go to the UBI, and occupational pensions stop, with a top-up for
        # anyone whose pension was worth more than the UBI. 0 = pensions as today, the UBI paid on top.
        "pension_fold": 1.0,
        "pension_keep_earned": 0.0,      # v9 option: with the fold, the funds still pay earned pensions (no top-up)
        # Seed money of 3 m kr. for every new firm, and a 30% state stake in it, with the easier access to capital
        # that comes with it. 0 = today, 1 = the reform.
        "venture_support": 1.0,
        "per_diem_cut": 1.0,             # dagpeningar abolished (EST ~13 ma.kr. saved or taxed)
        # Inheritance tax. Today 10% above an exemption of 6.79 m kr. for the estate (2026; 6.5 m in 2025
        # krónur), and a surviving spouse pays nothing. The floor is in 2025 krónur and indexed.
        "inheritance_tax_rate": .10,
        "inheritance_tax_floor": 6.5e6,
        # Advance inheritance and gifts. Taxed like inheritance today, 10%. Set below the inheritance rate and
        # estates move into gifts while the giver is alive.
        "gift_tax_rate": .10,
        # A tax on moving assets abroad: on the unrealised gains of people who emigrate with financial wealth above
        # the threshold (2025 krónur), as Norway (about 38% on gains above NOK 3 m) and Denmark (27-42%) levy
        # them. Iceland has none. It also closes moving abroad as a way round the inheritance tax.
        "exit_tax_rate": 0.0,
        "exit_tax_threshold": 50e6,
        # Staff moved into tax enforcement: a UBI needs no one to check who is entitled to unemployment or other
        # benefits, and they can work on tax enforcement instead.
        "tax_enforcement_fte": 0,
        "prison_ubi_withheld": .60,      # share of prison time without the borgaralaun (today's rule: after 4 months)
        # The borgaralaun cannot be pledged, assigned or seized by creditors — as benefits cannot be today — so no
        # lender can treat it as collateral. 1 = protected, 0 = it can back a loan.
        "ubi_protected": 1.0,
        # Payments to unlicensed foreign gambling sites blocked, as Norway does (with DNS blocking since 2025).
        "gambling_payment_block": 0.0,
        # Free health care, GP first (Danish model) (v3): no charge for GP, specialist, outpatient, test or therapy visits, and a
        # GP referral before a specialist. Medicines and adult dental care stay paid as today — in Denmark too.
        "free_health_care": 0.0,
        # The internet as infrastructure (v3): the state pays for the network on publicly laid lines and for the
        # international capacity (Farice's cables), and the connection is free. Companies go on selling phones,
        # routers, installation and service.
        "free_internet": 0.0,
        # Custodianship instead of ownership for ever: whoever holds an asset keeps it, and their heirs after
        # them, for as long as they keep investing in it and it keeps earning; what is neglected goes back to the
        # market for others to bid on. 0 = ownership as today, 1 = the rule in full, for every kind of property.
        "custodianship": 0.0,
        "capital_controls": .5,          # 0 = open capital account, 1 = strict: damps debt-driven risk premia
        # pension funds sell foreign assets to finance the current account and hold the króna up (bn ISK/yr)
        "pension_fx_support_bn": 0.0,
        "corporate_tax_rate": .20,       # economy-wide corporate income tax
        "frontier_programmes": [],
        "infrastructure_programmes": [],  # tunnels, Keflavík rail, city light rail, ring railway
        # The state stops carrying sick pay for its own employees; private insurance takes the risk instead.
        # EST: sickness absence runs about 5.5% of public hours, so this is worth roughly 39 ma.kr. a year —
        # more than every governing-cost cut combined. It is not free: whoever falls ill without cover loses
        # income, which the model carries through hardship into health and wellbeing.
        # No company or affiliated group may hold more than this share of the total square metres. Set to 1.0
        # for no cap. The reform's setting is 10% commercial and 5% residential.
        "commercial_ownership_cap": 1.0,
        "residential_ownership_cap": 1.0,
        "developer_exemption": 1.0,      # share of newly built stock exempt from the cap
        # 0 = ownership for ever. Otherwise the term in years before a property reverts to the public.
        "ownership_term_years": 0,
        # Sick pay and parental leave once the borgaralaun is the floor (a reform option). The state's own
        # schemes end — public sick pay and the parental leave fund — and what is paid above the borgaralaun
        # becomes the employer's: the period the law and agreements already give, rising with seniority, then
        # mandatory private insurance, as occupational pensions work now. Job protection is unchanged: no one may
        # be dismissed for taking leave. The level of the top-up is left to bargaining, so the model states an
        # assumption and gives it a lever.
        "state_leave_ended": 0.0,          # 1 = the state's sick pay and parental leave fund both end
        "leave_top_up": None,              # None = the assumption below, by whether agreements survive
        "employer_leave_cost_share": 0.0,  # filled each year from the scheme: employers' leave cost on wages
        "public_sick_pay_cut": 0.0,
        "sick_absence_rate": .055,       # EST: share of public hours lost to sickness
        "private_sickness_uptake": .60,  # EST: share who insure privately once the state stops
        # EST: where agreements still set terms, bargaining lands near today's parental leave rule — 80% of pay
        # under a cap. Where pay is set job by job, the model assumes it lands lower. Both are assumptions about
        # where bargaining ends up, not findings; the lever overrides them.
        "leave_top_up_agreements": .80,
        "leave_top_up_free_market": .55,
        # EST: the share of leave the employer pays directly before insurance takes over. Icelandic sick-pay
        # entitlement rises with seniority (two days a month in the first year, up to several months for long
        # service, lög nr. 19/1979 and the agreements), and most absence is short, so the employer's own period
        # covers roughly half of what is paid out. The rest is insured.
        "employer_leave_period_share": .5,
        "leave_insurance_loading": 1.15,   # EST: an insurer's margin and costs on the part beyond the employer
        "parental_leave_months": 12,       # today's entitlement, both parents together
        "parental_leave_cap_month": 800_000,   # the fund's ceiling, 2025 (island.is)
        # What the parental leave fund paid out in 2025, part of the national accounts' social benefits. EST from
        # the fund's recent accounts (~21-25 ma.kr.); to be replaced by Fæðingarorlofssjóður's 2025 figure.
        "parental_leave_fund_bn": 28.2,   # Fæðingarorlofssjóður via Hagstofa, 2025 (was EST 23.0)
        "governance_cut": 1.0,           # share of the governing-cost package applied (see static_balance)
        "presidency_cut": 0.80,          # a smaller presidential office
        "church_funding_cut": 1.0,       # no religious body funded; sóknargjöld fold into general tax       # e.g. ["controlled_environment_farming", "autonomous_fisheries"]
        # The state leads on costs: a public job pays, after tax and with the UBI, what it paid before the UBI.
        # Pay is cut by the UBI grossed up at the employee's marginal tax rate. 0 = no cut, 1 = the full offset.
        "public_wage_offset_ubi": 0.0,
        "culture_support_cut": 0.0,      # share of state support for the arts withdrawn (reform: 1.0)
        # --- further levers
        "minimum_wage": 0,               # statutory monthly floor, ISK (0 = none; agreements set the floor today)
        "full_time_hours_factor": 1.0,   # 0.8 = a four-day week; pay follows hours
        "ubi_taper_start": 0,            # earnings above which the UBI is withdrawn (0 = never: a true UBI)
        "ubi_taper_rate": 0.0,           # withdrawal rate above that point (a negative income tax at 1.0)
        "childcare_places_added": 0,     # new full-day places funded by the state
        "retraining_bn_per_year": 0,     # spending that helps people move between professions
        # dwellings the state has built each year on top of what the market builds: the supply-side answer to rents
        "public_dwellings_per_year": 0,
        "public_dwelling_cost_m_isk": 55,  # EST: build cost per dwelling, million ISK
        # agreements compensate prices net of the tax switch (Denmark's nettoprisindeks): the share of the VAT's
        # effect on the CPI left out of wage indexation. 0 = headline CPI, as today.
        "indexation_net_of_tax": 0.0,
        # share of the gap closed between the reform and today's net income for people on a disability or
        # old-age pension (policy.net_income); 0 = the reform as specified, with no floor
        "benefit_floor_topup": 0.0,
        "net_wealth_tax_pct": 0.0,       # yearly tax on household net wealth above the threshold
        "net_wealth_tax_threshold": 100e6,
        "sovereign_fund_share": 0.0,     # share of any surplus invested rather than used to repay debt
        "low_value_jobs_productivity_gain": 0.0,  # output per FTE gain from removing low-value jobs (e.g. .05)
        "low_value_job_weights": [1.6, .7, 1.2, 2.0, .8, .3, .4, .5, .8],  # EST: where low-value jobs sit, by group
        "low_value_jobs_ramp_years": 3,  # 0 = open, 1 = strict resources/occupancy tests (scales non-worker inflow)
    },

    # ---------------------------------------------------- status quo benefits (2026)
    "benefits": {
        # Today's safety net at 2026 law, from Tryggingastofnun, Skatturinn, Vinnumálastofnun, HMS and the municipalities'
        # published amounts (island.is, skatturinn.is, reykjavik.is; retrieved 2026-09). Until 2026-10-03 unemployment benefit and
        # social assistance were one 250,000 payment, there was no housing benefit or household supplement, child
        # benefit was a flat 25,000, and disability was estimated — together the status quo's poorest were too poor
        # (child poverty 20.8% against a published 12.8%), which flattered any reform set against it.
        "tr_old_age_full": 365_592,       # Tryggingastofnun 2026
        "tr_general_exemption": 43_658,   # Félags- og húsnæðismálaráðuneyti 2026 / 12
        "tr_work_exemption": 210_400,     # Félags- og húsnæðismálaráðuneyti 2026 / 12 (was the 2025 value)
        "tr_clawback": .45,               # the law as in force in 2026
        "tr_full_residence_years": 40,    # residence 16-67 for a full pension; pro rata below (law 100/2007, 17. gr.)
        # EST: nominal return on savings counted in the income tests (deposit rates ran 5-8% in 2024-25; much is held
        # at lower rates)
        "tr_capital_return": .05,
        # household supplement for pensioners and disabled people living alone
        "household_supplement_old_age": 92_384,      # Tryggingastofnun 2026
        "household_supplement_old_age_withdrawal": .119,   # the law as in force in 2026
        "household_supplement_disability": 69_126,   # Tryggingastofnun 2026
        "household_supplement_disability_withdrawal": .45, # Tryggingastofnun 2026
        # disability, the new system from 1 Sep 2025
        "disability_pension": 416_950,    # Tryggingastofnun 2026, full
        "disability_partial": 341_899,    # Tryggingastofnun 2026, for those who also work
        "disability_general_disregard": 105_200,    # Tryggingastofnun 2026, on all income
        "disability_earned_disregard": 263_000,     # Tryggingastofnun 2026, on earnings, partial pension
        # pension funds' disability pensions, 39.4 ma.kr. a year (2025): a share of the person's full-time pay, half
        # for those still working. CALIBRATED to the total on the 2025 base: .21 with v8's ~24,000 disabled under 67,
        # .15 with v9's 29,465 of whom a fifth work (at .21 the total came out at 55 ma.kr.).
        "fund_disability_replacement": .15,
        # TR's 2025 count, 29,465 (20,836 disability pension, 8,629 sickness or rehabilitation payments;
        # Tryggingastofnun), over the survey's inactive disabled and ill (~19,900); the difference work part-time
        # (population.py). Was 1.21 (~24,000), which left disability ~28 ma.kr. short (an external review of v8, 2026-10).
        "disability_register_ratio": 1.48,
        # of recipients, working part-time: TR's 29,465 less the labour force survey's 19,900 inactive disabled and ill
        # (2025), so both counts hold. An earlier setting of .2 is about a fifth; at .2 the model drew 3,700
        # more people out of work than the survey has, and the response to unearned income fell below the lottery
        # evidence (2026-10-12; v8's 46% had the opposite fault).
        "disability_working_share": .325,
        # unemployment benefit: individual, for those who lost a job and seek another
        "unemployment_basic": 383_870,    # Félags- og húsnæðismálaráðuneyti 2026
        "unemployment_income_related_cap": 605_159,  # Félags- og húsnæðismálaráðuneyti 2026
        "unemployment_replacement": .70,  # law 54/2006, of prior pay, the first three months
        "unemployment_income_related_share": .35,    # EST: share of a year's benefit months that fall in the first three
        # social assistance: residual and household-tested, for others of working age with no entitlement (Reykjavík)
        "social_assistance_single": 259_951,   # Reykjavíkurborg 2026
        "social_assistance_couple": 415_922,   # Reykjavíkurborg 2026, for the couple
        "social_assistance_refusal_cut": .5,   # cut for turning work down (Reykjavík's rules, 4. gr.)
        # EST: how much of real wage growth passes into benefit levels, as 69. gr. requires "regard to wages".
        # 1 = benefits keep their place against wages; 0 = prices only. The law's floor is prices, so the model
        # never indexes by less than that.
        "wage_indexation": .80,
        "nonwork_support": 250_000,       # EST: unemployment / municipal support for prime-age non-workers
        "support_spread": .12,            # EST: spread of that support across municipalities and households
        "nonwork_support_partner_cutoff": 450_000,  # EST: support withheld if partner earns more
        # Someone out of work by choice gets the municipalities' assistance only once their savings are drawn
        # down (Reykjavík's rules on fjárhagsaðstoð: assets are to be used first), and those who lost a job and
        # seek another are not tested. The test is written but switched off (0): tried at three months' support
        # (2026-09-26), it pushed the response to a payment out of the evidence (MPE 0.26-0.38 against 0.04-0.20).
        # The choice model gives a person with no income the subsistence floor and no drawing on savings, so a
        # tested-out saver's option of not working was worth almost nothing and the calibration made leisure
        # dearer to compensate. It needs savings drawn down in the choice first.
        "nonwork_asset_limit_months": 0.0,
        # child benefit (barnabætur), income-tested on the household's taxable income (the law as in force in 2026)
        "child_benefit_couple_year": 345_000,
        "child_benefit_single_year": 514_500,
        "child_benefit_under7_year": 130_000,
        "child_benefit_threshold_couple_year": 11_688_000,
        "child_benefit_threshold_single_year": 5_844_000,
        "child_benefit_withdrawal": .04,
        # housing benefit (húsnæðisbætur) for renters: base amount by household size less 9% of the household's income
        # above its limit, at most 75% of rent (the law as in force in 2026); 11.2 ma.kr. to ~23,000 households in 2025
        "housing_benefit_base_year": [609_504, 810_641, 944_732, 1_023_967, 1_109_298, 1_194_628],
        "housing_benefit_limit_year": [6_365_773, 8_466_478, 9_866_948, 10_694_499, 11_585_707, 12_476_915],
        "housing_benefit_reduction": .09,
        "housing_benefit_asset_limit": 13_900_000,  # Húsnæðis- og mannvirkjastofnun / ráðuneyti 2026
        # CALIBRATED: the share of the model's renters who claim, to ~23,000 households and 11.2 ma.kr. (HMS 2025);
        # see policy.housing_benefit
        "housing_benefit_claim_share": .33,
        # the resulting 67+ mean is checked in scripts/quality_check.py. Of base monthly earnings, full career; to
        # ~357k per RESIDENT 67+ in 2025 (Skatturinn's income-by-age file: 214.1 ma.kr. for 2024 over ~52,700 residents,
        # not the register's 60,403, less ~6 ma.kr. paid abroad, +8.5% per person to 2025). v8 used ~307k (.365),
        # from the register count, about 14% low.
        "occupational_pension_replacement": .4245,
        # v9: the spread of fund pensions around that mean, fitted to the state's top-up of max(0, pension - payment)
        # at five payment levels in an external register-based estimate (155.7 / 132.5 / 113.1 / 96.6 / ~73 ma.kr. at
        # 200-450 þús.): 0.9 gives 106 at 300 and 76 at 450. v8's .35 gave 71 at 300.
        "occupational_pension_sd": .9,
        # v9: capital income as the tax returns have it (Skatturinn 2024 by age and income decile, uprated: 355 ma.kr.
        # in 2025): 182k a month on average for those 67+, the top tenth of them holding 81%.
        # Assigned by wealth rank within age group, lognormal shares (sigma 2.16 gives the 81%); EST that the same
        # concentration holds under 67. Capital income tax 22% (lög 90/2003) above the yearly allowance on interest.
        "capital_income_total_bn": 355.3,
        "capital_income_67_month": 182_000,
        "capital_income_sigma": 2.16,
        "capital_income_tax": .22,
        "capital_income_allowance_year": 300_000,
        # v9: living arrangements (Hagstofa: 60% of those 67+ live with a spouse or partner, 1 Jan 2026; the 2021
        # census: about 22% of them live alone, the rest of the single ones with family or
        # others). Those who live with others pool income with that household for poverty and costs, and get no
        # household supplement, which is paid only to people living alone (law 99/2007, 8. gr.). EST for under 67.
        "living_alone_share_single_67": .55,
        # v9: young single adults living with their parents, by age (EST from Eurostat's young-people-at-home series for
        # Iceland, where young people leave home at about 25-26). v8 made everyone from 20 a household of their own:
        # 48-65% of those 18-24 counted as poor, and status-quo poverty over persons came out at 11.6% against 9.0%.
        "young_at_home_share": {"18": .90, "20": .55, "25": .20, "30": .0},
        "living_alone_share_single_under67": .50,
        # child pension (barnalífeyrir): per child under 18 of an old-age, disability or rehabilitation pensioner, or
        # of a deceased parent; untaxed (Tryggingastofnun, 2026). TR paid about 11 ma.kr.
        "child_pension": 50_634,
        # vaxtabætur, assessment year 2025 (Skatturinn, vaxtabætur amounts), yearly amounts; paid
        # 1.1-1.6 ma.kr. Mortgage interest 5.68% (Seðlabanki, average on household mortgages). The asset limits are EST from law 90/2003.
        "mortgage_interest_rate": .0568,
        "interest_rebate_debt_share": .07,
        "interest_rebate_income_rate": .085,
        "interest_rebate_max_interest_single": 840_000, "interest_rebate_max_interest_couple": 1_260_000,
        "interest_rebate_max_single": 420_000, "interest_rebate_max_couple": 630_000,
        "interest_rebate_asset_limit_single": 7_500_000, "interest_rebate_asset_limit_couple": 12_000_000,
    },

    # ---------------------------------------------------------------- costs
    "costs": {
        "basic_single": 170_000,          # EST: reference budget excl. housing, one adult
        "housing_renter_capital": 260_000,  # EST
        "housing_renter_other": 190_000,  # EST
        "housing_owner_mortgage": 170_000,  # EST
        "housing_owner_outright": 70_000,   # EST
        "living_with_parents": 60_000,    # EST: 16-19 year olds
        "parental_support": 120_000,      # EST: in-kind support to 16-19 year olds living at home
        "subsistence_share": .70,         # s: share of c_min that is truly essential
        "capital_share": .64,
    },

    # ------------------------------------------------------------ behaviour
    "behaviour": {
        "target_extensive_elasticity": .25,  # calibrates alpha (literature range .1-.5)
        "reoptimise_rate": .35,           # share of agents re-choosing each year
        "reoptimise_rate_first_year": .5, # a large reform prompts more people to reconsider
        "part_time_hours": .55,
        "gamma_meaning": .6,
        "gamma_disamenity": .8,
        "leisure_mean": .5, "leisure_sd": .45,
        "meaning_sd": .15,
        "work_ethic": 0.0,                # added to utility of any work (tweak)
        "independent_hours": .6,          # EST: hours put into self-directed work
        "gamma_creative": .9,             # EST: how much the pull towards self-directed work counts
        "independent_leisure_cost": .5,   # EST: self-directed hours cost only part of what paid hours cost
        # Selling the work is a lottery. EST: it sells in about half of years; in the others it brings in
        # almost nothing. Expected earnings are unchanged — what changes is the risk, which is what a floor
        # under income actually removes.
        "study_full_time_cost": 1.4,      # EST: how much harder a course makes holding a full-time job
        "independent_sale_probability": .5,
        "independent_floor_share": .10,   # EST: what the work still earns in a year it does not sell
        "baseline_independent_share": .015,  # EST: share of 16-74s doing this today (unpaid or barely paid)
        "entrepreneurial_spirit": 1.0,    # multiplies the rate of venture ideas per capita (tweak)
        "mobility_scale": 1.0,            # multiplies emigration income response (tweak)
    },

    # ---------------------------------------------------- characters (trait multipliers)
    "characters": {
        "Founder":             {"enterprise": 1.0, "leisure": 1.0, "mobility": 1.0, "meaning": 1.0},
        "Vocation":            {"enterprise": 1.0, "leisure": 1.0, "mobility": 1.0, "meaning": 1.0},
        "Breadwinner":         {"enterprise": 1.0, "leisure": 1.0, "mobility": 1.0, "meaning": 1.0},
        "Mobile professional": {"enterprise": 1.0, "leisure": 1.0, "mobility": 1.0, "meaning": 1.0},
        "Guest worker":        {"enterprise": 1.0, "leisure": 1.0, "mobility": 1.0, "meaning": 1.0},
        "Carer":               {"enterprise": 1.0, "leisure": 1.0, "mobility": 1.0, "meaning": 1.0},
        "Constrained":         {"enterprise": 1.0, "leisure": 1.0, "mobility": 1.0, "meaning": 1.0},
        "Student":             {"enterprise": 1.0, "leisure": 1.0, "mobility": 1.0, "meaning": 1.0},
        "Retiree":             {"enterprise": 1.0, "leisure": 1.0, "mobility": 1.0, "meaning": 1.0},
        "Balanced":            {"enterprise": 1.0, "leisure": 1.0, "mobility": 1.0, "meaning": 1.0},
    },

    # ---------------------------------------------------------------- education
    # Studying means years without earnings, so how many people do it turns on what they have to live on while
    # they are not working. EST magnitudes; the affordability response is the channel the US negative income tax
    # experiments identified, where school attendance and completion rose.
    "education": {
        # Set so the stock of students matches Hagstofa SKO00000: 19,528 in tertiary education in 2025.
        "enrolment_base": .072,           # yearly chance a young non-graduate starts, at subsistence income
        "students_2025": 19_528,
        "affordability_elasticity": 1.2,  # EST: how strongly a livable income raises that chance
        "years": 3,
        # how much of a year of the course gets done while also holding a job down (EST)
        "progress_part_time": .75,
        "progress_full_time": .40,
        "max_years": 8,                   # after this long without finishing, people give up
        # a baby slows a course (Bach et al. 2025: student mothers drop out more often); this is the share of the
        # normal pace kept in the two years after a birth
        "progress_with_infant": .7,       # EST
        "wage_premium": 1.12,             # EST: earnings gain on finishing, consistent with the wage distribution
        # v6: studying answers what a degree is worth. The expected pay of work that asks for a degree against work
        # that does not — pay times the chance of a post, from the shortages and queues — against the base year.
        # Enrolment elasticities to the college premium run 0.3-1.5 in the literature (Card and Lemieux 2001;
        # Kane 1994; Dynarski 2003 for cost); EST at the lower middle. Without it nobody studied for the jobs AI
        # leaves, and by 2045 low-skill work queued at 12-18% unemployment beside 10-27% shortages of doctors,
        # nurses, teachers and managers (found 2026-10-01).
        "return_elasticity": .8,          # EST
        # most who finish take work that asks for what they studied; the rest stay where they were, paid more
        "graduate_switch_share": .6,      # EST
        "cost_per_student_bn": 2.2e-3,    # EST: ~2.2 m ISK a year per student place
        "max_age": 34,
    },

    # ---------------------------------------------------------------- health
    # Public health spending was 405.8 ma.kr. in 2025, of which 261.0 was hospital services (Hagstofa THJ05511).
    # The evidence that a secure income improves health is unusually direct: Manitoba's Mincome cut hospital
    # use 8.5%, concentrated in accidents and mental health (Forget 2011); Finland's basic income trial found
    # clearly better mental wellbeing with no employment effect; the Cherokee casino payments reduced children's
    # psychiatric symptoms. 8.5% of hospital spending is about 22 ma.kr. a year, and that is the magnitude the
    # hardship weight below is set to reproduce.
    "health": {
        "public_spending_bn": 405.8,
        "hospital_share": .643,           # 261.0 of 405.8
        "disability_penalty": .55,        # EST: a disability's place in health, in the drawing and the dynamics alike
        "hardship_penalty": .18,          # EST: what living below subsistence does to health
        "unemployment_penalty": .10,      # EST: involuntary idleness, over and above the income
        "recovery_rate": .25,             # EST: how fast health returns once the cause is removed
        "age_gradient": .009,             # EST: yearly decline with age past 40
        "cost_elasticity": 1.6,           # EST: how sharply poor health raises what care costs
        "disability_onset": .004,         # EST: yearly chance of leaving work through ill health, at mean health
    },

    # ---------------------------------------------------- who owns the buildings
    # Concentrated ownership of rental property supports rents above what a competitive market would set. The
    # evidence is real but contested and the magnitudes are genuinely uncertain: work on institutional landlords
    # in the US finds rent effects of a few per cent, and Iceland's rental market has a handful of large owners.
    # Commercial property matters for a different reason — rent is a fixed cost that decides whether a small
    # business in Reykjavík is viable at all, which is the argument for capping it.
    #
    # Caps are expressed as the share of total square metres any one company or affiliated group may hold.
    # A binding cap forces divestment, which adds sellers and competitors and compresses the markup.
    "property_ownership": {
        "residential_markup": .06,        # EST: rent above competitive, from concentrated ownership
        "commercial_markup": .09,         # EST: the same for commercial space, where concentration is higher
        "residential_top_share": .14,     # EST: share of the rental stock the largest group holds today
        "commercial_top_share": .22,      # EST
        "divestment_years": 4,            # how long a forced sale takes to work through
        "commercial_rent_share_of_costs": .12,   # EST: rent as a share of a small firm's costs
        # New construction exempt from the caps. The cap then bites on buying existing stock but not on adding new,
        # which is the point: it aims the rule at accumulation rather than at construction.
        "developer_build_incentive": .18,  # EST: how much more gets built when builders may keep what they build
        "exempt_stock_dilution": .55,      # EST: how far exempt new stock lets concentration rebuild
        # Ownership for a term rather than for ever, reverting to the public afterwards — freehold turned into
        # long leasehold. The arithmetic of this is not in dispute: at a 3.5% real rate a finite claim is worth
        # 64% of a perpetual one at 30 years, 82% at 50, 92% at 75 and 97% at 100. Property values fall by the
        # remainder, immediately, because the market prices the term the day the rule passes.
        #
        # What is in dispute is the rest. Leasehold systems show real under-maintenance as terms run down, which
        # extensions for upgrades are meant to answer, and the reversion revenue arrives decades out — beyond any
        # horizon this model runs. Both are represented; neither is well pinned.
        "term_discount_rate": .035,
        "maintenance_decay": .35,          # EST: how much upkeep falls as a term runs down, before upgrades
        "upgrade_extension_offset": .60,   # EST: how much of that extensions for improvements win back
        "developer_term_years": 10,        # a builder keeps an exempt project this long, then must sell
        "forced_sale_build_incentive": .10,   # EST: the extra building that revolving door produces
        # Variety. The point of capping commercial ownership is not only lower rents: it is small owners able to
        # afford the high street, so that towns are not only tourist shops and international chains. Many
        # owners mean more kinds of shop, and that is worth something in itself. Evidence: independent firms keep
        # more of what they take in circulating locally (Civic Economics' studies of US towns find roughly two to
        # three times the local recirculation of chains), and consumers value variety as they value lower prices
        # (Broda and Weinstein put the gain from new import varieties at 2.6% of US income over 1972-2001). Here,
        # at the full effect of a cap that fully breaks today's concentration:
        "variety_venture_boost": .10,      # EST: more small firms started, over and above cheaper rent
        "variety_wellbeing": .03,          # EST: life-satisfaction points, for everyone, from livelier towns
        "variety_consumption_gain": .004,  # EST: what the variety is worth, as a share of real consumption
        # Custodianship: holding property for as long as it is looked after and earns, and losing it to the
        # market when it is neglected. No country runs this for all property; the pieces exist — use-it-or-lose-it
        # rules on land and mining claims, compulsory sale of derelict buildings, the self-assessed "common
        # ownership" tax (Posner and Weyl) — and every magnitude below is EST.
        "custodian_upkeep_gain": .15,      # EST: how much slower the stock wears out when upkeep is a condition
        "custodian_idle_share": .02,       # EST: dwellings left empty or derelict that return to use
        "custodian_idle_years": 5,
        "custodian_productivity": .015,    # EST: output gained as neglected firms and assets change hands
        "custodian_ramp_years": 8,
        "custodian_value_discount": .03,   # EST: what the risk of losing a neglected asset takes off prices
        "custodian_admin_bn": 2.0,         # EST: the assessments and auctions, a year
    },

    # ---------------------------------------------------------- inheritance
    # 14.7 ma.kr. in 2024, of which 9.1 from advance inheritance (fyrirframgreiddur arfur) and 5.6 from estates
    # (Vísir, 2025). Gifts are taxed alike, so revenue from them is carried in proportion to the estates.
    "inheritance": {
        "advance_ratio": 9.1 / 5.6,
        # EST: taxable estates against the net-of-tax rate, about .1-.2 in all (Kopczuk-Slemrod), split by route:
        # gifts while alive (closed when gifts are taxed alike), moving wealth abroad (closed by an exit tax at the
        # inheritance rate), and the rest — trusts, valuation, spending it first — which enforcement narrows.
        "avoidance_gifts": .10, "avoidance_abroad": .08, "avoidance_other": .06,
        "unrealised_gain_share": .40,      # EST: share of emigrants' financial wealth that is untaxed gain
        "heirs": 2,                        # an estate without a spouse passes to this many adults
        "rate_today": .10, "floor_today": 6.5e6,   # the status quo, whatever the reform sets
        # What the tax is levied on, as a share of what the model counts: estates are valued at assessed values,
        # net of debts and funeral costs, and much passes to a surviving spouse in an undivided estate first.
        # EST, set so the status quo raises about the 14.7 ma.kr. collected in 2024.
        "valuation_share": .45,
    },

    # ---------------------------------------------------------- tax enforcement
    # Evasion: Ríkisskattstjóri put it at 80-100 ma.kr. a year in 2014, about 4% of GDP then; scaled, about 200
    # today. What more investigators recover runs into diminishing returns. Vinnumálastofnun's four-person benefit
    # unit recovered 572 m kr. in 2012 (Alþingi 591/143) — 143 m kr. each a year.
    "enforcement": {
        "evasion_bn": 200.0,              # EST
        "recoverable_share": .25,         # EST: what enforcement can reach at all
        "yield_per_fte_m": 100.0,         # EST: m kr. a year for the first investigators, falling as more are added
        "cost_per_fte_m": 14.0,           # EST: pay and overheads
        "ramp_years": 2,                  # training
        "avoidance_cut_at_300": .5,       # EST: how much 300 more investigators narrow the "other" avoidance route
        # A UBI replaces the benefits, and with them most of the work of assessing and policing them at
        # Tryggingastofnun, Vinnumálastofnun and the municipalities. EST, saved whether or not the staff move.
        "benefit_admin_saved_bn": 4.0,
    },

    # ---------------------------------------------------------- gambling and high-cost credit
    # Icelanders lose about 20 ma.kr. a year to foreign betting sites that pay no tax here (estimates run from 9 for
    # sports betting alone to €245 m). On average, cash transfers do not raise spending on gambling, alcohol or
    # tobacco (Evans and Popova, 19 studies); the risk sits with the few at risk of problem gambling, and grows
    # where a lender can lend against a regular payment. EST throughout.
    "gambling": {
        "at_risk_share": .02,             # EST: adults at risk of problem gambling
        "foreign_losses_bn": 20.0,        # EST: lost to foreign sites a year, today
        "ubi_extra_loss": .08,            # EST: share of the payment an at-risk gambler loses on top
        "pledge_leverage": 1.5,           # EST: losses multiply by 1 + this where the payment can back a loan
        "block_effect": .6,               # EST: share of foreign gambling a payment block stops (Norway: partial)
        "displacement": .5,               # EST: share of what is stopped that moves to licensed Icelandic games
    },

    # ---------------------------------------------------------- links between levers (all EST)
    "links": {
        # Tourists pay VAT on hotels, restaurants and tours, mostly at 11% today. A flat rate raises what a stay
        # costs them, and what they buy falls with it; the treasury gains the higher VAT on what remains.
        "tourism_vat_today": .11, "tourism_vatable_share": .50, "tourism_price_elasticity": .8,
        # Input VAT that businesses can no longer reclaim is a cost to them, and part of it reaches their prices.
        "vat_input_price_per_100bn": .0078,      # rise in residents' prices per 100 ma.kr. (EST from the supply-use tables; was .02)
        # Most customs duties protect food: without them, imports compete with Icelandic farms.
        "farm_jobs_lost_without_customs": .10,   # share of farm work
        # Energy and transport subsidies keep heating and fares down: about 0.9% of household spending.
        "energy_transport_cpi_at_full_cut": .008,
        # Innovation support: the R&D credit and grants buy some research and some new firms.
        "innovation_productivity_at_full_cut": .003,
        "innovation_ideas_at_full_cut": .05,
        # Upkeep as the condition of holding property is work for the trades.
        "custodian_upkeep_fte": 1500,
        # Today part of what a job pays is a pension (15.5% contributions). Folding the funds into the UBI turns
        # that into a tax. People value a future pension at less than its cost.
        "pension_accrual_value": .40,
        # Wealth moves, is hidden and is revalued when it is taxed every year (Jakobsen et al., Denmark; Seim,
        # Sweden). Taxable wealth against the net-of-tax return; an exit tax and enforcement narrow it.
        "wealth_tax_elasticity": .30, "wealth_return": .03,
        # One multiplier on every avoidance response (inheritance routes, the wealth tax): a sensitivity, 1 = central.
        "avoidance_scale": 1.0,
        # Capital controls damp the risk premium on a large debt, and cost something: Iceland's 2008-2017 controls
        # held back foreign investment and trade in capital. EST: output lost at full strength.
        "capital_controls_productivity_cost": .005,
    },
    # The energy-and-transport subsidies (THJ05161, 2024), split so that cutting each shows what it does.
    "energy_split": {
        # Niðurgreiðsla húshitunar: homes without geothermal heat — about 9% of the population, the Westfjords,
        # the East, the islands and parts of the North — heat with electricity or oil and are paid part of the
        # difference. Cutting it is a heating bill for those homes, not a price rise for everyone. EST: a quarter
        # of households outside the capital area.
        "heating_bn": 4.5, "cold_area_share_outside_capital": .25, "heating_cpi_at_full_cut": .001,
        # EV and transition grants (Orkusjóður, the EV purchase grant). Cutting them slows the switch from petrol:
        # road transport emits about 0.95 Mt CO2e a year (EST, UST inventory), and without the grants EST 0.12 Mt
        # more by the tenth year. Each Mt of road CO2 is about 430 m litres of fuel, EST 35 ma.kr. of imports.
        "transition_bn": 7.2, "transition_emissions_at_full_cut_mt": .12, "transition_years": 10,
        "fuel_imports_bn_per_mt": 35.0, "transition_cpi_at_full_cut": .001,
        # Strætó's state contract and regional bus and ferry routes: fares rise or routes close.
        "transport_bn": 6.0, "transport_cpi_at_full_cut": .004, "transport_emissions_at_full_cut_mt": .02,
        # Local green heat. EST: 3 m kr. a home for a heat pump or a share of a small hydro or wind plant, the grant
        # paying half and the owner installing the rest; a converted home needs 60% less bought heat (a heat pump's
        # COP of about 3), so 60% less support, or a 60% smaller bill if the support is cut.
        "green_heat_cost_per_home_m": 3.0, "green_heat_grant_share": .5, "green_heat_saving": .6,
    },
    "free_services": {
        # Out of pocket: about 16% of current health spending of ~426 ma.kr. (OECD, 2022). EST split: medicines
        # ~22, adult dental ~20, glasses, aids and other ~8, and service co-payments ~15 — GP and specialist
        # visits, outpatient care, tests, physiotherapy (the greiðsluþátttökukerfi, capped a year per person).
        # The Danish model removes only the last.
        "health_out_of_pocket_bn": 65.0,
        "health_service_copay_bn": 15.73,  # what the Danish model makes free: fees for services (gov_items_2025.csv)
        "health_demand_response": .10,    # EST: more visits when they are free
        # Gatekeeping: specialists by referral. Specialist outpatient care bought by Sjúkratryggingar is EST 18
        # ma.kr.; systems with gatekeeping use specialists less (Sripa et al. 2019, BJGP, review), EST 15% here,
        # and half of that saving goes on the extra GP time it takes. Iceland is short of GPs, so it phases in.
        "specialist_bn": 18.0, "gatekeeping_specialist_cut": .15, "gatekeeping_gp_cost_share": .5,
        "gatekeeping_years": 4,
        # The connection: EST ~7,000 kr. a month for ~155,000 households, 13 ma.kr. EST 60% of the bill is the
        # line and international data, which becomes free; the rest is equipment and service, still sold.
        "internet_household_bn": 13.0,
        "internet_free_share_of_bill": .60,
        # What the state then pays: Farice's international capacity (EST 3 ma.kr., its yearly revenue) and running
        # the publicly laid access lines (EST 2). The difference from what households saved is the margin private
        # line owners earned on it, which the reform means to end.
        "internet_state_cost_bn": 5.0,
    },

    # ---------------------------------------------------------- agriculture
    # Cutting farm support: fewer farms, and in the short run dearer domestic food, partly offset where tariffs
    # go and imports compete.
    "agriculture": {
        "fte0": 3500,                     # EST: farm work
        "jobs_lost_at_full_cut": .25,     # EST: share of farm work that does not survive without support
        "cpi_effect_at_full_cut": .003,   # EST: food is about 14% of the CPI, domestic farm products a third of it
        # v3: part of what farm support cost goes to agricultural start-ups through RANNÍS instead
        # (support for innovation, not for established production). EST 1.5 ma.kr. a year at 15 m kr.
        # a start-up, 100 a year; half survive, each with 1.5 FTE once running (after 3 years).
        # Matvælasjóður had 477 m kr. to grant in 2025 (farm and marine products); with research at LbhÍ and Matís
        # and the development money inside the farm agreements, agricultural R&D is EST about 1 ma.kr. a year. The
        # reform keeps that and adds to it, since the rest of farm support goes.
        "startup_bn": 1.5, "startup_grant_m": 15.0, "startup_survival": .5, "startup_fte": 1.5,
        "startup_years": 3,
    },

    # ------------------------------------------------------------ trade and prices abroad
    # Exports were 1,997.4 ma.kr. in 2025 and imports 2,102.8 (THJ01102). What the model was missing is that
    # these are not one undifferentiated flow: Iceland sells fish, aluminium and travel, and the world prices of
    # those three move independently of each other and of the króna. Terms of trade — what a unit of exports
    # buys in imports — is a large part of why real wages grew 2.1%/yr against 1.07%/yr of productivity.
    #
    # Shares are EST of the right order; tourism is the largest earner, marine products and aluminium follow.
    "trade": {
        "shares": {"tourism": .36, "marine": .21, "aluminium": .17, "other": .26},
        "price": {"tourism": 1.0, "marine": 1.0, "aluminium": 1.0, "other": 1.0},   # world prices, 1.0 = 2025
        "import_price": 1.0,              # what Iceland buys, 1.0 = 2025
        "tourism_fte": 26_000,            # EST: people working in tourism at the 2025 level
        "tourism_revenue_bn": 600.0,      # EST: tourism's export earnings, 2024-25 (Hagstofa, ~600 ma.kr.)
        "tourism_labour_elasticity": 0.574, # TUNED 2016-25 backcast; was EST: how far tourism employment follows the money it earns
        "tot_income_passthrough": .55,    # EST: share of a terms-of-trade gain that reaches real incomes
    },

    # ---------------------------------------------------------------- schooling
    # Education cost 347.5 ma.kr. in 2025 (THJ05142). Tertiary is modelled agent by agent; compulsory and upper
    # secondary schooling is a cost driven by how many children there are, which migration and fertility move.
    "schooling": {
        "spending_bn": 258.0,             # EST: the 347.5 less the tertiary part modelled elsewhere
        "children_2025": 84_881,          # MAN00101, under 18
    },

    # ------------------------------------------------------------- emissions
    # Iceland's emissions are unusual: electricity is already clean, so industry — the smelters above all —
    # dominates. Ending the smelter contracts is therefore a large emissions change as well as a fiscal one, and
    # a model that reallocates 12.9 TWh without saying so is hiding the most defensible argument for doing it.
    # EST: about 1.8 Mt CO2e a year from the smelters, against roughly 4.6 Mt of total territorial emissions.
    "emissions": {
        "total_mt": 4.6,
        "smelter_mt": 1.8,
        "per_capita_baseline": True,
        "carbon_price_isk_per_t": 12_000,  # EST: ETS-linked, for valuing the change
    },

    # ---------------------------------------------------------------- crime
    # Public order and safety cost 75.9 ma.kr. in 2025 (THJ05142), of which police 41.5 and courts 10.8. Fire
    # protection does not respond to crime, so the responsive base is about 57 ma.kr.
    #
    # The evidence runs both ways and the model carries both. Cash transfers reduce acquisitive crime: the
    # Cherokee casino payments cut minor offending among the young, working through less poverty and better
    # parenting (Akee et al.); studies of welfare payment timing find property crime tracks how much money
    # households have. But Alaska's Permanent Fund Dividend shows the other side — property crime fell slightly
    # while substance-related incidents rose in the days after payment (Watson, Guettabi & Reimer 2020). A model
    # that only carried the favourable half of this literature would be advocacy, not evidence.
    "crime": {
        "responsive_spending_bn": 57.3,   # police, courts and prisons; fire protection excluded
        "hardship_weight": .55,           # EST: living below subsistence, the strongest driver
        "youth_idle_weight": .70,         # EST: involuntary idleness under 30, where offending concentrates
        "childhood_weight": .045,         # EST: per childhood year spent poor (Akee et al.)
        "substance_weight": .12,          # EST: the Alaska finding — a large payment raises substance incidents
        "substance_threshold": 300_000,   # EST: monthly payment above which that term starts to bite
        "cost_elasticity": .8,            # EST: how far spending follows offending
        # Prison. About 180 inmates on an average day (EST, Fangelsismálastofnun), at 56,750 kr. a day in 2024.
        # Today benefits stop after four months of continuous imprisonment (lög um almannatryggingar), which
        # is about 60% of prison time (EST). Withholding the borgaralaun makes prison dearer for the prisoner,
        # but the evidence is that the severity of punishment deters little; its certainty deters (Nagin 2013;
        # Chalfin and McCrary 2017). EST: 1% less offending if a prison year also costs a full year's payment of
        # 300 þús. a month.
        "prisoners0": 180,
        "prison_cost_per_day": 56_750,
        "forfeit_deterrence": .01,
    },

    # ---------------------------------------------------------- childhood and later life
    # Growing up out of poverty shows up decades later. The Cherokee payments raised educational attainment and
    # cut criminality (Akee et al.); Baby's First Years found unconditional cash to low-income mothers changed
    # infant brain activity (Noble et al. 2022). Modelled as a penalty carried into adulthood by the years a
    # child spent in a poor household, which a payment to every child removes.
    "childhood": {
        "earnings_persistence": .25,     # Nordic intergenerational earnings elasticity, ~.2-.3
        "wage_penalty_per_year": .011,    # EST: earnings cost of each childhood year spent poor
        "study_penalty_per_year": .030,   # EST: and the cost to the chance of going on to study
        "max_years": 18,
    },

    # ------------------------------------------------------------- life satisfaction
    # EST weights, in points on the 0-10 ladder. Signs and rough magnitudes follow the life-satisfaction
    # literature; the anchor is Iceland's published score, and only differences from it should be read.
    "wellbeing": {
        "anchor": 7.5,            # World Happiness Report / Eurostat: Iceland ~7.5 on the Cantril ladder
        "income": 0.60,           # per log point of equivalised income against the median
        "unemployment": 1.20,     # involuntary idleness, over and above the income it costs
        "ill_health": 1.00,
        "partner": 0.30,
        "work_quality": 0.50,     # meaning less disamenity, scaled by hours
        "security": 0.35,         # a contract with years left on it
        "housing_burden": 0.60,   # paying more than 40% of income for somewhere to live
        "hardship": 1.00,         # below subsistence
        "time_squeeze": 0.30,     # full-time work with a child under school age
    },

    # ---------------------------------------------------------------- childcare
    "childcare": {
        # EST: full-day places for 1-5 year olds today (leikskólar); Reykjavík already has a waiting list
        "places_full_time": 19_000,
        "cost_per_place_bn": 2.6e-3,      # EST: ~2.6 m ISK per place per year
        # EST: dagforeldrar places, which carry much of the under-2 gap before a leikskóli place opens up
        "childminder_places": 1_400,
        # a parent who gets neither falls back to part-time hours (behaviour.part_time_hours)
    },

    # ------------------------------------------------------- automation (automation.py)
    "automation": {
        # how fast machines get cheaper and more capable: 0 = no AI progress, .10 steady, .25 an AI jobs shock
        "ai_progress_rate": 0.0,
        "wage_sensitivity": 1.2,          # EST: how strongly expensive labour pulls automation forward
        "adoption_midpoint": 1.6,         # EST: cost ratio at which half the potential is taken up
        "adoption_curvature": 3.0,        # EST
        "adoption_speed": .25,            # EST: share of the gap closed each year (capital takes time)
        "operating_cost_share": .40,      # EST: running, energy and maintenance costs of the machines
        "output_gain": .25,               # EST: output per remaining worker at full automation of exposed tasks
        # clawback levers
        "levy_rate": 0.0,                 # tax on machine income, on top of corporate tax
        "state_capital_share": 0.0,       # public ownership stake in automation capital
        "dividend_payout": .6,
        "stake_required_return": .07,     # EST: return equity investors ask of automation capital (its price)
        "stake_financing_rate": .03,      # EST: the state's long-run real cost of borrowing to buy a stake
        "exposure": {                     # EST share of a profession's tasks a machine could do
            "Clerks": .85, "Other machine operators": .70, "Fish processing workers": .70,
            "Bus and truck drivers": .65, "Retail and other service": .60, "Refuse collectors": .55,
            "Other elementary": .55, "Business professionals": .55, "Other associate professionals": .55,
            "Lawyers": .50, "Cleaners": .45, "Engineers and IT": .45, "Other professionals": .45,
            "Waiters and bar staff": .45, "Fishers and farm workers": .40, "Cooks": .35, "Managers": .30,
            "Other craft and trades": .35, "Artists and writers": .35, "Pilots, officers and controllers": .35,
            "Academics": .25, "Doctors": .25, "Secondary teachers": .20, "Nurses and midwives": .15,
            "Primary and pre-school teachers": .15, "Care assistants": .10, "Child-care workers": .05,
        },
        # v3: augmentation and new tasks (automation.py). Complementarity EST after Pizzinelli et al. (IMF WP
        # 2023/216): the share of a profession's work AI makes faster rather than replaces.
        "complementarity": {
            "Managers": .70, "Doctors": .75, "Lawyers": .65, "Academics": .70, "Engineers and IT": .60,
            "Business professionals": .60, "Other professionals": .60, "Secondary teachers": .55,
            "Primary and pre-school teachers": .50, "Nurses and midwives": .50, "Pilots, officers and controllers": .50,
            "Artists and writers": .45, "Other associate professionals": .45, "Clerks": .20, "Child-care workers": .25,
            "Care assistants": .25, "Cooks": .15, "Waiters and bar staff": .15, "Retail and other service": .20,
            "Fish processing workers": .10, "Fishers and farm workers": .15, "Other craft and trades": .25,
            "Bus and truck drivers": .15, "Other machine operators": .15, "Cleaners": .05, "Refuse collectors": .10,
            "Other elementary": .10,
        },
        # CALIBRATED (scripts/ai_calibrate.py, 2026-09-19): at 5%/yr AI, +0.51 pp/yr productivity by 2035, unemployment
        # +0.6 pp, output +4.7% in the status quo; at 15%/yr, +1.4 pp/yr and unemployment +5 pp.
        "augmentation_gain": .25,         # output per hour at full augmentation of complementary work
        "augmentation_midpoint": .6,      # capability gain (over 1) at which half the augmentation is taken up
        "augmentation_curvature": 2.0,
        # Acemoglu and Restrepo (2019): in 1947-87 new tasks roughly offset displacement; since, less. Set high here
        # because the consensus expects little change in unemployment at the pace most forecast.
        "reinstatement_share": .95,       # CALIBRATED: share of displaced work that comes back as new tasks
        "reinstatement_speed": .45,       # CALIBRATED: share of the gap closed each year
        # share of AI's productivity gain that negotiated rounds pass into pay, as for trend productivity
        "wage_passthrough": 1.0,
    },

    # ------------------------------------------------------------------ culture
    "culture": {
        "state_support_share": .45,       # EST: share of demand for artists funded by the state today
        "ticket_income_elasticity": .8,   # EST: how ticket-funded demand follows household consumption
    },

    # ---------------------------------------------------------- labour demand
    "labour": {
        "demand_elasticity": 0.471,         # TUNED 2016-25 backcast; was EST: long-run own-wage labour demand elasticity (range .3-1.5)
        "consumption_loading": [.1, .2, .3, .3, .8, .2, .4, .3, .7],   # EST kappa, by occupation group
        "export_loading":      [.1, .2, .2, .1, .4, .9, .5, .7, .4],   # EST x, by occupation group
        "export_cost_elasticity": .6,     # EST
        # the older, pay-only rule for moving profession; superseded by step_occupation_change (occupation_mobility),
        # which carries pay, empty posts, education and the retraining lever. Left at 0 so moves are not counted twice.
        "occupational_mobility": 0.0,
        # Employment contracts: pay is agreed when the contract is signed and holds until it ends, so wages move
        # as contracts come up for renewal. Dismissal takes a notice period and costs severance.
        "contract_lengths_private": {1: .45, 2: .30, 3: .15, 5: .10},
        "contract_lengths_public": {1: .25, 2: .30, 3: .25, 5: .20},
        "productivity_passthrough": 1.0,  # share of productivity growth a negotiated round passes into pay
        # The wage curve: pay is lower where unemployment is higher, elasticity about -0.1 (Blanchflower and Oswald
        # 1994; Nijkamp and Poot 2005, meta-analysis), including under Nordic centralised bargaining. Applied to the
        # floor an agreement sets for a profession, from its excess supply against a frictional rate. Without it a
        # profession automation had emptied kept receiving the economy's productivity raises for decades at 15-20%
        # unemployment (found 2026-10-01).
        "wage_curve_elasticity": .10,
        "frictional_unemployment": .035,
        # Icelandic agreements have given more than productivity: real wages rose 2.2% a year 2005-2025 against
        # 1.1% of productivity. Two sources, both tuned in the backcast: a share of terms-of-trade gains since the
        # contract was signed (the tourism boom and the strong króna of 2016-17), and a real premium a year.
        "tot_passthrough": 0.039,  # TUNED 2016-25 backcast
        "agreement_real_premium": 0.00551,  # TUNED 2016-25 backcast
        # Settlements compensate the prices since the last round in full, and productivity on top. That is
        # what the record shows: real wages (LAU04800) never fell over any ten-year window since 1989, so
        # Icelandic bargaining has more than kept pace with inflation. Below 1.0 the erosion compounds —
        # at .90 and 3.5% inflation it cost 1.6 points of real wage growth a year.
        "inflation_compensation": 1.0,
        "agreement_cycle_years": 3,       # under collective agreements renewals are synchronised, not staggered
        "renewal_bargaining": 0.983,        # TUNED 2016-25 backcast; how far a renewed contract moves to the market rate (agreements: less)
        # Employers offer longer contracts where people are hard to keep, and people value the security enough
        # to trade some pay for it. Contract length is therefore an outcome, not a fixed rule.
        "offer_length_sensitivity": 6.0,  # extra years offered per unit of excess demand for labour
        "max_contract_years": 6,
        "stability_value": .35,           # EST: utility of a secure contract, per year of its length (max 5)
        "notice_months": 3,               # dismissal notice, paid
        # EST: of the full-time workers a shortfall reaches, the share whose hours are cut to part time instead of
        # losing the job. Without it the model had no involuntary part-time at all, so the metric read zero.
        "hours_cut_share": .25,
        # Iceland takes a labour-market shortfall as lost purchasing power, not lost jobs: unemployment stayed
        # near 4% through 2008 while real wages moved sharply. Share of any shortfall absorbed by prices.
        # How much of the labour people offer the economy ends up absorbed by it. At 1 the workforce is absorbed at
        # unchanged relative wages, so pay tracks productivity — the long-run closure, and what Iceland's record
        # shows: large immigration was absorbed without unemployment rising. Below 1, the unabsorbed remainder
        # pushes wages down every year, which is what made the baseline slide.
        "supply_absorption": 1.0,
        # Prices absorbing a labour shortfall directly: available as a lever, but off by default. With demand
        # absorbing the labour offered to it there is no persistent shortfall to absorb, and leaving it on
        # together with the negotiated floor makes the two chase each other into a wage-price spiral.
        "real_wage_absorption": .0,
        "max_yearly_erosion": .06,        # EST: most purchasing power a single year can take away
        "dismissal_speed": .8,            # share of surplus staff let go per year, given notice periods
        # The state raises pay where it cannot fill its own posts, instead of leaving the service short. EST: a
        # profession with a tenth of its public posts unfilled gains about 3.5% a year on the going rate, half of
        # what it gained falls away once the posts fill, and the state will go up to 40% above the market before
        # it stops. Iceland's nurses (2015, 2020) and teachers (2024) were settled this way, outside the general
        # round, at premiums of that order.
        # A shortage the pay rise does not close is carried two ways: the people in post work harder, and some of
        # the work is not done. EST: half and half. Iceland's own record in health and schooling is of both at once
        # — waiting lists and closed wards alongside overtime and larger classes.
        # Public staffing that follows need rather than a flat cut: what weighs on the state's
        # social work, and how much of each profession's public work is of that kind. EST, sized on Hagstofa's
        # spending by function (THJ05142): social protection administration, public order and safety, and the
        # part of health that is mental health. Essential care and teaching are driven by the population they
        # serve and are not in this table at all, so nothing here can cut a nurse or a teacher.
        "social_need_weights": {"hardship": .4, "child_poverty": .3, "crime": .3},
        "social_need_share": {"Clerks": .25, "Other associate professionals": .35, "Other professionals": .25,
                              "Lawyers": .30, "Managers": .10},
        "shortage_absorbed": .5,
        # EST: a profession with a tenth of its posts unfilled is as unpleasant to work in as one step of the
        # disamenity scale. Nurse burnout studies put intention-to-leave sharply higher at high patient loads
        # (Aiken et al. 2002); this is the mechanism that makes a shortage widen itself.
        "workload_disamenity": .4,
        # Iceland's collective agreements run in rounds a few years apart (the 2024 settlement was for four
        # years), so pay cannot answer a shortage in the year it appears. Where pay is set job by job it can.
        # People change profession, so the model can ask what happens when people can move to the work they are
        # best suited to. EST: about 4% of workers change
        # profession in a year, the young and those out of work more readily; moves follow how a profession's pay
        # has moved against the base year and how many of its posts are unfilled, within the education it asks
        # for. `match_quality_gain` is what moving to work that fits is worth in what a person produces — the
        # direction is better evidenced than the size, so it is a lever and 0 switches it off.
        "occupation_mobility": .04,
        "occupation_move_young": 2.0,
        "occupation_move_idle": 1.5,
        "occupation_move_max_age": 55,
        "occupation_pay_pull": 3.0,
        "occupation_shortage_pull": 1.5,
        "match_quality_gain": .02,
        # More moves under a secure income, at a 300 þús. payment: the share added to today's rate. The
        # direction follows the unemployment-insurance evidence that a cushion buys a better match (Nekoei and
        # Weber 2017, AER: longer benefits, higher re-employment wages); the size is an estimate.
        "occupation_mobility_security": .5,  # EST
        "agreement_round_years": 3,
        # TUNED 2016-25: at .35 the premium lifted public pay 18% above the market by 2025 and the public payroll
        # ran 60 ma.kr. above the national accounts; at .12 it reaches about 6%, which the record's payroll and
        # the public sector's modestly faster pay rises (Hagstofa's wage index by sector) bear out.
        "public_shortage_pay_speed": .12,
        "public_shortage_pay_decay": .5,
        "public_shortage_pay_cap": 1.4,
        "clearing_iterations": 80,
        "clearing_step": .15,             # how far the wage solver moves each iteration (small markets overshoot)
        "safety_wage_bound": .15,   # EST: how far a new offer may sit from the wage the job already pays
        "max_entry_share": .12,           # people entering a profession in one year, as a share of its size
    },

    # --------------------------------------------------------------- ventures
    "ventures": {
        "initial_founder_stock_years": 3.4,   # EST: steady-state founder stock = yearly founders x this
        "baseline_founders_per_year": 2700,   # EST: ~70% of FYR09002 enterprise births by individuals
        "idea_rate": .03,                     # EST: chance a re-thinking adult has a venture idea (x enterprise x spirit)
        "survival_year1": .79, "survival_later": .82,  # FYR09002: t+1 .79, t+3 .54
        "jobs_at_birth": 1.2, "job_growth_survivors": .10,
        "profit_pareto_alpha": 1.15, "profit_scale": 2_500_000,  # EST: annual ISK, minimum of Pareto
        "size_per_quality": 50.0,         # EST: jobs a firm grows towards, per unit of quality (average quality ~1.2)
        "profit_persistence": .7,         # EST: share of last year's profit a firm carries into this year
        "education_idea_bonus": .45,      # EST: how much a degree raises the chance of an idea worth acting on
        "education_quality_bonus": .30,   # EST: and how much better the firm that comes of it tends to be
        "capital_reference": 5_000_000,   # EST: capital that counts as a real start
        # EST: how much own capital eases starting. The whole payout now counts (it was a quarter of it, set aside),
        # so .43 keeps a full fund's effect where the quarter put it: 1 + .43 x 3 (the cap) = 1 + .8 x 1.6.
        "seed_capital_effect": .43,
        "profit_cap": 20e9,               # no single firm earns more than ~Iceland's largest companies
        "corporate_tax": .20, "dividend_payout": .30,
        "exit_probability": .01, "exit_multiple": 8,
        # v3: the state's stake is state_venture_stake × (1 - outside share of funding), at least stake_floor. EST:
        # outside money is 20% of a typical small firm's funding — most start on savings, the fund and the
        # borgaralaun — and 85% of a firm's by the time it is sold, after several rounds.
        "external_share_typical": .20, "external_share_at_exit": .85, "stake_floor": .05,
        # the deemed fund's share: one fund against what a small firm starts with (capital_reference, with its
        # outside share), and by the time a firm is sold one deemed fund for each round it raised
        "rounds_to_exit": 3,              # EST
        "capital_at_exit": 400e6,         # EST: capital raised by a firm by the time it is sold (kr.)
        "entry_selection_elasticity": .3,
        "founder_draw_share": .3,          # founder pays self this share of prior wage from seed/savings
        "capital_access_status_quo": .35,  # EST: share of would-be founders with own seed capital
        # v3: with no seed money the borgaralaun is the runway: living costs covered while a firm starts, but no
        # capital handed over. EST .6 (it was 1.0 with 3 m kr. a firm).
        "capital_access_platform": .6,
    },

    # --------------------------------------------------------------- migration
    "migration": {
        "eea_share_of_immigrants": .72,   # EST
        "emigration_income_elasticity": 0.825,  # TUNED 2016-25 backcast; was EST
        "recent_arrival_emigration_multiplier": 2.5,  # EST: return migration in the first 3 years
        "immigration_income_elasticity": 1.33,  # TUNED 2016-25 backcast; was EST
        "immigration_demand_elasticity": 2.94,  # TUNED 2016-25 backcast; was EST
        "immigration_tightness_elasticity": 1.97,  # TUNED 2016-25 backcast; how strongly arrivals follow unfilled jobs (tuned in the backcast)
        # Share of the jobs the economy adds in a year that are filled by people arriving for them. Iceland's
        # employment growth in 2016-2018 and 2022-2023 came mostly from arrivals; tuned in the backcast.
        "new_job_fill_share": 0.978,  # TUNED 2016-25 backcast
        "foreign_wage_ratio": [1.15, 1.20, 1.10, 1.00, .95, 1.00, 1.15, 1.05, .95],  # EST: Nordic net PPP / Iceland, by occupation
        "arrival_rent_elasticity": 1.0,   # EST: arrivals against rents (housing costs and migration: ~0.5-1)
        "max_arrival_rate": .07,          # EST: soft ceiling on a year's arrivals, share of the population
        "arrival_partner_share": .30,     # EST: share of arriving workers who bring a partner
        "arrival_partner_employment": .55,  # EST
        # children per arrival are no longer a setting: they come from Hagstofa's age profile of immigration
        "arrival_occupation_wage_response": 3.0,  # EST: arrivals tilt towards occupations whose real wage rose
        "immigrant_occupation_mix": [.03, .08, .07, .04, .24, .04, .16, .12, .22],  # EST, by occupation group
    },

    # ---------------------------------------------------------------- dynamic markets (macro.py)
    "markets": {
        # A second status quo, for comparison: the world as the last decade actually went,
        # rather than as the forecasts have it. Over 2016-25 consumer prices rose 4.3%/yr (VIS01005) against the
        # 2.5% target, the króna drifted weaker, and rents and house prices outran incomes. At 1 the whole
        # decade's pattern is on; at 0 the forecasts stand. It applies to the reform and to the status quo alike,
        # so the comparison is like for like — a calm baseline flatters whichever side is being defended.
        "history_like": 0.0,
        "history_inflation": .04,         # VIS01005: 4.3%/yr over 2016-25; .04 is the decade's central rate
        "history_fx_drift": .010,         # EST: the real króna's drift over the decade, a point a year weaker
        "history_rent_drift": .015,       # EST: real rents outran incomes by about this much a year (HMS)
        "freeze_prices": False,           # diagnostic: switch off price, rent, exchange-rate and interest reactions
        "freeze_wages": False,            # diagnostic: new contracts at the reference run's rates (income_effect_check)
        "real_rate0": .035,               # policy rate 7.75% (Aug 2026) less ~4% inflation
        "mortgage_indexed_share0": .65,   # nearly two in three household mortgages are CPI-indexed (2025)
        "mortgage_amortisation": .025,    # EST: principal repaid a year, a 40-year loan
        # EST: how much more household spending answers the policy rate once no lending is indexed (1 = twice
        # as much). The case for the reform is exactly that indexation mutes this; its size is not settled.
        "indexation_transmission_gain": 1.0,
        "taylor_inflation": 0.997,           # TUNED 2016-25 backcast; real-rate response to excess inflation (Taylor principle)
        "taylor_gap": .25,                # response to labour-market pressure (relative to the status-quo path)
        "debt_maturity_years": 6,         # EST: average time for the debt stock to reprice
        "debt_indexed_share": .35,        # EST: CPI-indexed share of government debt
        "indexed_real_coupon0": .025,     # EST: average real coupon on the indexed government debt (RIKS indexed yields)
        "indexed_rate_passthrough": .5,   # EST: how far the real rate on new indexed debt follows the policy rate
        "long_rate_passthrough": .5,      # EST: how far the real mortgage rate follows the real policy rate
        "long_rate_years": 3.0,           # EST: years over which mortgage rates catch up (fixed-rate terms of 3-5)
        # Hagstofa THJ11011: labour productivity grew 1.07%/yr 2008-2025. Real wages (LAU04800) grew 2.1%/yr
        # over 2005-2025; the rest came from terms of trade, which the model does not project.
        "productivity_growth": .0107,
        # Iceland's CPI rose 4.55%/yr over 2005-2025 and 3.43%/yr over 2015-2025 (VIS01005); the Seðlabanki
        # targets 2.5%. Without a trend the model only shows relative-price drift, and a nominal contract never
        # loses its value between settlements — which is exactly how Icelanders take the hit in practice.
        "trend_inflation": .025,
        # Share of a tax-driven step in the price level the central bank looks through. Inflation targeters,
        # Seðlabanki included, treat a VAT change as a one-off shift in the level and answer only its second-round
        # effects on wages and expectations, which the net-of-tax index still carries. Applies in both worlds;
        # with VAT unchanged it changes nothing in the status quo.
        "policy_looks_through_tax": 1.0,
        "sovereign_fund_return": .035,    # EST: real return on a surplus put aside (Norwegian-style fund)
        "debt_risk_premium": .05,         # EST: real-rate premium per unit of debt/GDP above 2025, before capital controls
        # CPI weights from the 2025 basket (Hagstofa VIS01306): housing 30.3%, food 15.4%, transport 15.2%
        "w_tradable": .38, "w_nontradable": .32, "w_housing": .30,
        "cpi_food_weight": .154,
        "labour_cost_passthrough": 0.726,    # TUNED 2016-25 backcast; was EST
        "demand_pressure_passthrough": 0.218,  # TUNED 2016-25 backcast; was EST
        "profit_margin_elasticity": 1.0,  # EST: how far margins move when prices outrun wage costs
        "price_adjustment": 0.636,           # TUNED 2016-25 backcast; share of the gap to target prices closed each year
        "export_price_elasticity": 1.16,    # TUNED 2016-25 backcast; was EST
        "import_income_elasticity": 1.26,  # TUNED 2016-25 backcast; was EST
        "import_price_elasticity": 0.842,    # TUNED 2016-25 backcast; was EST
        "vat_input_export_burden_bn": 135.3,   # borne by exporters at the full restriction (EST, 97-152)
        "fx_current_account_response": 0.544,  # TUNED 2016-25 backcast; was EST: log change in króna per unit change of CA/GDP
        "fx_inflation_passthrough": 0.601,   # TUNED 2016-25 backcast; was EST
        "residential_share": .70,         # EST: share of fasteignamat that is housing
        "dwellings0": 165_000,            # EST (HMS)
        "housing_income_elasticity": 0.63,  # TUNED 2016-25 backcast; was EST
        "housing_price_elasticity": 0.71,   # TUNED 2016-25 backcast; was EST: rent elasticity of housing demand
        "rent_adjustment": .6,
        "housing_depreciation_and_risk": .03,  # EST: part of the user cost of owning
        "fund_housing_share": .5,         # EST: share of start-of-life payouts spent on housing
        # buying a first home (model.step_home_purchase)
        "first_home_deposit": .15,        # Seðlabanki: first-time buyers may borrow up to 85% of the price
        "first_home_dsti": .40,           # Seðlabanki (2022): payments up to 40% of disposable income, first-time
        "first_home_price_share": .80,    # EST: a first home against the average dwelling (a single buys smaller)
        "mortgage_payment_rate": .0055,   # EST: monthly payment per króna borrowed (indexed 40-year loans ~.45%,
                                          # non-indexed 25-year ~.8%; a mix)
        "first_home_rate": .40,           # EST: share of households able to buy who do in a year, set so first-time
                                          # purchases run near HMS's 3,500-4,000 a year
        # the pension funds' yearly net purchases of foreign assets, a steady outflow the króna answers today; as
        # far as contributions go to the state instead, it stops (macro.update_end_of_year)
        "pension_fx_outflow_bn": 100.0,   # EST: order of the funds' net foreign purchases, 2023-25 (Seðlabanki)
        "construction0": .011,            # EST: yearly completions/stock in the status quo (depreciation + population growth)
        "construction_elasticity": 1.3,   # TUNED 2016-25 backcast; was EST: response to house prices over building costs
        "dwelling_depreciation": .006,
    },

    # --------------------------------------------------------------- fisheries (sectors.py)
    "fisheries": {
        "revenue0": 303.6, "intermediate0": 79.3, "compensation0": 113.5,  # SJA08109, 2023, bn ISK
        "capital_cost0": 38.0,
        "fte0": 8000,                     # EST: fishing + processing FTE
        "occupation_mix": [.03, .02, .03, .02, .02, .45, .05, .30, .08],  # EST
        "imported_input_share": .6,       # EST: fuel, gear, etc.
        "labour_cost_elasticity": .2,     # EST: processing jobs vs wage costs in foreign currency
        "export_share": .95,
        "catch_index": 1.0,               # total allowable catch relative to 2025
        "rent_capture": .8,               # reform: share of profit above normal return captured by quota leases
        # what veiðigjald captures today: about 17.3 ma.kr. in 2026 after the 2025 reform, of 72.8 profit above a
        # normal return. Left at zero, the reform was credited with the whole fee as new money.
        "rent_capture_status_quo": .24,
    },

    # A fund holding part of the fishery's rent since the quota system began (v8, the counterfactual past; built by
    # scripts/fisheries_history.py). Off unless it holds assets or takes rent.
    "fisheries_fund": {
        "assets_bn": 0.0,                 # at the start, in the base year's krónur
        "capture": 0.0,                   # share of the rent it takes, the state's fee included (never below the fee)
        "payout": .03,                    # share of its value paid out each year, equally to every adult
        "return": .04,                    # EST: real yearly return abroad (a 60/40 world portfolio)
        "foreign_inflation": .02,         # EST
    },

    # ----------------------------------------------------------------- energy (sectors.py)
    # A resource windfall — oil or gas on the Jan Mayen ridge (the Dreki licences, 2013-18, found nothing worth
    # drilling), or minerals — as a world setting: it happens to the status quo and the reform alike, and the
    # question the page asks is what each does with it. Off by default. Sizes are for the page's optimistic
    # scenarios, not a forecast. Norway's petroleum net cash flow to the state ran 10-20% of mainland GDP at its
    # height (Norwegian Ministry of Finance, National Budget), under a 78% marginal tax on the rent (22% company
    # tax + 56% special tax, Petroleum Taxation Act); EST that Iceland's own hydrocarbon law would take as much.
    "windfall": {
        "rent_bn": 0.0,                   # resource rent a year at full production, before the state's take (2025 kr.)
        "start_year": 4,                  # EST: first production, years after the base year (a find already made)
        "ramp_years": 5,                  # EST: years from first production to full
        "state_take": .78,                # Norway's marginal take on petroleum rent
        "rent_share_of_revenue": .6,      # EST: rent is about 60% of the value produced at typical prices
        "fte_per_100bn": 300,             # EST: direct jobs per 100 ma.kr. of rent (Norway ~25,000 direct on ~8,000 ma.kr.)
        "occupation_mix": [.05, .30, .10, .03, .02, .0, .20, .25, .05],
    },
    # The state's deemed stake in every company that raises capital (a reform option). Each funding round, in an
    # old company or a new one, issues the state shares worth one deemed start-of-life fund, diluting the owners;
    # over the years the state comes to own a growing share of the corporate sector, and its dividends are revenue.
    # Firms answer by raising less equity (debt, or abroad), and less new equity means a little less investment.
    # All EST: Iceland has no such instrument, and nobody else does at this scale.
    "public_equity": {
        "enabled": 1.0,
        "rounds_per_year": 4000,          # EST: ~3,000 companies registered a year (RSK) and ~1,000 capital increases
        "round_size": 60e6,               # EST: equity raised per round, value-weighted average (kr.)
        "equity_value_bn": 6000.0,        # EST: listed (~2,700, Nasdaq Iceland 2025) and unlisted equity, 2025
        "raising_share": .12,             # EST: share of corporate profits earned by firms raising capital in a year
        "payout": .5,                     # EST: share of after-tax profits paid as dividends (listed firms ~50%)
        "avoidance_elasticity": 1.0,      # EST: rounds fall to (1 - a round's deemed share) ** this
        "productivity_cost": .04,         # EST: long-run output lost if the state took all new equity
        "cost_years": 10,                 # EST: how long investment takes to adjust
    },
    # A pandemic, and two ways of answering it.
    "crisis": {
        # Most of 2020-21's support paid wages — hlutabætur, notice-period support — and under the reform wages
        # are lower, since the payment already carries part of everyone's income: that part scales with the
        # reform's pay against the status quo's. Closure and revenue-loss grants do not. EST.
        "wage_linked_share": .6,
        # "Shielding": no money to firms and no shutdown; those at high risk are offered a top-up to live in
        # designated areas (the empty hotels), and young people out of work are paid well to be on call there.
        # Set year by year as history keys (shield_*); the sizes below are what the long view and the past use. EST.
        "shield_people": 30_000,          # EST: ~45,000 over 70 and ~15,000 younger at high risk; half accept
        "shield_topup": 150_000,          # EST: kr. a month on top of the payment
        "shield_carers": 6_000,           # EST: one young carer for five shielded
        "shield_carer_pay": 650_000,      # EST: kr. a month, gross
        "shield_room_night": 12_000,      # EST: kr. a night for a hotel room at the state's rate
        "shield_people_per_room": 1.5,
        "lockdown_share": .30,            # EST: share of 2020-21's output fall that came from domestic restrictions
    },
    "energy": {
        "smelter_twh0": 12.9,             # Orkustofnun: ~65% of 19.6 TWh
        "smelter_price_usd_mwh": 35.0,    # EST: average contract price
        "aluminium_price_link": .4,       # EST: how much of the contract price follows the aluminium price
        "generation_cost_usd_mwh": 15.0,  # EST: running + capital cost of existing hydropower
        "smelter_net_export_bn_per_twh": 17.0,  # EST: 442 bn Al+Si exports x .5 net of imported alumina, per TWh
        "smelter_fte0": 2000,             # EST: direct jobs
        "smelter_occupation_mix": [.05, .10, .10, .03, .02, .0, .20, .45, .05],
        "alternative_occupation_mix": [.08, .25, .15, .05, .05, .10, .12, .15, .05],
        "state_dividend_share": .8,       # Landsvirkjun is state-owned; share of rent change paid to the treasury
        # reform levers
        "smelter_exit_share": 0.0,        # share of smelter contracts ended (a reform option; 0 by default)
        "exit_start_year": 3,
        "exit_years": 3,
        "contract_compensation_bn": 150.0,  # EST: total arbitration/compensation, spread over the exit years
        "alternative_uses": [             # EST: share of freed power, price, jobs, net exports, ramp-up
            {"name": "Data centres", "share": .30, "price_usd_mwh": 55, "jobs_per_twh": 40, "net_export_bn_per_twh": 6, "ramp_years": 3},
            {"name": "E-fuels and hydrogen", "share": .25, "price_usd_mwh": 35, "jobs_per_twh": 60, "net_export_bn_per_twh": 9, "ramp_years": 6},
            {"name": "Land-based aquaculture", "share": .15, "price_usd_mwh": 45, "jobs_per_twh": 150, "net_export_bn_per_twh": 22, "ramp_years": 5},
            {"name": "Greenhouses and food", "share": .10, "price_usd_mwh": 40, "jobs_per_twh": 250, "net_export_bn_per_twh": 8, "ramp_years": 4},
            {"name": "Electrified transport", "share": .10, "price_usd_mwh": 60, "jobs_per_twh": 20, "net_export_bn_per_twh": 12, "ramp_years": 6},
        ],
    },

    # ------------------------------------------------------- frontier programmes (frontier.py)
    # Switchable state investments in automation built on cheap power, cold water and the fishing grounds.
    # All figures are EST orders of magnitude in bn ISK per year at full scale.
    # ------------------------------------------------------------ infrastructure
    # Public works Iceland has repeatedly deferred. Costs are EST, anchored where public estimates exist: the
    # Borgarlína light rail has been costed around 100-130 ma.kr., a Keflavík rail link around 105-150 ma.kr.,
    # and road tunnels run roughly 15-30 ma.kr. each. A ring railway has no serious costing and the figure here
    # is a placeholder of the right order, not an estimate.
    #
    # These differ from the frontier programmes: they earn no export revenue and pay back through travel time,
    # which shows up as productivity, plus the construction work itself. Ordinary road building and maintenance
    # is not modelled because it continues at about the same level either way.
    "infrastructure": {
        "scale": 1.0,
        "programmes": {
            "keflavik_rail": {
                "label": "Keflavík–Reykjavík rail link",
                "start_year": 2, "build_years": 7, "capex_bn_per_year": 21, "upkeep_bn_per_year": 3.5,
                "fte": 900, "occupation_mix": [.05, .12, .12, .05, .05, .0, .38, .18, .05],
                "productivity_gain": .004,   # the airport commute, for workers and for tourism
            },
            "city_light_rail": {
                "label": "Reykjavík light rail",
                "start_year": 1, "build_years": 10, "capex_bn_per_year": 11, "upkeep_bn_per_year": 4,
                "fte": 700, "occupation_mix": [.05, .12, .12, .05, .05, .0, .38, .18, .05],
                "productivity_gain": .006,   # the largest travel-time saving, because most people live here
                "construction_cost_cut": .02,
            },
            "country_tunnels": {
                "label": "Tunnels for the countryside",
                "start_year": 2, "build_years": 12, "capex_bn_per_year": 14, "upkeep_bn_per_year": 2.5,
                "fte": 800, "occupation_mix": [.04, .10, .10, .04, .04, .02, .40, .21, .05],
                "productivity_gain": .003,   # towns that can reach each other in winter
            },
            "ring_railway": {
                "label": "Railway around the country",
                "start_year": 5, "build_years": 15, "capex_bn_per_year": 40, "upkeep_bn_per_year": 12,
                "fte": 2200, "occupation_mix": [.05, .12, .12, .05, .05, .0, .38, .18, .05],
                "productivity_gain": .005,
            },
        },
    },

    "frontier": {
        "scale": 1.0,                     # multiplies the ambition of every enabled programme
        "success_rate": .7,               # EST: share of promised returns actually realised
        "programmes": {
            "controlled_environment_farming": {
                "label": "Indoor farming at scale",
                "start_year": 2, "build_years": 5, "capex_bn_per_year": 35, "upkeep_bn_per_year": 8,
                "twh": 1.2, "fte": 1400, "occupation_mix": [.05, .10, .10, .05, .10, .35, .10, .10, .05],
                "exports_bn": 25, "import_substitution_bn": 45, "state_return_bn": 12,
                "food_price_cut": .12,    # cheaper fresh food in the basket
            },
            "cultivated_protein": {
                "label": "Cultivated protein works",
                "start_year": 4, "build_years": 6, "capex_bn_per_year": 45, "upkeep_bn_per_year": 12,
                "twh": 1.8, "fte": 900, "occupation_mix": [.06, .25, .18, .05, .04, .05, .12, .20, .05],
                "exports_bn": 70, "import_substitution_bn": 25, "state_return_bn": 25,
                "food_price_cut": .06,
            },
            "autonomous_fisheries": {
                "label": "Autonomous fishing and processing",
                "start_year": 2, "build_years": 5, "capex_bn_per_year": 25, "upkeep_bn_per_year": 6,
                "twh": 0.4, "fte": 400, "occupation_mix": [.05, .25, .25, .05, .02, .08, .15, .10, .05],
                "exports_bn": 0, "import_substitution_bn": 0, "state_return_bn": 10,
                "fisheries_labour_cut": .35,   # fewer crew and processing hands
                "fisheries_revenue_gain": .08,  # better selection, less waste, steadier quality
            },
            "robotic_construction": {
                "label": "Factory-built housing",
                "start_year": 2, "build_years": 4, "capex_bn_per_year": 20, "upkeep_bn_per_year": 5,
                "twh": 0.3, "fte": 1200, "occupation_mix": [.05, .10, .12, .05, .03, .0, .40, .20, .05],
                "exports_bn": 5, "import_substitution_bn": 15, "state_return_bn": 8,
                "construction_cost_cut": .20,   # cheaper homes, so more get built
            },
            "carbon_mineralisation": {
                "label": "Carbon storage services",
                "start_year": 3, "build_years": 6, "capex_bn_per_year": 30, "upkeep_bn_per_year": 10,
                "twh": 1.5, "fte": 700, "occupation_mix": [.06, .22, .20, .05, .02, .0, .25, .15, .05],
                "exports_bn": 60, "import_substitution_bn": 0, "state_return_bn": 20,
            },
        },
    },

    # ------------------------------------------------------------ the housing ladder and moves (housing.py, v10)
    "housing_segments": {
        # Dwellings by size (housing.SIZES): studio, flat for one or two, flat for a family with a child, flat or
        # small house for two children, house for three or four, large house. EST from the census's dwellings by
        # number of rooms (1, 2, 3, 4, 5-6, 7+); to be checked against Hagstofa's 2021 census table.
        "stock_shares": [.06, .17, .27, .24, .19, .07],
        "largest_let": 3,                  # EST: few homes larger than a two-child flat are let
        "value_step": 1.25,                # EST: a size no owner holds is worth this much more than the size below
        "well_off_share": .25,             # EST: the top quarter by income or wealth wants a size more than it needs
        "adjustment": .5,                  # EST: share of the gap to a size's clearing price closed in a year
        "construction_split_elasticity": 4.0,   # EST: new building tilts towards the sizes whose prices have risen
        "conversion_rate": .03,            # EST: share of a size's stock divided a step down a year per unit of the gap
        "_rent_factor": None,              # each size's rent against the market's, set every year by update_segments
        "leave_home_elasticity": 1.0,      # EST: young adults leave home faster as a studio gets cheaper against pay
        # Choosing a size (housing.choose_size), among the one needed and the two above: EST, so that at the base
        # year's prices about three in four take the size they need, and a size 25% dearer than the next loses about
        # half its takers to it
        "extra_room_penalty": 1.2,
        "size_price_elasticity": 3.0,
    },
    "downsizing": {
        # Yearly chance that a household with more room than it needs moves down the ladder, by age. EST from moving
        # rates of older owners in Europe and the US, 1-3% a year and rising with age (Banks et al. 2012; Angelini and
        # Laferrère 2012); most such moves follow a partner's death or ill health (Venti and Wise 2004).
        "hazard_under_55": .015, "hazard_67": .020, "hazard_75": .030, "hazard_85": .045,
        "widowed_multiplier": 3.0,         # EST: in the two years after a partner's death
        # EST: the hazard rises by this multiple of how far income is below the poverty line, as a share of the line
        # (a household 30% below it moves twice as often). The evidence of moving for money is weak; 0-6 is plausible.
        "income_gap_response": 3.0,
        # EST: at 55-66 it rises by this multiple of how much further, in this run than at the start, the income of
        # those just retired falls below that of those still working (moving before the money runs short)
        "anticipation_response": 4.0,
        "renter_share": .5,                # EST: renters with room to spare move down at half the owners' rate
        "price_response": 3.0,             # EST: less often by the smaller home's price against their own, to this power
        "max_steps_down": 3,
        "min_release": .10,                # EST: a move that frees less than a tenth of the price is not made
        "transaction_cost": .03,           # agent's fee with VAT (~2%) and stamp duty (0.8%)
        "min_equity": 15e6,                # EST: owners with less equity than this (2025 kr.) do not move for money
        "annuitised_share": .6,            # EST: the part of the cash turned into a lifetime income; the rest is spent
        "annuity_real_rate": .03,          # EST: the real return an annuity pays
    },
    "upscaling": {
        # A crowded household of working age moves up with this yearly chance per size it lacks (two at most),
        # if it can pay: the deposit from its equity and savings, the payments within the central bank's limit
        "hazard": .12,                     # EST: a crowded family moves within about four to eight years
        "price_response": 2.0,             # EST: less often by the larger home's price against its own, to this power
        "deposit": .20,                    # EST: of the new home's price
        # EST: households with the room they need trade up a size at this rate times how far the larger home's
        # price has fallen below their own's (to the power price_response, less one); none at the base year's prices
        "trade_up_rate": .05,
    },

    # ------------------------------------------------------------ household wealth (model.py)
    "wealth": {
        "net_worth_excl_pensions_pct_gdp": 206,  # Landssamtök lífeyrissjóða (2022): 206% of GDP
        "liquid_share": .30,              # EST: financial net wealth share; the rest is housing equity
        "wealth_sd": 1.2,                 # EST: lognormal dispersion
        "pareto_alpha": 1.6,              # EST: tail of the top 1% (wealth taxes and top shares: ~1.4-1.8)
        "mpc_bottom": .98, "mpc_top": 0.862,  # TUNED 2016-25 backcast; was EST: marginal propensity to consume out of income, by income rank
        "mpc_liquid_wealth": 0.0249,         # TUNED 2016-25 backcast; was EST: yearly consumption out of liquid wealth
        "mpc_housing_wealth": .015,       # EST: yearly consumption out of housing equity
        "liquid_return": .02,             # EST: real return
        "annuity_rate": .04,              # wealth drawdown available to finance not working
        "borrowing_limit_months": 3,
        # household consumption is calibrated to the observed saving rate: consumption 2,439.6 bn against
        # gross disposable income 2,520.6 bn in 2025 (Hagstofa THJ02103, THJ06021) = 3.2% saved
        "target_consumption_ratio": .968,
        # v9: EST share of capital income (after its tax) spent in the year; most of it is the wealthiest's and is
        # reinvested. The consumption ratio above is calibrated on the rest of income, as in v8.
        "mpc_capital_income": .25,
        "consumption_rate_sensitivity": 2.0,
        # EST: how much more of their income people spend once it is guaranteed rather than
        # merely large. A move from nothing guaranteed to everything guaranteed raises the marginal propensity to
        # consume by this much. Precautionary saving is well evidenced — Carroll (1997) buffer-stock theory,
        # Carroll and Samwick (1998) put precautionary wealth near a tenth to a fifth of household wealth — but
        # the size of the response to a permanent floor is not settled, so this is a lever and it can be set to 0.
        "security_mpc_gain": .10,  # EST: % less consumption per percentage point of extra real rate
    },

    # ------------------------------------------------------------- demography
    "demography": {
        "couple_catch_up": .3,             # EST: share of each age band's shortfall in couples closed in a year (step_partnerships)
        "births_per_year": 4300,          # EST ~2025
        "fertility_income_elasticity": .5,  # EST (range .1-1): births change per unit (usable child income change / household income)
        "deaths_per_year": 2600,          # EST
        "mortality_improvement": .012,    # EST: yearly fall in death rates at every age (Hagstofa's projections
                                          # assume life expectancy rising about a year a decade)
        # When in life children come. Iceland's mean age at a birth is about 31 and rising.
        # The hypothesis tested: with a secure income, studying and raising a small child can happen together,
        # so births come earlier, before a career rather than in the middle of building one.
        "birth_age_mean": 31.0,           # Hagstofa: mean age of mothers at all births, ~31
        "birth_timing_shift": 1.0,        # EST (lever, 0-3): years earlier at a 300 þús. payment, reached over
        "birth_timing_years": 5,          # ... this many years; the move itself adds births while it happens
        # A birth costs a mother some of her pay for good — the wage-rate part of the child penalty, not the hours,
        # which the childcare and choice model already carry. Miller (2011, US, fertility-shock IV) finds each year
        # of delay worth about 3% in wages; Kleven et al. (2019) put Denmark's long-run earnings penalty near 20%,
        # mostly hours. Timing it against labour-market entry rather than age (Herr 2011) shows a birth *before* a
        # career costs less than one early in it; Bach et al. (2025, Danish siblings) find student mothers who
        # finish catch up or overtake by 40 from university colleges, not quite from universities. Picchio et al.
        # (2021, Italy) find the cost smallest when a first child comes 7-9 years after leaving school, and
        # Doren (2019) that timing barely matters for the less educated. So: a modest penalty, a partial saving
        # for a birth before a career, and the model measures both against today's timing, not against zero.
        "birth_career_penalty": .04,      # EST: permanent wage-rate loss from a birth in the early career
        "birth_before_career_share": .5,  # EST: share of that loss a birth while studying or before 25 carries
    },
}


def energy_cuts(p):
    """The three parts of the energy-and-transport subsidies, as shares cut. A part left at None follows the
    combined lever, so older scenarios read as they did."""
    pol = p["policy"]
    both = pol.get("subsidy_cut_energy_transport", 0.0)
    return {k: both if pol.get(f"subsidy_cut_{k}") is None else pol[f"subsidy_cut_{k}"]
            for k in ("heating", "transition", "transport")}


def deep_merge(base, override):
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path=None, **overrides):
    p = DEFAULTS
    if path:
        p = deep_merge(p, yaml.safe_load(pathlib.Path(path).read_text()))
    return deep_merge(p, overrides)
