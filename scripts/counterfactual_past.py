"""The decade as it happened, and the same decade with the reform in place from 2016.

    .venv/bin/python scripts/counterfactual_past.py [--ubi 300]

Both runs start from the society calibrated to 2015 and walk through 2016-2025 with each year's world imposed as it
was — what tourism, fish and aluminium earned, what imports and oil cost, the COVID collapse and the support paid
through it. The status quo also gets each year's own tax and benefit rules; the reform gets the reference settings
(the page's defaults, with the payment in 2015 krónur) and keeps them. The reform run is measured against the
status quo's own path, exactly as the forward runs are.

What is printed is what would have been: the record, moved by the difference the reform makes in the model. The
model's own misses in the status quo (scripts/backcast.py) cancel in that difference as far as they are the same in
both runs, which is the reason for reporting it that way.

Three things are read off:
  * the shocks — the tourism boom of 2016-18, COVID in 2020-21, the inflation of 2022-23 — each as the change across
    the shock with and without the payment, so the question answered is whether the reform cushions or amplifies;
  * the start-of-life fund over its first decade: what it holds, what it pays out, and to whom;
  * the decade's totals: the budget, debt, employment, prices, population.

Writes data/processed/counterfactual_past.json.
"""
import argparse
import json
import pathlib
import re
import sys
import time

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ubisim.abm import model  # noqa: E402
import backcast as bc  # noqa: E402
from build_emulator import KEYS, LEVERS, WORLD, default_x, overrides_for  # noqa: E402
from history_params import calendar_overrides  # noqa: E402

OUT = ROOT / "data/processed/counterfactual_past.json"
# policy settings the reform expresses in krónur of 2025, to be put in 2015 krónur
KRONA = ("ubi_adult", "ubi_child", "ubi_taper_start", "inheritance_tax_floor", "net_wealth_tax_threshold",
         "minimum_wage")
SHOCKS = {
    "The tourism boom (2016-18)": ("2016", "2018", None),
    "COVID (2019-20)": ("2019", "2020", "2019"),
    "The inflation of 2022-23": ("2021", "2023", "2021"),
}
READ = [("unemployment", "unemployment_rate", "pts", 100), ("employment", "employment_rate_16_74", "pts", 100),
        ("hardship", "hardship_rate", "pts", 100), ("poverty, fixed line", "poverty_rate_anchored", "pts", 100),
        ("child poverty", "child_poverty_rate", "pts", 100), ("income fell by a fifth", "income_fell_20pct", "pts", 100),
        ("poorest tenth's income", "net_income_d1", "%", None), ("median income", "real_income_median", "%", None),
        ("housing cost burden", "housing_cost_burden", "pts", 100), ("struggling", "wellbeing_struggling", "pts", 100),
        ("immigrants", "immigrants", "%", None), ("output", "output_index", "%", None)]


def page_scenario(sid="yours300"):
    """A scenario the page offers, as lever positions: by default the reference reform, which the page
    opens on. The lever defaults alone are not the reform: they keep today's income-tax rates and abolish the
    personal allowance, a package that over-finances the payment by several points of GDP."""
    page = (ROOT / "artifacts/explorer_v3/index.html").read_text()
    m = re.search(r"^const SCENARIOS = (\[.*\]);$", page, re.M)
    sc = next(s for s in json.loads(m.group(1)) if s["id"] == sid)
    return np.array([sc["x"].get(k, default_x(k)) for k in KEYS]), sc["name"]


def reference_reform(base, ubi, sid="yours300", x=None):
    """The reference reform, in the base year's krónur. The world is not part of it — the backcast imposes the
    world as it was: world prices, AI, the last decade — and nor are the behavioural settings, which stay at their
    tuned values."""
    if x is None:
        x, _ = page_scenario(sid)
    over = overrides_for(x)
    # every setting that describes the world or behaviour rather than policy, removed by its own path: the past's
    # status quo runs with the tuned values, so the reform must too
    for key in WORLD:
        path = next(l[5] for l in LEVERS if l[0] == key).split(".")
        node = over
        for part in path[:-1]:
            node = node.get(part, {})
        node.pop(path[-1], None)
    over.pop("trade", None)
    # birth timing, profession moves, the match gain and spending on security are platform channels: kept
    k = base.p["base"]["krona_scale"]
    g = base.p["base"]["static_scale"]
    if ubi is not None:   # otherwise the scenario's own amount
        over["policy"]["ubi_adult"] = over["policy"]["ubi_child"] = ubi * 1000.0
    for key in KRONA:
        if key in over["policy"] and over["policy"][key]:
            over["policy"][key] = float(over["policy"][key]) * k
    if "agriculture" in over:
        over["agriculture"] = {kk: (v * g if kk.endswith("_bn") else v) for kk, v in over["agriculture"].items()}
    return over


def run(base, over=None, reference=None):
    """A decade with each year's world, crisis support and identified shocks imposed (backcast.py --identify):
    the same shocks in both runs, so the difference is what the policy made of them."""
    soc = model.scenario(base, over or {})
    if reference is not None:
        soc.reference = reference
    shocks = bc.load_shocks()
    rows = []
    for year in bc.YEARS:
        cal = bc.with_shocks(calendar_overrides(year, bc.BASE_YEAR), year, shocks)
        if over and "policy" in over:   # the reform sets its own taxes and benefits; the world and the crisis carry
            cal = {k: v for k, v in cal.items() if k in ("trade", "history")}   # over (a fund alone keeps today's)
        soc.set_policy(cal)
        rows.append(soc.step())
    return rows, soc


