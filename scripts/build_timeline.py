"""The long view: every scenario the page offers, run in the model from a point in the past or from today, with or
without a shock ahead, and the status quo beside it under the same world.

    .venv/bin/python scripts/build_timeline.py [--workers 8] [--modes past today] [--shocks none oil_spike ...]

Two ways of looking:

* **From the past** — the society calibrated to 2015 walks through 2016-2025 as they happened (each year's world,
  crisis support and identified shocks, backcast.py --identify), then ten years on in the world the page assumes.
  The status quo also has each year's own tax and benefit rules; a platform scenario has its own from 2016.
* **From today** — the society calibrated to 2025, thirty-five years ahead: long enough for the start-of-life fund
  to pay whole cohorts, which a ten-year view never shows.

A shock ahead is given to both runs alike, from the same year, so what the page shows is what each system makes of
it. The shocks are stress tests, not forecasts: each has a documented historical or scientific anchor for its size
and shape (SHOCKS below), and each is a change to the model's world — prices, productivity, migration, the pace of
automation, the bank's rate — never to its behaviour.

Writes artifacts/explorer_v3/timeline.js (window.UBI_TIMELINE) and data/processed/timeline.json.
"""
import argparse
import copy
import json
import pathlib
import pickle
import re
import sys
import time
from multiprocessing import Pool

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ubisim.abm import model, params  # noqa: E402
import backcast as bc  # noqa: E402
from build_emulator import KEYS, WORLD, default_x, overrides_for, world_overrides  # noqa: E402
from build_explorer_data import calibrated, params_fingerprint  # noqa: E402
from counterfactual_past import reference_reform  # noqa: E402
from history_params import calendar_overrides, load as load_history  # noqa: E402

PAGE = ROOT / "artifacts/explorer_v3/index.html"
OUT_JS = ROOT / "artifacts/explorer_v3/timeline.js"
OUT_JSON = ROOT / "data/processed/timeline.json"
# Runs are kept under the fingerprint of the model and parameters that made them, so a rebuild after any change to
# the model starts afresh instead of mixing old runs with new ones.
CACHE = ROOT / "data/processed/timeline_runs" / params_fingerprint()
PAY_SUFFIX, PAY_FOLLOW = "~pay", .8
SHIELD_SUFFIX = "~shield"      # from the past: COVID answered by shielding instead of as it was
PAST_AHEAD = 10          # years after 2025 in the view from the past
TODAY_YEARS = 35         # 2026-2060
ONSET = {"past": 2028, "today": 2030}

