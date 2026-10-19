"""Run the scenario grid for the interactive explorer and write artifacts/explorer_v2/data.js.

    .venv/bin/python scripts/build_explorer_data.py [--years 15] [--recalibrate]

Grid: UBI level x immigration regime x extra property tax x output gain x smelter exit, each compared with the
status quo. Also bundles every experiment battery (data/experiments/*/results.json) and Monte Carlo result
(data/montecarlo/*/results.json) so the explorer can show them.
"""
import argparse
import itertools
import hashlib
import json
import os
import pathlib
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ubisim.abm import model, params  # noqa: E402
from ubisim.abm import params  # noqa: E402
from ubisim.abm.params import OCCUPATIONS  # noqa: E402
from ubisim.abm.population import CHARACTERS  # noqa: E402

OUT = ROOT / "artifacts/explorer_v3/data.js"
UBI = [250_000, 300_000, 350_000, 400_000, 450_000, 500_000]
IMMIGRATION = {"open": {}, "closed": {"immigration_cap_multiple": 1.0, "residence_rules_strictness": 1.0}}
# The lever dataset (build_lever_data.py) now covers property tax, the frontier programmes and króna support as
# interactive levers, so the grid no longer sweeps them. What the grid alone still provides is the full metric set
# — every profession, every character — at each UBI level and immigration regime.
FRONTIER = [[]]
FX_SUPPORT = [0.0]
PROP_TAX = [0.0]

