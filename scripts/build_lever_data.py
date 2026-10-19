"""Precompute the lever effects the explorer needs to be interactive.

    .venv/bin/python scripts/build_lever_data.py [--years 15]

The site serves runs computed in advance, so every setting a visitor can choose has to exist already. A full
factorial over fifteen levers does not (3^15 runs), so the design is:

  * an exact core: every UBI level x immigration regime, run in full;
  * for every other lever, each of its settings run at every UBI level, stored as the difference from the core run
    at that UBI. The interaction that matters most — how a lever behaves at a low versus a high UBI — is therefore
    exact, because the deltas are conditional on the UBI level.

Moving one lever off its default is exact. Moving several adds their effects together, which is an approximation,
and the page says so. Writes artifacts/explorer_v2/levers.js.
"""
import argparse
import json
import os
import pathlib
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ubisim.abm import model, params  # noqa: E402
from build_explorer_data import METRICS, calibrated  # noqa: E402

OUT = ROOT / "artifacts/explorer_v3/levers.js"
UBI = [250_000, 300_000, 350_000, 400_000, 450_000, 500_000]
# Every UBI level gets its own exact core run. A lever's effect is measured at three of them and interpolated
# between, which halves the compute: the deltas move smoothly with the UBI level, unlike the levels themselves.
ANCHORS = [300_000, 400_000, 500_000]

# The outcomes a lever may move on the page. Kept to the headline set: storing every metric for every lever
# setting would make the payload far too large to ship.
HEADLINE = [
    "balance", "debt", "net_income", "net_income_p10", "net_income_p90", "own_net_income",
    *[f"net_d{i}" for i in range(1, 11)],
    "emp", "fte", "unemp", "part", "independent", "ventures", "poverty", "poverty_anchored", "child_poverty", "gini", "p90_p10",
    "cpi", "infl", "fx", "rent", "house", "ca", "output", "population", "emig", "imm",
    "income_tax", "vat", "property_tax", "public_payroll", "ubi_cost", "consumption",
    "wage_ratio", "ptr", "replacement", "housing_burden", "tenure", "automated", "machine_income",
    "essential_gap", "nurse_gap", "teacher_gap", "brain_drain", "sovereign_fund", "weekly_hours",
    "wellbeing", "struggling", "thriving", "students", "tertiary", "poverty_anchored",
    "net_income_sd", "standard_weeks", "infra_capex", "infra_jobs", "weekly_hours",
]

