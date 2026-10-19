"""The thorough path: every page scenario run in the full model many times over — random seeds, draws of the
uncertain parameters, shocks ahead — so that what the page shows as one line can be read with its spread.

The page and its guide rest on one run per scenario (the long view) or on a fitted surface checked against single
runs (the explorer). One run is one draw of chance and one set of estimates. For a decision of national weight the
questions are how much of a result is the model's randomness, how much the estimates it leans on, and whether the
sign survives both. This answers them by brute force, and is built to be spread over as many machines as exist.

    PY=../iceland-ubi-simulation/.venv/bin/python
    $PY scripts/ensemble.py plan  --name full --seeds 10 --draws 40 --years 35 --shocks none ai_shock amoc
    $PY scripts/ensemble.py run   --name full --workers 6            # on this machine, resumable
    $PY scripts/ensemble.py run   --name full --shard 17 --shards 200  # one task of a cluster array
    $PY scripts/ensemble.py slurm --name full --shards 200            # writes a SLURM array script
    $PY scripts/ensemble.py summarise --name full

A job is one world (the scenario's world settings), one draw of the parameters, one seed and one shock: the status
quo is run once and every scenario in that world beside it, all with the same random numbers, so the differences
are the policy's and not the dice's. Each job writes its own file under data/ensemble/<name>/jobs/, so a run that
is stopped, or a cluster task that fails, is simply run again; finished jobs are skipped.

Cost: a 35-year run is about 5 minutes on one core, so a job of six scenarios and the status quo about 35 minutes.
10 seeds x 40 draws x 3 shocks x 2 worlds = 2,400 jobs = about 1,400 core-hours: a week on this machine, an
afternoon on a few hundred cores. `--population-seeds` adds whole re-drawn populations, each needing its own
calibration (about 25 minutes, done once per seed and cached); `--elasticity-levels` samples the labour-supply
elasticity on the three pre-calibrated levels the Monte Carlo uses.
"""
import argparse
import hashlib
import json
import pathlib
import pickle
import sys
import time
from multiprocessing import Pool

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ubisim.abm import model, params, uncertainty  # noqa: E402
from build_emulator import KEYS, WORLD, overrides_for, world_overrides  # noqa: E402
from build_explorer_data import cache_fresh, calibrated, stamp_cache  # noqa: E402
import build_timeline as tl  # noqa: E402

OUT = ROOT / "data/ensemble"
READ = tl.READ + ["fund_payout", "gini", "real_wage_index", "public_payroll_bn", "vacancy_rate"]
# The ranges the Monte Carlo draws from, brought up to date: the retired pay-only mobility rule is out (drawn, it
# switched a double-counting rule back on), and the newer estimates the long view leans on are in.
RANGES = {k: v for k, v in uncertainty.RANGES.items() if k != "labour.occupational_mobility"}
RANGES.update({
    "labour.occupation_mobility": (0.02, 0.06),
    "labour.occupation_shortage_pull": (0.75, 2.5),
    "automation.reinstatement_share": (0.80, 1.00),
    "automation.adoption_speed": (0.15, 0.35),
    "migration.arrival_rent_elasticity": (0.5, 1.5),
    "demography.mortality_improvement": (0.008, 0.016),
    "ventures.profit_persistence": (0.5, 0.85),
    "automation.wage_sensitivity": (0.6, 1.8),
    "labour.wage_curve_elasticity": (0.05, 0.15),
    "education.return_elasticity": (0.3, 1.5),
    "education.graduate_switch_share": (0.4, 0.8),
    "public_equity.avoidance_elasticity": (0.3, 2.0),
    "public_equity.productivity_cost": (0.01, 0.10),
    "public_equity.equity_value_bn": (4000.0, 9000.0),
    "public_equity.rounds_per_year": (2000, 6000),
})