# The shocks. `k` is years since onset (0 = the first year hit); each returns multipliers or settings for that year.
# All are stated every year, including a return to normal, since a society's settings carry from year to year.
SHOCKS = {
    "none": {"name": "No shock", "note": "The world the page assumes, with nothing unusual ahead.", "sources": []},
    "oil_spike": {
        "name": "Oil price shock",
        "note": "Brent doubles for a year and eases back over four, as in 1979-80, 2008 and 2022. Fuel is about a "
                "tenth of Iceland's imports, and dearer flights cost some tourism.",
        "sources": ["Kilian (2009), AER 99(3): oil supply and demand shocks",
                    "Hagstofa: fuel's share of goods imports"]},
    "oil_crash": {
        "name": "Oil price collapse",
        "note": "Brent halves for a year and recovers over four, with metal prices sagging alongside, as in 2015-16 "
                "and 2020. Cheaper imports; smelters earn less.",
        "sources": ["Baffes et al. (2015), World Bank PRN/15/01: the 2014-15 oil price collapse"]},
    "ai_shock": {
        "name": "AI jobs shock",
        "note": "Automation of cognitive work at the fastest pace the model allows (25% a year cheaper and more "
                "capable), from the onset on. The IMF puts about 60% of jobs in advanced economies in reach of AI; "
                "the model decides from wages and costs how many are actually replaced.",
        "sources": ["Cazzaniga et al. (2024), IMF SDN/2024/001: Gen-AI and the future of work",
                    "Eloundou et al. (2024), Science 384: GPTs are GPTs",
                    "Korinek & Suh (2024), NBER w32255: scenarios for the transition to AGI"]},
    "amoc": {
        "name": "Atlantic overturning collapse (AMOC)",
        "note": "The ocean circulation that keeps Iceland mild weakens and collapses over a decade. Winters colder by "
                "several degrees, sea ice nearer the coast, fish stocks move: fish earnings fall by up to 30%, "
                "tourism by 20%, food and imports cost 10% more, output per worker 2% lower, more people leave and "
                "fewer come. Iceland's National Security Council listed a collapse as a national security risk in "
                "2025. The sizes are EST: no economic study of a collapse for Iceland exists yet.",
        "sources": ["van Westen, Kliphuis & Dijkstra (2024), Science Advances 10: AMOC on tipping course",
                    "Ditlevsen & Ditlevsen (2023), Nature Communications 14: collapse likely 2025-2095",
                    "Ritchie et al. (2020), Nature Food 1: AMOC collapse and British agriculture",
                    "Government of Iceland, National Security Council (2025): AMOC as a security risk"]},
    "pandemic": {
        "name": "Pandemic",
        "note": "Tourism falls by three-quarters for a year and recovers over three, as it did in 2020-22; the state "
                "pays the support it paid then (3% and 2% of GDP) and keeps jobs through reduced hours.",
        "sources": ["Hagstofa: tourism revenue 2019-22", "IMF (2021), Iceland Article IV: COVID support"]},
    "pandemic_shield": {
        "name": "Pandemic, answered by shielding",
        "note": "The same pandemic, answered two ways. The status quo answers as Iceland did in 2020. The reform "
                "gives no money to firms and keeps the country open: about 30,000 people at high risk are offered "
                "150 þús. a month on top of the payment to live in designated areas — the empty hotels, whose rent "
                "the state pays — and some 6,000 young people out of work are paid 650 þús. a month to be on call "
                "there. Lives saved are not in the model, which has no deaths from a pandemic; the sizes are "
                "estimates for an illustrative alternative response.",
        "sources": ["Hagstofa: tourism revenue 2019-22", "IMF (2021), Iceland Article IV: COVID support",
                    "Sweden's and Iceland's 2020 experience of protecting care homes (Directorate of Health)"]},
    "financial": {
        "name": "Banking and currency crisis",
        "note": "A crisis on the pattern of 2008-10 at about half its depth — Iceland's banks are now about one "
                "times GDP, not nine: credit tightens, the bank rate jumps, jobs and output fall, many leave.",
        "sources": ["Laeven & Valencia (2018), IMF WP/18/206: systemic banking crises database",
                    "Hagstofa: 2008-10 output, unemployment and migration"]},
    "fish_collapse": {
        "name": "Fish stock collapse",
        "note": "Fish earnings fall by 40% and recover over a decade, as when the herring collapsed in 1967-69 "
                "(export earnings fell by nearly half) or the capelin failed in 2019-20.",
        "sources": ["Jónsson (1994), Economic History of Iceland: the herring collapse",
                    "Hafrannsóknastofnun: capelin advice 2019-2020"]},
    "windfall": {
        "name": "Resource windfall",
        "note": "Oil, gas or minerals come on stream from the onset and reach a resource rent of 10% of GDP in "
                "five years — Norway's scale at its height — taxed at Norway's 78% marginal rate. The export "
                "earnings lift the króna, which costs the other export industries (the 'Dutch disease'). Iceland's "
                "one search, the Dreki licences on the Jan Mayen ridge (2013-18), was given up, so this is a "
                "what-if, not a forecast.",
        "sources": ["Norwegian Ministry of Finance: the National Budget, petroleum net cash flow",
                    "Corden & Neary (1982), Economic Journal 92: booming sector and de-industrialisation",
                    "Orkustofnun (2018): relinquishment of the Dreki area licences"]},
}


def ramp(seq, k, after=1.0):
    return seq[k] if 0 <= k < len(seq) else (after if k >= len(seq) else 1.0)