# name: (label, unit, [(setting label, overrides), ...]) — the first setting is the default and is not run
LEVERS = {
    # The 2025 effective rate is 102.8 / 17,300 = 0.59% of assessed value, so "+1 pp" nearly triples it. The
    # labels show the resulting rate rather than the increment, because the increment on its own means nothing.
    "prop_tax": ("Property tax", "% of value", [
        ("0.59 today", {}), ("1.6", {"policy": {"prop_tax_extra_pp": 1.0}}),
        ("2.6", {"policy": {"prop_tax_extra_pp": 2.0}}), ("3.6", {"policy": {"prop_tax_extra_pp": 3.0}})]),
    "vat": ("VAT", "%", [
        ("25", {}), ("20", {"policy": {"vat_platform": .20}}), ("30", {"policy": {"vat_platform": .30}})]),
    "income_tax": ("Income tax rates", "x", [
        ("as today", {}), ("-20%", {"policy": {"platform_income_tax_scale": .8}}),
        ("+20%", {"policy": {"platform_income_tax_scale": 1.2}})]),
    "corporate_tax": ("Corporate tax", "%", [
        ("20", {}), ("15", {"policy": {"corporate_tax_rate": .15}}), ("25", {"policy": {"corporate_tax_rate": .25}})]),
    "wealth_tax": ("Net wealth tax", "%", [
        ("none", {}), ("0.5", {"policy": {"net_wealth_tax_pct": 0.5}}),
        ("1.0", {"policy": {"net_wealth_tax_pct": 1.0}})]),
    "minimum_wage": ("Minimum wage", "þús./mán.", [
        ("none", {}), ("450", {"policy": {"minimum_wage": 450_000}}),
        ("600", {"policy": {"minimum_wage": 600_000}})]),
    "hours": ("Standard week", "", [
        ("5 days", {}), ("4.5 days", {"policy": {"full_time_hours_factor": .9}}),
        ("4 days", {"policy": {"full_time_hours_factor": .8}})]),
    "taper": ("Withdraw UBI above an income", "", [
        ("never", {}), ("from 800 þús., 30%", {"policy": {"ubi_taper_start": 800_000, "ubi_taper_rate": .30}}),
        ("from 600 þús., 50%", {"policy": {"ubi_taper_start": 600_000, "ubi_taper_rate": .50}})]),
    "payroll_cut": ("Cut in public payroll", "%", [
        ("20", {}), ("10", {"policy": {"public_payroll_cut": .10}}), ("30", {"policy": {"public_payroll_cut": .30}})]),
    "childcare": ("Extra childcare places", "", [
        ("none", {}), ("3,000", {"policy": {"childcare_places_added": 3000}}),
        ("6,000", {"policy": {"childcare_places_added": 6000}})]),
    "housing": ("State-built dwellings", "per year", [
        ("none", {}), ("1,000", {"policy": {"public_dwellings_per_year": 1000}}),
        ("2,000", {"policy": {"public_dwellings_per_year": 2000}})]),
    "retraining": ("Retraining", "ma.kr./yr", [
        ("none", {}), ("15", {"policy": {"retraining_bn_per_year": 15}}),
        ("30", {"policy": {"retraining_bn_per_year": 30}})]),
    "fund": ("Surplus into a fund", "", [
        ("no", {}), ("half", {"policy": {"sovereign_fund_share": .5}})]),
    "fx": ("Pension funds hold the króna", "ma.kr./yr", [
        ("none", {}), ("150", {"policy": {"pension_fx_support_bn": 150.}}),
        ("300", {"policy": {"pension_fx_support_bn": 300.}})]),
    "frontier": ("Frontier programmes", "", [
        ("none", {}), ("all five", {"policy": {"frontier_programmes": [
            "controlled_environment_farming", "cultivated_protein", "autonomous_fisheries",
            "robotic_construction", "carbon_mineralisation"]}})]),
    "ai": ("AI progress", "per year", [
        ("none", {}), ("steady 10%", {"automation": {"ai_progress_rate": .10}}),
        ("shock 25%", {"automation": {"ai_progress_rate": .25}})]),
    "clawback": ("Take a share of machine income", "", [
        ("tax only", {}), ("levy + public stake", {"automation": {"levy_rate": .40, "state_capital_share": .50}})]),
    "infrastructure": ("Infrastructure", "", [
        ("none", {}),
        ("city light rail", {"policy": {"infrastructure_programmes": ["city_light_rail"]}}),
        ("+ Keflavík rail, tunnels", {"policy": {"infrastructure_programmes":
            ["city_light_rail", "keflavik_rail", "country_tunnels"]}}),
        ("+ ring railway", {"policy": {"infrastructure_programmes":
            ["city_light_rail", "keflavik_rail", "country_tunnels", "ring_railway"]}})]),
    "culture": ("Cut in state culture support", "%", [
        ("100", {}), ("50", {"policy": {"culture_support_cut": .5}}), ("0", {"policy": {"culture_support_cut": 0.}})]),
}



