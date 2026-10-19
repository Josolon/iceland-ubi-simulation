"""The backcast: start the model in 2015 from that year's data, walk it through 2016-2025 as they happened — each
year's tax rules, what tourism, fish and aluminium earned, what oil cost, the COVID support — and set what it
produces against what Hagstofa recorded.

    .venv/bin/python scripts/backcast.py                       # the status quo, as it was
    .venv/bin/python scripts/backcast.py --counterfactual 300  # the reform from 2016, through the same years

Writes data/processed/backcast.json and prints the comparison. Nothing is tuned here: this is how far the model,
as it stands, is from the decade it did not see.
"""
import argparse
import json
import pathlib
import pickle
import sys
import copy
import math
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402

from ubisim.abm import model, params  # noqa: E402
from history_params import base_overrides, calendar_overrides, load  # noqa: E402
from build_explorer_data import params_fingerprint  # noqa: E402

BASE_YEAR = 2015
SHOCKS = ROOT / "data/processed/history_shocks.json"
YEARS = list(range(2016, 2026))
OUT = ROOT / "data/processed/backcast.json"
CACHE = ROOT / f"data/processed/calibrated_base{BASE_YEAR}.pkl"


def calibrated_base(recalibrate=False):
    stamp = CACHE.with_suffix(".params")
    if CACHE.exists() and stamp.exists() and stamp.read_text() == params_fingerprint() and not recalibrate:
        return pickle.loads(CACHE.read_bytes())
    p = params.load(policy={"regime": "status_quo", "wage_setting": "status_quo"})
    p = params.deep_merge(p, base_overrides(BASE_YEAR))
    t = time.time()
    soc = model.Society(p).calibrate(verbose=False)
    print(f"calibrated to {BASE_YEAR} ({time.time() - t:.0f}s)", flush=True)
    CACHE.write_bytes(pickle.dumps(soc))
    stamp.write_text(params_fingerprint())
    return soc


# The borgaralaun and nothing else: every other part of the reform where it was that year.
UBI_ALONE = {"wage_setting": "status_quo", "pension_fold": 0.0, "venture_support": 0.0, "per_diem_cut": 0.0,
             "customs_kept": 1.0, "agriculture_subsidy_cut": 0.0, "subsidy_cut_innovation": 0.0,
             "subsidy_cut_energy_transport": 0.0, "subsidy_cut_other": 0.0, "vat_input_restriction_gain": 0.0,
             "custodianship": 0.0, "public_payroll_cut": 0.0, "prop_tax_extra_pp": 0.0, "governance_cut": 0.0,
             "presidency_cut": 0.0, "church_funding_cut": 0.0, "culture_support_cut": 0.0,
             "residence_rules_strictness": 0.0, "capital_controls": 0.0, "vat_platform": .18, "vat_platform_capture": 1.0}


def load_shocks():
    """Each year's identified shocks (identify()), or none if they have not been identified yet."""
    return json.loads(SHOCKS.read_text()) if SHOCKS.exists() else {}


def with_shocks(cal, year, shocks):
    """A year's overrides with its identified shocks added to the history block, which every run keeps."""
    sh = shocks.get(str(year))
    if not sh:
        return cal
    return {**cal, "history": {**cal.get("history", {}), **sh}}


