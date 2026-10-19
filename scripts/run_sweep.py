"""Sweep UBI levels in the agent-based model and compare every run with the status quo, year by year.

    .venv/bin/python scripts/run_sweep.py                       # default sweep, 10 years
    .venv/bin/python scripts/run_sweep.py --scenario scenarios/closed.yaml --levels 200000,300000,450000
    .venv/bin/python scripts/run_sweep.py --recalibrate

Outputs in data/results/<name>/: yearly.csv (every run and year), summary.csv (one row per run),
characters.csv (share of 2025 workers who stopped working, by character), report.md and charts.
"""
import argparse
import os
import pathlib
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from ubisim.abm import model, params  # noqa: E402
from ubisim.abm.params import OCCUPATIONS  # noqa: E402
from ubisim.abm.population import CHARACTERS  # noqa: E402
from build_explorer_data import cache_fresh, stamp_cache  # noqa: E402

CACHE = ROOT / "data/processed/calibrated_status_quo.pkl"
HARSH = ["Elementary", "Plant and machine operators", "Agriculture and fishery", "Service and sales"]


def calibrated(recalibrate=False, overrides=None):
    if not recalibrate and not overrides and cache_fresh(CACHE):
        return pickle.loads(CACHE.read_bytes())
    p = params.load(**(overrides or {}))
    p = params.deep_merge(p, {"policy": {"regime": "status_quo", "wage_setting": "status_quo"}})
    soc = model.Society(p).calibrate()
    if not overrides:
        stamp_cache(CACHE, pickle.dumps(soc))
    return soc


def run_one(args):
    base_bytes, overrides, years, reference, label = args
    base = pickle.loads(base_bytes)
    soc = model.scenario(base, overrides)
    soc.reference = reference
    rows = []
    for _ in range(years):
        h = soc.step()
        rows.append({"run": label, **h})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", help="YAML with platform overrides (behaviour, policy, ...)")
    ap.add_argument("--levels", default="100000,150000,200000,250000,300000,350000,400000,450000,500000,600000")
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--name", default=None)
    ap.add_argument("--recalibrate", action="store_true")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()

    scen = yaml.safe_load(pathlib.Path(a.scenario).read_text()) if a.scenario else {}
    # behavioural / structural overrides must be present at calibration; policy overrides only in the reform
    calib_over = {k: v for k, v in scen.items() if k not in ("policy",)}
    name = a.name or (pathlib.Path(a.scenario).stem if a.scenario else "default")
    out = ROOT / "data/results" / name
    out.mkdir(parents=True, exist_ok=True)

    t = time.time()
    base = calibrated(a.recalibrate, calib_over or None)
    base_bytes = pickle.dumps(base)
    print(f"calibrated ({time.time() - t:.0f}s)")

    sq = model.scenario(base, {})
    sq_rows = [{"run": "status_quo", **sq.step()} for _ in range(a.years)]
    reference = sq.own_history  # full accounts incl. occupation supply and market fields
    print(f"status quo done ({time.time() - t:.0f}s)")

    levels = [int(x) for x in a.levels.split(",")]
    jobs = []
    for lvl in levels:
        pol = {"regime": "platform", "wage_setting": "free_market", "ubi_adult": lvl, "ubi_child": lvl}
        pol.update(scen.get("policy", {}))
        pol["ubi_adult"], pol["ubi_child"] = lvl, lvl
        jobs.append((base_bytes, {"policy": pol}, a.years, reference, f"ubi_{lvl}"))
    rows = list(sq_rows)
    with ProcessPoolExecutor(a.workers) as ex:
        for r in ex.map(run_one, jobs):
            rows.extend(r)
            print(f"{r[0]['run']} done ({time.time() - t:.0f}s)")

    df = pd.DataFrame(rows)
    df.to_csv(out / "yearly.csv", index=False)
    summarise(df, levels, a.years, out, scen)
    print("results in", out)


