"""The past, had it been done differently: every combination of the past panel's levers, each run in the model itself
from the society calibrated to 2015 through 2016-2025 as they happened (v8).

    .venv/bin/python scripts/build_past_grid.py [--workers 6] [--quick]

The levers, and why they are few enough to run every combination exactly rather than fit a surface:
  * payment      none, or the picture's own: 275 þús. of 2025 in the guide's starting picture, 300 in the reference
                 reform, each with the financing designed for it (other amounts with that financing only
                 measure over- or under-financing);
  * basis        the 2025 amount put into 2015 krónur by prices (the same purchasing power, default) or by pay
                 (the same share of pay; about 37% less, since real wages rose that much over the decade);
  * transition   1 or 3 years (policy.transition_years);
  * COVID        answered as it was, or by shielding (build_timeline.shield_past);
  * fund         a fund taking a share of the fishery's rent from 1984: none, a third, half, all of it
                 (scripts/fisheries_history.py builds it to 2015; the model carries it on);
  * controls     what the fund did under the 2008-17 capital controls: paid out, froze its payouts, or brought 30%
                 home in 2009 to retire public debt.
Combinations that cannot differ are run once (no payment: no picture, basis, transition or shielding; no fund: no
controls).

Every run is measured against the status quo of the same decade, with the same rules (scripts/null_test.py).
The page shows the record moved by each run's difference from that status quo where a record exists, and the model's
own levels for poverty, hardship and incomes, which have no yearly record. Writes artifacts/explorer_v3/past_grid.js.
"""
import argparse
import itertools
import json
import pathlib
import pickle
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ubisim.abm import model  # noqa: E402
import backcast as bc  # noqa: E402
import fisheries_history as fh  # noqa: E402
from build_emulator import KEYS, default_x  # noqa: E402
from build_timeline import shield_past  # noqa: E402
from counterfactual_past import reference_reform  # noqa: E402
from history_params import calendar_overrides  # noqa: E402

OUT = ROOT / "artifacts/explorer_v3/past_grid.js"
PAYMENTS = (0, "own")
PICTURES = ("guide", "yours300")
BASES = ("prices", "pay")
TRANSITIONS = (1, 3)
COVID = ("record", "shield")
CAPTURES = (0.0, .33, .5, 1.0)
CONTROLS = ("pay", "freeze", "repatriate")
READ = ["employment_rate_16_74", "unemployment_rate", "output_index", "cpi", "balance_bn", "debt_pct_gdp",
        "population", "immigrants", "emigrants", "real_income_median", "net_income_mean_real", "poverty_rate",
        "poverty_rate_anchored", "child_poverty_rate", "hardship_rate", "wellbeing_index", "income_pensioners",
        "fisheries_fund_real_bn", "fisheries_dividend_bn", "acc_fund_assets", "exchange_rate"]
_BASE = None


def load_base(blob):
    global _BASE
    _BASE = pickle.loads(blob)


def picture_x(name):
    if name == "guide":
        sc = next(s for s in json.loads((ROOT / "data/processed/scenarios_guide_start.json").read_text()) if s["id"] == "B")
    else:
        page = (ROOT / "artifacts/explorer_v3/index.html").read_text()
        sc = next(s for s in json.loads(re.search(r"^const SCENARIOS = (\[.*\]);$", page, re.M).group(1))
                  if s["id"] == name)
    return np.array([sc["x"].get(k, default_x(k)) for k in KEYS])


def fund_settings(capture, controls):
    """The fund as it stood at the start of 2016, from the accounting history, and what it did in the controls."""
    if not capture:
        return None, 0.0
    P, FX, N = fh.cpi(), fh.usd_per_isk(), fh.adults()
    base = fh.rent_base(P)
    r = fh.simulate(base, capture=capture, crisis=controls, P=P, FX=FX, N=N)
    # model krónur are 2015's; the history's are each year's own
    debt_retired = r[2009]["repatriated"] / 1e3 * P[2015] / P[2009]
    return {"assets_bn": r[2015]["fund_isk"] / 1e3, "capture": capture}, debt_retired