def draws(n, seed):
    """Latin hypercube over RANGES; draw 0 is always the central estimate (no overrides)."""
    if n <= 0:
        return [{}]
    rng = np.random.default_rng(seed)
    k = len(RANGES)
    cells = np.array([rng.permutation(n) for _ in range(k + 1)]).T
    u = (cells + rng.random((n, k + 1))) / n
    out = [{}]
    for i in range(n):
        d = {path: lo + (hi - lo) * u[i, j] for j, (path, (lo, hi)) in enumerate(RANGES.items())}
        d["behaviour.target_extensive_elasticity"] = uncertainty.ELASTICITY_LEVELS[int(u[i, k] * 3)]
        out.append(d)
    return out


def overrides(draw):
    out = {}
    for path, value in draw.items():
        if path.startswith("behaviour."):
            continue
        section, key = path.split(".", 1)
        out.setdefault(section, {})[key] = float(value)
    return out


# ------------------------------------------------------------------ calibrated bases
def base_blob(pop_seed, elasticity):
    """The calibrated society for a population seed and a labour-supply elasticity, cached like the others."""
    if pop_seed == 0 and elasticity is None:
        return pickle.dumps(calibrated(1, False))
    tag = f"calibrated_ens_seed{pop_seed}" + (f"_el{elasticity:g}" if elasticity is not None else "")
    cache = ROOT / f"data/processed/{tag}.pkl"
    if cache_fresh(cache):
        return cache.read_bytes()
    over = {"policy": {"regime": "status_quo", "wage_setting": "status_quo"}}
    beh = {"entrepreneurial_spirit": 1}
    if elasticity is not None:
        beh["target_extensive_elasticity"] = elasticity
    p = params.load(behaviour=beh, **over)
    if pop_seed:
        p["seed"] = int(pop_seed)
    blob = pickle.dumps(model.Society(p).calibrate(verbose=False))
    stamp_cache(cache, blob)
    return blob


# ------------------------------------------------------------------ plan
def plan(a):
    scen = tl.page_scenarios()
    if a.scenarios:
        scen = [s for s in scen if s["id"] in a.scenarios]
    worlds = {}
    for sc in scen:
        w = tuple(round(float(sc["x"][KEYS.index(k)]), 6) for k in WORLD)
        worlds.setdefault(w, []).append(sc["id"])
    ds = draws(a.draws, a.draw_seed)
    jobs = []
    for w, ids in worlds.items():
        for di, d in enumerate(ds):
            for s in range(a.seeds):
                for ps in range(a.population_seeds):
                    for shock in a.shocks:
                        key = json.dumps([w, di, s, ps, shock])
                        jobs.append({"id": hashlib.sha1(key.encode()).hexdigest()[:12], "world": list(w),
                                     "scenarios": ids, "draw": di, "seed": s, "pop_seed": ps, "shock": shock})
    d = OUT / a.name
    (d / "jobs").mkdir(parents=True, exist_ok=True)
    manifest = {"name": a.name, "years": a.years, "draws": ds, "elasticity_levels": a.elasticity_levels,
                "scenarios": {sc["id"]: {"name": sc["name"], "x": sc["x"].tolist()} for sc in scen},
                "jobs": jobs, "planned": time.strftime("%Y-%m-%d %H:%M")}
    (d / "manifest.json").write_text(json.dumps(manifest, indent=1))
    runs = sum(len(j["scenarios"]) + 1 for j in jobs)
    print(f"{len(jobs)} jobs, {runs} model runs of {a.years} years "
          f"(~{runs * a.years * 8.5 / 3600:,.0f} core-hours at ~8.5 s a model-year) → {d}")


# ------------------------------------------------------------------ run
_BASES = {}
_MANIFEST = None


def init(manifest):
    global _MANIFEST
    _MANIFEST = manifest


def base_for(job):
    el = _MANIFEST["draws"][job["draw"]].get("behaviour.target_extensive_elasticity") \
        if _MANIFEST["elasticity_levels"] else None
    key = (job["pop_seed"], el)
    if key not in _BASES:
        _BASES.clear()                      # one society in memory per process
        _BASES[key] = pickle.loads(base_blob(*key))
    return _BASES[key]