def summarise(df, levels, years, out, scen):
    sq = df[df.run == "status_quo"].set_index("year")
    recs, chars = [], []
    for lvl in levels:
        r = df[df.run == f"ubi_{lvl}"].set_index("year")
        last = r.loc[years]
        sql = sq.loc[years]
        real_wage = {o: (last[f"wage_{o}"] / last.price_level) / (sql[f"wage_{o}"] / sql.price_level) - 1 for o in OCCUPATIONS}
        rec = {
            "ubi_isk_month": lvl,
            "employment_rate_pp": 100 * (last.employment_rate_16_74 - sql.employment_rate_16_74),
            "workers_2025_stopped_pp": 100 * (last.baseline_workers_stopped - sql.baseline_workers_stopped),
            "fte_change_pct": 100 * (last.fte / sql.fte - 1),
            "fte_per_adult": last.fte_per_adult_16_74, "fte_per_adult_sq": sql.fte_per_adult_16_74,
            "unemployment_rate_pp": 100 * (last.unemployment_rate - sql.unemployment_rate),
            "part_time_share_pp": 100 * (last.part_time_share - sql.part_time_share),
            "voluntary_nonwork_pp": 100 * (last.voluntary_nonwork_share - sql.voluntary_nonwork_share),
            "real_labour_income_change_pct": 100 * (last.acc_labour_income_real / sql.acc_labour_income_real - 1),
            "harsh_jobs_real_wage_pct": 100 * np.mean([real_wage[o] for o in HARSH]),
            **{f"real_wage_pct_{o}": 100 * v for o, v in real_wage.items()},
            "price_level_vs_sq_pct": 100 * (last.price_level / sql.price_level - 1),
            "new_ventures_per_year": r.new_ventures.mean(),
            "new_ventures_per_year_sq": sq.new_ventures.mean(),
            "venture_jobs_final": last.venture_jobs,
            "emigrants_per_year": r.emigrants.mean(), "emigrants_per_year_sq": sq.emigrants.mean(),
            "immigrants_per_year": r.immigrants.mean(), "immigrants_per_year_sq": sq.immigrants.mean(),
            "births_per_year": r.births.mean(), "births_per_year_sq": sq.births.mean(),
            "population_final": last.population, "population_final_sq": sql.population,
            "balance_bn_year1": r.loc[1].balance_bn, "balance_bn_final": last.balance_bn,
            "balance_pct_gdp_final": 100 * last.balance_bn / 4955.6,
        }
        recs.append(rec)
        for c in CHARACTERS:
            chars.append({"ubi_isk_month": lvl, "character": c,
                          "stopped_pp_vs_sq": 100 * (last[f"stopped_{c}"] - sql[f"stopped_{c}"])})
    summ = pd.DataFrame(recs)
    summ.to_csv(out / "summary.csv", index=False)
    ch = pd.DataFrame(chars).pivot(index="character", columns="ubi_isk_month", values="stopped_pp_vs_sq")
    ch.to_csv(out / "characters.csv")

    exit_rows = summ[summ.harsh_jobs_real_wage_pct >= 5]
    threshold = int(exit_rows.ubi_isk_month.min()) if len(exit_rows) else None
    breakeven = summ[summ.balance_bn_final >= 0]
    be = int(breakeven.ubi_isk_month.max()) if len(breakeven) else None

    fmt = lambda v, d=1: f"{v:,.{d}f}"
    lines = [f"# UBI sweep — {out.name}", "",
             f"Year {years} of each run compared with the status quo in the same year. "
             f"Real wages are deflated by the model's consumer price level.", "",
             f"- **Right-to-exit threshold** (lowest UBI where unpleasant jobs' real wages rise ≥ 5%): "
             f"{'none in range' if threshold is None else f'{threshold:,} ISK/month'}",
             f"- **Highest UBI with a non-negative general government balance in year {years}**: "
             f"{'none in range' if be is None else f'{be:,} ISK/month'}", "",
             "| UBI/month | Employment (pp) | Stöðuígildi/adult (FTE) | Part-time share (pp) | Unemployment (pp) | "
             "Chose not to work (pp) | 2025 workers stopped (pp) | Unpleasant-job real wage % | Professionals real wage % | "
             "Prices % | Ventures/yr | Emigrants/yr | Immigrants/yr | Births/yr | "
             f"Balance yr1 (bn) | Balance yr{years} (bn) |",
             "|" + "---:|" * 16]
    for _, r in summ.iterrows():
        lines.append(f"| {int(r.ubi_isk_month):,} | {fmt(r.employment_rate_pp)} | {r.fte_per_adult:.3f} (sq {r.fte_per_adult_sq:.3f}) | "
                     f"{fmt(r.part_time_share_pp)} | {fmt(r.unemployment_rate_pp)} | {fmt(r.voluntary_nonwork_pp)} | "
                     f"{fmt(r.workers_2025_stopped_pp)} | {fmt(r.harsh_jobs_real_wage_pct)} | {fmt(r.real_wage_pct_Professionals)} | "
                     f"{fmt(r.price_level_vs_sq_pct)} | {fmt(r.new_ventures_per_year, 0)} | {fmt(r.emigrants_per_year, 0)} | "
                     f"{fmt(r.immigrants_per_year, 0)} | {fmt(r.births_per_year, 0)} | {fmt(r.balance_bn_year1, 0)} | "
                     f"{fmt(r.balance_bn_final, 0)} |")
    s0 = summ.iloc[0]
    lines += ["", f"Status quo averages: ventures {fmt(s0.new_ventures_per_year_sq, 0)}/yr, emigrants "
              f"{fmt(s0.emigrants_per_year_sq, 0)}/yr, immigrants {fmt(s0.immigrants_per_year_sq, 0)}/yr, births "
              f"{fmt(s0.births_per_year_sq, 0)}/yr.", "",
              "## Share of 2025 workers who stopped working, change vs status quo (pp), by character", "",
              ch.round(1).to_markdown(), "", "## Scenario overrides", "", "```yaml",
              yaml.safe_dump(scen or {"(defaults)": True}, sort_keys=False).strip(), "```"]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    charts(df, summ, levels, years, out)


