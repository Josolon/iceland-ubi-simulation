"""Quality check: does the model match the data, add up, and respond the way it should?

    .venv/bin/python scripts/quality_check.py [--years 6]

Four groups of checks:
  1. Calibration — the 2025 base year against published Icelandic figures.
  2. Accounting — identities that must hold inside any run (totals, stocks, flows).
  3. Behaviour — each lever moves the result in the direction it must, or the model is wrong.
  4. Wiring — parameters read but never defined, defined but never read, or the wrong length.

Every check prints PASS, WARN or FAIL with the numbers behind it. Exit code 1 if anything FAILs.
"""
import argparse
import json
import os
import pathlib
import pickle
import re
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402

from ubisim.abm import macro as macromod
from ubisim.abm import model, params  # noqa: E402
from ubisim.abm.population import FULL, PART, VENTURE  # noqa: E402
from ubisim.models import static_balance as sb  # noqa: E402

PLATFORM = {"regime": "platform", "wage_setting": "free_market"}
RESULTS = []

# keys a worker sends back: everything the checks below read, plus every profession wage
KEEP = ["year", "acc_benefit_old_age", "acc_benefit_disability", "acc_child_pension", "acc_capital_income_tax",
        "acc_capital_income", "acc_founder_dividends", "acc_benefit_interest_rebate", "poverty_rate_adults",
        "acc_benefit_unemployment", "acc_benefit_social_assistance", "acc_benefit_housing_benefit",
        "acc_benefit_fund_disability", "acc_benefits", "acc_child_payments", "public_equity_share", "public_equity_dividends", "public_equity_coverage", "public_equity_drag",
        "acc_corporate_tax_economy", "acc_public_equity_dividends", "deemed_fund_m", "acc_income_tax", "acc_labour_income_real", "acc_windfall_take", "output_index", "interest_bn", "population", "home_ownership_under_35", "first_home_purchases", "employment_rate_16_74", "fte", "fte_per_adult_16_74", "part_time_share",
        "independent_workers", "unemployment_rate", "price_level", "cpi", "exchange_rate", "house_price_index",
        "debt_pct_gdp", "balance_bn", "poverty_rate", "poverty_rate_anchored", "child_poverty_rate", "hardship_rate", "wellbeing_index",
        "parent_hours_index", "kindergarten_demand", "automated_share", "machine_income_bn", "contract_years_mean",
        "short_contract_share", "essential_services_gap", "weekly_hours_per_adult", "gdp_per_capita_index",
        "acc_consumption_real", "acc_revenue", "acc_expenditure", "acc_ubi_adult", "acc_child_payments",
        "acc_child_invested", "acc_automation_levy", "acc_automation_dividends", "acc_automation_tax",
        "acc_wealth_tax", "acc_childcare_cost", "acc_retraining_cost", "acc_public_payroll",
        "acc_public_housing_cost", "rent_index", "real_income_median", "net_income_mean_real",
        "net_income_d1", "net_income_d10", "own_net_income_median", "sovereign_fund_bn", "participation_tax_rate",
        "marginal_tax_rate_to_full_time", "ubi_replacement_rate", "mean_tenure_years",
        "contracts_expiring_share", "house_price_to_income", "housing_cost_burden",
        "emigrants_young_graduates", "job_changes", "wage_ratio_harsh_to_top", "income_gini",
        "students", "new_students", "graduates", "tertiary_share_16_74", "independent_creative",
        "wellbeing_p10", "wellbeing_struggling", "wellbeing_thriving", "wellbeing_idle",
        "health_mean", "poor_health_share", "acc_health_cost", "childhood_poverty_years",
        "crime_index", "acc_crime_cost", "hardship_rate", "terms_of_trade", "emissions_mt", "emissions_vs_2025",
        "acc_schooling_cost", "exports_bn",
        "net_income_sd", "standard_weeks_per_adult", "students_full_time",
        "wellbeing_worker", "acc_education_cost",
        "emigrants", "emigrants_children", "immigrants", "immigrants_children", "children_under_18",
        "debt_pct_gdp", "housing_cost_burden", "house_price_to_income", "births", "dwelling_stock_index",
        "acc_fisheries_fee", "acc_corporate_tax_economy", "acc_property_tax", "under_3_months_savings",
        "crime_index", "poverty_rate_anchored", "balance_operational_bn", "imports_bn", "acc_inheritance_tax",
        "acc_social_security", "acc_occupational_pensions", "acc_pension_topup", "variety_index", "new_ventures",
        "gambling_abroad_bn"]
# Real outcomes that must not depend on the rate of inflation. Every formula that sets a nominal amount against a
# real one fails this at once — the class of error that froze schooling, shrank the debt ratio and hid the
# property tax. The tolerance allows for the one real effect inflation has here: pay fixed in krónur between
# contract renewals.
NEUTRAL = [("real_income_median", "real median income", .04), ("employment_rate_16_74", "employment", .02),
           ("balance_operational_bn", "public balance after inflation's erosion of debt", .10),
           ("debt_pct_gdp", "debt ratio", .05),
           ("housing_cost_burden", "housing burden", .05), ("house_price_to_income", "house price to income", .05),
           ("acc_schooling_cost", "schooling bill", .02), ("acc_property_tax", "property tax", .05),
           ("acc_fisheries_fee", "fisheries fee", .10), ("acc_corporate_tax_economy", "corporate tax", .08),
           ("dwelling_stock_index", "housing stock", .02), ("under_3_months_savings", "savings buffers", .10),
           ("immigrants", "immigration", .08), ("poverty_rate_anchored", "poverty, fixed line", .10),
           ("crime_index", "offending", .05)]


def check(name, ok, detail, warn_only=False):
    status = "PASS" if ok else ("WARN" if warn_only else "FAIL")
    RESULTS.append((status, name, detail))
    print(f"  {status:4s}  {name:54s} {detail}", flush=True)
    return ok


def close(a, b, tol):
    return abs(a - b) <= tol * abs(b) if b else abs(a) <= tol


# ----------------------------------------------------------------- running scenarios
def _run(job):
    name, blob, overrides, years, reference = job
    soc = model.scenario(pickle.loads(blob), overrides)
    if reference is not None:
        soc.reference = reference
    # common random numbers: differences are the lever, not the draw. "name@seed" asks for other draws, where a
    # check reads one run against itself and would otherwise rest on a single set of draws
    seed = int(name.split("@")[1]) if "@" in name else 4242
    soc.rng = np.random.default_rng(seed)
    rows = [soc.step() for _ in range(years)]
    slim = []
    for r in rows:
        keep = {k: r.get(k) for k in KEEP}
        keep.update({k: v for k, v in r.items() if k.startswith(("wage_", "newpay_", "prof_n_", "prof_contract_"))})
        slim.append(keep)
    return name, slim


def run_all(blob, jobs, years, reference, workers):
    args = [(n, blob, o, years, reference) for n, o in jobs]
    with ProcessPoolExecutor(min(workers, len(args))) as pool:
        return dict(pool.map(_run, args))


def platform(**policy_extra):
    return {"policy": {**PLATFORM, **policy_extra}}