def identify(base, iterations=8):
    """Find, year by year, the shocks that make the status quo reproduce the record.

    A model cannot generate every force that moved a decade — the investment and construction boom of 2016-18,
    the refugees of 2022-24, the budget's one-offs — and fitting parameters until it does would bend the behaviour
    everything else rests on. So, as a historical shock decomposition does, the unexplained part of each year is
    measured as a shock: a level of labour demand that reproduces unemployment, a productivity level that
    reproduces output, a scale on arrivals that reproduces immigration, a scale on leaving that reproduces
    emigration, the bank's departure from its rule that reproduces the real policy rate, and a residual that
    reproduces the budget. The same shocks are then given to every counterfactual run, so the question they answer
    is what those years would have done with a different policy in place. Since v6 the króna's unexplained move
    (capital flows, `fx_shock`) is identified too, reproducing consumer prices. Pay and debt are not targeted, and
    stay a test of the model."""
    act = actual()
    gdp0 = base.p["base"]["GDP0"]
    soc = model.scenario(base, {})
    dl, pl, ar, rs, es, fs = 1.0, 1.0, 1.0, 0.0, 1.0, 0.0
    out = {}
    for year in YEARS:
        y = str(year)
        cal = calendar_overrides(year, BASE_YEAR)
        u, g, imm, rr = act["unemployment_rate"][y], act["gdp_real"][y], act["immigrants"][y], act["real_rate"][y]
        emi = act["emigrants"][y]
        cp = act["cpi"][y]
        for it in range(iterations):
            trial = copy.deepcopy(soc)
            # the residual is stated as zero: settings merge into the society's parameters, so an unstated
            # residual would carry last year's into this year's trial (found 2026-09-26: 2020's -96 ma.kr. sat in
            # the 2021 trial, and every residual after a large one was wrong by it)
            h = {**cal.get("history", {}), "demand_level": dl, "productivity_level": pl, "arrival_scale": ar,
                 "rate_shock": rs, "emigration_scale": es, "fx_shock": fs, "fiscal_residual_bn": 0.0}
            trial.set_policy({**cal, "history": h})
            r = trial.step()
            eu = r["unemployment_rate"] - u
            eg = math.log(max(r["output_index"], 1e-6) / g)
            ei = math.log(max(r["immigrants"], 1.0) / imm)
            er = r["real_rate"] - rr
            ee = math.log(max(r["emigrants"], 1.0) / emi)
            ep = math.log(max(r["cpi"], 1e-6) / cp)
            tried = (dl, pl, ar, rs, es, fs)
            if abs(eu) < .002 and abs(eg) < .003 and abs(ei) < .02 and abs(er) < .002 and abs(ee) < .03 \
                    and abs(ep) < .004:
                break
            if it == iterations - 1:
                break                         # keep the shocks the last trial ran with, which the residual is for
            dl *= math.exp(2.0 * eu)          # unemployment too high: more room for jobs
            pl *= math.exp(-.8 * eg)          # output too high: less output per hour
            ar *= math.exp(-.9 * ei)          # too many arrivals: fewer
            rs -= er                          # the rule's rate against the bank's: the difference, added
            es *= math.exp(-.9 * ee)          # too many leaving: fewer
            fs -= 1.5 * ep                    # prices too high: a stronger króna (tradables are ~0.4 of the CPI)
        dl, pl, ar, rs, es, fs = tried
        bal = act["balance_pct_gdp"].get(y)
        mod = 100 * r["balance_bn"] / (gdp0 * r["output_index"])
        residual = (bal - mod) / 100 * gdp0 * r["output_index"] if bal is not None else 0.0
        sh = {"demand_level": dl, "productivity_level": pl, "arrival_scale": ar, "rate_shock": rs,
              "emigration_scale": es, "fx_shock": fs,
              "fiscal_residual_bn": residual}
        soc.set_policy({**cal, "history": {**cal.get("history", {}), **sh}})
        r = soc.step()
        out[y] = sh
        print(f"{y}: demand {dl:.3f}  productivity {pl:.3f}  arrivals x{ar:.2f}  leaving x{es:.2f}  rate {rs:+.3f}  "
              f"króna {fs:+.3f}  residual {residual:+7.1f} bn   cpi {r['cpi']:.3f}/{cp:.3f}  "
              f"unemployment {r['unemployment_rate']:.3f}/{u:.3f}  output {r['output_index']:.3f}/{g:.3f}  "
              f"arrivals {r['immigrants']:,.0f}/{imm:,.0f}  balance {100 * r['balance_bn'] / (gdp0 * r['output_index']):+.2f}/"
              f"{bal if bal is not None else float('nan'):+.2f}  ({it + 1} tries)", flush=True)
    SHOCKS.write_text(json.dumps(out, indent=1))
    print(f"wrote {SHOCKS}")
    return out


def run(base, platform=None, variant="platform", fixed_arrivals=None, shocks=None):
    """Step through 2016-2025, imposing each year's rules and world before it is simulated.

    platform: a borgaralaun in þús. of 2025 krónur a month, paid from 2016. variant "platform" is the reform as
    written, with its own taxes; "alone" is the borgaralaun with every other rule as it actually was that year."""
    over = {}
    if platform:
        amount = platform * 1000 * base.p["base"]["krona_scale"]
        pol = {"regime": "platform", "wage_setting": "free_market", "ubi_adult": amount, "ubi_child": amount}
        if variant == "alone":
            pol.update(UBI_ALONE)
            over["fisheries"] = {"rent_capture": base.p["fisheries"]["rent_capture_status_quo"]}
            over["energy"] = {"smelter_exit_share": 0.0}
        over["policy"] = pol
    soc = model.scenario(base, over)
    if fixed_arrivals is not None:
        soc.fixed_arrivals = fixed_arrivals
    rows = []
    for year in YEARS:
        cal = with_shocks(calendar_overrides(year, BASE_YEAR), year, shocks or {})
        if platform and variant == "platform":   # the reform sets its own taxes; the world and crisis carry over
            cal = {k: v for k, v in cal.items() if k in ("trade", "history")}
        elif platform:                             # the year's own tax rules, allowance included
            cal["policy"]["platform_personal_credit"] = cal["policy"]["personal_credit"]
        soc.set_policy(cal)
        rows.append(soc.step())
    return rows


