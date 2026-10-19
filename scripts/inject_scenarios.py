"""Put the scenarios the page offers into it, with the model's own numbers rather than the fitted surface's.

    .venv/bin/python scripts/inject_scenarios.py --prepare     # after scenarios.py v3
    .venv/bin/python scripts/verify_scenarios.py --file data/processed/scenarios_page.json
    .venv/bin/python scripts/inject_scenarios.py               # writes SCENARIOS into the explorer page

--prepare collects the reference reform (the scenario the page opens on, read from the page) and the search's
scenarios into data/processed/scenarios_page.json, levers as a dictionary. The second step reads that file and the
verification, writes each scenario's note from the model's run, and replaces the SCENARIOS line in the page.
"""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_emulator import KEYS  # noqa: E402

PAGE = ROOT / "artifacts/explorer_v3/index.html"
SEARCH = ROOT / "data/processed/scenarios_v3.json"
PAGED = ROOT / "data/processed/scenarios_page.json"
VERIFIED = ROOT / "data/processed/scenarios_verified.json"
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
    out = [{"id": OWN, "name": own["name"], "x": own["x"], "own": True}]
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
    m = {k: r["model"] for k, r in v.items()}
    parts = [f"in 2035 the budget is {m['balance']:+,.0f} ma.kr.", f"household income {m['net_income'] / 1000:,.0f} "
             f"þús. a month", f"unemployment {100 * m['unemp']:.1f}%",
             f"essential services short {m['essential_gap']:,.0f} posts", f"child poverty {100 * m['child_poverty']:.1f}%"]
    text = "Run in the model itself, not only on the fitted surface: " + ", ".join(parts) + "."
    if sc.get("surface_vs_sq") is not None:
        text += (f" Over 2027-35 the fitted surface puts the budget {sc['surface_vs_sq']:+,.0f} ma.kr. against the "
                 f"status quo.")
    if sc.get("moved"):
        text += " Levers moved: " + ", ".join(f"{k} {v:.1f}" if isinstance(v, (int, float)) else f"{k} {v}"
                                             for k, v in list(sc["moved"].items())[:10]) + "."
    return text


def inject():
    scen = json.loads(PAGED.read_text())
    ver = json.loads(VERIFIED.read_text())
    out = []
    for sc in scen:
        v = ver.get(sc["name"])
        if not v:
            print(f"no verification for {sc['name']}; left out")
            continue
        name = "300 þús., reference reform" if sc.get("own") else sc["name"]
        body = note(sc, v)
        if sc.get("own"):
            body = "The reference reform, as the page opens. " + body
        if sc.get("optimistic"):
            body = ("An openly optimistic route to a larger payment, and the largest payment it carried in the "
                    "search, 50 þús. at a time. Its budget was held to today's status quo — without the windfall or "
                    "the robots, since they are what pays. The page compares it with a status quo that has them "
                    "too, so there it shows what the payment costs against the windfall spent today's way. ") + body
        out.append({"id": sc["id"], "name": name, "note": body, "x": sc["x"]})
    s = PAGE.read_text()
    _, m = page_scenarios()
    s = s[:m.start()] + "const SCENARIOS = " + json.dumps(out, ensure_ascii=False) + ";" + s[m.end():]
    PAGE.write_text(s)
    print(f"wrote {len(out)} scenarios into {PAGE.name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    a = ap.parse_args()
    prepare() if a.prepare else inject()