def shock_settings(name, k, w0, platform=False):
    """The world in year k after the onset (k < 0: before it), from the world just before, w0. `platform`: the run
    is a platform scenario, which answers a "shielded" pandemic its own way."""
    if name == "none" or k < 0:
        return {}
    m = {"tourism": 1.0, "marine": 1.0, "aluminium": 1.0, "import": 1.0, "prod": 1.0, "arrive": 1.0, "leave": 1.0,
         "demand": 1.0, "rate": 0.0, "crisis": 0.0, "retention": 0.0, "ai": None}
    if name in ("oil_spike", "oil_crash"):
        brent = ramp([2.0, 1.6, 1.3, 1.1] if name == "oil_spike" else [.5, .6, .8, .9], k)
        m["import"] = 1 + .10 * (brent - 1)
        m["tourism"] = 1 - .05 * (brent - 1)          # airfares: fuel is about a quarter of an airline's costs
        if name == "oil_crash":
            m["aluminium"] = ramp([.85, .9, .95, 1.0], k)
    elif name == "ai_shock":
        m["ai"] = .25
    elif name == "amoc":
        r = min(1.0, (k + 1) / 10)
        m.update(marine=1 - .30 * r, tourism=1 - .20 * r, prod=1 - .02 * r, arrive=1 - .30 * r, leave=1 + .30 * r)
        m["import"] = 1 + .10 * r
    elif name in ("pandemic", "pandemic_shield"):
        m["tourism"] = ramp([.25, .5, .85], k)
        m["arrive"] = ramp([.6, .8], k)
        m["leave"] = ramp([.8, .9], k)
        gdp = w0["gdp_bn"]
        m["crisis"] = ramp([.03 * gdp, .02 * gdp], k, after=0.0)
        m["retention"] = ramp([.6, .3], k, after=0.0)
    elif name == "financial":
        m["rate"] = ramp([.03, .02, .01], k, after=0.0)
        m["demand"] = ramp([.96, .94, .96, .98], k)
        m["prod"] = ramp([.98, .97, .98, .99], k)
        m["leave"] = ramp([1.4, 1.5, 1.2], k)
        m["arrive"] = ramp([.6, .6, .8], k)
    elif name == "fish_collapse":
        m["marine"] = ramp([.6, .6, .65, .7, .75, .8, .85, .9, .95], k)
    out = {"trade": {"price": {"tourism": w0["tourism"] * m["tourism"], "marine": w0["marine"] * m["marine"],
                               "aluminium": w0["aluminium"] * m["aluminium"]},
                     "import_price": w0["import_price"] * m["import"]},
           "history": {"productivity_level": w0["productivity_level"] * m["prod"],
                       "arrival_scale": w0["arrival_scale"] * m["arrive"],
                       "emigration_scale": w0["emigration_scale"] * m["leave"],
                       "demand_level": w0["demand_level"] * m["demand"],
                       "rate_shock": w0["rate_shock"] + m["rate"],
                       "crisis_support_bn": m["crisis"], "job_retention": m["retention"]}}
    shield = shield_settings(k) if name == "pandemic_shield" and platform else shield_settings(None)
    if name == "pandemic_shield" and platform:
        out["history"].update({"crisis_support_bn": 0.0, "job_retention": 0.0})
    out["history"].update(shield)
    if m["ai"] is not None:
        out["automation"] = {"ai_progress_rate": m["ai"]}
    if name == "windfall":
        # the rent is set here, year by year, so it starts at the onset whatever year the run began in
        out["windfall"] = {"rent_bn": .10 * w0["gdp_bn"] * min(1.0, (k + 1) / 5), "start_year": 0, "ramp_years": 1}
    return out


def shield_settings(k, months=(9, 6)):
    """The reform's shielding, year k after a pandemic's onset (None: none). Stated every year, ended after."""
    c = params.DEFAULTS["crisis"]
    m = months[k] if k is not None and 0 <= k < len(months) else 0
    rooms = c["shield_people"] / c["shield_people_per_room"]
    return {"shield_months": float(m), "shield_carers": float(c["shield_carers"] if m else 0),
            "shield_housing_bn": rooms * c["shield_room_night"] * 30 * m / 1e9}


def world_now(soc):
    """The world a society is in, for a shock to be set against."""
    p = soc.p
    tr, h = p.get("trade") or {}, p.get("history") or {}
    price = tr.get("price") or {}
    return {"tourism": float(price.get("tourism", 1.0)), "marine": float(price.get("marine", 1.0)),
            "aluminium": float(price.get("aluminium", 1.0)), "import_price": float(tr.get("import_price", 1.0)),
            "productivity_level": float(h.get("productivity_level", 1.0)),
            "arrival_scale": float(h.get("arrival_scale", 1.0)), "emigration_scale": float(h.get("emigration_scale", 1.0)),
            "demand_level": float(h.get("demand_level", soc.demand_level)), "rate_shock": float(h.get("rate_shock", 0.0)),
            "gdp_bn": float(soc.macro.GDP0 * soc.macro.output)}


