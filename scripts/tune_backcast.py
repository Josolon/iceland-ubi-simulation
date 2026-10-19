"""Tune the uncertain responses so the model reproduces 2016-2021, and test it on 2022-2025.

    .venv/bin/python scripts/tune_backcast.py --draws 600          # the runs, then the fit
    .venv/bin/python scripts/tune_backcast.py --refit              # fit the saved runs again

1. A Latin hypercube over the uncertain responses (literature ranges, uncertainty.RANGES), each point a backcast:
   the model started in 2015 and walked through the actual years.
2. A quadratic surface per series and year, fitted to the runs, predicts any setting instantly.
3. The loss: each series' miss against the record in 2016-2021, in units that make the series comparable (a
   percentage point of unemployment weighs as much as 5,000 people of population). 2022-2025 are never used.
4. The best settings by the surface, checked by real runs; and the plausible set — settings within a margin of the
   best — whose spread is the new, narrower range for each response.

Writes data/processed/tuning_runs.json (raw) and data/processed/tuning.json (the result).
"""
import argparse
import json
import pathlib
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402

from ubisim.abm import model, params  # noqa: E402
from ubisim.abm.uncertainty import RANGES  # noqa: E402
import backcast as bc  # noqa: E402

TUNED = ["labour.demand_elasticity", "labour.renewal_bargaining", "markets.labour_cost_passthrough",
         "markets.demand_pressure_passthrough", "markets.price_adjustment", "markets.export_price_elasticity",
         "markets.import_income_elasticity", "markets.import_price_elasticity", "markets.fx_current_account_response",
         "markets.fx_inflation_passthrough", "markets.taylor_inflation", "markets.housing_price_elasticity",
         "markets.housing_income_elasticity", "markets.construction_elasticity", "wealth.mpc_top",
         "wealth.mpc_liquid_wealth", "migration.immigration_income_elasticity",
         "migration.emigration_income_elasticity"]
EXTRA = {"migration.immigration_demand_elasticity": (0.5, 3.0), "migration.immigration_tightness_elasticity": (0.0, 8.0), "trade.tourism_labour_elasticity": (0.3, 1.2),
         "labour.supply_absorption": (0.5, 1.0)}
SPACE = [(k, *RANGES[k]) for k in TUNED] + [(k, *v) for k, v in EXTRA.items()]
TRAIN = [str(y) for y in range(2016, 2022)]
TEST = [str(y) for y in range(2022, 2026)]
# how much a miss in each series counts: one unit here weighs as much as one in any other
SCALE = {"unemployment_rate": .01, "employment_rate": .01, "inflation": .01, "real_wage": .02, "gdp_real": .02,
         "population": 5000, "immigrants": 2000, "emigrants": 2000, "balance_pct_gdp": 1.0, "debt_pct_gdp": 5.0,
         "exports_real": .05}
RAW = ROOT / "data/processed/tuning_runs.json"
OUT = ROOT / "data/processed/tuning.json"


def overrides(theta):
    over = {}
    for (path, _, _), v in zip(SPACE, theta):
        sec, key = path.split(".", 1)
        over.setdefault(sec, {})[key] = float(v)
    return over


def one(job):
    i, theta, blob = job
    import pickle
    base = pickle.loads(blob)
    base.set_policy(overrides(theta))
    rows = bc.run(base)
    return i, bc.simulated(rows, base)


def with_inflation(s):
    """Year-on-year inflation from the CPI index, the form the record is compared in."""
    out = {k: dict(v) for k, v in s.items()}
    cpi = s["cpi"]
    ys = sorted(cpi)
    out["inflation"] = {y: cpi[y] / (cpi[ys[i - 1]] if i else 1.0) - 1 for i, y in enumerate(ys)}
    return out


def actual():
    a = bc.actual()
    cpi = a["cpi"]
    ys = sorted(cpi)
    a["inflation"] = {y: cpi[y] / (cpi[ys[i - 1]] if i else 1.0) - 1 for i, y in enumerate(ys)}
    a["real_wage"] = {y: v / a["real_wage"]["2016"] for y, v in a["real_wage"].items()}
    return a


def loss(sim, act, years):
    tot, n = 0.0, 0
    for k, sc in SCALE.items():
        for y in years:
            if y in act.get(k, {}) and y in sim.get(k, {}):
                tot += ((sim[k][y] - act[k][y]) / sc) ** 2
                n += 1
    return tot / max(n, 1)


def design(n, k, rng):
    cells = np.array([rng.permutation(n) for _ in range(k)]).T
    return (cells + rng.random((n, k))) / n


