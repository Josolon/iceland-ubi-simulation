"""Year-by-year trace of the counterfactual past: every account line and the demographic flows, platform against
the status quo, to find what drives the difference.

    .venv/bin/python scripts/counterfactual_trace.py [--years 2016 2019 2020 2021 2022 2025]
"""
import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import backcast as bc  # noqa: E402
from counterfactual_past import reference_reform, run  # noqa: E402

FLOWS = ["population", "immigrants", "emigrants", "employment_rate_16_74", "unemployment_rate", "output_index", "cpi",
         "exchange_rate", "real_rate", "balance_bn", "debt_pct_gdp"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="+", default=["2016", "2019", "2020", "2021", "2022", "2025"])
    ap.add_argument("--ubi", type=float, default=300.0)
    ap.add_argument("--scenario", default="yours300")
    a = ap.parse_args()
    base = bc.calibrated_base()
    sq_rows, sq = run(base)
    pf_rows, pf = run(base, reference_reform(base, a.ubi, a.scenario), reference=sq.own_history)
    at = {str(y): i for i, y in enumerate(bc.YEARS)}
    for y in a.years:
        s, p = sq_rows[at[y]], pf_rows[at[y]]
        print(f"\n===== {y}")
        for k in FLOWS:
            if k in s:
                print(f"  {k:28s} {s[k]:14,.3f} {p[k]:14,.3f} {p[k] - s[k]:+14,.3f}")
        acc = sorted({k for k in s if k.startswith("acc_")} | {k for k in p if k.startswith("acc_")})
        rows = [(k, s.get(k, 0.0) or 0.0, p.get(k, 0.0) or 0.0) for k in acc]
        rows = [r for r in rows if isinstance(r[1], (int, float)) and isinstance(r[2], (int, float))]
        rows.sort(key=lambda r: -abs(r[2] - r[1]))
        print("  largest account differences (ma.kr.)")
        for k, v0, v1 in rows[:22]:
            print(f"    {k:40s} {v0:10,.1f} {v1:10,.1f} {v1 - v0:+10,.1f}")
        st = {k: v for k, v in p.items() if k.startswith("static_")}
        if st:
            print("  platform's fixed lines")
            for k, v in sorted(st.items(), key=lambda kv: -abs(kv[1] or 0))[:14]:
                print(f"    {k:52s} {v:+10,.1f}")


if __name__ == "__main__":
    main()