# What each lever actually does, in one sentence, and what today's level is. Shipped with the data so the page
# can explain itself rather than expecting the reader to know.
NOTES = {
    "prop_tax": "Recurring tax on assessed property value. Today it raises 102.8 ma.kr. on a stock assessed at "
                "17,300 ma.kr. — an effective 0.59%. Raising it pushes house prices down, because the tax "
                "capitalises into what a buyer will pay.",
    "vat": "Value added tax on household spending. The reform sets a single 25% rate; the status quo averages "
           "about 18% once the reduced rate and exemptions are counted.",
    "income_tax": "Scales every bracket rate up or down together. Today's rates are 31.49 / 37.99 / 46.29%.",
    "corporate_tax": "Tax on company profits, 20% today. It also applies to income the state attributes to "
                     "machines under the automation module.",
    "wealth_tax": "A yearly tax on household net wealth above 100 m ISK. Iceland has none today.",
    "minimum_wage": "A statutory monthly floor. Iceland has no statutory minimum — the floor comes from "
                    "collective agreements, around 425 þús. kr.",
    "hours": "The standard full-time week. Note that FTE is measured in 2025 weeks, so a shorter week lowers "
             "FTE per adult by design; look at hours per adult for whether people are working less.",
    "taper": "Withdraws the borgaralaun above an income, turning it into a negative income tax. Cheaper, but it "
             "raises the effective marginal rate on the people it is withdrawn from.",
    "payroll_cut": "How much of the public wage bill is cut. The reform assumes 20%; today's bill is "
                   "709.6 ma.kr.",
    "childcare": "Full-day places beyond today's roughly 19,000, which already leave a waiting list in "
                 "Reykjavík. Places let parents of small children work more.",
    "housing": "Dwellings the state builds regardless of what the market would build. About 165,000 dwellings "
               "exist; the market adds roughly 1.1% a year.",
    "retraining": "Money that speeds movement between professions, raising how many people switch each year.",
    "fund": "Puts half of any budget surplus into a fund earning a real return instead of repaying debt.",
    "fx": "Pension funds sell foreign assets to finance imports and hold the króna up. It works, but the fund "
          "shrinks and so does the return it pays towards the borgaralaun.",
    "frontier": "Five state-funded ventures built on cheap power: indoor farming, cultivated protein, "
                "autonomous fishing, factory-built housing and carbon storage.",
    "infrastructure": "Public works Iceland has deferred: light rail in the city, a Keflavík rail link, "
                      "tunnels for the countryside, a railway around the country. They pay back in travel time, "
                      "which shows up as productivity, and employ people while being built. Ordinary road "
                      "building is not shown because it continues at about the same level either way.",
    "ai": "How fast machines get cheaper and more capable. A shock at 25% a year is the AI-jobs scenario; "
          "take-up still depends on what the labour costs, so dearer labour automates faster.",
    "clawback": "How much of the income attributed to machines the state takes — a levy plus a public "
                "ownership stake, on top of ordinary corporate tax.",
    "culture": "How much state support for the arts is withdrawn. The reform cuts all of it except housing, "
               "leaving the rest to ticket sales.",
}

def base_policy(ubi):
    return {"policy": {"regime": "platform", "wage_setting": "free_market", "ubi_adult": ubi, "ubi_child": ubi}}


def run(job):
    key, blob, overrides, years, reference = job
    soc = model.scenario(pickle.loads(blob), overrides)
    soc.reference = reference
    rows = [soc.step() for _ in range(years)]
    out = {}
    for short in HEADLINE:
        col = METRICS.get(short)
        if not col:
            continue
        vals = [r.get(col) for r in rows]
        out[short] = [None if v is None or v != v else float(f"{v:.5g}") for v in vals]
    return key, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=15)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    t = time.time()
    base = calibrated(1.0, recalibrate=False)
    blob = pickle.dumps(base)
    sq = model.scenario(base, {})
    [sq.step() for _ in range(a.years)]
    reference = sq.own_history
    print(f"status quo done ({time.time() - t:.0f}s)", flush=True)

    jobs = [(f"core|{u // 1000}", blob, base_policy(u), a.years, reference) for u in UBI]
    for name, (_, _, settings) in LEVERS.items():
        for si, (_, over) in enumerate(settings):
            if si == 0:
                continue                      # the default is the core run
            for u in ANCHORS:
                jobs.append((f"{name}|{si}|{u // 1000}", blob,
                             params.deep_merge(base_policy(u), over), a.years, reference))
    print(f"{len(jobs)} runs queued", flush=True)

    results = {}
    with ProcessPoolExecutor(a.workers) as ex:
        for i, (key, series) in enumerate(ex.map(run, jobs, chunksize=2)):
            results[key] = series
            if i % 20 == 19:
                print(f"  {i + 1}/{len(jobs)} ({time.time() - t:.0f}s)", flush=True)

    # store each lever setting as its difference from the core run at the same UBI level
    deltas = {}
    for key, series in results.items():
        name, *rest = key.split("|")
        if name == "core":
            continue
        si, u = rest
        core = results[f"core|{u}"]
        deltas[key] = {k: [None if v is None or core[k][j] is None else float(f"{v - core[k][j]:.5g}")
                           for j, v in enumerate(vals)] for k, vals in series.items() if k in core}

    meta = {"ubi": [u // 1000 for u in UBI], "anchors": [u // 1000 for u in ANCHORS], "notes": NOTES,
            "years": a.years, "headline": HEADLINE,
            "levers": {n: {"label": lab, "unit": unit, "settings": [s for s, _ in sett]}
                       for n, (lab, unit, sett) in LEVERS.items()},
            "generated": time.strftime("%Y-%m-%d")}
    payload = {"meta": meta, "core": {k: v for k, v in results.items() if k.startswith("core|")}, "deltas": deltas}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("window.UBI_LEVERS = " + json.dumps(payload, separators=(",", ":")) + ";\n")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB, {time.time() - t:.0f}s)")


if __name__ == "__main__":
    main()