def charts(df, summ, levels, years, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(12, 8))
    x = summ.ubi_isk_month / 1000
    ax[0, 0].plot(x, summ.employment_rate_pp, marker="o", label="employment rate (pp)")
    ax[0, 0].plot(x, summ.workers_2025_stopped_pp, marker="o", label="2025 workers stopped (pp)")
    ax[0, 0].plot(x, 100 * (summ.fte_per_adult / summ.fte_per_adult_sq - 1), marker="o", label="stöðuígildi per adult (%)")
    ax[0, 0].plot(x, summ.unemployment_rate_pp, marker="o", label="unemployment rate (pp)")
    ax[0, 0].set_title(f"Work, year {years} vs status quo")
    for o in ["Elementary", "Service and sales", "Craft and trades", "Professionals", "Managers"]:
        ax[0, 1].plot(x, summ[f"real_wage_pct_{o}"], marker=".", label=o)
    ax[0, 1].axhline(0, color="grey", lw=.5)
    ax[0, 1].set_title("Real wage change by occupation (%)")
    ax[1, 0].plot(x, summ.new_ventures_per_year, marker="o", label="new ventures/yr")
    ax[1, 0].plot(x, summ.emigrants_per_year, marker="o", label="emigrants/yr")
    ax[1, 0].plot(x, summ.immigrants_per_year, marker="o", label="immigrants/yr")
    ax[1, 0].set_title("Ventures and migration (yearly average)")
    ax[1, 1].plot(x, summ.balance_bn_year1, marker="o", label="year 1")
    ax[1, 1].plot(x, summ.balance_bn_final, marker="o", label=f"year {years}")
    ax[1, 1].axhline(0, color="grey", lw=.5)
    ax[1, 1].set_title("General government balance (bn ISK, 2025 prices)")
    for a_ in ax.flat:
        a_.set_xlabel("UBI (thousand ISK/month)")
        a_.legend(fontsize=8)
        a_.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(out / "sweep.png", dpi=130)


if __name__ == "__main__":
    main()