# ------------------------------------------------------------------ what is read off each year
READ = ["population", "output_index", "unemployment_rate", "employment_rate_16_74", "real_income_median",
        "poverty_rate_anchored", "child_poverty_rate", "hardship_rate", "balance_bn", "debt_pct_gdp", "cpi",
        "acc_fund_assets", "home_ownership_under_35", "new_ventures", "births", "income_pensioners",
        "income_in_work", "wellbeing_index", "immigrants", "emigrants", "mean_birth_age"]


def slim(soc, r):
    out = {k: (None if (v := r.get(k)) is None or v != v else float(v)) for k in READ}
    out["fund_payout"] = float(getattr(soc.macro, "fund_payout", 0.0))
    return out


# ------------------------------------------------------------------ the runs
_BASE = None


def load_base(blob, today_years=None):
    global _BASE, TODAY_YEARS
    _BASE = pickle.loads(blob)
    if today_years:
        TODAY_YEARS = today_years


def rebase_indexation(soc):
    """From 2025 on, benefits follow wages again, from the level the record left them at. The backcast imposes the
    record's levels and switches the model's own indexation off; switched back on against the 2015 wage it would
    add the whole decade's real rise a second time."""
    w = soc.D0_pub + soc.D0_priv
    wage = float((soc.omega * w).sum() / max(w.sum(), 1e-9))
    soc.real_wage0 = wage / max(soc.price * (1 + soc.p["markets"]["trend_inflation"]), .1)
    return {"benefits": {"wage_indexation": float(params.DEFAULTS["benefits"]["wage_indexation"])}}


def is_platform(over):
    return bool(over) and (over.get("policy") or {}).get("regime") == "platform"


def shield_past(cal, year, shocks):
    """2020-21 answered by shielding instead of as it was: no support to firms and no job retention, the domestic
    part of the output fall avoided (`crisis.lockdown_share` of the identified productivity fall against 2019),
    and the shielded areas for nine months of 2020 and six of 2021."""
    k = {2020: 0, 2021: 1}.get(year)
    if k is None:
        return cal
    h = dict(cal.get("history", {}))
    pre = shocks.get("2019", {}).get("productivity_level", 1.0)
    share = params.DEFAULTS["crisis"]["lockdown_share"]
    if "productivity_level" in h:
        h["productivity_level"] += share * max(pre - h["productivity_level"], 0.0)
    h.update({"crisis_support_bn": 0.0, "job_retention": 0.0, **shield_settings(k)})
    return {**cal, "history": h}


def run_past(job):
    """2016-2025 as it happened, then ten years on; a shock from ONSET['past']."""
    tag, over, reference, shock = job
    soc = model.scenario(_BASE, over or {})
    if reference is not None:
        soc.reference = reference
    shocks = bc.load_shocks()
    rows = []
    shielded = isinstance(tag, tuple) and str(tag[-1]).endswith(SHIELD_SUFFIX)
    for year in bc.YEARS:
        cal = bc.with_shocks(calendar_overrides(year, bc.BASE_YEAR), year, shocks)
        if over and "policy" in over:   # a run that sets its own policy; a fund alone keeps today's
            cal = {k: v for k, v in cal.items() if k in ("trade", "history")}
        if shielded:
            cal = shield_past(cal, year, shocks)
        soc.set_policy(cal)
        rows.append(slim(soc, soc.step()))
    # on from 2025: the world stays where 2025 left it, the decade's levels held, its one-year shocks ended
    last = shocks.get("2025", {})
    # Migration's identified scales are held at their 2021-25 average rather than reset to 1: they are mostly the
    # model's own shortfall in arrivals against the record, not a one-year event, and reset to 1 the arrivals fell
    # well below the record's, labour ran short and public pay and the payroll climbed — the status quo's deficit
    # went from 3% to 9% of GDP in ten years (2026-09-29).
    recent = [shocks[str(y)] for y in range(2021, 2026) if str(y) in shocks]
    mean = lambda k: float(np.mean([r.get(k, 1.0) for r in recent])) if recent else 1.0
    cont = {"history": {"demand_level": last.get("demand_level", 1.0),
                        "productivity_level": last.get("productivity_level", 1.0),
                        "arrival_scale": mean("arrival_scale"), "emigration_scale": mean("emigration_scale"),
                        "rate_shock": 0.0, "fx_shock": 0.0,
                        "fiscal_residual_bn": last.get("fiscal_residual_bn", 0.0),
                        "crisis_support_bn": 0.0, "job_retention": 0.0}}
    if not (over and "policy" in over):
        cont.update(rebase_indexation(soc))
        # the record's thresholds end in 2025; from there they rise as the law sets them
        cont["policy"] = {"threshold_real_growth": float(params.DEFAULTS["policy"]["threshold_real_growth"])}
    soc.set_policy(cont)
    w0 = world_now(soc)
    for i in range(PAST_AHEAD):
        year = 2026 + i
        soc.set_policy(shock_settings(shock, year - ONSET["past"], w0, platform=is_platform(over)))
        rows.append(slim(soc, soc.step()))
    return tag, rows, soc.own_history if reference is None else None