def simulate(a):
    import pickle
    base = bc.calibrated_base()
    blob = pickle.dumps(base)
    rng = np.random.default_rng(31)
    U = design(a.draws, len(SPACE), rng)
    lo = np.array([s[1] for s in SPACE]); hi = np.array([s[2] for s in SPACE])
    TH = lo + U * (hi - lo)
    runs = [None] * a.draws
    t = time.time()
    with ProcessPoolExecutor(a.workers) as ex:
        for k, (i, s) in enumerate(ex.map(one, [(i, TH[i], blob) for i in range(a.draws)], chunksize=1)):
            runs[i] = s
            if k % 20 == 19:
                print(f"  {k + 1}/{a.draws} ({time.time() - t:.0f}s)", flush=True)
                RAW.write_text(json.dumps({"space": SPACE, "U": U.tolist(), "runs": runs}))
    RAW.write_text(json.dumps({"space": SPACE, "U": U.tolist(), "runs": runs}))
    return U, runs


def quad(U):
    Z = U - .5
    k = Z.shape[1]
    cols = [np.ones(len(Z))] + [Z[:, j] for j in range(k)] + [Z[:, j] ** 2 for j in range(k)]
    cols += [Z[:, a] * Z[:, b] for a in range(k) for b in range(a + 1, k)]
    return np.column_stack(cols)


def fit(U, runs):
    act = actual()
    runs = [with_inflation(r) for r in runs if r]
    A = quad(U[:len(runs)])
    lam = 1e-2 * len(runs)
    G = np.linalg.solve(A.T @ A + lam * np.eye(A.shape[1]), A.T)
    surf = {}
    for k in SCALE:
        for y in TRAIN + TEST:
            vals = np.array([r.get(k, {}).get(y, np.nan) for r in runs], float)
            if np.isfinite(vals).all():
                surf[(k, y)] = G @ vals
    def predict(Uq):
        Aq = quad(np.atleast_2d(Uq))
        return [{k: {y: float(Aq[i] @ b) for (kk, y), b in surf.items() if kk == k} for k in SCALE}
                for i in range(len(Aq))]
    # search the surface: many random points, then shrink around the best
    rng = np.random.default_rng(5)
    cand = rng.random((20000, U.shape[1]))
    L0 = np.array([loss(s, act, TRAIN) for s in predict(cand)])
    best, L_best = cand[np.argmin(L0)], float(L0.min())
    for scale in (.2, .1, .05, .02):
        near = np.clip(best + rng.normal(0, scale, (2000, U.shape[1])), 0, 1)
        Ln = np.array([loss(s, act, TRAIN) for s in predict(near)])
        if Ln.min() < L_best:
            best, L_best = near[np.argmin(Ln)], float(Ln.min())
    # the plausible set: random settings that fit nearly as well as the best
    plausible = cand[L0 < L_best * 1.25 + .5]
    lo = np.array([s[1] for s in SPACE]); hi = np.array([s[2] for s in SPACE])
    val = lambda u: lo + np.asarray(u) * (hi - lo)
    get = lambda path: (lambda sec, key: params.DEFAULTS[sec][key])(*path.split(".", 1))
    default = np.array([(get(s[0]) - s[1]) / (s[2] - s[1]) for s in SPACE])
    res = {
        "best": {s[0]: float(v) for s, v in zip(SPACE, val(best))},
        "default": {s[0]: float(v) for s, v in zip(SPACE, val(default))},
        "plausible_range": {s[0]: [float(np.percentile(val(plausible)[:, j], 10)),
                                   float(np.percentile(val(plausible)[:, j], 90))] for j, s in enumerate(SPACE)}
        if len(plausible) > 20 else None,
        "surface_loss": {"best_train": L_best, "best_test": loss(predict(best)[0], act, TEST),
                         "default_train": loss(predict(default)[0], act, TRAIN),
                         "default_test": loss(predict(default)[0], act, TEST)},
        "runs": len(runs),
    }
    return res


def verify(res):
    """Real runs at the default and the best settings: the surface's word is not taken for it."""
    base = bc.calibrated_base()
    act = actual()
    out = {}
    for name in ("default", "best"):
        b = bc.calibrated_base()
        b.set_policy(overrides([res[name][s[0]] for s in SPACE]))
        sim = with_inflation(bc.simulated(bc.run(b), base))
        out[name] = {"train": loss(sim, act, TRAIN), "test": loss(sim, act, TEST), "series": sim}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=600)
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--refit", action="store_true")
    a = ap.parse_args()
    if a.refit:
        raw = json.loads(RAW.read_text())
        U, runs = np.array(raw["U"]), raw["runs"]
    else:
        U, runs = simulate(a)
    res = fit(U, runs)
    res["verified"] = verify(res)
    OUT.write_text(json.dumps(res, indent=1))
    s = res["surface_loss"]
    v = res["verified"]
    print(f"loss on the surface: default train {s['default_train']:.2f} test {s['default_test']:.2f}; "
          f"best train {s['best_train']:.2f} test {s['best_test']:.2f}")
    print(f"loss in real runs:   default train {v['default']['train']:.2f} test {v['default']['test']:.2f}; "
          f"best train {v['best']['train']:.2f} test {v['best']['test']:.2f}")
    for k in res["best"]:
        rng = res["plausible_range"][k] if res["plausible_range"] else ["-", "-"]
        print(f"  {k:45s} default {res['default'][k]:7.3f}  best {res['best'][k]:7.3f}  plausible {rng}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
