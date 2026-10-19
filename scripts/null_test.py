"""The null test: a run measured the way reforms are, with nothing changed, must reproduce the status quo exactly.

    .venv/bin/python scripts/null_test.py [--years 6]

Every reform is compared with the status-quo run and is given that run's path as its `reference`. If the reference
changes how the model behaves, rather than only what it is compared with, part of every reform's reported effect is
the comparison itself. Until v8 it did: the status quo re-run through the reference drifted to output -15%, prices
-20% and a budget +209 ma.kr. by 2025 in the backcast (found 2026-10-08). Checked here forward from 2025 and through
the past from 2015. Prints PASS or FAIL; exits non-zero on a failure.
"""
import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ubisim.abm import model  # noqa: E402

KEYS = ["employment_rate_16_74", "unemployment_rate", "output_index", "cpi", "exchange_rate", "balance_bn",
        "debt_pct_gdp", "population", "net_income_mean_real", "poverty_rate", "child_poverty_rate"]


def compare(a_rows, b_rows):
    worst = 0.0
    for a, b in zip(a_rows, b_rows):
        for k in KEYS:
            if k in a and a[k] is not None and b.get(k) is not None:
                worst = max(worst, abs(float(a[k]) - float(b[k])) / max(abs(float(a[k])), 1e-6))
    return worst


def forward(years):
    from build_explorer_data import calibrated
    base = calibrated(1.0, recalibrate=False)
    sq = model.scenario(base, {})
    sq_rows = [sq.step() for _ in range(years)]
    again = model.scenario(base, {})
    again.reference = sq.own_history
    return compare(sq_rows, [again.step() for _ in range(years)])


def past():
    import backcast as bc
    from counterfactual_past import run
    base = bc.calibrated_base()
    sq_rows, sq = run(base)
    soc = model.scenario(base, {})
    soc.reference = sq.own_history
    from history_params import calendar_overrides
    shocks = bc.load_shocks()
    rows = []
    for year in bc.YEARS:
        soc.set_policy(bc.with_shocks(calendar_overrides(year, bc.BASE_YEAR), year, shocks))
        rows.append(soc.step())
    return compare(sq_rows, rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=6)
    a = ap.parse_args()
    ok = True
    for name, f in (("forward from 2025", lambda: forward(a.years)), ("the past from 2015", past)):
        worst = f()
        good = worst < 1e-9
        ok &= good
        print(f"{'PASS' if good else 'FAIL'}  {name}: largest relative difference {worst:.2e}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
