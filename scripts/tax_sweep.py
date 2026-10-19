"""Income tax rates, lowered step by step from the guide's starting picture: where is the sweet spot?

    .venv/bin/python scripts/tax_sweep.py [--bottom 10 15 20 25 31.49] [--top 46.29 50] [--years 10] [--workers 2]

The bracket rates are set directly (the lowest bracket down to about 10%, the top at most 50%):
the bottom rate over --bottom, the top over --top, the middle rate kept where today's sits between the two
(37.99% between 31.49 and 46.29). The thresholds stay today's, 498,122 and 1,398,450 kr. a month. The guide's own
picture (today's rates x 1.35: 42.5 / 51.3 / 62.5%) is run beside them for reference.

Every point is a run of the model itself (not the fitted surface, which only reaches 70% of today's rates). The
guide's starting picture (data/processed/scenarios_guide_start.json, B) with only the income tax rates moved: the
three bracket rates scaled together (policy.platform_income_tax_scale; 1.0 = today's 31.49 / 37.99 / 46.29%). Each
run is measured against the status quo of the same world, as the page's runs are.

Reported for the last year and over the years: the budget, work, output, incomes, poverty, inequality. Two
candidate sweet spots: the lowest rates that keep the budget at or above zero in the last year, and the rates that
maximise the households' median income with the budget still at or above the status quo's.
Writes data/processed/tax_sweep.json.
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
from build_emulator import KEYS, default_x, overrides_for, world_overrides  # noqa: E402

OUT = ROOT / "data/processed/tax_sweep.json"
READ = ["balance_bn", "debt_pct_gdp", "employment_rate_16_74", "fte_per_adult_16_74", "unemployment_rate", "output_index",
        "real_income_median", "net_income_mean_real", "poverty_rate", "child_poverty_rate", "hardship_rate",
        "net_income_d1", "net_income_d10", "acc_income_tax", "cpi"]
_BASE = None


def load(blob):
    global _BASE
    _BASE = pickle.loads(blob)


def brackets(bottom, top):
    """The three bracket rates for a bottom and top rate, the middle one where today's sits between them."""
    mid = bottom + (top - bottom) * (37.99 - 31.49) / (46.29 - 31.49)
    return [[0, bottom / 100], [498_122, mid / 100], [1_398_450, top / 100]]


def run(job):
    scale, x, years, ref = job
    over = overrides_for(np.asarray(x))
    if isinstance(scale, tuple):            # (bottom, top) in %: rates set directly
        over["policy"]["platform_income_tax_brackets"] = brackets(*scale)
        over["policy"]["platform_income_tax_scale"] = 1.0
    elif scale is not None:
        over["policy"]["platform_income_tax_scale"] = scale
    soc = model.scenario(_BASE, over if scale is not None else world_overrides(np.asarray(x)))
    if ref is not None:
        soc.reference = ref
    rows = [soc.step() for _ in range(years)]
    out = {k: [None if r.get(k) is None else float(r[k]) for r in rows] for k in READ}
    return scale, out, soc.own_history if ref is None else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bottom", type=float, nargs="+", default=[10, 15, 20, 25, 31.49])
    ap.add_argument("--top", type=float, nargs="+", default=[46.29, 50])
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    B = next(s for s in json.loads((ROOT / "data/processed/scenarios_guide_start.json").read_text()) if s["id"] == "B")
    x = [B["x"].get(k, default_x(k)) for k in KEYS]
    base = calibrated(1.0, recalibrate=False)
    blob = pickle.dumps(base)
    load(blob)
    _, sq, ref = run((None, x, a.years, None))
    a.scales = [1.35] + [(b, t) for t in a.top for b in a.bottom]
    with ProcessPoolExecutor(a.workers, initializer=load, initargs=(blob,)) as ex:
        got = dict((s, o) for s, o, _ in ex.map(run, [(s, x, a.years, ref) for s in a.scales]))
    OUT.write_text(json.dumps({"runs": {str(s): got[s] for s in a.scales}, "status_quo": sq}, indent=1))   # first
    last = lambda o, k: float("nan") if o[k][-1] is None else o[k][-1]
    fmt = lambda v: f"{v:11.3f}" if (v != v or abs(v) < 10) else f"{v:11,.0f}"
    print(f"the guide's picture with the income tax brackets set; year {a.years} (2035) unless marked")
    label = lambda s: "guide x1.35" if not isinstance(s, tuple) else "/".join(f"{v * 100:.0f}" for _, v in brackets(*s))
    head = ["rates %", "budget", "budget avg", "employment", "FTE/adult", "unemp", "output", "median inc", "poverty",
            "child pov", "hardship", "inc tax bn"]
    print("  " + " ".join(f"{h:>11s}" for h in head))
    rows = []
    for s in a.scales:
        o = got[s]
        r = [label(s), last(o, "balance_bn"), float(np.mean(o["balance_bn"])), last(o, "employment_rate_16_74"),
             last(o, "fte_per_adult_16_74"), last(o, "unemployment_rate"), last(o, "output_index"),
             last(o, "real_income_median"), last(o, "poverty_rate"), last(o, "child_poverty_rate"),
             last(o, "hardship_rate"), last(o, "acc_income_tax")]
        rows.append(r)
        print(f"  {r[0]:>11s} " + " ".join(fmt(v) for v in r[1:]))
    q = [None, last(sq, "balance_bn"), float(np.mean(sq["balance_bn"])), last(sq, "employment_rate_16_74"),
         last(sq, "fte_per_adult_16_74"), last(sq, "unemployment_rate"), last(sq, "output_index"),
         last(sq, "real_income_median"), last(sq, "poverty_rate"), last(sq, "child_poverty_rate"),
         last(sq, "hardship_rate"), last(sq, "acc_income_tax")]
    print("  " + f"{'status quo':>11s} " + " ".join(fmt(v) for v in q[1:]))
    grid = [r for r, s in zip(rows, a.scales) if isinstance(s, tuple)]
    balanced = [r for r in grid if r[1] >= 0]
    lowest = min(balanced, key=lambda r: float(r[0].split("/")[0])) if balanced else None
    fair = [r for r in grid if r[1] >= q[1]]
    best = max(fair, key=lambda r: r[7]) if fair else None
    print(f"\nlowest bottom rate with the budget at or above zero in {2025 + a.years}: "
          + (f"{lowest[0]}" if lowest else "none in the range"))
    print("highest median income with the budget at or above the status quo's: "
          + (f"{best[0]} (median {best[7]:,.0f} kr./month)" if best else "none in the range"))
    OUT.write_text(json.dumps({"settings": [label(s) for s in a.scales], "years": a.years,
                               "runs": {label(s): got[s] for s in a.scales},
                               "status_quo": sq}, indent=1))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