def one_run(base, over, reference, job, years):
    soc = model.scenario(base, over)
    soc.rng = np.random.default_rng(10_000 * job["pop_seed"] + 1_000 * job["seed"] + 7)   # common random numbers
    if reference is not None:
        soc.reference = reference
    w0 = tl.world_now(soc)
    rows = []
    for i in range(years):
        soc.set_policy(tl.shock_settings(job["shock"], 2026 + i - tl.ONSET["today"], w0))
        r = soc.step()
        rows.append({k: (None if (v := r.get(k)) is None or v != v else float(v)) for k in READ})
        rows[-1]["fund_payout"] = float(getattr(soc.macro, "fund_payout", 0.0))
    return rows, soc.own_history


def run_job(job):
    path = OUT / _MANIFEST["name"] / "jobs" / f"{job['id']}.pkl"
    if path.exists():
        return job["id"], "skipped"
    t = time.time()
    base = base_for(job)
    years = _MANIFEST["years"]
    x = {sid: np.array(_MANIFEST["scenarios"][sid]["x"]) for sid in job["scenarios"]}
    extra = overrides(_MANIFEST["draws"][job["draw"]])
    first = x[job["scenarios"][0]]
    sq_rows, hist = one_run(base, params.deep_merge(world_overrides(first), extra), None, job, years)
    out = {"job": job, "status_quo": sq_rows, "platform": {}}
    for sid, xs in x.items():
        out["platform"][sid], _ = one_run(base, params.deep_merge(overrides_for(xs), extra), hist, job, years)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(out))
    tmp.rename(path)                        # a job is either wholly written or not there
    return job["id"], f"{time.time() - t:.0f}s"


def run(a):
    d = OUT / a.name
    manifest = json.loads((d / "manifest.json").read_text())
    jobs = manifest["jobs"]
    if a.shards > 1:
        jobs = jobs[a.shard::a.shards]
    todo = [j for j in jobs if not (d / "jobs" / f"{j['id']}.pkl").exists()]
    print(f"{len(todo)} of {len(jobs)} jobs to run", flush=True)
    # a job's society is kept per process, so jobs are grouped by the base they need
    todo.sort(key=lambda j: (j["pop_seed"], manifest["draws"][j["draw"]].get("behaviour.target_extensive_elasticity", 0)))
    t = time.time()
    with Pool(a.workers, initializer=init, initargs=(manifest,)) as pool:
        for n, (jid, how) in enumerate(pool.imap_unordered(run_job, todo), 1):
            print(f"  {n}/{len(todo)} {jid} {how}  ({(time.time() - t) / 3600:.1f} h)", flush=True)


def slurm(a):
    d = OUT / a.name
    py = a.python or "python"
    script = f"""#!/bin/bash
#SBATCH --job-name=ubi-{a.name}
#SBATCH --array=0-{a.shards - 1}
#SBATCH --cpus-per-task={a.cpus}
#SBATCH --mem-per-cpu=3G
#SBATCH --time={a.hours}:00:00
#SBATCH --output={d}/logs/%A_%a.log
# One array task runs every {a.shards}th job of the manifest, with {a.cpus} worker processes. Finished jobs are
# skipped, so the array can simply be resubmitted after a failure. Build the calibrated bases first, on one node:
#   {py} scripts/ensemble.py run --name {a.name} --workers 1 --shard 0 --shards 1000000
cd {ROOT}
{py} scripts/ensemble.py run --name {a.name} --workers {a.cpus} --shard $SLURM_ARRAY_TASK_ID --shards {a.shards}
"""
    (d / "logs").mkdir(parents=True, exist_ok=True)
    (d / "run_array.sbatch").write_text(script)
    print(f"wrote {d / 'run_array.sbatch'} — submit with: sbatch {d / 'run_array.sbatch'}")


# ------------------------------------------------------------------ summarise
Q = (5, 25, 50, 75, 95)