METRICS = {
    "population": "population", "emp": "employment_rate_16_74", "fte": "fte_per_adult_16_74",
    "part": "part_time_share", "unemp": "unemployment_rate", "vac": "vacancy_rate",
    "stopped": "baseline_workers_stopped", "ventures": "new_ventures", "firms": "firms_alive",
    "vjobs": "venture_jobs", "emig": "emigrants", "imm": "immigrants", "births": "births", "kids": "children_under_18",
    "cpi": "cpi", "infl": "inflation", "fx": "exchange_rate", "rate": "real_rate", "rent": "rent_index",
    "house": "house_price_index", "stock": "dwelling_stock_index", "ca": "current_account_pct_gdp",
    "debt": "debt_pct_gdp", "interest": "interest_bn", "balance": "balance_bn", "balance_op": "balance_operational_bn", "output": "output_index",
    "exports": "exports_bn", "imports": "imports_bn",
    "ubi_cost": "acc_ubi_adult", "child_cost": "acc_child_payments", "income_tax": "acc_income_tax",
    "social_security": "acc_social_security", "vat": "acc_vat", "property_tax": "acc_property_tax",
    "public_payroll": "acc_public_payroll", "fund_assets": "acc_fund_assets", "state_equity": "acc_state_equity",
    "consumption": "acc_consumption_real", "benefits": "acc_benefits",
    "public_payroll_real": "acc_public_payroll", "fisheries_fee": "acc_fisheries_fee",
    "energy_dividend": "acc_energy_dividend_change", "compensation": "acc_contract_compensation",
    "fte_removed": "acc_low_value_fte_removed", "liquid_wealth": "acc_household_liquid_wealth",
    "housing_equity": "acc_household_housing_equity", "wealth_gini": "wealth_gini",
    "median_liquid": "wealth_median_liquid", "low_buffer": "wealth_low_buffer_share",
    "smelter_twh": "sector_smelter_twh", "alt_twh": "sector_alt_twh", "fish_rent": "sector_fish_rent",
    "energy_exports": "sector_energy_exports", "fish_exports": "sector_fish_exports",
    "labour_income": "acc_labour_income_real", "unemployed": "involuntary_unemployed",
    **{f"w_{o}": f"wage_{o}" for o in OCCUPATIONS},
    **{f"c_{c}": f"stopped_{c}" for c in CHARACTERS},
    # professions: how many work in each and what they are paid in real terms
    **{f"pn_{o}": f"prof_n_{o.replace(' ', '_')}" for o in OCCUPATIONS},
    **{f"pp_{o}": f"prof_pay_{o.replace(' ', '_')}" for o in OCCUPATIONS},
    **{f"pe_{o}": f"prof_earn_{o.replace(' ', '_')}" for o in OCCUPATIONS},
    **{f"pf_{o}": f"prof_fte_{o.replace(' ', '_')}" for o in OCCUPATIONS},
    **{f"pc_{o}": f"prof_contract_{o.replace(' ', '_')}" for o in OCCUPATIONS},
    "contract_years": "contract_years_mean", "short_contracts": "short_contract_share",
    "new_wage_index": "new_contract_wage_index", "severance": "severance_bn",
    # families, childcare, distribution, pension assets and frontier programmes
    "children_1_5": "children_1_5", "kg_demand": "kindergarten_demand", "kg_full_day": "kindergarten_full_day_demand",
    "kg_under2": "kindergarten_demand_under_2", "kg_gap": "kindergarten_gap",
    "parent_hours": "parent_hours_index", "parents_not_working": "parents_not_working_share",
    "poverty": "poverty_rate", "poverty_anchored": "poverty_rate_anchored", "hardship": "hardship_rate", "real_income_median": "real_income_median",
    "forced_idle": "forced_idle_share", "automated": "automated_share", "machine_income": "machine_income_bn",
    "displaced": "automation_displaced_fte", "auto_tax": "acc_automation_tax", "auto_levy": "acc_automation_levy",
    "auto_dividends": "acc_automation_dividends",
    **{f"au_{o}": f"auto_{o.replace(' ', '_')}" for o in OCCUPATIONS},
    "independent": "independent_workers", "independent_share": "independent_share",
    "independent_creative": "independent_creative", "activity": "activity_rate_16_74",
    "wage_ratio": "wage_ratio_harsh_to_top", "gini": "income_gini", "top_decile": "income_top_decile_share",
    "p90_p10": "income_p90_p10", **{f"inc_q{i}": f"income_q{i}" for i in range(1, 6)},
    "pension_fx_assets": "pension_fx_assets", "fx_support": "fx_support_used",
    "frontier_capex": "frontier_capex_bn", "frontier_exports": "frontier_exports_bn",
    "frontier_twh": "frontier_twh", "frontier_fte": "frontier_fte", "frontier_return": "frontier_state_return_bn",
    # what working is worth, what housing costs, how settled jobs are, and where the state's money sits
    "ptr": "participation_tax_rate", "mtr": "marginal_tax_rate_to_full_time",
    "ptr_over_70": "share_facing_over_70pct_ptr", "gain_from_work": "gain_from_full_time_isk",
    "replacement": "ubi_replacement_rate", "price_to_income": "house_price_to_income",
    "housing_burden": "housing_cost_burden", "housing_over_40": "share_housing_over_40pct",
    "renters": "renter_share", "expiring": "contracts_expiring_share", "tenure": "mean_tenure_years",
    "job_moves": "job_changes", "brain_drain": "emigrants_young_graduates",
    "sovereign_fund": "sovereign_fund_bn", "sovereign_fund_gdp": "sovereign_fund_pct_gdp",
    "child_poverty": "child_poverty_rate", "pensioner_poverty": "pensioner_poverty_rate",
    # v10: the housing ladder (housing.py): each size's price index, a studio's rent, households with less or more room
    # than they need, older owners moving down, the income from released equity, the state's claims on homes
    **{f"h_size{j}": f"housing_price_size{j}" for j in range(6)}, "studio_rent": "housing_studio_rent_index",
    "crowded": "housing_crowded_share", "spare_room": "housing_spare_room_share", "downsizers": "downsizers",
    "equity_annuity": "equity_annuity_bn", "claims": "claims_outstanding_bn", "first_homes": "first_home_purchases",
    "wellbeing": "wellbeing_index", "involuntary_part": "involuntary_part_time",
    # a shortage shows up three ways: pay, work not done, and load on those who stay
    "service_unmet": "essential_service_unmet", "workload": "essential_workload",
    "health_unmet": "health_service_unmet", "teaching_unmet": "teaching_service_unmet",
    "shortage_premium": "public_shortage_premium", "shortage_pay": "public_shortage_pay_bn",
    "leave_saved": "acc_leave_saved", "distress": "social_distress_index",
    "birth_age": "mean_birth_age", "childcare_short": "childcare_places_short",
    "inc_pensioners": "income_pensioners", "inc_disabled": "income_disabled", "inc_students": "income_students",
    "inc_out_of_work": "income_out_of_work", "inc_in_work": "income_in_work",
    "essential_gap": "essential_services_gap", "nurse_gap": "shortfall_nurse", "doctor_gap": "shortfall_doctor",
    "teacher_gap": "shortfall_teacher", "care_gap": "shortfall_care",
    "gdp_pc": "gdp_per_capita_index", "productivity": "productivity_per_hour",
    "ownership_under35": "home_ownership_under_35", "weekly_hours": "weekly_hours_per_adult",
    "tax_labour": "tax_share_labour", "tax_consumption": "tax_share_consumption",
    "tax_capital": "tax_share_capital", "tax_resource": "tax_share_resource",
    "niip": "net_foreign_assets_pct_gdp", "poverty_gap": "poverty_gap",
    "net_income_sd": "net_income_sd", "net_income_cv": "net_income_cv",
    "health": "health_mean", "poor_health": "poor_health_share", "health_cost": "acc_health_cost",
    "crime": "crime_index", "crime_cost": "acc_crime_cost",
    "terms_of_trade": "terms_of_trade", "export_prices": "export_prices",
    "exports": "exports_bn", "imports": "imports_bn",
    "emissions": "emissions_mt", "emissions_vs_2025": "emissions_vs_2025",
    # v3
    "emissions_transition": "emissions_transition_mt", "fuel_imports_extra": "fuel_imports_extra_bn",
    "heating_bill": "cold_area_heating_bill", "teens_moved_out": "teens_moved_out",
    "ai_productivity": "automation_productivity", "ai_new_tasks": "automation_new_task_fte",
    "state_equity": "acc_state_equity", "green_heat": "green_heat_share",
    "emissions_value": "emissions_value_bn", "schooling_cost": "acc_schooling_cost",
    "sick_pay_saved": "acc_sick_pay_saved", "commercial_rent": "commercial_rent_index",
    "term_value": "term_value_factor", "maintenance": "maintenance_factor",
    "inheritance_tax": "acc_inheritance_tax", "fisheries_fee": "acc_fisheries_fee", "variety": "variety_index",
    "social_security": "acc_social_security", "pension_topup": "acc_pension_topup", "prisoners": "prisoners",
    # insecurity: a floor is about variance, not the average
    "income_fell_20": "income_fell_20pct", "income_fell_40": "income_fell_40pct",
    "income_volatility": "income_volatility", "no_buffer": "under_3_months_savings",
    "no_emergency": "cannot_meet_emergency",
    "childhood_poverty": "childhood_poverty_years", "new_disabled": "new_disabled",
    "standard_weeks": "standard_weeks_per_adult", "dropouts": "dropouts",
    "students_full_time": "students_full_time",
    "infra_capex": "infra_capex_bn", "infra_jobs": "infra_fte",
    "infra_open": "infra_projects_open", "infra_gain": "infra_productivity_gain",
    # studying, and how good life actually is
    "students": "students", "new_students": "new_students", "graduates": "graduates",
    "tertiary": "tertiary_share_16_74", "education_cost": "acc_education_cost",
    "wellbeing_p10": "wellbeing_p10", "struggling": "wellbeing_struggling",
    "thriving": "wellbeing_thriving", "wb_worker": "wellbeing_worker", "wb_idle": "wellbeing_idle",
    "wb_pensioner": "wellbeing_pensioner", "wb_parent": "wellbeing_parent",
    **{f"wbc_{k}": f"wb_{k}" for k in ["income", "unemployment", "health", "partner", "work_quality",
                                       "security", "housing", "hardship", "time_squeeze"]},
    # the honest basis for comparing a lower-wage UBI economy with the status quo
    "net_income": "net_income_mean_real", "net_income_p10": "net_income_p10",
    "net_income_p90": "net_income_p90", "own_net_income": "own_net_income_median",
    **{f"net_d{i}": f"net_income_d{i}" for i in range(1, 11)},
}


