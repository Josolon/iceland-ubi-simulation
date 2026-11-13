"""Put the scenarios the page offers into it, with the model's own numbers rather than the fitted surface's.

    .venv/bin/python scripts/inject_scenarios.py --prepare     # after scenarios.py v3
    .venv/bin/python scripts/verify_scenarios.py --file data/processed/scenarios_page.json
    .venv/bin/python scripts/inject_scenarios.py               # writes SCENARIOS into the explorer page

--prepare collects the reference reform (the scenario the page opens on, build_emulator.REFERENCE_REFORM) and the
search's scenarios into data/processed/scenarios_page.json, levers as a dictionary. The second step reads that file and the
verification, writes each scenario's note from the model's run, and replaces the SCENARIOS line in the page.
"""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_emulator import KEYS, reference_x  # noqa: E402

PAGE = ROOT / "artifacts/explorer_v3/index.html"
SEARCH = ROOT / "data/processed/scenarios_v3.json"
PAGED = ROOT / "data/processed/scenarios_page.json"
VERIFIED = ROOT / "data/processed/scenarios_verified.json"
# every year of the same runs (verify_scenarios.py writes them beside the 2035 figures), and the Guide's start
SERIES = ROOT / "data/processed/scenarios_verified_series.json"
GUIDE_SERIES = ROOT / "data/processed/scenarios_guide_start_verified_series.json"
GUIDE_NAME = "Guide start as the Guide shows it"
# what the page's cards read from a scenario's own run (RUN_KEYS on the page)
RUN_KEYS = ["balance", "net_income", "fte", "cpi", "debt", "unemp", "child_poverty", "poverty", "hardship"]


def run_for(series):
    """A scenario's own run for the page: the mean of its runs, its status quo's, and their spread, each year."""
    if not series:
        return None
    r5 = lambda v: [None if x is None else float(f"{x:.5g}") for x in v]
    out = {"years": series["years"], "seeds": series["seeds"]}
    for k in RUN_KEYS:
        out[k], out["sq_" + k], out["sd_" + k] = r5(series[k]), r5(series["sq_" + k]), r5(series["sd_" + k])
    return out
IDS = {"250, moderate": "s250", "300, standard": "std300", "300, fisheries fee as today": "fish300",
       "300, children paid to families": "kids300", "350, balanced mix": "bal350"}
OWN = "yours300"


def page_scenarios():
    s = PAGE.read_text()
    m = re.search(r"^const SCENARIOS = (\[.*\]);$", s, re.M)
    return json.loads(m.group(1)), m


def prepare():
    current, _ = page_scenarios()
    own = next(sc for sc in current if sc["id"] == OWN)
    out = [{"id": OWN, "name": own["name"], "x": reference_x(), "own": True}]
    for sc in json.loads(SEARCH.read_text()):
        if sc["name"] not in IDS:
            continue
        x = sc["x"] if isinstance(sc["x"], dict) else dict(zip(KEYS, sc["x"]))
        out.append({"id": IDS[sc["name"]], "name": sc["name"], "x": x, "surface_vs_sq": sc.get("vs_sq_2027_35"),
                    "moved": sc.get("moved", {})})
    # the optimistic routes to a larger payment (scenarios.py high), when they have been searched
    high = ROOT / "data/processed/scenarios_high.json"
    for sc in json.loads(high.read_text()) if high.exists() else []:
        x = sc["x"] if isinstance(sc["x"], dict) else dict(zip(KEYS, sc["x"]))
        out.append({"id": sc["id"], "name": sc["name"], "x": x, "surface_vs_sq": sc.get("vs_sq_2027_35"),
                    "moved": sc.get("moved", {}), "optimistic": True})
    PAGED.write_text(json.dumps(out, indent=1))
    print(f"wrote {PAGED}: {len(out)} scenarios")


def note(sc, v):
    """The scenario's 2035 figures from the full model, each beside the status quo it is compared with. The levers
    it moves are listed by the page itself (SCENARIOS[].moved), in the page's own labels and units."""
    m = {k: r["model"] for k, r in v.items()}
    q = {k: r.get("status_quo") for k, r in v.items()}
    sd = v["balance"].get("sd_vs_status_quo")
    seeds = f" (the difference varies by ±{sd:,.0f} between {v['balance']['seeds']} runs)" if sd else ""
    sg = lambda x: f"{x:+,.0f}".replace("-", "−")
    parts = [f"the budget {sg(m['balance'])} ma.kr. against the status quo's {sg(q['balance'])}{seeds}",
             f"household income {m['net_income'] / 1000:,.0f} þús. a month per person against {q['net_income'] / 1000:,.0f}",
             f"unemployment {100 * m['unemp']:.1f}% against {100 * q['unemp']:.1f}%",
             f"essential services short of {m['essential_gap']:,.0f} full-time posts against {q['essential_gap']:,.0f}",
             f"child poverty {100 * m['child_poverty']:.1f}% against {100 * q['child_poverty']:.1f}%"]
    text = "In the full model, in 2035: " + "; ".join(parts) + "."
    if sc.get("surface_vs_sq") is not None:
        text += (f" Over 2027-35 the fitted surface puts its budget {sc['surface_vs_sq']:,.0f} ma.kr. better than "
                 f"the status quo's in total." if sc["surface_vs_sq"] >= 0 else
                 f" Over 2027-35 the fitted surface puts its budget {-sc['surface_vs_sq']:,.0f} ma.kr. worse than "
                 f"the status quo's in total.")
    return text


def inject():
    scen = json.loads(PAGED.read_text())
    ver = json.loads(VERIFIED.read_text())
    runs = json.loads(SERIES.read_text()) if SERIES.exists() else {}
    out = []
    for sc in scen:
        v = ver.get(sc["name"])
        if not v:
            print(f"no verification for {sc['name']}; left out")
            continue
        name = "300 þús., reference reform" if sc.get("own") else sc["name"]
        body = note(sc, v)
        if sc.get("own"):
            body = "The reference reform, the setting the Explorer opens on. " + body
        if sc.get("optimistic"):
            body = ("An openly optimistic route to a larger payment: the largest payment, searched in steps of "
                    "50 þús., that the gain in its name (a resource windfall, a robot dividend or both) can pay for "
                    "while the budget does no worse than the status quo's without that gain. The figures below "
                    "compare it with a status quo that has the same gain, so they show what the payment costs "
                    "against that gain spent under today's rules. ") + body
        rec = {"id": sc["id"], "name": name, "note": body, "moved": list(sc.get("moved", {})), "x": sc["x"]}
        if run_for(runs.get(sc["name"])):
            rec["run"] = run_for(runs[sc["name"]])
        else:
            print(f"no yearly run for {sc['name']}: its cards show the surface")
        out.append(rec)
    s = PAGE.read_text()
    _, m = page_scenarios()
    s = s[:m.start()] + "const SCENARIOS = " + json.dumps(out, ensure_ascii=False) + ";" + s[m.end():]
    g = json.loads(GUIDE_SERIES.read_text()).get(GUIDE_NAME) if GUIDE_SERIES.exists() else None
    s, n = re.subn(r"^const GUIDE_RUN = .*;$", lambda _: "const GUIDE_RUN = " + json.dumps(run_for(g)) + ";", s,
                   count=1, flags=re.M)
    if not n:
        raise SystemExit("no GUIDE_RUN line in the page")
    PAGE.write_text(s)
    print(f"wrote {len(out)} scenarios into {PAGE.name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    a = ap.parse_args()
    prepare() if a.prepare else inject()
