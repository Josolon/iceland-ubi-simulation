"""Run named simulations defined in a YAML file and compare them with the status quo.

    .venv/bin/python scripts/run_experiments.py experiments/inflation_and_exit.yaml [--years 10]

YAML layout:

    base:                     # overrides shared by every experiment (any params.py section)
      policy: {ubi_adult: 450000, ubi_child: 450000, immigration_cap_multiple: 1.0}
    experiments:
      no_indexation:
        label: "UBI not indexed to prices"
        policy: {ubi_indexation: 0.0}
      tight_money:
        markets: {taylor_inflation: 1.5}

Policy, market and labour settings apply to the reform only; the status quo is the calibrated baseline.
Behaviour or character overrides need a separate calibration (use run_sweep.py --scenario for those).

Writes data/experiments/<file stem>/results.json (series in explorer format) and report.md.
"""
import argparse
import json
import os
import pathlib
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from ubisim.abm import model, params  # noqa: E402
from build_explorer_data import METRICS, calibrated  # noqa: E402

HARSH = params.HARSH        # professions rated unpleasant (disamenity >= .55)
TOP_PAID = params.TOP_PAID  # best-paid quarter of professions
PLATFORM = {"regime": "platform", "wage_setting": "free_market"}
REFORM_SECTIONS = {"policy", "markets", "labour", "ventures", "migration", "demography", "costs", "benefits", "housing",
                   "fisheries", "energy", "wealth", "automation", "frontier", "culture", "childcare"}


def series_of(rows):
    return {short: [None if r.get(col) is None or r.get(col) != r.get(col) else float(f"{r.get(col):.5g}") for r in rows]
            for short, col in METRICS.items()}


def run(args):
    base_bytes, overrides, years, reference, name = args
    soc = model.scenario(pickle.loads(base_bytes), overrides)
    soc.reference = reference
    return name, series_of([soc.step() for _ in range(years)])


def avg(series, year, window=3):
    """Average of the last `window` years: single years are noisy, especially in small professions."""
    lo = max(0, year - window)
    vals = [v for v in series[lo:year] if v is not None and v == v]
    return sum(vals) / len(vals) if vals else float("nan")


