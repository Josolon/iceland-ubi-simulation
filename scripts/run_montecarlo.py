"""Monte Carlo over the estimated parameters for a set of scenarios (same YAML format as run_experiments.py).

    .venv/bin/python scripts/run_montecarlo.py experiments/montecarlo.yaml --draws 40 [--years 10]

Each draw samples every uncertain parameter (src/ubisim/abm/uncertainty.py), runs its own status quo with those
parameters, then every scenario with the same random numbers, so differences are not noise from the draw itself.
Writes data/montecarlo/<stem>/results.json (percentile bands, per-draw outcomes, parameter sensitivities) and report.md.
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
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import yaml  # noqa: E402

from ubisim.abm import model, params, uncertainty  # noqa: E402
from run_experiments import PLATFORM, series_of, summary  # noqa: E402
from build_explorer_data import cache_fresh, stamp_cache  # noqa: E402
from ensemble import RANGES  # noqa: E402

# the ranges kept up to date in ensemble.py (the retired pay-only mobility rule out, the newer estimates in)
uncertainty.RANGES = RANGES

KEY_OUTCOMES = ["balance_bn", "debt_pct_gdp", "avg_inflation_pct", "harsh_real_wage_pct", "fte_per_adult_pct",
                "top_paid_real_wage_pct", "pay_gap_harsh_vs_top_pct", "cpi_vs_sq_pct", "consumption_vs_sq_pct", "house_prices_vs_sq_pct"]
BAND_SERIES = ["balance", "debt", "cpi", "fte", "emp", "unemp", "infl", "fx", "house", "ca", "consumption",
               "population", "imm", "emig", "ventures", "public_payroll"]


def calibration(elasticity):
    cache = ROOT / f"data/processed/calibrated_elasticity{elasticity:g}.pkl"
    if cache_fresh(cache):
        return cache.read_bytes()
    p = params.load(behaviour={"target_extensive_elasticity": elasticity},
                    policy={"regime": "status_quo", "wage_setting": "status_quo"})
    soc = model.Society(p).calibrate(verbose=False)
    blob = pickle.dumps(soc)
    stamp_cache(cache, blob)
    return blob


def run_draw(args):
    draw_id, draw, base_blob, scenarios, years = args
    over = uncertainty.as_overrides(draw)
    rng_seed = 1000 + draw_id

    def fresh(extra):
        soc = model.scenario(pickle.loads(base_blob), params.deep_merge(over, extra))
        soc.rng = np.random.default_rng(rng_seed)  # common random numbers across the draw's runs
        return soc

    sq = fresh({})
    sq_series = series_of([sq.step() for _ in range(years)])
    out = {"draw": draw_id, "params": draw, "status_quo": sq_series, "runs": {}, "summary": {}}
    for name, ex in scenarios.items():
        soc = fresh(ex)
        soc.reference = sq.own_history
        s = series_of([soc.step() for _ in range(years)])
        out["runs"][name] = s
        out["summary"][name] = summary(s, sq_series, years)
    return out


def spearman(x, y):
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    if np.std(rx) == 0 or np.std(ry) == 0:
        return 0.0
    return float(np.corrcoef(rx, ry)[0, 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--draws", type=int, default=40)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    spec = yaml.safe_load(pathlib.Path(a.file).read_text())
    base_over = spec.get("base", {})
    scenarios, labels = {}, {}
    for name, ex in spec["experiments"].items():
        ex = dict(ex or {})
        labels[name] = ex.pop("label", name)
        scenarios[name] = params.deep_merge(params.deep_merge({"policy": PLATFORM}, base_over), ex)
    out = ROOT / "data/montecarlo" / pathlib.Path(a.file).stem
    out.mkdir(parents=True, exist_ok=True)

    t = time.time()
    blobs = {lvl: calibration(lvl) for lvl in uncertainty.ELASTICITY_LEVELS}
    print(f"calibrations ready ({time.time() - t:.0f}s)", flush=True)
    draws = uncertainty.latin_hypercube(a.draws, np.random.default_rng(a.seed))
    jobs = [(i, d, blobs[d["behaviour.target_extensive_elasticity"]], scenarios, a.years) for i, d in enumerate(draws)]
    results = []
    with ProcessPoolExecutor(a.workers) as pool:
        for r in pool.map(run_draw, jobs):
            results.append(r)
            print(f"  draw {len(results)}/{a.draws} ({time.time() - t:.0f}s)", flush=True)

    years = a.years
    bands, stats, sens = {}, {}, {}
    param_names = list(draws[0].keys())
    for name in scenarios:
        bands[name] = {}
        for k in BAND_SERIES:
            mat = np.array([[np.nan if v is None else v for v in r["runs"][name][k]] for r in results], float)
            ref = np.array([[np.nan if v is None else v for v in r["status_quo"][k]] for r in results], float)
            bands[name][k] = {q: np.nanpercentile(mat, q, axis=0).round(4).tolist() for q in (10, 50, 90)}
            bands[name][k + "_vs_sq"] = {q: np.nanpercentile(mat - ref, q, axis=0).round(4).tolist() for q in (10, 50, 90)}
        stats[name] = {o: {q: float(np.percentile([r["summary"][name][o] for r in results], q)) for q in (10, 50, 90)}
                       for o in KEY_OUTCOMES}
        stats[name]["share_exit_effect"] = float(np.mean([r["summary"][name]["harsh_real_wage_pct"] >= 5 for r in results]))
        stats[name]["share_balanced"] = float(np.mean([r["summary"][name]["balance_bn"] >= 0 for r in results]))
        sens[name] = {o: {pn: spearman([r["params"][pn] for r in results], [r["summary"][name][o] for r in results])
                          for pn in param_names} for o in ["balance_bn", "harsh_real_wage_pct", "avg_inflation_pct", "fte_per_adult_pct"]}

    (out / "results.json").write_text(json.dumps({"years": years, "draws": a.draws, "labels": labels, "bands": bands,
                                                  "stats": stats, "sensitivity": sens,
                                                  "per_draw": [{"params": r["params"], "summary": r["summary"]} for r in results]}))
    lines = [f"# Monte Carlo: {pathlib.Path(a.file).stem}", "", f"{a.draws} draws over {len(uncertainty.RANGES) + 1} uncertain "
             f"parameters; year {years} vs each draw's own status quo. Cells: median [10th – 90th percentile].", "",
             "| Scenario | Balance (bn) | Debt % GDP | Avg inflation %/yr | Unpleasant jobs real % | Stöðuígildi % | P(exit effect) | P(balanced) |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    f = lambda s, o, d=0: f"{s[o][50]:,.{d}f} [{s[o][10]:,.{d}f} – {s[o][90]:,.{d}f}]"
    for name, s in stats.items():
        lines.append(f"| {labels[name]} | {f(s, 'balance_bn')} | {f(s, 'debt_pct_gdp')} | {f(s, 'avg_inflation_pct', 1)} | "
                     f"{f(s, 'harsh_real_wage_pct', 1)} | {f(s, 'fte_per_adult_pct', 1)} | {100 * s['share_exit_effect']:.0f}% | "
                     f"{100 * s['share_balanced']:.0f}% |")
    lines += ["", "## What decides the outcome (rank correlation with the parameter, strongest five)", ""]
    for name in scenarios:
        lines.append(f"### {labels[name]}")
        for o in ["balance_bn", "harsh_real_wage_pct", "avg_inflation_pct"]:
            top = sorted(sens[name][o].items(), key=lambda kv: -abs(kv[1]))[:5]
            lines.append(f"- **{o}**: " + ", ".join(f"{k} ({v:+.2f})" for k, v in top))
        lines.append("")
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"results in {out} ({time.time() - t:.0f}s)")


if __name__ == "__main__":
    main()
