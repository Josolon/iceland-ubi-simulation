"""The past with the reform in it, for the page: data/processed/counterfactual_past.json → past.js.

    .venv/bin/python scripts/build_past_data.py

Run scripts/backcast.py --identify and scripts/counterfactual_past.py first.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "data/processed/counterfactual_past.json"
OUT = ROOT / "artifacts/explorer_v3/past.js"


def main():
    d = json.loads(SRC.read_text())
    years = [str(y) for y in d["years"]]
    series = {k: {"record": [v["actual"].get(y) for y in years], "with": [v["would"].get(y) for y in years]}
              for k, v in d["would_have_been"].items()}
    fund = {k: {"platform": [v["platform"].get(y) for y in years], "status_quo": [v["status_quo"].get(y) for y in years]}
            for k, v in d["fund"].items()}
    out = {"years": d["years"], "ubi": d["ubi"], "series": series, "shocks": d["shocks"], "fund": fund,
           "totals": d.get("totals", {})}
    OUT.write_text("window.UBI_PAST = " + json.dumps(out, separators=(",", ":"), default=float) + ";\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