def run_today(job):
    """2026-2060 from the society calibrated to 2025; a shock from ONSET['today']."""
    tag, over, reference, shock = job
    soc = model.scenario(_BASE, over)
    if reference is not None:
        soc.reference = reference
    w0 = world_now(soc)
    rows = []
    for i in range(TODAY_YEARS):
        year = 2026 + i
        soc.set_policy(shock_settings(shock, year - ONSET["today"], w0, platform=is_platform(over)))
        rows.append(slim(soc, soc.step()))
    return tag, rows, soc.own_history if reference is None else None


def page_scenarios():
    s = PAGE.read_text()
    m = re.search(r"^const SCENARIOS = (\[.*\]);$", s, re.M)
    return [{"id": sc["id"], "name": sc["name"], "x": np.array([sc["x"].get(k, default_x(k)) for k in KEYS])}
            for sc in json.loads(m.group(1))]


def run_mode(mode, base, scenarios, shocks, workers):
    """Every scenario against the status quo in its own world. From today, a scenario's world — the pace of AI, the
    last-decade world, world prices, the sensitivities — is the status quo's too: run in the page's default world
    instead, the status quo had no AI while the scenarios had 5% a year, and the automation that took a tenth of the
    jobs by 2060 was booked to the payment (found 2026-09-29). From the past, the world is the record's for both."""
    fn = run_past if mode == "past" else run_today
    blob = pickle.dumps(base)
    world_of, sq_over = {}, {}
    for sc in scenarios:
        if mode == "past":
            wid = "record"
            sq_over[wid] = None
        else:
            w = tuple(round(float(sc["x"][KEYS.index(k)]), 6) for k in WORLD)
            wid = "w" + "_".join(f"{v:g}" for v in w).replace(".", "p")
            sq_over[wid] = world_overrides(sc["x"])
        world_of[sc["id"]] = wid
    pf_over = {sc["id"]: (reference_reform(base, None, x=sc["x"]) if mode == "past" else overrides_for(sc["x"]))
               for sc in scenarios}
    # From today, each scenario also with the payment following pay as well as prices, the rule today's benefits
    # follow: over thirty-five years that choice decides much of the budget and of poverty on a fixed line, so the
    # page lets the two be set side by side (stored as "<id>~pay").
    if mode == "past":
        for sc in list(scenarios):
            vid = sc["id"] + SHIELD_SUFFIX
            world_of[vid] = world_of[sc["id"]]
            pf_over[vid] = pf_over[sc["id"]]
            scenarios = scenarios + [{**sc, "id": vid}]
    if mode == "today":
        for sc in list(scenarios):
            vid = sc["id"] + PAY_SUFFIX
            world_of[vid] = world_of[sc["id"]]
            pf_over[vid] = params.deep_merge(pf_over[sc["id"]], {"policy": {"ubi_wage_indexation": PAY_FOLLOW}})
            scenarios = scenarios + [{**sc, "id": vid}]
    t = time.time()
    out = {s: {"status_quo": {}, "platform": {}} for s in shocks}
    # every run is kept as it finishes, so a build that is stopped picks up where it was
    CACHE.mkdir(parents=True, exist_ok=True)
    span = PAST_AHEAD if mode == "past" else TODAY_YEARS      # a short smoke test never stands in for a full run
    key = lambda kind, a, b: CACHE / f"{mode}_{kind}_{a}_{b}_{span}y.pkl"
    sq_rows, hist = {}, {}
    with Pool(workers, initializer=load_base, initargs=(blob, TODAY_YEARS)) as pool:
        todo = []
        for s in shocks:
            for wid, ov in sq_over.items():
                k = key("sq", wid, s)
                if k.exists():
                    sq_rows[(wid, s)], hist[(wid, s)] = pickle.loads(k.read_bytes())
                else:
                    todo.append(((wid, s), ov, None, s))
        for tag, rows, h in pool.imap_unordered(fn, todo):
            sq_rows[tag], hist[tag] = rows, h
            key("sq", *tag).write_bytes(pickle.dumps((rows, h)))
            print(f"  {mode} status quo, {tag[1]} in {tag[0]} ({time.time() - t:.0f}s)", flush=True)
        jobs = []
        for s in shocks:
            for sc in scenarios:
                if sc["id"].endswith(SHIELD_SUFFIX) and s != "none":
                    continue                     # COVID's other answer, shown without a shock ahead
                if not sc["id"].endswith((PAY_SUFFIX, SHIELD_SUFFIX)):   # a variant reads its scenario's status quo
                    out[s]["status_quo"][sc["id"]] = sq_rows[(world_of[sc["id"]], s)]
                k = key("pf", sc["id"], s)
                if k.exists():
                    out[s]["platform"][sc["id"]] = pickle.loads(k.read_bytes())
                else:
                    jobs.append(((s, sc["id"]), pf_over[sc["id"]], hist[(world_of[sc["id"]], s)], s))
        for (s, sid), rows, _ in pool.imap_unordered(fn, jobs):
            out[s]["platform"][sid] = rows
            key("pf", sid, s).write_bytes(pickle.dumps(rows))
            print(f"  {mode} {sid}, {s} ({time.time() - t:.0f}s)", flush=True)
    return out


