"""How much of the fall in work rests on what: firms' hiring, the norm, and each part of the reform.

    .venv/bin/python scripts/work_sensitivity.py [--years 10] [--workers 6]

Three sets of runs, each reform against a status quo with the same behaviour, written to
data/processed/work_sensitivity.json:
  - labour demand: firms' own-wage elasticity across its range (uncertainty.RANGES), the fitted value among them;
  - the norm: the response to others' work switched off, as estimated, and doubled;
  - the channels: the reform built up a part at a time, so that each step's change in work is what that part adds.
The steps are in the order the reform works: the payment on today's taxes, then the financing and the rest of the
package, then the haggling round. The order matters in a model with interactions, so read the steps as an account of
this one path and not as each part's effect on its own.
"""
import argparse
import json
import pathlib
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import numpy as np  # noqa: E402

from build_emulator import KEYS, TODAY, reference_x, set_path, overrides_for, world_overrides  # noqa: E402
from build_explorer_data import calibrated  # noqa: E402
from ubisim.abm import model  # noqa: E402

DEMAND = "labour.demand_elasticity"
NORM = "behaviour.norm_scale"
READ = ("fte_per_adult_16_74", "employment_rate_16_74", "balance_bn", "net_income_mean_real", "child_poverty_rate")
_BASE = None


def run(job):
    global _BASE
    name, x, extra, years = job
    if _BASE is None:
        _BASE = pickle.loads((ROOT / "data/processed/_work_base.pkl").read_bytes())
    a = np.array([x[k] for k in KEYS])
    so, ro = world_overrides(a), overrides_for(a)
    for path, v in extra.items():
        set_path(so, path, v)
        set_path(ro, path, v)
    sq, soc = model.scenario(_BASE, so), model.scenario(_BASE, ro)
    out = []
    for _ in range(years):
        s = sq.step()
        soc.reference = sq.own_history
        r = soc.step()
        out.append({k: (r[k], s[k]) for k in READ})
    return name, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    (ROOT / "data/processed/_work_base.pkl").write_bytes(pickle.dumps(calibrated(1.0, recalibrate=False)))
    x = reference_x()
    from ubisim.abm import params, uncertainty
    lo, hi = uncertainty.RANGES[DEMAND]
    fitted = params.DEFAULTS["labour"]["demand_elasticity"]
    today = {k: (v if k not in TODAY else None) for k, v in x.items()}
    jobs = [(f"demand {e:.3f}", x, {DEMAND: float(e)}, a.years) for e in sorted({lo, fitted, *np.linspace(lo, hi, 4)})]
    jobs += [(f"norm {n:g}", x, {NORM: float(n)}, a.years) for n in (0, 1, 2)]
    # the payment on today's rules: every lever with a value today sits there, the payment and what comes with it stay
    from build_emulator import LEVERS  # noqa: PLC0415
    spec = {l[0]: l for l in LEVERS}
    for k in TODAY:
        today[k] = float(np.clip((TODAY[k] - spec[k][3]) / (spec[k][4] - spec[k][3]), 0, 1))
    no_round = dict(x, haggle=0.0)
    jobs += [("the payment on today's rules", today, {}, a.years), ("the whole package, no round", no_round, {}, a.years)]
    with ProcessPoolExecutor(a.workers) as ex:
        res = dict(ex.map(run, jobs))
    (ROOT / "data/processed/_work_base.pkl").unlink()
    (ROOT / "data/processed/work_sensitivity.json").write_text(json.dumps(res, indent=1))
    for name, rows in res.items():
        y = rows[-1]
        print(f"{name:32s} work {y['fte_per_adult_16_74'][0]:.3f} vs {y['fte_per_adult_16_74'][1]:.3f}  "
              f"budget {y['balance_bn'][0] - y['balance_bn'][1]:+6.0f}  "
              f"child poverty {y['child_poverty_rate'][0]:.3f} vs {y['child_poverty_rate'][1]:.3f}", flush=True)


if __name__ == "__main__":
    main()