def run_one(job):
    key, over, ref, shield, debt_retired = job
    soc = model.scenario(_BASE, over or {})
    if ref is not None:
        soc.reference = ref
    if debt_retired:
        soc.macro.debt -= debt_retired
    shocks = bc.load_shocks()
    rows = []
    for year in bc.YEARS:
        cal = bc.with_shocks(calendar_overrides(year, bc.BASE_YEAR), year, shocks)
        if over and "policy" in over:
            cal = {k: v for k, v in cal.items() if k in ("trade", "history")}
        if shield:
            cal = shield_past(cal, year, shocks)
        soc.set_policy(cal)
        rows.append(soc.step())
    sim = bc.simulated(rows, _BASE)
    out = {k: [None if r.get(k) is None else float(r[k]) for r in rows] for k in READ}
    out.update({f"rec_{k}": [sim[k][str(y)] for y in bc.YEARS] for k in sim})
    return key, out, soc.own_history if ref is None else None


def jobs_for(base, quick=False):
    pics = {p: picture_x(p) for p in PICTURES}
    k, w = base.p["base"]["krona_scale"], base.p["base"]["ratios"]["wages"]
    funds = {(c, ctl): fund_settings(c, ctl) for c in CAPTURES for ctl in (CONTROLS if c else ("pay",))}
    out = []
    if quick:
        funds = {k: v for k, v in funds.items() if k[1] == "pay"}
    for pay in PAYMENTS:
        combos = itertools.product(PICTURES, BASES, TRANSITIONS, COVID) if pay else [(None, None, None, "record")]
        for pic, basis, tr, covid in combos:
            for (cap, ctl), (ff, retired) in funds.items():
                over = {}
                if pay:
                    over = reference_reform(base, None, x=pics[pic])
                    over["policy"]["transition_years"] = tr
                    if basis == "pay":
                        for u in ("ubi_adult", "ubi_child"):
                            over["policy"][u] *= w / k
                if ff:
                    over["fisheries_fund"] = ff
                key = f"{pay}|{pic}|{basis}|{tr}|{covid}|{cap}|{ctl}"
                out.append((key, over, covid == "shield", retired))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--quick", action="store_true", help="the fund only as paid out, a smoke test")
    a = ap.parse_args()
    t = time.time()
    base = bc.calibrated_base()
    blob = pickle.dumps(base)
    load_base(blob)
    _, sq, sq_hist = run_one(("sq", None, None, False, 0.0))
    jobs = jobs_for(base, a.quick)
    print(f"{len(jobs)} runs", flush=True)
    runs = {}
    with ProcessPoolExecutor(a.workers, initializer=load_base, initargs=(blob,)) as ex:
        for i, (key, out, _) in enumerate(ex.map(run_one, [(k, o, sq_hist, s, r) for k, o, s, r in jobs])):
            runs[key] = out
            if i % 25 == 0:
                print(f"  {i + 1}/{len(jobs)} ({time.time() - t:.0f}s)", flush=True)
    act = bc.actual()
    P, FX, N = fh.cpi(), fh.usd_per_isk(), fh.adults()
    hist = fh.rent_base(P)
    history = {f"{c}|{ctl}": {str(y): {kk: v for kk, v in r.items() if kk in ("fund_2025_isk", "dividend_per_adult_month_2025",
                                                                             "take", "rent")}
                              for y, r in fh.simulate(hist, capture=c, crisis=ctl, P=P, FX=FX, N=N).items()}
               for c in CAPTURES if c for ctl in CONTROLS}
    data = {"meta": {"years": bc.YEARS, "payments": PAYMENTS, "pictures": PICTURES, "bases": BASES,
                     "transitions": TRANSITIONS, "covid": COVID, "captures": CAPTURES, "controls": CONTROLS,
                     "krona_2015_per_2025": base.p["base"]["krona_scale"],
                     "generated": time.strftime("%Y-%m-%d")},
            "record": act, "status_quo": sq, "runs": runs, "fund_history": history}
    OUT.write_text("window.UBI_PAST_GRID = " + json.dumps(data, separators=(",", ":"), default=float) + ";\n")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB, {time.time() - t:.0f}s)")


if __name__ == "__main__":
    main()