def record_past(base):
    """The record, for the view from the past: what happened, on the page's footing."""
    act = bc.actual()
    h = load_history()["outcomes"]
    ys = [str(y) for y in bc.YEARS]
    return {"gdp_real": act["gdp_real"], "unemployment_rate": act["unemployment_rate"],
            "population": act["population"], "balance_pct_gdp": act["balance_pct_gdp"],
            "debt_pct_gdp": act["debt_pct_gdp"], "cpi": act["cpi"],
            "employment_rate": act["employment_rate"], "years": ys}


# the decade's shocks, as the page marks them (backcast.py identifies their size; these are the names)
PAST_EVENTS = [
    {"from": 2016, "to": 2018, "name": "Tourism boom", "note": "Arrivals doubled in three years; a building boom."},
    {"from": 2019, "to": 2019, "name": "WOW air collapses", "note": "The low-cost airline's fall cut arrivals by a seventh."},
    {"from": 2020, "to": 2021, "name": "COVID", "note": "Tourism fell by three-quarters; the state paid about 3% of GDP in support."},
    {"from": 2022, "to": 2023, "name": "Inflation", "note": "Prices rose 8-9% a year; the bank rate went from 0.75% to 9.25%."},
    {"from": 2023, "to": 2024, "name": "Reykjanes eruptions", "note": "Grindavík evacuated; its housing bought out by the state."},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--modes", nargs="+", default=["past", "today"])
    ap.add_argument("--shocks", nargs="+", default=list(SHOCKS))
    ap.add_argument("--scenarios", nargs="+", default=None, help="scenario ids from the page (default: all)")
    ap.add_argument("--today-years", type=int, default=TODAY_YEARS, help="shorter, for a smoke test")
    a = ap.parse_args()
    globals()["TODAY_YEARS"] = a.today_years
    scen = page_scenarios()
    if a.scenarios:
        scen = [s for s in scen if s["id"] in a.scenarios]
    data = {"shocks": {k: {kk: v for kk, v in SHOCKS[k].items()} for k in a.shocks},
            "scenarios": [{"id": s["id"], "name": s["name"]} for s in scen], "onset": ONSET, "modes": {}}
    for mode in a.modes:
        base = bc.calibrated_base() if mode == "past" else calibrated(1.0, recalibrate=False)
        runs = run_mode(mode, base, scen, a.shocks, a.workers)
        years = list(range(2016, 2026 + PAST_AHEAD)) if mode == "past" else list(range(2026, 2026 + TODAY_YEARS))
        b = base.p.get("base") or {}
        entry = {"years": years, "runs": runs, "gdp0": base.macro.GDP0, "krona_scale": b.get("krona_scale", 1.0),
                 "base_year": b.get("year", 2025)}
        if mode == "past":
            entry["record"] = record_past(base)
            entry["events"] = PAST_EVENTS
        data["modes"][mode] = entry
    OUT_JSON.write_text(json.dumps(data, default=float))
    OUT_JS.write_text("window.UBI_TIMELINE = " + json.dumps(data, default=float, separators=(",", ":")) + ";\n")
    print(f"wrote {OUT_JS} ({OUT_JS.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