def _fingerprint():
    """A short hash of the defaults and of the model's code. A calibrated society carries its own copy of the
    parameters, so a cache built before a parameter changed would silently keep serving the old value — and the
    same holds for code: a baseline added to calibrate() is simply absent from a society pickled before it."""
    h = hashlib.sha1(json.dumps(params.DEFAULTS, sort_keys=True, default=str).encode())
    for src in sorted((ROOT / "src/ubisim").rglob("*.py")):
        h.update(src.relative_to(ROOT).as_posix().encode())
        h.update(src.read_bytes())
    return h.hexdigest()[:10]


# Taken once, when this process loads the model, so it describes the code that is actually running. Taken at the
# moment a calibration is saved, it would describe whatever is on disk by then — and an edit made during a long
# calibration would stamp the old result as current.
_FINGERPRINT = _fingerprint()


def params_fingerprint():
    return _FINGERPRINT


def cache_fresh(cache):
    """A cached calibration is usable only if it was stamped with today's parameters and code."""
    stamp = cache.with_suffix(".params")
    return cache.exists() and stamp.exists() and stamp.read_text() == params_fingerprint()


def stamp_cache(cache, blob):
    cache.write_bytes(blob)
    cache.with_suffix(".params").write_text(params_fingerprint())


def calibrated(spirit, recalibrate):
    cache = ROOT / f"data/processed/calibrated_spirit{spirit:g}.pkl"
    stamp = cache.with_suffix(".params")
    if cache.exists() and not recalibrate and stamp.exists() and stamp.read_text() == params_fingerprint():
        return pickle.loads(cache.read_bytes())
    if cache.exists() and not recalibrate:
        print("parameters or model code changed since this calibration was cached — recalibrating", flush=True)
    p = params.load(behaviour={"entrepreneurial_spirit": spirit},
                    policy={"regime": "status_quo", "wage_setting": "status_quo"})
    soc = model.Society(p).calibrate(verbose=False)
    cache.write_bytes(pickle.dumps(soc))
    stamp.write_text(params_fingerprint())
    return soc


