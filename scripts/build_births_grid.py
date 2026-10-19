"""Births against the child payment, run directly rather than fitted.

    .venv/bin/python scripts/build_births_grid.py --seeds 3 --years 10

Births are a Poisson draw on a base of about 4,300 a year, so a single run moves by a hundred or more for no reason
at all, and a response surface fitted over thirty levers cannot pull the policy effect out of that. The question
the flat child payment raises — do people have children for a living? — deserves better than a surface that
predicts worse than its own average.

So this runs a grid over the two levers that matter to it, the borgaralaun and the share of each child's payment
held in their fund, with every other lever where the reform puts it, and repeats every cell with several
independent seeds. The page shows the average and the spread between seeds, so the noise is visible rather than
hidden.

Writes artifacts/explorer_v2/births.js.
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

from ubisim.abm import model  # noqa: E402
from build_emulator import KEYS, LEVERS, default_x, overrides_for  # noqa: E402
from build_explorer_data import METRICS, calibrated  # noqa: E402

OUT = ROOT / "artifacts/explorer_v3/births.js"
UBI = [0, 100, 200, 300, 400, 450, 500, 600]          # þús. kr. a month
HELD = [20, 30, 40, 50, 60, 70, 80, 90]              # % of each child's payment held in their fund
SERIES = ["births", "kids", "population", "child_cost", "balance", "child_poverty", "fund_assets", "wb_parent",
          "parent_hours"]
SEED0 = 101


def point(ubi, held):
    """The reform as specified, with these two levers moved."""
    x = np.array([default_x(k) for k in KEYS])
    for key, value in (("ubi", ubi), ("child_invested", held)):
        j = KEYS.index(key)
        lo, hi = LEVERS[j][3], LEVERS[j][4]
        x[j] = (value - lo) / (hi - lo)
    return x


def run(job):
    key, over, seed, blob, years, reference = job
    soc = model.scenario(pickle.loads(blob), over)
    soc.reference = reference
    soc.rng = np.random.default_rng(seed)
    rows = [soc.step() for _ in range(years)]
    return key, seed, {s: [None if (v := r.get(METRICS[s])) is None or v != v else float(v) for r in rows]
                       for s in SERIES}


def summarise(runs):
    """Mean and between-seed standard deviation, year by year."""
    out = {}
    for s in SERIES:
        M = np.array([[np.nan if v is None else v for v in r[s]] for r in runs], dtype=float)
        out[s] = {"mean": [None if np.isnan(v) else float(f"{v:.6g}") for v in np.nanmean(M, 0)],
                  "sd": [None if np.isnan(v) else float(f"{v:.4g}") for v in np.nanstd(M, 0, ddof=1)]}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    t = time.time()
    base = calibrated(1.0, recalibrate=False)
    blob = pickle.dumps(base)
    ref_soc = model.scenario(base, {})
    for _ in range(a.years):
        ref_soc.step()
    reference = ref_soc.own_history
    seeds = [SEED0 + i for i in range(a.seeds)]

    jobs = [("status_quo", {}, s, blob, a.years, reference) for s in seeds]
    jobs += [(f"{u}|{h}", overrides_for(point(u, h)), s, blob, a.years, reference)
             for u in UBI for h in HELD for s in seeds]
    print(f"{len(jobs)} runs", flush=True)
    results = {}
    with ProcessPoolExecutor(a.workers) as ex:
        for done, (key, seed, series) in enumerate(ex.map(run, jobs, chunksize=1)):
            results.setdefault(key, []).append(series)
            if done % 20 == 19:
                print(f"  {done + 1}/{len(jobs)} ({time.time() - t:.0f}s)", flush=True)

    payload = {
        "meta": {"ubi": UBI, "held": HELD, "seeds": a.seeds, "years": a.years, "base_year": 2025,
                 "series": SERIES, "generated": time.strftime("%Y-%m-%d"),
                 "note": "Every other lever where the reform puts it. Mean and spread over independent seeds."},
        "status_quo": summarise(results["status_quo"]),
        "cells": {k: summarise(v) for k, v in results.items() if k != "status_quo"},
    }
    OUT.write_text("window.UBI_BIRTHS = " + json.dumps(payload, separators=(",", ":")) + ";\n")
    sq = payload["status_quo"]["births"]
    print(f"\nwrote {OUT} ({OUT.stat().st_size / 1e3:.0f} kB, {time.time() - t:.0f}s)")
    print(f"status quo births, year {a.years}: {sq['mean'][-1]:,.0f} ± {sq['sd'][-1]:,.0f}")
    for u in UBI:
        row = [payload["cells"][f"{u}|{h}"]["births"]["mean"][-1] for h in HELD]
        print(f"  UBI {u:>3}: " + " ".join(f"{v:6,.0f}" for v in row))


if __name__ == "__main__":
    main()
