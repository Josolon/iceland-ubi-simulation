"""Thirty years ahead: what the start-of-life fund does once whole cohorts reach 25 with it.

    .venv/bin/python scripts/long_run.py [--years 30] [--ubi 300]

The page looks ten years ahead, and in ten years the fund has paid almost nobody: it saves while a child is under 18
and pays out at 25, so a child born in 2026 is paid in 2051, and the first cohorts with a full childhood of saving
arrive in the 2040s. Its effect on the economy — deposits on homes, capital to start something with, wealth at the
age decisions are made — can only be seen over a horizon this long.

Both runs start from the calibrated 2025 society in the same world (the page's defaults), the reform measured
against the status quo's own path as the forward runs are. Thirty years is far beyond what the model is tested on:
the backcast covers ten, and a society this far ahead is made of people the model itself brought into being. Read
the direction and the order of magnitude, not the decimals.

Writes data/processed/long_run.json.
"""
import argparse
import json
import pathlib
import pickle
import sys
import time

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ubisim.abm import model  # noqa: E402
from build_explorer_data import calibrated  # noqa: E402
from build_emulator import KEYS, default_x, overrides_for, world_overrides  # noqa: E402

OUT = ROOT / "data/processed/long_run.json"
READ = [("fund assets, ma.kr.", "acc_fund_assets", 1), ("paid out that year, ma.kr.", "fund_payout", 1),
        ("home ownership under 35", "home_ownership_under_35", 100), ("new firms a year", "new_ventures", 1),
        ("household income, median", "real_income_median", 1e-3), ("income: pensioners", "income_pensioners", 1e-3),
        ("income: in work", "income_in_work", 1e-3), ("poverty, fixed line", "poverty_rate_anchored", 100),
        ("employment 16-74", "employment_rate_16_74", 100), ("output", "output_index", 1),
        ("population", "population", 1), ("balance, ma.kr.", "balance_bn", 1), ("debt, % of GDP", "debt_pct_gdp", 1),
        ("house prices", "house_price_index", 1), ("births", "births", 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=30)
    ap.add_argument("--ubi", type=float, default=300.0)
    a = ap.parse_args()
    base = calibrated(1.0, recalibrate=False)
    blob = pickle.dumps(base)
    x = np.array([default_x(k) for k in KEYS])
    t = time.time()
    sq = model.scenario(pickle.loads(blob), world_overrides(x))
    def stepped(soc):
        rows = []
        for _ in range(a.years):
            r = soc.step()
            r["fund_payout"] = float(getattr(soc.macro, "fund_payout", 0.0))   # not among the outputs; read here
            rows.append(r)
        return rows

    sq_rows = stepped(sq)
    over = overrides_for(x)
    over["policy"]["ubi_adult"] = over["policy"]["ubi_child"] = a.ubi * 1000.0
    pf = model.scenario(pickle.loads(blob), over)
    pf.reference = sq.own_history
    pf_rows = stepped(pf)
    print(f"{a.years} years, both runs ({time.time() - t:.0f}s)\n")
    years = [2025 + i + 1 for i in range(a.years)]
    show = [i for i, y in enumerate(years) if y % 5 == 0 or i == len(years) - 1]
    print(f"{'':30s}" + "".join(f"{years[i]:>10d}" for i in show))
    out = {"years": years, "ubi": a.ubi, "series": {}}
    for label, col, k in READ:
        s = [r.get(col) for r in sq_rows]
        p = [r.get(col) for r in pf_rows]
        out["series"][label] = {"status_quo": s, "platform": p}
        if all(v is None for v in p):
            continue
        f = lambda v: f"{v * k:10,.1f}" if v is not None and v == v else f"{'–':>10s}"
        print(f"{label:30s}" + "".join(f(p[i]) for i in show))
        print(f"{'  status quo':30s}" + "".join(f(s[i]) for i in show))
    OUT.write_text(json.dumps(out, default=float))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