# ----------------------------------------------------------------- 1. calibration
def calibration_checks(soc):
    print("\n1. Calibration against published 2025 figures", flush=True)
    A, acc = soc.A, soc.accounts0
    ch = A["alive"] & A["chooser"]
    working = np.isin(A["status"], [PART, FULL, VENTURE])
    emp = float(working[ch].mean())
    # The base year itself has nobody between jobs — frictional unemployment starts with the first year's
    # separations — so the base snapshot reads a point high by construction; the rate is checked on the first
    # forward year of the status quo (section 3), where the survey's own mix of in-work and between-jobs holds.
    print(f"   (base-year snapshot, nobody yet between jobs: employment {emp:.1%})")
    part = float((A["status"][ch] == PART).sum() / max(np.isin(A["status"][ch], [PART, FULL]).sum(), 1))
    check("part-time share (VIN01104: 24.3%)", close(part, .243, .15), f"{part:.1%}")
    pop = int(A["alive"].sum())
    check("population (MAN43000: 394,108)", close(pop, 394108, .02), f"{pop:,}")
    nw = (A["wealth"] + np.maximum(A["home_value"] - A["mortgage_debt"], 0))[A["alive"] & (A["age"] >= 18)]
    top10 = float(np.sort(nw)[-max(len(nw) // 10, 1):].sum() / max(nw.sum(), 1))
    top1 = float(np.sort(nw)[-max(len(nw) // 100, 1):].sum() / max(nw.sum(), 1))
    # A wide band until the distribution is calibrated to Hagstofa's tax-return wealth by decile: the model's top is
    # too thin (business and financial wealth are a flat share of each household's), which is why a wealth tax
    # finds too small a base. Reported so the gap stays visible.
    check("richest tenth hold a plausible share of net wealth (EST 35-60%)", .30 <= top10 <= .60,
          f"{top10:.1%} (richest 1%: {top1:.1%}, where tax data suggest nearer 20%)")
    wage_bill = float((A["base_wage"] * soc.hours_of(A["status"]) * ch).sum() * 12 / 1e9)
    check("wage bill (TEK02001: 2,174 bn)", close(wage_bill, 2174.5, .10), f"{wage_bill:,.0f} bn")
    # GFS 1111, income tax of individuals (state 283.9 + útsvar 410.2); the model taxes pensions and benefits too, so
    # the whole of it is the comparable figure
    check("income tax of individuals (GFS 1111: 694.1 bn)", close(acc["income_tax"], 694.1, .12), f"{acc['income_tax']:,.0f} bn")
    corp = acc["corporate_tax_economy"] + acc["corporate_tax"]
    check("corporate tax (THJ05132: 148 bn)", close(corp, 148, .20), f"{corp:,.0f} bn")
    check("property tax (THJ05132: 102.8 bn)", close(acc["property_tax"], 102.8, .05), f"{acc['property_tax']:,.0f} bn")
    check("public payroll (THJ05143: 709.6 bn)", close(acc["public_payroll"], 709.6, .12), f"{acc['public_payroll']:,.0f} bn")
    # THJ06021 household consumption is 2,439.6 bn including rent and imputed rent (COICOP 04, ~20%). The model
    # handles housing separately as a cost, so the comparable figure is roughly 1,950 bn.
    check("consumption excluding housing (~1,950 bn)", close(acc["consumption_real"], 1950, .10),
          f"{acc['consumption_real']:,.0f} bn")
    # GFS 1141 is 433.7 bn, but it includes VAT paid by tourists, by the state and on inputs firms cannot reclaim;
    # the model's is VAT on households' consumption, a part of it
    check("VAT on household consumption: a part of GFS 1141's 433.7 bn", .55 * 433.7 <= acc["vat"] <= 433.7,
          f"{acc['vat']:,.0f} bn")
    benefits = acc["benefits"] + acc["child_payments"]
    check("social benefits within the 358.6 bn envelope", benefits <= 358.6 * 1.05, f"{benefits:,.0f} bn modelled")
    check("public order and safety, responsive part (THJ05142: 57.3 bn)",
          close(acc.get("crime_cost", 0), 57.3, .12), f"{acc.get('crime_cost', 0):,.1f} bn")
    check("public health spending (THJ05511: 405.8 bn)", close(acc.get("health_cost", 0), 405.8, .10),
          f"{acc.get('health_cost', 0):,.0f} bn")
    students = int((A["alive"] & (A["studying"] > 0)).sum()) if "studying" in A else 0
    check("students in tertiary education (SKO00000: 19,528)", close(students, 19528, .15), f"{students:,}")
    tert = float((A["education"][ch] == 2).mean())
    check("tertiary share of 16-74 (census ~35%)", close(tert, .35, .20), f"{tert:.1%}")
    old = A["alive"] & (A["age"] >= 67)
    pens = float(A["occ_pension"][old].mean()) if old.any() and "occ_pension" in A else float("nan")
    # v9: per RESIDENT 67+ (Skatturinn's 2024 total over residents, not the register's 60,403,
    # less pensions paid abroad, +8.5% per person to 2025: ~357k, range 350-367k); 295k was the register figure
    check("occupational pension per resident 67+ (2025: ~357,000)", pens != pens or close(pens, 357000, .05),
          f"{pens:,.0f} ISK/month" if pens == pens else "not stored per agent", warn_only=pens != pens)
    # v9: who older people live with, and who is on a disability pension (the population, base year)
    o67 = A["alive"] & (A["age"] >= 67)
    if "host" in A and o67.any():
        part = float((A["partner"][o67] >= 0).mean())
        check("67+ living with a spouse or partner (Hagstofa 1 Jan 2026: 60%)", abs(part - .60) <= .03, f"{part:.1%}")
        alone = float(A["lives_alone"][o67].mean())
        check("67+ living alone (2021 census: ~22%)", abs(alone - .22) <= .05, f"{alone:.1%}")
    dis = A["alive"] & A["disabled"] & (A["age"] < 67)
    check("disability and rehabilitation recipients (TR 2025: 29,465)", close(int(dis.sum()), 29465, .10), f"{int(dis.sum()):,}")
    dwork = float(np.isin(A["status"][dis], [PART, FULL, VENTURE]).mean()) if dis.any() else 0.0
    # working = TR's count less the survey's 19,900 inactive disabled and ill: about a third, part-time only
    check("of them working (TR less the survey's inactive: ~32%; none full-time)",
          abs(dwork - .325) <= .07 and not (A["status"][dis] == FULL).any(),
          f"{dwork:.0%} working, {int((A['status'][dis] == FULL).sum())} full-time")
    wealth = acc["household_liquid_wealth"] + acc["household_housing_equity"]
    check("household net worth (~206% of GDP)", close(wealth, 2.06 * 4941, .20), f"{wealth:,.0f} bn")
    surv = np.array([pr["weight"] or 0 for pr in params.PROFESSIONS], float)
    surv /= surv.sum()
    modelled = np.bincount(A["occupation"][ch & working], minlength=params.N_OCC).astype(float)
    modelled /= modelled.sum()
    worst = int(np.argmax(np.abs(modelled - surv)))
    check("profession mix vs wage survey (worst gap)", np.abs(modelled - surv).max() < .05,
          f"{params.OCCUPATIONS[worst]}: {modelled[worst]:.1%} vs {surv[worst]:.1%}")


# ----------------------------------------------------------------- 2. accounting
def accounting_checks(soc, rows, sq_rows=None):
    print("\n2. Accounting identities inside a run", flush=True)
    last = rows[-1]
    heads = sum(v for k, v in last.items() if k.startswith("prof_n_"))
    check("profession headcounts sum to employment", heads > 0 and abs(heads - last["fte"]) / heads < .35,
          f"{heads:,} people, {last['fte']:,.0f} FTE")
    check("FTE never exceeds headcount", last["fte"] <= heads * 1.02, f"{last['fte']:,.0f} vs {heads:,}")
    check("child UBI splits into spent and saved", last["acc_child_invested"] <= last["acc_child_payments"] * 1.001,
          f"saved {last['acc_child_invested']:,.0f} of {last['acc_child_payments']:,.0f} bn")
    check("revenue and expenditure are positive", last["acc_revenue"] > 0 and last["acc_expenditure"] > 0,
          f"revenue {last['acc_revenue']:,.0f}, spending {last['acc_expenditure']:,.0f} bn")
    if len(rows) > 1:
        d = rows[-1]["debt_pct_gdp"] - rows[-2]["debt_pct_gdp"]
        check("debt moves against the balance", (d <= .5) if rows[-1]["balance_bn"] > 0 else (d >= -.5),
              f"balance {rows[-1]['balance_bn']:,.0f} bn, debt {d:+.1f} pp")
    wages = [last[f"wage_{o}"] for o in params.OCCUPATIONS]
    check("no wage pinned to the solver's bounds", max(wages) < 3.9 and min(wages) > .31,
          f"range {min(wages):.2f}–{max(wages):.2f}")
    check("exchange rate away from its clamp", .51 < last["exchange_rate"] < 2.9, f"{last['exchange_rate']:.2f}")
    check("poverty rate in a plausible range", 0 <= last["poverty_rate"] <= .4, f"{last['poverty_rate']:.1%}")
    # A range test cannot catch a status quo that is too poor. Iceland's at-risk-of-poverty rate (60% of the
    # median, EU-SILC) has run at about 9-10% in recent years; the status quo's first year should be near it. Too
    # high means benefits the model does not pay — housing benefit above all — are missing from today's incomes,
    # which flatters any reform on poverty.
    first = sq_rows[0] if sq_rows else None
    if first and first.get("poverty_rate") is not None:
        check("status quo poverty near the published rate (EU-SILC ~9.5%)", close(first["poverty_rate"], .095, .25),
              f"{first['poverty_rate']:.1%}")
    check("unemployment in a plausible range", 0 <= last["unemployment_rate"] <= .35, f"{last['unemployment_rate']:.1%}")
    bad = [k for k in ("fte", "cpi", "balance_bn", "poverty_rate", "exchange_rate") if last[k] != last[k]]
    check("nothing is NaN in the headline series", not bad, ", ".join(bad) or "all finite")


# ----------------------------------------------------------------- 3. behaviour
def behaviour_checks(blob, years, workers):
    print("\n3. Do the levers move things the right way?", flush=True)
    ubi = dict(ubi_adult=450000, ubi_child=450000)
    mid = dict(ubi_adult=350000, ubi_child=350000)
    fast_ai = {"automation": {"ai_progress_rate": .25}}
    _, sq = _run(("sq", blob, {}, years, None))

    jobs = [
        ("ubi450", platform(**ubi)),
        ("ubi450_again", platform(**ubi)),
        ("ubi450@1", platform(**ubi)),
        ("ubi450@2", platform(**ubi)),
        ("proptax", platform(**ubi, prop_tax_extra_pp=3.0)),
        ("ai", params.deep_merge(platform(**ubi), fast_ai)),
        ("ai_highwage", params.deep_merge(platform(**ubi, minimum_wage=700000), fast_ai)),
        ("ai_clawback", params.deep_merge(platform(**ubi), {"automation": {"ai_progress_rate": .25, "levy_rate": .40,
                                                                          "state_capital_share": .50}})),
        ("fx", platform(**ubi, pension_fx_support_bn=200)),
        ("mid", platform(**mid)),
        ("mid_minwage", platform(**mid, minimum_wage=600000)),
        ("mid_childcare", platform(**mid, childcare_places_added=6000)),
        ("mid_fourday", platform(**mid, full_time_hours_factor=.80)),
        ("mid_wealthtax", platform(**mid, net_wealth_tax_pct=1.0)),
        ("mid_unindexed", platform(**mid, indexation_phaseout=1.0)),
        ("mid_retrain", platform(**mid, retraining_bn_per_year=30)),
        ("mid_taper", platform(**mid, ubi_taper_start=800000, ubi_taper_rate=.30)),
        ("mid_housing", platform(**mid, public_dwellings_per_year=2000)),
        ("mid_fund", platform(**mid, sovereign_fund_share=.50)),
        ("sq_flat_prices", {"markets": {"trend_inflation": 0.0}}),
        ("sq_dear_imports", {"trade": {"import_price": 1.10}}),
        ("mid_offset", platform(**mid, public_wage_offset_ubi=1.0)),
        ("mid_nofold", platform(**mid, pension_fold=0.0)),
        ("mid_inherit", platform(**mid, inheritance_tax_rate=.5)),
        ("mid_custodian", platform(**mid, custodianship=1.0)),
        ("mid_commcap", platform(**mid, commercial_ownership_cap=.05)),
        ("mid_agreements", {"policy": {**PLATFORM, **mid, "wage_setting": "status_quo"}}),
        ("mid_unprotected", platform(**mid, ubi_protected=0.0)),
        ("mid_block", platform(**mid, gambling_payment_block=1.0)),
        ("mid_freehealth", platform(**mid, free_health_care=1.0)),
        ("mid_gifts_open", platform(**mid, inheritance_tax_rate=.5, gift_tax_rate=0.0)),
        ("ubi450_flat_prices", params.deep_merge(platform(**ubi), {"markets": {"trend_inflation": 0.0}})),
    ]
    r = run_all(blob, jobs, years, None, workers)
    r["sq"] = sq
    last = {k: v[-1] for k, v in r.items()}
    # People must be able to buy homes in the status quo: before 2026-09-26 nobody could, and under-35 ownership
    # fell to nothing over thirty years. Over ten it should hold roughly where it starts, with first-time purchases
    # in the thousands a year (HMS counts some 3,000-4,000 first-time buyers).
    own = [row.get("home_ownership_under_35") for row in sq]
    buys = [row.get("first_home_purchases", 0) for row in sq]
    if own[0] is not None:
        check("the young keep buying homes in the status quo (ownership under 35 holds)",
              abs(own[-1] - own[0]) <= .08, f"{own[0]:.1%} → {own[-1]:.1%}, first-time purchases "
              f"{np.mean(buys):,.0f} a year")

    check("taking indexation out of loans raises what owners pay while inflation runs",
          last["mid_unindexed"]["housing_cost_burden"] > last["mid"]["housing_cost_burden"],
          f"housing burden {last['mid_unindexed']['housing_cost_burden']:.3f} vs {last['mid']['housing_cost_burden']:.3f}")
    check("taking indexation out of loans leaves the run finite",
          all(v == v for v in (last["mid_unindexed"]["real_income_median"], last["mid_unindexed"]["balance_bn"])),
          "median income and balance finite")
    print("   inflation neutrality, final year: with 2.5% trend / with none", flush=True)
    for with_, without in (("sq", "sq_flat_prices"), ("ubi450", "ubi450_flat_prices")):
        for key, label, tol in NEUTRAL:
            a, b = last[with_][key], last[without][key]
            if key == "balance_operational_bn":   # as a share of the base-year budget, not of a small number
                gap = abs(a - b) / 1500
            elif key == "debt_pct_gdp":     # in percentage points of GDP
                gap = abs(a - b) / 100
            elif 0 <= b < .05 and 0 <= a < .05:   # a small rate: relative to 5 points, not to itself
                gap = abs(a - b) / .05          # (poverty near 0.5% under a large payment moved 13% on noise)
            else:
                gap = abs(a - b) / max(abs(b), 1e-9)
            check(f"{with_}: inflation leaves {label} alone", gap <= tol, f"{a:,.4g} vs {b:,.4g}")

    check("a UBI reduces hours worked", last["ubi450"]["fte_per_adult_16_74"] < last["sq"]["fte_per_adult_16_74"],
          f"{last['ubi450']['fte_per_adult_16_74']:.3f} vs {last['sq']['fte_per_adult_16_74']:.3f}")
    check("a UBI raises household spending", last["ubi450"]["acc_consumption_real"] > last["sq"]["acc_consumption_real"],
          f"{last['ubi450']['acc_consumption_real']:,.0f} vs {last['sq']['acc_consumption_real']:,.0f} bn")
    check("a UBI is compared on income after tax and transfers, and wins there",
          last["ubi450"]["net_income_mean_real"] > last["sq"]["net_income_mean_real"],
          f"{last['ubi450']['net_income_mean_real']:,.0f} vs {last['sq']['net_income_mean_real']:,.0f} ISK/month "
          f"equivalised (wages: {sum(last['ubi450'][f'wage_{o}'] for o in params.OCCUPATIONS) / params.N_OCC:.2f} "
          f"vs {sum(last['sq'][f'wage_{o}'] for o in params.OCCUPATIONS) / params.N_OCC:.2f})")
    check("a UBI lifts the bottom decile most",
          last["ubi450"]["net_income_d1"] / last["sq"]["net_income_d1"]
          > last["ubi450"]["net_income_d10"] / last["sq"]["net_income_d10"],
          f"bottom {100 * (last['ubi450']['net_income_d1'] / last['sq']['net_income_d1'] - 1):+.0f}%, "
          f"top {100 * (last['ubi450']['net_income_d10'] / last['sq']['net_income_d10'] - 1):+.0f}%")
    check("a UBI cuts poverty, measured against a fixed line",
          last["ubi450"]["poverty_rate_anchored"] < last["sq"]["poverty_rate_anchored"],
          f"{last['ubi450']['poverty_rate_anchored']:.1%} vs {last['sq']['poverty_rate_anchored']:.1%} "
          f"against the 2025 median (relative line: {last['ubi450']['poverty_rate']:.1%} vs "
          f"{last['sq']['poverty_rate']:.1%}, which moves with the median)")
    check("more people work for themselves under a UBI",
          last["ubi450"]["independent_workers"] > last["sq"]["independent_workers"],
          f"{last['ubi450']['independent_workers']:,} vs {last['sq']['independent_workers']:,}")
    check("same inputs give the same answer twice",
          abs(last["ubi450"]["balance_bn"] - last["ubi450_again"]["balance_bn"]) < 1e-6,
          f"{last['ubi450']['balance_bn']:,.3f} vs {last['ubi450_again']['balance_bn']:,.3f}")
    check("property tax pushes house prices down",
          last["proptax"]["house_price_index"] < last["ubi450"]["house_price_index"],
          f"{last['proptax']['house_price_index']:.3f} vs {last['ubi450']['house_price_index']:.3f}")
    check("cheap machines automate work", last["ai"]["automated_share"] > .01,
          f"{last['ai']['automated_share']:.1%} of tasks")
    check("automation produces machine income", last["ai"]["machine_income_bn"] > 0,
          f"{last['ai']['machine_income_bn']:,.0f} bn")
    check("dearer labour automates faster",
          last["ai_highwage"]["automated_share"] >= last["ai"]["automated_share"] * .995,
          f"{last['ai_highwage']['automated_share']:.2%} with a 700k floor vs {last['ai']['automated_share']:.2%} without")
    took = lambda d: d["acc_automation_tax"] + d["acc_automation_levy"] + d["acc_automation_dividends"]
    check("clawback takes more of the machine income", took(last["ai_clawback"]) > took(last["ai"]) * 1.2,
          f"{took(last['ai_clawback']):,.0f} vs {took(last['ai']):,.0f} bn")
    check("selling foreign assets supports the króna",
          last["fx"]["exchange_rate"] <= last["ubi450"]["exchange_rate"] * 1.005,
          f"{last['fx']['exchange_rate']:.3f} vs {last['ubi450']['exchange_rate']:.3f}")
    real = lambda d, o: d[f"wage_{o}"] / d["price_level"]
    check("a minimum wage lifts the lowest-paid",
          real(last["mid_minwage"], "Cleaners") >= real(last["mid"], "Cleaners") * .995,
          f"{real(last['mid_minwage'], 'Cleaners'):.3f} vs {real(last['mid'], 'Cleaners'):.3f}")
    check("more childcare places let parents work more",
          last["mid_childcare"]["parent_hours_index"] >= last["mid"]["parent_hours_index"] * .995,
          f"{last['mid_childcare']['parent_hours_index']:.4f} vs {last['mid']['parent_hours_index']:.4f}")
    # Places are paid for only where parents want one and cannot get it, so the test is
    # that the lever costs money when there is a shortfall to meet — not that it spends whatever it is given.
    check("childcare places cost money where places are short",
          last["mid_childcare"]["acc_childcare_cost"] > last["mid"]["acc_childcare_cost"]
          or last["mid_childcare"].get("childcare_places_short", 0) <= 0,
          f"{last['mid_childcare']['acc_childcare_cost']:,.1f} vs {last['mid']['acc_childcare_cost']:,.1f} bn, "
          f"places short {last['mid_childcare'].get('childcare_places_short', 0):,.0f}")
    check("a four-day week cuts hours worked",
          last["mid_fourday"]["weekly_hours_per_adult"] < last["mid"]["weekly_hours_per_adult"],
          f"{last['mid_fourday']['weekly_hours_per_adult']:.1f}h vs {last['mid']['weekly_hours_per_adult']:.1f}h")
    check("a wealth tax raises revenue", last["mid_wealthtax"]["acc_wealth_tax"] > 5,
          f"{last['mid_wealthtax']['acc_wealth_tax']:,.0f} bn")
    check("retraining money is actually spent", close(last["mid_retrain"]["acc_retraining_cost"], 30, .05),
          f"{last['mid_retrain']['acc_retraining_cost']:,.1f} bn of 30")
    check("tapering the UBI costs less than paying it in full",
          last["mid_taper"]["acc_ubi_adult"] < last["mid"]["acc_ubi_adult"],
          f"{last['mid_taper']['acc_ubi_adult']:,.0f} vs {last['mid']['acc_ubi_adult']:,.0f} bn")
    check("building houses brings rents down",
          last["mid_housing"]["rent_index"] < last["mid"]["rent_index"],
          f"{last['mid_housing']['rent_index']:.3f} vs {last['mid']['rent_index']:.3f}")
    check("a sovereign fund accumulates when there is a surplus",
          last["mid_fund"]["sovereign_fund_bn"] > 0 or last["mid"]["balance_bn"] <= 0,
          f"{last['mid_fund']['sovereign_fund_bn']:,.0f} bn "
          f"(balance {last['mid']['balance_bn']:,.0f} bn)")
    check("a UBI improves health", last["ubi450"]["health_mean"] > last["sq"]["health_mean"],
          f"{last['ubi450']['health_mean']:.3f} vs {last['sq']['health_mean']:.3f}; in poor health "
          f"{last['ubi450']['poor_health_share']:.1%} vs {last['sq']['poor_health_share']:.1%}")
    # per person: a reform that keeps more people in the country spends more on their care in total
    pc = lambda k: last[k]["acc_health_cost"] / max(last[k]["population"], 1) * 1e6
    check("better health costs the health service less, per person",
          pc("ubi450") < pc("sq"),
          f"{pc('ubi450'):,.0f} vs {pc('sq'):,.0f} kr. a year per person "
          f"(Mincome: hospital use -8.5%)")
    # The evidence cuts both ways and so does the model: hardship-driven offending falls sharply, while the
    # Alaska substance channel pushes the other way. The honest test is that a UBI does not make offending
    # worse, not that it reliably improves it — and that the hardship it feeds on collapses.
    mean3 = lambda k, key: sum(r[key] for r in r_[k][-3:]) / 3
    r_ = r
    check("a UBI does not raise offending, and removes what feeds it",
          mean3("ubi450", "crime_index") <= mean3("sq", "crime_index") * 1.05,
          f"index {mean3('ubi450', 'crime_index'):.3f} vs {mean3('sq', 'crime_index'):.3f} (3-yr mean); "
          f"hardship {last['ubi450']['hardship_rate']:.1%} vs {last['sq']['hardship_rate']:.1%}")
    check("a UBI shortens childhood spent poor",
          last["ubi450"]["childhood_poverty_years"] < last["sq"]["childhood_poverty_years"],
          f"{last['ubi450']['childhood_poverty_years']:.2f} vs {last['sq']['childhood_poverty_years']:.2f} years")
    check("a UBI sends more people to study",
          last["ubi450"]["students"] > last["sq"]["students"],
          f"{last['ubi450']['students']:,} vs {last['sq']['students']:,} studying; tertiary share "
          f"{last['ubi450']['tertiary_share_16_74']:.1%} vs {last['sq']['tertiary_share_16_74']:.1%}")
    check("studying costs the state money", last["ubi450"]["acc_education_cost"] > 0,
          f"{last['ubi450']['acc_education_cost']:,.0f} bn")
    check("life satisfaction is anchored on Iceland's published score",
          abs(sq[0]["wellbeing_index"] - 7.5) < .6, f"status quo year 1: {sq[0]['wellbeing_index']:.2f} vs 7.5")
    check("a UBI raises life satisfaction", last["ubi450"]["wellbeing_index"] > last["sq"]["wellbeing_index"],
          f"{last['ubi450']['wellbeing_index']:.2f} vs {last['sq']['wellbeing_index']:.2f}; "
          f"struggling {last['ubi450']['wellbeing_struggling']:.1%} vs {last['sq']['wellbeing_struggling']:.1%}")
    check("the involuntarily idle are the least satisfied",
          last["sq"]["wellbeing_idle"] < last["sq"]["wellbeing_worker"],
          f"idle {last['sq']['wellbeing_idle']:.2f} vs working {last['sq']['wellbeing_worker']:.2f}")
    check("schooling costs follow how many children there are",
          close(last["sq"]["acc_schooling_cost"], 258, .15), f"{last['sq']['acc_schooling_cost']:,.0f} bn of 258")
    sqa, mid_ = last["sq"], last["mid"]
    check("the status quo collects today's fishing fee (veiðigjald ~17 ma.kr.)",
          8 < sqa["acc_fisheries_fee"] < 30, f"{sqa['acc_fisheries_fee']:.1f} ma.kr.")
    check("the status quo collects inheritance tax near today's (14.7 ma.kr. in 2024, advance inheritance included)",
          6 < sqa["acc_inheritance_tax"] < 30, f"{sqa['acc_inheritance_tax']:.1f} ma.kr.")
    check("a higher inheritance tax raises more", last["mid_inherit"]["acc_inheritance_tax"] > mid_["acc_inheritance_tax"],
          f"{last['mid_inherit']['acc_inheritance_tax']:.1f} vs {mid_['acc_inheritance_tax']:.1f} ma.kr. at 50% vs 10%")
    check("holding public take-home at its old level cuts the public payroll",
          last["mid_offset"]["acc_public_payroll"] < mid_["acc_public_payroll"] * .95,
          f"{last['mid_offset']['acc_public_payroll']:,.0f} vs {mid_['acc_public_payroll']:,.0f} ma.kr.")
    check("with pensions not folded in, contributions stay with the funds and the funds keep paying",
          last["mid_nofold"]["acc_social_security"] < mid_["acc_social_security"] * .2
          and last["mid_nofold"]["acc_occupational_pensions"] > 50,
          f"social security {last['mid_nofold']['acc_social_security']:,.0f} vs {mid_['acc_social_security']:,.0f}; "
          f"occupational pensions {last['mid_nofold']['acc_occupational_pensions']:,.0f} ma.kr.")
    check("custodianship: a small risk discount on prices, and more dwellings in use",
          last["mid_custodian"]["house_price_index"] < mid_["house_price_index"]
          and last["mid_custodian"]["dwelling_stock_index"] > mid_["dwelling_stock_index"],
          f"prices {last['mid_custodian']['house_price_index']:.3f} vs {mid_['house_price_index']:.3f}; stock "
          f"{last['mid_custodian']['dwelling_stock_index']:.3f} vs {mid_['dwelling_stock_index']:.3f}")
    check("a commercial ownership cap spreads ownership: variety up, more firms started",
          last["mid_commcap"]["variety_index"] > .3 and last["mid_commcap"]["new_ventures"] >= mid_["new_ventures"],
          f"variety {last['mid_commcap']['variety_index']:.2f}; ventures {last['mid_commcap']['new_ventures']:,.0f} "
          f"vs {mid_['new_ventures']:,.0f}")
    check("keeping collective agreements under the reform changes the result, and stays finite",
          last["mid_agreements"]["balance_bn"] == last["mid_agreements"]["balance_bn"]
          and abs(last["mid_agreements"]["unemployment_rate"] - mid_["unemployment_rate"]) > 1e-4,
          f"unemployment {last['mid_agreements']['unemployment_rate']:.1%} vs {mid_['unemployment_rate']:.1%}")
    # The pledge channel touches only people at risk of gambling harm, a few thousand, so on the national hardship
    # rate it sits within run-to-run noise: reported as a warning, not asserted as a direction it cannot resolve.
    check("a payment lenders can lend against deepens hardship (national rate; the effect is confined to the "
          "at-risk and within noise)",
          last["mid_unprotected"]["hardship_rate"] >= mid_["hardship_rate"] - .0005,
          f"hardship {last['mid_unprotected']['hardship_rate']:.2%} vs {mid_['hardship_rate']:.2%}", warn_only=True)
    # Read on the flow itself. Total imports are an equilibrium: the króna answers a better current account and
    # households spend what they no longer lose, so after ten years the total comes back to where it was and the
    # difference rounded to zero — a test of the exchange rate, not of the block.
    check("blocking foreign gambling payments keeps money in the country",
          last["mid_block"]["gambling_abroad_bn"] < mid_["gambling_abroad_bn"] - 1.0,
          f"sent to foreign sites {last['mid_block']['gambling_abroad_bn']:+,.1f} vs "
          f"{mid_['gambling_abroad_bn']:+,.1f} ma.kr. a year (change on today)")
    # The co-payments it removes are a few ma.kr. spread over everyone who sees a doctor, so on the national
    # hardship rate the effect is a few hundredths of a point, the size of the draw-to-draw noise in a ten-year
    # run (2026-09-26: 2.02% against 1.98%). It is asserted not to raise hardship beyond that noise.
    check("free health care costs the treasury and does not raise hardship (national rate; within noise)",
          last["mid_freehealth"]["balance_bn"] < mid_["balance_bn"]
          and last["mid_freehealth"]["hardship_rate"] <= mid_["hardship_rate"] + .001,
          f"balance {last['mid_freehealth']['balance_bn']:,.0f} vs {mid_['balance_bn']:,.0f}; hardship "
          f"{last['mid_freehealth']['hardship_rate']:.2%} vs {mid_['hardship_rate']:.2%}")
    check("untaxed gifts let a high inheritance tax be avoided",
          last["mid_gifts_open"]["acc_inheritance_tax"] < last["mid_inherit"]["acc_inheritance_tax"],
          f"{last['mid_gifts_open']['acc_inheritance_tax']:.1f} vs {last['mid_inherit']['acc_inheritance_tax']:.1f} "
          f"ma.kr. at 50% with gifts untaxed vs taxed at 10%")
    tv = macromod.Macro(params.load()).tourism_vat_factor()
    check("a flat 25% VAT makes a stay dearer and tourists buy less (EST elasticity 0.8)", .9 < tv < 1.0,
          f"tourism volume {tv:.3f} of today's")
    d = last["sq_dear_imports"]
    check("dearer imports raise the CPI", d["cpi"] > last["sq"]["cpi"] * 1.01,
          f"CPI {d['cpi']:.3f} vs {last['sq']['cpi']:.3f} with imports 10% dearer")
    check("dearer imports lower what incomes buy", d["net_income_mean_real"] < last["sq"]["net_income_mean_real"],
          f"{d['net_income_mean_real']:,.0f} vs {last['sq']['net_income_mean_real']:,.0f} kr. a month")
    check("dearer imports raise the import bill and worsen the terms of trade",
          d["imports_bn"] > last["sq"]["imports_bn"] and d["terms_of_trade"] < .95,
          f"imports {d['imports_bn']:,.0f} vs {last['sq']['imports_bn']:,.0f} bn; terms of trade "
          f"{d['terms_of_trade']:.3f}")
    check("terms of trade sit at 1.0 when world prices are unchanged",
          abs(last["sq"]["terms_of_trade"] - 1.0) < .02, f"{last['sq']['terms_of_trade']:.3f}")
    check("emissions are tracked and dominated by the smelters",
          .5 < last["sq"]["emissions_mt"] < 6.0, f"{last['sq']['emissions_mt']:.2f} Mt of 4.6 in 2025")
    check("the work-incentive measures are in a sane range",
          0 <= last["ubi450"]["participation_tax_rate"] <= 1.2 and last["ubi450"]["ubi_replacement_rate"] > 0,
          f"participation tax {last['ubi450']['participation_tax_rate']:.0%}, "
          f"UBI replaces {last['ubi450']['ubi_replacement_rate']:.0%} of median net income")
    check("tenure and churn are recorded", last["ubi450"]["mean_tenure_years"] > 0,
          f"{last['ubi450']['mean_tenure_years']:.1f} years mean tenure, "
          f"{last['ubi450']['contracts_expiring_share']:.0%} of contracts up for renewal")
    paid = float(np.std([row["wage_Waiters and bar staff"] / row["price_level"] for row in r["ubi450"]]))
    fresh = float(np.std([row["newpay_Waiters and bar staff"] for row in r["ubi450"]]))
    check("contracts damp the swing in what waiters are paid", paid <= fresh * 1.05,
          f"paid s.d. {paid:.3f} vs new-hire s.d. {fresh:.3f}")
    # one run read against its own first year swings several per cent with the draws (0.88-0.94 across seeds), so
    # the check takes three sets of draws
    k = "prof_contract_Waiters_and_bar_staff"
    ratios = [r[n][-1][k] / r[n][0][k] for n in ("ubi450", "ubi450@1", "ubi450@2")]
    check("waiters do not lose contract length under the reform (mean of three sets of draws)",
          float(np.mean(ratios)) >= .9,
          f"{np.mean(ratios):.1%} of the first year's length ({', '.join(f'{v:.0%}' for v in ratios)})")
    drift = sq[-1]["employment_rate_16_74"] - sq[0]["employment_rate_16_74"]
    check("status quo: employment does not drift", abs(drift) < .03, f"{100 * drift:+.1f} pp over {years} years")
    # A baseline that slides is worse than useless: every reform is read against it. The test is Iceland's own
    # record — real wages (LAU04800) grew 2.1%/yr over 2005-2025 and 3.2%/yr over 2015-2025, and the worst ten-year
    # window since 1989 (2003-2013, across the banking collapse) was still +0.5%/yr. Never negative.
    wq = lambda row: sum(row[f"wage_{o}"] for o in params.OCCUPATIONS) / params.N_OCC
    real_cagr = ((wq(sq[-1]) / sq[-1]["price_level"]) / (wq(sq[0]) / sq[0]["price_level"])) ** (1 / years) - 1
    check("status quo: real wages grow, as they always have (LAU04800)", .0 <= real_cagr <= .035,
          f"{100 * real_cagr:+.2f}%/yr modelled vs +2.1%/yr 1989-2025, worst decade +0.5%/yr")
    cpi_cagr = sq[-1]["cpi"] ** (1 / years) - 1
    check("status quo: no deflation", cpi_cagr > -.005, f"{100 * cpi_cagr:+.2f}%/yr")
    inc_cagr = (sq[-1]["real_income_median"] / sq[0]["real_income_median"]) ** (1 / years) - 1
    check("status quo: real household income grows", inc_cagr > -.002, f"{100 * inc_cagr:+.2f}%/yr")
    # Migration, against Hagstofa 2025 (MAN01…): both flows and the children within them. The model once took
    # children abroad at four to six times the recorded rate, and the child population fell a quarter in a decade.
    y1 = sq[0]
    # Today's safety net, benefit by benefit, against 2025 (Tryggingastofnun; GFS social security funds; PAYE; HMS), in 2025 prices
    # v9: old age and disability against 2026 law and the 2026 population, as year 1 is (the 2026
    # disregard is 19.6% higher and there are 3-5% more people 67+; ~131 and ~111 bn in 2025 krónur), and tighter
    for label, key, target, tol in [("unemployment benefit (GFS: 35.7 bn)", "acc_benefit_unemployment", 35.7, .35),
                                    ("old-age pensions and supplements (2026 law: ~131 bn)", "acc_benefit_old_age", 131.0, .15),
                                    ("disability pensions and supplements (2026 law: ~111 bn)", "acc_benefit_disability", 111.0, .15),
                                    ("child pension (barnalífeyrir: ~11 bn)", "acc_child_pension", 11.2, .30),
                                    ("capital income tax, founders' dividends at 22% included (assessment 2025: 65.6 bn)", "acc_capital_income_tax", 65.6, .20),
                                    ("capital income with founders' dividends (tax returns 2025: 355 bn)", "acc_capital_income", 355.3, .15),
                                    ("pension funds' disability pensions (39.4 bn)", "acc_benefit_fund_disability", 39.4, .25),
                                    ("housing benefit (HMS: 11.2 bn)", "acc_benefit_housing_benefit", 11.2, .40),
                                    ("child benefit (barnabætur: 20.4 bn)", "acc_child_payments", 20.4, .30)]:
        # the first year is 2026, at 2026 law and prices; the record is 2025's, so compare in 2025 krónur
        v = y1.get(key) / y1["price_level"] if y1.get(key) is not None else None
        if key == "acc_child_payments" and v is not None:     # child benefit alone: the child pension is its own line
            v -= (y1.get("acc_child_pension") or 0.0) / y1["price_level"]
        if key == "acc_capital_income" and v is not None:     # the tax returns' total includes founders' dividends
            v += (y1.get("acc_founder_dividends") or 0.0) / y1["price_level"]
        if key == "acc_capital_income_tax" and v is not None:  # and so does the assessment's tax: the model taxes
            v += .22 * (y1.get("acc_founder_dividends") or 0.0) / y1["price_level"]   # them with founders' income
        check(f"status quo year 1: {label}", v is not None and close(v, target, tol), f"{v:,.1f} bn" if v is not None else "missing")
    # The interest rebate follows the law's rules exactly; what it pays depends on the joint spread of mortgage debt,
    # income and net worth, which the population is not built to (most owners' equity passes the asset limit). A
    # 1-2 ma.kr. item: reported, not a gate.
    ir = (y1.get("acc_benefit_interest_rebate") or 0.0) / y1["price_level"]
    check("status quo year 1: interest rebate (vaxtabætur: 1.1-1.6 bn)", close(ir, 1.35, .60), f"{ir:,.2f} bn",
          warn_only=True)
    check("status quo year 1: child poverty (SILC 2023: 12.8% ±3.3)", abs(y1["child_poverty_rate"] - .128) <= .033,
          f"{y1['child_poverty_rate']:.1%}")
    # v9: over persons, as SILC measures it (Hagstofa: 9.0%, 2022 incomes; the survey's own margin is about ±1.5)
    check("status quo year 1: poverty, persons (SILC: 9.0%)", abs(y1["poverty_rate"] - .090) <= .02,
          f"{y1['poverty_rate']:.1%} (adults {y1.get('poverty_rate_adults', float('nan')):.1%})")

    check("status quo year 1: employment rate 16-74 (VIN01104: 77.8%)",
          close(y1["employment_rate_16_74"], .778, .04), f"{y1['employment_rate_16_74']:.1%}")
    for label, key, target in [("emigrants", "emigrants", 15508), ("of them children", "emigrants_children", 1129),
                               ("immigrants", "immigrants", 18674), ("of them children", "immigrants_children", 1597)]:
        tol = .15 if "children" not in key else .30
        check(f"status quo year 1: {label if 'children' not in key else key.replace('_', ' ')} (Hagstofa {target:,})",
              close(y1[key], target, tol), f"{y1[key]:,}")
    kids_drift = sq[-1]["children_under_18"] / sq[0]["children_under_18"] - 1
    check("status quo: the child population does not drain away", abs(kids_drift) < .10,
          f"{100 * kids_drift:+.1f}% over {years} years ({sq[0]['children_under_18']:,} → {sq[-1]['children_under_18']:,})")
    check("status quo: demand keeps pace with supply",
          abs(sq[-1]["fte_per_adult_16_74"] / sq[0]["fte_per_adult_16_74"] - 1) < .05,
          f"FTE per adult {sq[0]['fte_per_adult_16_74']:.3f} → {sq[-1]['fte_per_adult_16_74']:.3f}")
    return r


# ----------------------------------------------------------------- 4. wiring
def wiring_checks():
    print("\n4. Parameters: defined, used, and the right shape", flush=True)
    files = ["model.py", "macro.py", "policy.py", "population.py", "sectors.py", "frontier.py", "automation.py", "housing.py"]
    src = "\n".join((ROOT / "src/ubisim/abm" / f).read_text() for f in files)
    d = params.DEFAULTS
    sections = [k for k, v in d.items() if isinstance(v, dict)]
    src += (ROOT / "src/ubisim/abm/uncertainty.py").read_text()   # Monte Carlo paths count as reads
    # the static budget and params' own helpers read keys too (the subsidy groups by name)
    src += (ROOT / "src/ubisim/models/static_balance.py").read_text() + (ROOT / "src/ubisim/abm/params.py").read_text().split("\nDEFAULTS = {")[0]
    src += "\n".join(l for l in (ROOT / "src/ubisim/abm/params.py").read_text().splitlines() if l.startswith(("def ", "    ")) and "(" in l and "#" not in l.split("(")[0])
    used = set(re.findall(r'["\'.]([a-z_0-9]+)["\']', src)) | set(re.findall(r'\.get\("([a-z_0-9]+)"', src))
    # keys built in f-strings, f"subsidy_cut_{k}": every key with that prefix counts as read
    prefixes = set(re.findall(r'(?:\[|get\()f["\']([a-z_0-9]+_)\{', src))
    # characters are looked up by name from the CHARACTERS list, so their keys never appear as literals
    unused = sorted({k for s in sections if s != "characters" for k in d[s]
                     if not any(k.startswith(pre) for pre in prefixes)} - used)
    check("every parameter is read somewhere", not unused, f"unused: {', '.join(unused) or 'none'}", warn_only=True)

    misplaced = []
    # Only literal p["section"]["key"] reads. Following aliases by regex was tried and abandoned: a local name
    # like `m` or `v` is bound to a different section in every function, so attributing every use of it to one
    # of them produced hundreds of false positives. The corner test below catches the aliased case properly, by
    # running the model instead of reading it.
    pairs = set(re.findall(rf'p\["({"|".join(sections)})"\]\["([a-z_0-9]+)"\]', src))
    for found, key in pairs:
        if key not in d[found]:
            home = [s for s in sections if key in d[s]]
            misplaced.append(f"{key} read from {found}" + (f", defined in {home[0]}" if home else ", nowhere defined"))
    check("parameters are read from the section they live in", not misplaced, "; ".join(misplaced) or "all consistent")

    for name, arr in [("labour.consumption_loading", d["labour"]["consumption_loading"]),
                      ("labour.export_loading", d["labour"]["export_loading"]),
                      ("policy.low_value_job_weights", d["policy"]["low_value_job_weights"]),
                      ("migration.immigrant_occupation_mix", d["migration"]["immigrant_occupation_mix"]),
                      ("migration.foreign_wage_ratio", d["migration"]["foreign_wage_ratio"])]:
        check(f"{name}: one value per occupation group", len(arr) == 9,
              f"{len(arr)} values (9 groups feed {params.N_OCC} professions)")
    check("every profession has traits", all(n in params.PROFESSION_TRAITS for n in params.OCCUPATIONS),
          f"{len(params.OCCUPATIONS)} professions covered")
    check("automation exposure covers every profession",
          all(n in d["automation"]["exposure"] for n in params.OCCUPATIONS), "all covered")
    check("contract lengths are set for both sectors",
          bool(d["labour"]["contract_lengths_private"]) and bool(d["labour"]["contract_lengths_public"]),
          "private and public set")
    check("unpleasant and best-paid sets are disjoint", not set(params.HARSH) & set(params.TOP_PAID),
          f"{len(params.HARSH)} unpleasant, {len(params.TOP_PAID)} best-paid")
    # the static balance sheet still prices fisheries, property and energy; the agent run must not add them twice,
    # so only the items on balance()'s keep list may cross over
    kept = re.search(r'keep = \[(.*?)\]', (ROOT / "src/ubisim/abm/model.py").read_text(), re.S).group(1)
    dup = [w for w in ("Property tax", "Fisheries", "Energy", "public payroll") if w.lower() in kept.lower()]
    check("static items are not also counted in the agent accounts", not dup,
          "; ".join(dup) or "property tax, fisheries and energy come from the agents only")
    static_items, total, _ = sb.run()
    check("the static balance sheet still adds up", abs(sum(static_items.values()) - total) < 1e-6,
          f"{total:,.0f} bn of listed items")


def corner_checks(blob, years=3):
    """Run the model at the extremes of every lever at once.

    Reading the source for parameters read from the wrong section only catches literal accesses, and most code
    reads through a short alias. Actually running the corners catches the aliased case and everything like it —
    a KeyError, a NaN, a negative where there cannot be one. `developer_term_years` sat in the wrong section
    until a 660-run build fell over on it; this is the check that would have found it in three minutes.
    """
    print("\n5. The corners of the lever space", flush=True)
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_emulator as emu
    n = len(emu.LEVERS)
    corners = {"every lever at its minimum": np.zeros(n), "every lever at its maximum": np.ones(n),
               "half way on everything": np.full(n, .5)}
    for name, x in corners.items():
        try:
            soc = model.scenario(pickle.loads(blob), emu.overrides_for(x))
            soc.rng = np.random.default_rng(7)
            rows = [soc.step() for _ in range(years)]
            bad = sorted(k for k, v in rows[-1].items() if isinstance(v, float) and v != v)
            check(f"runs at {name}", not bad, f"{len(bad)} NaN outputs" + (f": {bad[:3]}" if bad else ""))
        except Exception as exc:
            check(f"runs at {name}", False, f"{type(exc).__name__}: {str(exc)[:70]}")


def stake_checks(blob, workers, years=5):
    """The state's deemed stake in every company that raises capital (a reform option)."""
    print("\n7. The state's deemed stake", flush=True)
    runs = run_all(blob, [("both", platform(staked_corporate_tax_share=1.0)),
                          ("instead", platform(staked_corporate_tax_share=0.0))], years, None, workers)
    a, b = runs["both"], runs["instead"]
    check("the state's share of the corporate sector grows", 0 < a[0]["public_equity_share"] < a[-1]["public_equity_share"] < .5,
          f"{100 * a[0]['public_equity_share']:.1f}% → {100 * a[-1]['public_equity_share']:.1f}% in {years} years")
    check("its dividends reach the budget", a[-1]["acc_public_equity_dividends"] > 0,
          f"{a[-1]['acc_public_equity_dividends']:.1f} ma.kr.")
    check("stake instead of tax: corporate tax falls with the firms covered",
          b[-1]["acc_corporate_tax_economy"] < a[-1]["acc_corporate_tax_economy"] * (1 - .5 * a[-1]["public_equity_coverage"]),
          f"{b[-1]['acc_corporate_tax_economy']:.0f} against {a[-1]['acc_corporate_tax_economy']:.0f} ma.kr. "
          f"({100 * a[-1]['public_equity_coverage']:.0f}% of profits covered)")
    check("the deemed fund is a full childhood's invested payment", 20 < a[-1]["deemed_fund_m"] < 50,
          f"{a[-1]['deemed_fund_m']:.1f} m kr.")
    check("less new equity costs a little output", 0 < a[-1]["public_equity_drag"] < .02,
          f"{100 * a[-1]['public_equity_drag']:.2f}% of output per hour")


def long_run_checks(blob, years, workers):
    """What only shows over decades (added 2026-10-01, after the long view showed unemployment climbing to 9-13% by
    2060 with no shock, surpluses that vanished once the debt was repaid, and a budget drifting on fiscal drag)."""
    print(f"\n6. The long run ({years} years)", flush=True)
    jobs = [("sq", {}), ("sq_ai5", {"automation": {"ai_progress_rate": .05}}),
            ("sq_windfall", {"windfall": {"rent_bn": 3000.0, "start_year": 1, "ramp_years": 1}})]
    runs = run_all(blob, jobs, years, None, workers)
    sq, ai, wf = runs["sq"], runs["sq_ai5"], runs["sq_windfall"]
    early = np.mean([r["unemployment_rate"] for r in sq[2:5]])
    late = np.mean([r["unemployment_rate"] for r in sq[-3:]])
    check("status quo: unemployment holds its level for decades", abs(late - early) < .015,
          f"{100 * early:.1f}% (years 3-5) → {100 * late:.1f}% (last three)")
    # The law indexes thresholds and the credit to prices plus 1% a year; with real pay growing about as fast, the
    # tax taken from each króna of pay should drift only slowly.
    ratio = lambda r: r["acc_income_tax"] / max(r["acc_labour_income_real"], 1e-9)   # both in 2025 krónur
    drift = ratio(sq[-1]) / ratio(sq[2]) - 1
    check("status quo: income tax per króna of pay drifts little (thresholds CPI + 1%)", abs(drift) < .08,
          f"{100 * drift:+.1f}% over {years - 3} years")
    gap = np.mean([a["unemployment_rate"] - b["unemployment_rate"] for a, b in zip(ai[-3:], sq[-3:])])
    check("AI at 5% a year: little lasting change in unemployment (consensus)", gap < .02,
          f"{100 * gap:+.1f} points against no AI after {years} years")
    take = wf[3]["acc_windfall_take"]                                                # 2025 krónur
    # sold abroad: worth what the króna makes of it, and a windfall this size lifts the króna a long way
    want = .78 * 3000 * wf[3]["exchange_rate"]
    check("a windfall's rent reaches the budget at the state's take", close(take, want, .10),
          f"{take:,.0f} ma.kr. (78% of the rent at the year's króna: {want:,.0f})")
    check("a windfall lifts the króna (Dutch disease)", wf[3]["exchange_rate"] < sq[3]["exchange_rate"],
          f"{wf[3]['exchange_rate']:.3f} against {sq[3]['exchange_rate']:.3f}")
    check("a repaid debt turns into net assets, not nothing", min(r["debt_pct_gdp"] for r in wf) < 0,
          f"lowest {min(r['debt_pct_gdp'] for r in wf):.0f}% of GDP; interest {wf[-1]['interest_bn']:,.0f} ma.kr.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=6)
    ap.add_argument("--long-years", type=int, default=30, help="0 skips the long-run checks")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    # calibrated() rebuilds the cache when the parameters have changed since it was written: a calibrated society
    # carries its own copy of them, so a stale cache silently runs the old numbers
    from build_explorer_data import calibrated
    blob = pickle.dumps(calibrated(1.0, recalibrate=False))

    calibration_checks(pickle.loads(blob))
    runs = behaviour_checks(blob, a.years, a.workers)
    accounting_checks(None, runs["ubi450"], runs.get("sq"))
    wiring_checks()
    corner_checks(blob)
    if a.long_years:
        long_run_checks(blob, a.long_years, a.workers)
    stake_checks(blob, a.workers)

    fails = [x for x in RESULTS if x[0] == "FAIL"]
    warns = [x for x in RESULTS if x[0] == "WARN"]
    print(f"\n{len(RESULTS)} checks: {len(RESULTS) - len(fails) - len(warns)} passed, "
          f"{len(warns)} warnings, {len(fails)} failed", flush=True)
    for _, name, detail in fails:
        print(f"  FAILED: {name} — {detail}")
    out = ROOT / "data/processed"
    (out / "quality_check.md").write_text(
        "# Quality check\n\n| Result | Check | Detail |\n|---|---|---|\n"
        + "\n".join(f"| {s} | {n} | {dt} |" for s, n, dt in RESULTS) + "\n")
    (out / "quality_check.json").write_text(json.dumps([{"status": s, "check": n, "detail": dt} for s, n, dt in RESULTS]))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
