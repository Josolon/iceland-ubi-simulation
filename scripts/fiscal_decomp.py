"""The status quo's public accounts, line by line, against the national accounts: 2016-2025 in the backcast.

    .venv/bin/python scripts/fiscal_decomp.py

The status quo walks through the decade with the identified shocks, except the fiscal residual, which is what this
explains. Every line is in real krónur of 2015 (the record deflated by the CPI), as the change from 2015, so a line
that grows too slowly or too fast shows as a gap that widens year by year.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import backcast as bc  # noqa: E402
from ubisim.abm import model  # noqa: E402
from history_params import calendar_overrides, load  # noqa: E402

# model lines (acc_ in the snapshot) and the national-accounts line each is compared with
PAIRS = [("income tax", ["acc_income_tax"], "income_tax_individuals_bn"),
         ("corporate tax", ["acc_corporate_tax", "acc_corporate_tax_economy"], "corporate_tax_bn"),
         ("property tax", ["acc_property_tax"], "property_tax_bn"),
         ("inheritance tax", ["acc_inheritance_tax"], "inheritance_tax_bn"),
         ("public payroll", ["acc_public_payroll"], "gov_payroll_bn"),
         ("social benefits", ["acc_benefits", "acc_child_payments"], "gov_social_benefits_bn"),
         ("interest", ["acc_interest"], "gov_interest_bn")]


def main():
    base = bc.calibrated_base()
    o = load()["outcomes"]
    shocks = {y: {**s, "fiscal_residual_bn": 0.0} for y, s in bc.load_shocks().items()}
    soc = model.scenario(base, {})
    rows = []
    for year in bc.YEARS:
        soc.set_policy(bc.with_shocks(calendar_overrides(year, bc.BASE_YEAR), year, shocks))
        rows.append(soc.step())
    a0 = soc.accounts0
    cpi = lambda y: o["cpi"][y] / o["cpi"]["2015"]
    real = lambda k, y: o[k][y] / cpi(y)
    ys = [str(y) for y in bc.YEARS]
    print("change from 2015, ma.kr. of 2015: model / record")
    print(f"{'':18s}" + "".join(f"{y:>14s}" for y in ys))
    for label, keys, rec in PAIRS:
        m0 = sum((a0.get(k[4:], 0.0) or 0.0) / a0.get("price", 1.0) for k in keys)
        line = f"{label:18s}"
        for y, r in zip(ys, rows):
            m = sum(r.get(k, 0.0) or 0.0 for k in keys) - m0
            line += f"{m:+7.0f}/{real(rec, y) - real(rec, '2015'):+6.0f}"
        print(line + f"   (2015: model {m0:.0f}, record {o[rec]['2015']:.0f})")
    for label, k in (("revenue", "revenue"), ("expenditure", "expenditure")):
        m0 = a0[k] / a0.get("price", 1.0)
        line = f"{label + ' (modelled)':18s}"
        for y, r in zip(ys, rows):
            line += f"{r.get('acc_' + k, 0) - m0:+7.0f}/{real('gov_' + k + '_bn', y) - real('gov_' + k + '_bn', '2015'):+6.0f}"
        print(line + f"   (2015: model {m0:.0f}, record {o['gov_' + k + '_bn']['2015']:.0f})")
    gdp0 = base.p["base"]["GDP0"]
    print("\nbalance, % of GDP: model / record, and the gap in ma.kr.")
    for y, r in zip(ys, rows):
        mod = 100 * r["balance_bn"] / (gdp0 * r["output_index"])
        print(f"  {y}: {mod:+6.2f} / {o['gov_balance_pct_gdp'][y]:+6.2f}   gap {(o['gov_balance_pct_gdp'][y] - mod) / 100 * gdp0 * r['output_index']:+7.1f}"
              f"   output {r['output_index']:.3f}  cpi {r['cpi']:.3f}/{cpi(y):.3f}")


if __name__ == "__main__":
    main()