def series(rows, col):
    return {str(y): r.get(col) for y, r in zip(bc.YEARS, rows)}


def change(s, a, b, pct):
    if a is None or s.get(a) is None or s.get(b) is None:
        return None
    return 100 * (s[b] / s[a] - 1) if pct else s[b] - s[a]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ubi", type=float, default=300.0, help="þús. a month, 2025 krónur")
    ap.add_argument("--scenario", default="yours300", help="a scenario id from the page")
    a = ap.parse_args()
    base = bc.calibrated_base()
    t = time.time()
    sq_rows, sq = run(base)
    over = reference_reform(base, a.ubi, a.scenario)
    print(f"platform: {page_scenario(a.scenario)[1]}")
    pf_rows, _ = run(base, over, reference=sq.own_history)
    print(f"both runs ({time.time() - t:.0f}s)\n")
    sim_sq, sim_pf, act = bc.simulated(sq_rows, base), bc.simulated(pf_rows, base), bc.actual()
    out = {"ubi": a.ubi, "scenario": page_scenario(a.scenario)[1], "years": bc.YEARS, "would_have_been": {}, "shocks": {}, "fund": {}}

    print(f"what would have been, with a {a.ubi:.0f} þús. platform from 2016 (the record moved by the model's difference)")
    print(f"{'':22s}" + "".join(f"{y:>9d}" for y in bc.YEARS))
    for k in ("unemployment_rate", "employment_rate", "real_wage", "gdp_real", "cpi", "population", "balance_pct_gdp",
              "debt_pct_gdp"):
        would = {y: act[k][y] + sim_pf[k][y] - sim_sq[k][y] for y in act[k] if y in sim_pf.get(k, {}) and y in sim_sq[k]}
        out["would_have_been"][k] = {"actual": act[k], "would": would}
        fmt = (lambda v: f"{v:9,.0f}") if k == "population" else (lambda v: f"{v:9.3f}")
        print(f"{k + ' (record)':22s}" + "".join(fmt(act[k][str(y)]) if str(y) in act[k] else " " * 9 for y in bc.YEARS))
        print(f"{'  with the reform':22s}" + "".join(fmt(would[str(y)]) if str(y) in would else " " * 9 for y in bc.YEARS))

    print("\nthe shocks: change across each, without and with the reform")
    for name, (y0, y1, _) in SHOCKS.items():
        y0 = y0 if y0 != "2015" else "2016"
        print(f"\n  {name}, {y0} to {y1}")
        rec = {}
        for label, col, unit, scale in READ:
            s_sq, s_pf = series(sq_rows, col), series(pf_rows, col)
            pct = unit == "%"
            c_sq, c_pf = change(s_sq, y0, y1, pct), change(s_pf, y0, y1, pct)
            if c_sq is None or c_pf is None:
                continue
            if scale:
                c_sq, c_pf = c_sq * scale, c_pf * scale
            rec[label] = {"status_quo": c_sq, "platform": c_pf, "unit": unit}
            print(f"    {label:26s} {c_sq:+8.2f} {unit:3s} without   {c_pf:+8.2f} {unit:3s} with")
        out["shocks"][name] = rec

    print("\nthe start-of-life fund, first decade (ma.kr. of 2015; payouts at 25)")
    print(f"{'':22s}" + "".join(f"{y:>9d}" for y in bc.YEARS))
    for label, col in (("assets", "acc_fund_assets"), ("paid out", "fund_payout"),
                       ("home ownership <35", "home_ownership_under_35"), ("new firms", "new_ventures")):
        s_pf, s_sq = series(pf_rows, col), series(sq_rows, col)
        out["fund"][label] = {"platform": s_pf, "status_quo": s_sq}
        vals = [s_pf[str(y)] for y in bc.YEARS]
        if all(v is None for v in vals):
            continue
        print(f"{label:22s}" + "".join(f"{v:9.2f}" if v is not None else " " * 9 for v in vals))
        if label in ("home ownership <35", "new firms"):
            print(f"{'  status quo':22s}" + "".join(f"{s_sq[str(y)]:9.2f}" if s_sq[str(y)] is not None else " " * 9
                                                 for y in bc.YEARS))

    b = sim_pf["balance_pct_gdp"], sim_sq["balance_pct_gdp"]
    ys = [y for y in b[0] if y in b[1]]
    out["totals"] = {"balance_pts_per_year": float(np.mean([b[0][y] - b[1][y] for y in ys])),
                     "debt_2025_pts": sim_pf["debt_pct_gdp"]["2025"] - sim_sq["debt_pct_gdp"]["2025"]}
    print(f"\nover the decade: balance {out['totals']['balance_pts_per_year']:+.2f} points of GDP a year against the "
          f"status quo; debt in 2025 {out['totals']['debt_2025_pts']:+.1f} points")
    OUT.write_text(json.dumps(out, indent=1, default=float))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