def actual():
    """What happened, in the model's terms: indices on the base year, rates as shares, money in ma.kr."""
    h = load()
    o = h["outcomes"]
    b = str(BASE_YEAR)
    ys = [str(y) for y in YEARS]
    cpi = lambda y: o["cpi"][y] / o["cpi"][b]
    real_wage = {y: (o["wage_index"][y] / o["wage_index"][b]) / cpi(y) for y in ys}
    return {
        "employment_rate": {y: o["employment_rate"][y] / 100 for y in ys},
        "unemployment_rate": {y: o["unemployment_rate"][y] / 100 for y in ys},
        "cpi": {y: cpi(y) for y in ys},
        "real_wage": real_wage,
        "gdp_real": {y: o["gdp_real_index"][y] / o["gdp_real_index"][b] for y in ys},
        "population": {y: o["population_end_of_year"][y] for y in ys},
        "emigrants": {y: o["emigration_icelandic"][y] + o["emigration_foreign"][y] for y in ys},
        "immigrants": {y: o["immigration_icelandic"][y] + o["immigration_foreign"][y] for y in ys},
        "balance_pct_gdp": {y: o["gov_balance_pct_gdp"][y] for y in ys if y != "2016"},   # 2016: a one-off
        "debt_pct_gdp": {y: 100 * o["gov_liabilities_bn"][y] / o["gdp_bn"][y] for y in ys},
        "exports_real": {y: (o["exports_bn"][y] / o["exports_bn"][b]) / cpi(y) for y in ys},
        # the bank's key rate less that year's inflation (Seðlabanki, annual averages)
        "real_rate": {y: (h["policy"]["key_rate_pct"][y] - 100 * (o["cpi"][y] / o["cpi"][str(int(y) - 1)] - 1)) / 100
                      for y in ys},
    }


def simulated(rows, base):
    """The model's run, on the same footing."""
    gdp0 = base.p["base"]["GDP0"]
    # Hagstofa's wage index (LAU04800) prices the same jobs year after year. The model's equivalent is each
    # profession's pay weighted by its first-year hours; labour income per FTE also moved with the job mix
    occ = [k[len("wage_"):] for k in rows[0] if k.startswith("wage_") and f"supply_{k[len('wage_'):]}" in rows[0]]
    weights = np.array([rows[0][f"supply_{o}"] for o in occ])
    index = lambda r: float(np.array([r[f"wage_{o}"] for o in occ]) @ weights) / r["cpi"]
    w0 = index(rows[0])
    out = {}
    for y, r in zip(YEARS, rows):
        y = str(y)
        put = lambda k, v: out.setdefault(k, {}).__setitem__(y, float(v))
        put("employment_rate", r["employment_rate_16_74"])
        put("unemployment_rate", r["unemployment_rate"])
        put("cpi", r["cpi"])
        put("real_wage", index(r) / w0)
        put("gdp_real", r["output_index"])
        put("population", r["population"])
        put("emigrants", r["emigrants"])
        put("immigrants", r["immigrants"])
        put("balance_pct_gdp", 100 * r["balance_bn"] / (gdp0 * r["output_index"]))
        put("debt_pct_gdp", r["debt_pct_gdp"])
        put("exports_real", r["exports_bn"] / base.p["base"]["X0"])
        put("real_rate", r["real_rate"])
    # the model's first-year wage is the reference; put the record on the same footing
    return out


