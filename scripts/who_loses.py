"""Who in the poorest tenth comes out worse under the reform, and why.

    .venv/bin/python scripts/who_loses.py [--years 5]

Both runs branch from one calibrated society and people keep their row, so person i is the same person in each.
The poorest tenth is chosen in the status quo's own year, on net income per adult in 2025 krónur, and the change
is read for the same people under the reform as specified (the page's defaults), in the same world
and against its own status-quo reference path, exactly as the fitted surface's runs are made. Groups are what
people *are* in the status quo — pensioner, disabled, out of work, student, in work — so the question answered is
"which of today's poorest lose", not "who is poor afterwards".
"""
import argparse
import pickle
import sys
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ubisim.abm import model  # noqa: E402
from build_explorer_data import calibrated  # noqa: E402
from build_emulator import KEYS, default_x, overrides_for, world_overrides  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=5)
    a = ap.parse_args()
    base = calibrated(1.0, recalibrate=False)
    blob = pickle.dumps(base)
    x = np.array([default_x(k) for k in KEYS])
    sq = model.scenario(pickle.loads(blob), world_overrides(x))
    for _ in range(a.years):
        sq.step()
    pf = model.scenario(pickle.loads(blob), overrides_for(x))
    pf.reference = sq.own_history
    for _ in range(a.years):
        pf.step()
    A, B = sq.A, pf.A
    n = min(len(A["alive"]), len(B["alive"]))
    both = np.flatnonzero(A["alive"][:n] & B["alive"][:n] & (A["age"][:n] >= 18))
    inc_sq = sq.net_now[both] / sq.price
    inc_pf = pf.net_now[both] / pf.price
    cut = np.quantile(inc_sq, .1)
    poor = inc_sq <= cut
    st = A["status"][both]
    groups = {
        "pensioner (67+)": A["age"][both] >= 67,
        "disabled, working age": (A["age"][both] < 67) & A["disabled"][both],
        "student": (A["age"][both] < 67) & ~A["disabled"][both] & (A["studying"][both] > 0),
        "out of work": (A["age"][both] < 67) & ~A["disabled"][both] & (A["studying"][both] == 0)
        & (st == model.NONWORK),
        "in work or a venture": (A["age"][both] < 67) & ~A["disabled"][both] & (A["studying"][both] == 0)
        & (st != model.NONWORK),
    }
    print(f"poorest tenth of adults in the status quo, year {a.years}: net income below {cut:,.0f} kr./month "
          f"(2025 krónur); {poor.sum():,} people")
    print(f"{'group':26s} {'share':>7s} {'sq kr.':>9s} {'platform':>9s} {'change':>8s} {'worse off':>10s}")
    for name, g in groups.items():
        m = poor & g
        if not m.any():
            continue
        ch = inc_pf[m] / np.maximum(inc_sq[m], 1) - 1
        print(f"{name:26s} {m.sum() / poor.sum():7.1%} {inc_sq[m].mean():9,.0f} {inc_pf[m].mean():9,.0f} "
              f"{np.median(ch):+8.1%} {(ch < -.01).mean():10.1%}")
    ch = inc_pf[poor] / np.maximum(inc_sq[poor], 1) - 1
    print(f"{'all of the poorest tenth':26s} {1:7.1%} {inc_sq[poor].mean():9,.0f} {inc_pf[poor].mean():9,.0f} "
          f"{np.median(ch):+8.1%} {(ch < -.01).mean():10.1%}")
    # and everyone, since those today's system pays best among the poor sit just above the poorest tenth
    print(f"\nall adults, by group")
    for name, g in groups.items():
        if not g.any():
            continue
        c = inc_pf[g] / np.maximum(inc_sq[g], 1) - 1
        print(f"{name:26s} {g.mean():7.1%} {inc_sq[g].mean():9,.0f} {inc_pf[g].mean():9,.0f} "
              f"{np.median(c):+8.1%} {(c < -.01).mean():10.1%}")


if __name__ == "__main__":
    main()