def summarise(a):
    d = OUT / a.name
    manifest = json.loads((d / "manifest.json").read_text())
    done = [pickle.loads(p.read_bytes()) for p in sorted((d / "jobs").glob("*.pkl"))]
    if not done:
        print("no finished jobs")
        return
    years = manifest["years"]
    keys = [k for k in READ if k != "fund_payout" and any(r[k] is not None for r in done[0]["status_quo"])]
    by = {}
    for res in done:
        shock = res["job"]["shock"]
        for sid, rows in res["platform"].items():
            by.setdefault((sid, shock), []).append((rows, res["status_quo"]))
    summary, lines = {}, [f"# Ensemble {a.name}", "",
                          f"{len(done)} of {len(manifest['jobs'])} jobs finished; {years} years from 2026. "
                          "Percentiles across seeds and parameter draws; 'diff' is the scenario minus the status quo "
                          "run beside it, with the same seed and parameters.", ""]
    for (sid, shock), runs in sorted(by.items()):
        cell = {"n": len(runs), "level": {}, "diff": {}, "p_better": {}}
        for k in keys:
            lv = np.array([[np.nan if r[y][k] is None else r[y][k] for y in range(years)] for r, _ in runs])
            sq = np.array([[np.nan if s[y][k] is None else s[y][k] for y in range(years)] for _, s in runs])
            cell["level"][k] = np.nanpercentile(lv, Q, axis=0).round(4).tolist()
            cell["diff"][k] = np.nanpercentile(lv - sq, Q, axis=0).round(4).tolist()
            cell["p_better"][k] = np.nanmean(lv > sq, axis=0).round(3).tolist()
        summary[f"{sid}|{shock}"] = cell
        name = manifest["scenarios"][sid]["name"]
        lines.append(f"## {name} — {tl.SHOCKS[shock]['name']} ({len(runs)} runs)")
        lines.append("")
        y_mid, y_end = 2025 + min(10, years), 2025 + years
        lines.append(f"| | {y_mid} median (5-95%) | {y_end} median (5-95%) | share of runs better than the status quo, {y_end} |")
        lines.append("|---|---|---|---|")
        for k, lab, better_high in [("balance_bn", "budget, ma.kr. (vs status quo)", True),
                                    ("unemployment_rate", "unemployment (vs status quo)", False),
                                    ("poverty_rate_anchored", "poverty, fixed line (vs status quo)", False),
                                    ("real_income_median", "median income (vs status quo)", True)]:
            def at(y):
                if y >= years or not cell["diff"][k][2] or cell["diff"][k][2][y] != cell["diff"][k][2][y]:
                    return "–"
                q = [cell["diff"][k][i][y] for i in range(len(Q))]
                return f"{q[2]:+.3g} ({q[0]:+.3g} to {q[4]:+.3g})"
            pb = cell["p_better"][k][-1]
            lines.append(f"| {lab} | {at(min(10, years) - 1)} | {at(years - 1)} | {100 * (pb if better_high else 1 - pb):.0f}% |")
        lines.append("")
    (d / "summary.json").write_text(json.dumps({"years": years, "quantiles": Q, "cells": summary}))
    (d / "report.md").write_text("\n".join(lines))
    print(f"wrote {d / 'report.md'}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--name", required=True)
    p.add_argument("--seeds", type=int, default=5)
    p.add_argument("--draws", type=int, default=0, help="parameter draws besides the central estimate")
    p.add_argument("--draw-seed", type=int, default=11)
    p.add_argument("--population-seeds", type=int, default=1)
    p.add_argument("--elasticity-levels", action="store_true")
    p.add_argument("--years", type=int, default=35)
    p.add_argument("--shocks", nargs="+", default=["none"])
    p.add_argument("--scenarios", nargs="*")
    p = sub.add_parser("run")
    p.add_argument("--name", required=True)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=1)
    p = sub.add_parser("slurm")
    p.add_argument("--name", required=True)
    p.add_argument("--shards", type=int, default=100)
    p.add_argument("--cpus", type=int, default=4)
    p.add_argument("--hours", type=int, default=24)
    p.add_argument("--python")
    p = sub.add_parser("summarise")
    p.add_argument("--name", required=True)
    a = ap.parse_args()
    {"plan": plan, "run": run, "slurm": slurm, "summarise": summarise}[a.cmd](a)


if __name__ == "__main__":
    main()