def compare(sim, act):
    """For each series: the model and the record by year, and the error — mean absolute, in the series' units."""
    table = {}
    for k, a in act.items():
        s = sim.get(k, {})
        ys = [y for y in a if y in s]
        if k == "real_wage":   # the model's index starts at its own 2016; rebase the record to 2016 too
            a = {y: a[y] / a["2016"] for y in ys}
        err = [s[y] - a[y] for y in ys]
        table[k] = {"model": {y: s[y] for y in ys}, "actual": {y: a[y] for y in ys},
                    "mean_abs_error": float(np.mean(np.abs(err))) if err else None,
                    "bias": float(np.mean(err)) if err else None}
    return table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recalibrate", action="store_true")
    ap.add_argument("--counterfactual", type=float, default=None, help="platform borgaralaun, þús. a month (2025 kr.)")
    ap.add_argument("--identify", action="store_true", help="identify each year's shocks, then run with them")
    ap.add_argument("--raw", action="store_true", help="the model alone, without the identified shocks")
    a = ap.parse_args()
    base = calibrated_base(a.recalibrate)
    t = time.time()
    if a.identify:
        identify(base)
    shocks = {} if a.raw else load_shocks()
    rows = run(base, shocks=shocks)
    act = actual()
    res = {"base_year": BASE_YEAR, "years": YEARS, "status_quo": compare(simulated(rows, base), act)}
    print(f"backcast run ({time.time() - t:.0f}s)\n")
    if a.counterfactual:
        sq = simulated(rows, base)
        res["counterfactual"] = {"ubi": a.counterfactual}
        arrivals = [r["immigrants"] for r in rows]
        for variant in ("platform", "alone", "platform, arrivals as in the status quo"):
            if variant.startswith("platform, arrivals"):
                cf = simulated(run(base, a.counterfactual, "platform", fixed_arrivals=arrivals, shocks=shocks), base)
            else:
                cf = simulated(run(base, a.counterfactual, variant, shocks=shocks), base)
            # what would have been: the record, moved by the difference the borgaralaun makes in the model
            would = {k: {y: act[k][y] + cf[k][y] - sq[k][y] for y in act[k] if y in cf.get(k, {}) and y in sq.get(k, {})}
                     for k in act}
            res["counterfactual"][variant] = {"model": cf, "effect": {k: {y: cf[k][y] - sq[k][y] for y in cf[k]
                                                                         if y in sq.get(k, {})} for k in cf},
                                              "would_have_been": would}
            print(f"\ncounterfactual, {variant}, {a.counterfactual:.0f} þús. from 2016: what would have been")
            for k in ("unemployment_rate", "employment_rate", "real_wage", "population", "balance_pct_gdp",
                      "debt_pct_gdp", "cpi"):
                print(f"  {k:20s}" + "".join(f"{would[k].get(str(y), float('nan')):>10.3f}" if abs(would[k].get(str(y), 0)) < 1000
                                              else f"{would[k].get(str(y), float('nan')):>10,.0f}" for y in YEARS))
    if a.counterfactual:
        # what the extra arrivals do: each variant against the model's own status quo, per head where it matters
        sq = simulated(rows, base)
        print("\neffect in 2025 against the model's status quo")
        for variant, r in res["counterfactual"].items():
            if not isinstance(r, dict):
                continue
            m = r["model"]
            head = lambda s, y="2025": s["gdp_real"][y] / s["population"][y]
            print(f"  {variant:42s} population {100 * (m['population']['2025'] / sq['population']['2025'] - 1):+5.1f}%"
                  f"  GDP {100 * (m['gdp_real']['2025'] / sq['gdp_real']['2025'] - 1):+5.1f}%"
                  f"  GDP per head {100 * (head(m) / head(sq) - 1):+5.1f}%"
                  f"  real wage {100 * (m['real_wage']['2025'] / sq['real_wage']['2025'] - 1):+5.1f}%"
                  f"  balance 2021-25 {sum(m['balance_pct_gdp'][y] - sq['balance_pct_gdp'][y] for y in ('2021', '2022', '2023', '2024', '2025')) / 5:+5.2f} pts/yr"
                  f"  debt {m['debt_pct_gdp']['2025'] - sq['debt_pct_gdp']['2025']:+5.1f} pts")
    OUT.write_text(json.dumps(res, indent=1))
    print(f"{'':20s}" + "".join(f"{y:>9d}" for y in YEARS) + "   mean |error|")
    for k, v in res["status_quo"].items():
        fmt = (lambda x: f"{x:9,.0f}") if k in ("population", "emigrants", "immigrants") else (lambda x: f"{x:9.3f}")
        print(f"{k + ' model':20s}" + "".join(fmt(v["model"].get(str(y), np.nan)) if str(y) in v["model"] else f"{'':9s}"
                                            for y in YEARS) + f"   {v['mean_abs_error']:.3f}")
        print(f"{'  actual':20s}" + "".join(fmt(v["actual"][str(y)]) if str(y) in v["actual"] else f"{'':9s}" for y in YEARS))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
