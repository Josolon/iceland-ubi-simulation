"""Second round of tuning: a narrower box around round one's best, the new structural settings at full range, and
the choice made by real runs rather than by the fitted surface.

    .venv/bin/python scripts/tune_round2.py --draws 400

Round one's quadratic surface, with every pair crossed among 22 settings, was too rough to search on: it put the
default's loss at 22 where real runs gave 9. Here the box is small enough for main effects and squares to fit, the
surface only proposes candidates, and each candidate is run for real; the one that fits 2016-2021 best is kept, and
its 2022-2025 error — never used in choosing — is the test.

Writes data/processed/tuning_round2_runs.json and data/processed/tuning_round2.json.
"""
import argparse
import json
import pathlib
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402

import backcast as bc  # noqa: E402
import tune_backcast as t1  # noqa: E402

ROUND1 = ROOT / "data/processed/tuning.json"
RAW = ROOT / "data/processed/tuning_round2_runs.json"
OUT = ROOT / "data/processed/tuning_round2.json"
NEW = [("labour.tot_passthrough", 0.0, 1.0), ("labour.agreement_real_premium", 0.0, .02),
       ("migration.new_job_fill_share", 0.0, 1.0)]


def space():
    best = json.loads(ROUND1.read_text())["best"]
    out = []
    for path, lo, hi in t1.SPACE:
        w = .25 * (hi - lo)
        out.append((path, max(lo, best[path] - w), min(hi, best[path] + w)))
    return out + NEW


def overrides(sp, theta):
    over = {}
    for (path, _, _), v in zip(sp, theta):
        sec, key = path.split(".", 1)
        over.setdefault(sec, {})[key] = float(v)
    return over


def one(job):
    i, over, blob = job
    base = pickle.loads(blob)
    base.set_policy(over)
    return i, t1.with_inflation(bc.simulated(bc.run(base), base))


def surface(U, runs):
    Z = U - .5
    A = np.column_stack([np.ones(len(Z)), Z, Z ** 2 - 1 / 12])
    G = np.linalg.solve(A.T @ A + 1e-3 * len(Z) * np.eye(A.shape[1]), A.T)
    coef = {}
    for k in t1.SCALE:
        for y in t1.TRAIN + t1.TEST:
            v = np.array([r.get(k, {}).get(y, np.nan) for r in runs], float)
            if np.isfinite(v).all():
                coef[(k, y)] = G @ v

    def predict(Uq):
        Zq = np.atleast_2d(Uq) - .5
        Aq = np.column_stack([np.ones(len(Zq)), Zq, Zq ** 2 - 1 / 12])
        vals = {kk: Aq @ c for kk, c in coef.items()}
        return [{k: {y: float(vals[(k, y)][i]) for (kk, y) in coef if kk == k} for k in t1.SCALE}
                for i in range(len(Zq))]
    return predict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=400)
    ap.add_argument("--workers", type=int, default=9)
    ap.add_argument("--refit", action="store_true")
    a = ap.parse_args()
    sp = space()
    lo, hi = np.array([s[1] for s in sp]), np.array([s[2] for s in sp])
    base = bc.calibrated_base()
    blob = pickle.dumps(base)
    act = t1.actual()
    t = time.time()
    if a.refit:
        raw = json.loads(RAW.read_text())
        U, runs = np.array(raw["U"]), raw["runs"]
    else:
        U = t1.design(a.draws, len(sp), np.random.default_rng(47))
        runs = [None] * a.draws
        jobs = [(i, overrides(sp, lo + U[i] * (hi - lo)), blob) for i in range(a.draws)]
        with ProcessPoolExecutor(a.workers) as ex:
            for k, (i, s) in enumerate(ex.map(one, jobs, chunksize=1)):
                runs[i] = s
                if k % 20 == 19:
                    print(f"  {k + 1}/{a.draws} ({time.time() - t:.0f}s)", flush=True)
                    RAW.write_text(json.dumps({"space": sp, "U": U.tolist(), "runs": runs}))
        RAW.write_text(json.dumps({"space": sp, "U": U.tolist(), "runs": runs}))
    keep = [i for i, r in enumerate(runs) if r]
    U, runs = U[keep], [runs[i] for i in keep]
    # the best real runs of the design itself, and what the surface proposes
    real_loss = np.array([t1.loss(r, act, t1.TRAIN) for r in runs])
    predict = surface(U, runs)
    rng = np.random.default_rng(9)
    cand = rng.random((30000, U.shape[1]))
    L = np.array([t1.loss(s, act, t1.TRAIN) for s in predict(cand)])
    proposed = [cand[i] for i in np.argsort(L)[:6]] + [U[i] for i in np.argsort(real_loss)[:3]]
    jobs = [(i, overrides(sp, lo + u * (hi - lo)), blob) for i, u in enumerate(proposed)]
    # the round-one best and the defaults, run on the same footing
    r1 = json.loads(ROUND1.read_text())
    jobs.append((len(jobs), t1.overrides([r1["best"][p] for p, _, _ in t1.SPACE]), blob))
    jobs.append((len(jobs), {}, blob))
    with ProcessPoolExecutor(a.workers) as ex:
        checked = dict(ex.map(one, jobs, chunksize=1))
    names = [f"candidate {i + 1}" for i in range(len(proposed))] + ["round one best", "default"]
    scores = {names[i]: {"train": t1.loss(s, act, t1.TRAIN), "test": t1.loss(s, act, t1.TEST)}
              for i, s in checked.items()}
    pick = min((n for n in names[:len(proposed)]), key=lambda n: scores[n]["train"])
    u = proposed[names.index(pick)]
    res = {"space": sp, "chosen": pick,
           "values": {p: float(v) for (p, _, _), v in zip(sp, lo + u * (hi - lo))},
           "scores": scores,
           "series": {n: checked[i] for i, n in enumerate(names) if n in (pick, "default", "round one best")},
           "design_best_train": float(real_loss.min()), "runs": len(runs)}
    OUT.write_text(json.dumps(res, indent=1))
    print(f"\n{'':18s} {'train 2016-21':>14s} {'test 2022-25':>13s}")
    for n in names:
        print(f"{n:18s} {scores[n]['train']:14.2f} {scores[n]['test']:13.2f}{'   <- chosen' if n == pick else ''}")
    print("\nchosen values:")
    for p, v in res["values"].items():
        print(f"  {p:48s} {v:8.4f}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