def run(args):
    base_bytes, overrides, years, reference, key = args
    soc = model.scenario(pickle.loads(base_bytes), overrides)
    soc.reference = reference
    rows = [soc.step() for _ in range(years)]
    series = {}
    for short, col in METRICS.items():
        vals = [r.get(col) for r in rows]
        series[short] = [None if v is None or v != v else float(f"{v:.4g}") for v in vals]
    return key, series, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=15)
    ap.add_argument("--recalibrate", action="store_true")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    t = time.time()
    status_quo, runs = {}, {}
    for spirit in [1.0]:
        base = calibrated(spirit, a.recalibrate)
        base_bytes = pickle.dumps(base)
        soc_ref = model.scenario(base, {})
        rows = [soc_ref.step() for _ in range(a.years)]
        status_quo[f"s{spirit:g}"] = {short: [None if r.get(col) is None or r.get(col) != r.get(col)
                                              else float(f"{r.get(col):.4g}") for r in rows]
                                      for short, col in METRICS.items()}
        reference = soc_ref.own_history  # full accounts incl. occupation supply and market fields
        print(f"spirit {spirit}: calibrated and status quo done ({time.time() - t:.0f}s)", flush=True)
        jobs = []
        for ubi, (imm, imm_pol), tax, front, fx in itertools.product(UBI, IMMIGRATION.items(), PROP_TAX, FRONTIER, FX_SUPPORT):
            pol = {"regime": "platform", "wage_setting": "free_market", "ubi_adult": ubi, "ubi_child": ubi,
                   "prop_tax_extra_pp": tax, "frontier_programmes": front, "pension_fx_support_bn": fx, **imm_pol}
            jobs.append((base_bytes, {"policy": pol}, a.years, reference,
                         f"{imm}|{ubi // 1000}|t{tax:g}|f{int(bool(front))}|x{int(fx)}"))
        with ProcessPoolExecutor(a.workers) as ex:
            for i, (key, series, _) in enumerate(ex.map(run, jobs, chunksize=2)):
                runs[key] = series
                if i % 12 == 11:
                    print(f"  {i + 1}/{len(jobs)} runs ({time.time() - t:.0f}s)", flush=True)
    meta = {
        "years": a.years, "base_year": 2025, "ubi": [u // 1000 for u in UBI], "immigration": list(IMMIGRATION),
        "prop_tax": PROP_TAX, "frontier": [0, 1], "fx_support": [int(x) for x in FX_SUPPORT],
        "professions": OCCUPATIONS, "harsh": params.HARSH, "top_paid": params.TOP_PAID,
        "occupations": OCCUPATIONS, "characters": CHARACTERS, "generated": time.strftime("%Y-%m-%d"),
    }
    write(meta, status_quo, runs)


def bundle(folder):
    out = {}
    for f in sorted((ROOT / "data" / folder).glob("*/results.json")):
        out[f.parent.name] = json.loads(f.read_text())
    return out


def write(meta, status_quo, runs):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, "status_quo": status_quo["s1"] if "s1" in status_quo else status_quo, "runs": runs,
               "experiments": bundle("experiments"), "montecarlo": bundle("montecarlo")}
    OUT.write_text("window.UBI_DATA = " + json.dumps(payload, separators=(",", ":")) + ";\n")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    if "--bundle-only" in sys.argv:  # refresh experiments/Monte Carlo without rerunning the grid
        text = OUT.read_text()
        old = json.loads(text[text.index("=") + 1:].rstrip().rstrip(";"))
        write(old["meta"], {"s1": old["status_quo"]}, old["runs"])
        print("bundled into", OUT)
    else:
        main()
