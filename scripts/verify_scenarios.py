"""Run the scenarios the page offers through the model itself, and say where the fitted surface was wrong.

    .venv/bin/python scripts/verify_scenarios.py [--file data/processed/scenarios_v3.json] [--workers 4]

The page answers instantly from a surface fitted to about 1,500 runs. That surface is an approximation, and a
scenario chosen *by searching it* is exactly the kind of point where an approximation flatters itself: the search
walks towards wherever the fit happens to be optimistic. So every scenario the page puts forward as a standard
picture is run in the model proper and the two are printed side by side. What is published is the model's answer;
the surface's is shown so the size of its error is on the record.
"""
import argparse
import json
import pathlib
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ubisim.abm import model  # noqa: E402
from build_explorer_data import calibrated  # noqa: E402
from build_emulator import KEYS, LEVERS, overrides_for, METRICS, world_overrides  # noqa: E402
from surrogate import Surface  # noqa: E402

SHOW = [("balance", "balance_bn", "ma.kr."), ("net_income", "net_income_mean_real", "kr./month"),
        ("fte", "fte_per_adult", "FTE"), ("cpi", "cpi", "index"), ("unemp", "unemployment_rate", "share"),
        ("essential_gap", "essential_services_gap", "posts"), ("debt", "debt_pct_gdp", "% of GDP"),
        ("child_poverty", "child_poverty_rate", "share"), ("poverty", "poverty_rate", "share"),
        ("poverty_anchored", "poverty_rate_anchored", "share"), ("hardship", "hardship_rate", "share")]

_BASE = None


def load_base(blob):
    global _BASE
    _BASE = pickle.loads(blob)


def run_one(job):
    """The scenario, measured the way the surface's own runs were measured.

    Each run in the build is anchored to the status quo of its own world — that reference is what demand is
    scaled against. Leaving it out makes every scenario look better than it is, by a wide and consistent margin
    (found 2026-09-21, when a first verification showed the model beating the surface's budget four times over
    in every single scenario, which is not what a fit error looks like)."""
    name, x, years, seed = job
    x = np.asarray(x)
    sq = model.scenario(_BASE, world_overrides(x))
    soc = model.scenario(_BASE, overrides_for(x))
    if seed:
        sq.rng, soc.rng = np.random.default_rng(seed), np.random.default_rng(seed)
    sq_rows = [sq.step() for _ in range(years)]
    soc.reference = sq.own_history
    rows = [soc.step() for _ in range(years)]
    return name, {**{short: [r.get(METRICS.get(short, col)) for r in rows] for short, col, _ in SHOW},
                  **{"sq_" + short: [r.get(METRICS.get(short, col)) for r in sq_rows] for short, col, _ in SHOW}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="data/processed/scenarios_v3.json")
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default="data/processed/scenarios_verified.json")
    ap.add_argument("--seeds", type=int, default=5, help="runs of each scenario, each with its own status quo")
    a = ap.parse_args()
    scen = json.loads((ROOT / a.file).read_text())
    if isinstance(scen, dict):
        scen = [scen]
    s = Surface()
    base = calibrated(1.0, recalibrate=False)
    blob = pickle.dumps(base)
    jobs = []
    for sc in scen:
        x = sc["x"] if isinstance(sc["x"], list) else [sc["x"].get(k, s.levers[i]["default"])
                                                       for i, k in enumerate(KEYS)]
        jobs += [(sc["name"], x, a.years, seed) for seed in range(a.seeds)]
    # 2.1: what is published is the mean over seeds, with their spread: one lever's effect on the 2035 balance cannot
    # be read below about ±15 ma.kr. from a single run
    with ProcessPoolExecutor(a.workers, initializer=load_base, initargs=(blob,)) as ex:
        runs = {}
        for name, r in ex.map(run_one, jobs):
            runs.setdefault(name, []).append(r)
    mean = lambda v: None if any(u is None for u in v) else float(np.mean(v))
    got = {name: {k: [mean([r[k][y] for r in rs]) for y in range(a.years)] for k in rs[0]} for name, rs in runs.items()}
    out = {}
    for name, x, _, seed in jobs:
        if seed:
            continue
        X = np.asarray(x, float)[None, :]
        pred = s.eval(X, [k for k, _, _ in SHOW])
        print(f"\n{name}")
        print(f"  {'measure':22s} {'model':>12s} {'surface':>12s} {'difference':>12s} {'status quo':>12s}")
        rec = {}
        for short, col, unit in SHOW:
            m = got[name][short][-1]
            # the surface's entry for the same year as the run's last (it now reaches 2060 in five-year steps)
            years_on = list(s.E["meta"].get("year_list") or range(2026, 2026 + s.years))
            p = float(pred[short][0][years_on.index(2025 + a.years)])
            if m is None:
                continue
            d = "" if not p else f"{100 * (m / p - 1):+.1f}%" if abs(p) > 1e-9 else ""
            q = got[name]["sq_" + short][-1]
            print(f"  {short:22s} {m:12,.3f} {p:12,.3f} {d:>12s} {q if q is not None else float('nan'):12,.3f}   {unit}")
            diffs = [r[short][-1] - r["sq_" + short][-1] for r in runs[name]
                     if r[short][-1] is not None and r["sq_" + short][-1] is not None]
            rec[short] = {"model": float(m), "surface": p, "status_quo": None if q is None else float(q),
                          "seeds": len(runs[name]), "sd_vs_status_quo": float(np.std(diffs, ddof=1)) if len(diffs) > 1 else None}
        out[name] = rec
    (ROOT / a.out).write_text(json.dumps(out, indent=1))
    print(f"\nwrote {ROOT / a.out}")
    # Every year of the same runs, for the page to show the model's own figures while a scenario is selected: the
    # mean over seeds for the scenario and its status quo, and the spread between seeds of their difference.
    sd = lambda v: float(np.std(v, ddof=1)) if len(v) > 1 and None not in v else None
    series = {name: {**got[name], **{"sd_" + short: [sd([r[short][y] - r["sq_" + short][y] for r in rs
                                                        if r[short][y] is not None and r["sq_" + short][y] is not None])
                                                    for y in range(a.years)] for short, _, _ in SHOW},
                     "years": list(range(2026, 2026 + a.years)), "seeds": len(rs)}
              for name, rs in runs.items()}
    out_series = (ROOT / a.out).with_name((ROOT / a.out).stem + "_series.json")
    out_series.write_text(json.dumps(series, indent=1))
    print(f"wrote {out_series}")


if __name__ == "__main__":
    main()