def summary(r, q, year):
    i = year - 1
    harsh_nom = sum(avg(r[f"w_{o}"], year) for o in HARSH) / sum(avg(q[f"w_{o}"], year) for o in HARSH)
    cpi_rel = avg(r["cpi"], year) / avg(q["cpi"], year)
    prof_nom = sum(avg(r[f"w_{o}"], year) for o in TOP_PAID) / sum(avg(q[f"w_{o}"], year) for o in TOP_PAID)
    annual_infl = (r["cpi"][i] / 1.0) ** (1 / year) - 1
    return {
        "balance_bn": r["balance"][i], "debt_pct_gdp": r["debt"][i],
        "cpi_vs_sq_pct": 100 * (cpi_rel - 1), "avg_inflation_pct": 100 * annual_infl,
        "krona_vs_sq_pct": 100 * (r["fx"][i] / q["fx"][i] - 1),
        "harsh_nominal_wage_pct": 100 * (harsh_nom - 1), "harsh_real_wage_pct": 100 * (harsh_nom / cpi_rel - 1),
        "top_paid_real_wage_pct": 100 * (prof_nom / cpi_rel - 1),
        "pay_gap_harsh_vs_top_pct": 100 * (harsh_nom / prof_nom - 1),
        # the price level that would still leave unpleasant jobs +5% better paid in real terms, given this nominal path
        "max_cpi_for_exit_pct": 100 * (harsh_nom / 1.05 - 1),
        "fte_per_adult_pct": 100 * (r["fte"][i] / q["fte"][i] - 1),
        "part_time_pp": 100 * (r["part"][i] - q["part"][i]),
        "workers_stopped_pp": 100 * (r["stopped"][i] - q["stopped"][i]),
        "house_prices_vs_sq_pct": 100 * (r["house"][i] / q["house"][i] - 1),
        "current_account_pct_gdp": r["ca"][i],
        "consumption_vs_sq_pct": 100 * (r["consumption"][i] / q["consumption"][i] - 1),
        # how people live, and what the machines are doing
        "poverty_rate_pct": 100 * avg(r["poverty"], year),
        "poverty_change_pp": 100 * (avg(r["poverty"], year) - avg(q["poverty"], year)),
        "hardship_rate_pct": 100 * avg(r["hardship"], year),
        "real_income_median_pct": 100 * (avg(r["real_income_median"], year) / avg(q["real_income_median"], year) - 1),
        "forced_idle_pct": 100 * avg(r["forced_idle"], year),
        "automated_share_pct": 100 * avg(r["automated"], year),
        "machine_income_bn": avg(r["machine_income"], year),
        "state_take_from_machines_bn": avg(r["auto_tax"], year) + avg(r["auto_levy"], year) + avg(r["auto_dividends"], year),
        "independent_workers": avg(r["independent"], year),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    spec = yaml.safe_load(pathlib.Path(a.file).read_text())
    base_over = spec.get("base", {})
    out = ROOT / "data/experiments" / pathlib.Path(a.file).stem
    out.mkdir(parents=True, exist_ok=True)

    t = time.time()
    base = calibrated(1.0, False)
    base_bytes = pickle.dumps(base)
    sq = model.scenario(base, {})
    sq_series = series_of([sq.step() for _ in range(a.years)])
    reference = sq.own_history
    print(f"status quo ready ({time.time() - t:.0f}s)", flush=True)

    jobs, labels = [], {}
    for name, ex in spec["experiments"].items():
        ex = dict(ex or {})
        labels[name] = ex.pop("label", name)
        bad = set(ex) - REFORM_SECTIONS
        if bad:
            raise SystemExit(f"{name}: sections {bad} need recalibration; use run_sweep.py --scenario instead")
        wants_status_quo = (ex.get("policy") or {}).get("regime") == "status_quo"
        base_regime = {"policy": {"regime": "status_quo", "wage_setting": "status_quo"}} if wants_status_quo else {"policy": PLATFORM}
        over = params.deep_merge(base_regime, base_over if not wants_status_quo else {k: v for k, v in base_over.items() if k != "policy"})
        over = params.deep_merge(over, ex)
        jobs.append((base_bytes, over, a.years, reference, name))

    results = {}
    with ProcessPoolExecutor(a.workers) as pool:
        for name, series in pool.map(run, jobs):
            results[name] = series
            print(f"  {name} done ({time.time() - t:.0f}s)", flush=True)

    rows = {name: summary(results[name], sq_series, a.years) for name in results}
    (out / "results.json").write_text(json.dumps({"years": a.years, "labels": labels, "status_quo": sq_series,
                                                  "runs": results, "summary": rows, "spec": spec}, indent=None))
    cols = [("balance_bn", "Balance (bn)", 0), ("debt_pct_gdp", "Debt % GDP", 0), ("avg_inflation_pct", "Avg infl. %/yr", 1),
            ("cpi_vs_sq_pct", "Prices vs SQ %", 1), ("harsh_nominal_wage_pct", "Unpleasant jobs nominal %", 1),
            ("harsh_real_wage_pct", "Unpleasant jobs real %", 1), ("max_cpi_for_exit_pct", "Max prices for exit %", 1),
            ("top_paid_real_wage_pct", "Best-paid real %", 1),
            ("pay_gap_harsh_vs_top_pct", "Unpleasant vs best-paid", 1), ("fte_per_adult_pct", "Stöðuígildi %", 1),
            ("consumption_vs_sq_pct", "Consumption %", 1), ("poverty_rate_pct", "Poverty %", 1),
            ("real_income_median_pct", "Median real income %", 1), ("automated_share_pct", "Automated %", 1),
            ("machine_income_bn", "Machine income", 0), ("state_take_from_machines_bn", "State take", 0)]
    lines = [f"# Experiments: {pathlib.Path(a.file).stem}", "", f"Year {a.years}, each compared with the status quo in the same year.",
             "*Max prices for exit*: the price level (vs status quo) at which unpleasant jobs would still be +5% better off "
             "in real terms, given the nominal wages this run produced.", "",
             "| Experiment | " + " | ".join(c[1] for c in cols) + " |", "|---|" + "---:|" * len(cols)]
    for name, r in rows.items():
        lines.append(f"| {labels[name]} | " + " | ".join(f"{r[k]:,.{d}f}" for k, _, d in cols) + " |")
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nresults in {out} ({time.time() - t:.0f}s)")


if __name__ == "__main__":
    main()
