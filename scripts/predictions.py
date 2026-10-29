"""The status quo's forecasts for 2026-2030, written down before the record exists, with the margin each must meet.

    .venv/bin/python scripts/predictions.py            # write data/processed/predictions_<version>.json
    .venv/bin/python scripts/predictions.py --check    # set every version's against data/processed/record.json

The forecasts are the exact status-quo run the explorer page carries (artifacts/explorer_v3/emulator.js): today's
tax and benefit rules, the world as the forecasts describe it (prices near the 2.5% target, world prices for tourism,
fish, aluminium and imports at their 2025 level) and no faster AI than today's. They are therefore conditional on
that world. A miss that the world explains (a tourism collapse, an eruption, a war) is not a failure of the model's
behaviour, and the margin cannot tell the two apart. The stronger test, once the years have happened, is the one
scripts/backcast.py makes for 2016-2025: run the years with the world as it was and compare again.

The margins are set from the backcast's errors over 2016-2025 and stated here, before the record, so they cannot be
chosen to fit it. A forecast outside its margin in two or more years counts as a failure, and the forecast is then
reported as failed, with the version that made it. Each release writes its own file and the earlier ones stay as
they were made: a later version's forecasts never replace an earlier version's.

Record sources: Hagstofa's labour force survey, consumer price index, population (MAN00101), births (MAN05201) and
EU-SILC at-risk-of-poverty rates for persons and for children under 18 (LIF01151).
"""
import argparse
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
EMU = ROOT / "artifacts/explorer_v3/emulator.js"
CITATION = ROOT / "CITATION.cff"
RECORD = ROOT / "data/processed/record.json"
YEARS = [2026, 2027, 2028, 2029, 2030]

# output key, what it is, the margin, its unit, and how the margin was set
FORECASTS = [
    ("unemp", "unemployment rate, 16-74 (labour force survey)", 0.010, "share",
     "the backcast misses by 0.25 points on average with demand identified; 1 point allows for the demand shocks a "
     "forecast cannot know"),
    ("emp", "employment rate, 16-74", 0.025, "share", "the backcast's mean miss is 1.4 points, with a bias of -1.1"),
    ("infl", "consumer price inflation, annual average", 0.020, "share",
     "a judgement: the backcast reproduces prices only through an identified exchange-rate shock, so prices are "
     "the least tested forecast here"),
    ("population", "population on 1 January of the following year", 0.015, "relative",
     "the backcast ends 1.0% above the record in 2025"),
    ("births", "live births", 0.10, "relative",
     "a judgement: births are fixed near 4,300 a year in the base and move only through income"),
    ("poverty", "at-risk-of-poverty rate, persons (60% of the median)", 0.020, "share",
     "the model matches EU-SILC's 9.0% in 2025; the margin allows for the survey's sampling error"),
    ("child_poverty", "at-risk-of-poverty rate, children under 18", 0.030, "share",
     "wider than for persons, since the survey samples fewer children"),
]


def status_quo():
    s = EMU.read_text()
    d = json.loads(s[s.index("=") + 1:].strip().rstrip(";"))
    years = d["meta"]["year_list"]
    return {k: {y: d["status_quo"][k][years.index(y)] for y in YEARS} for k, *_ in FORECASTS}, d["meta"]["generated"]


def version():
    """The release, from CITATION.cff, as major.minor: a patch release changes no forecast."""
    line = next(l for l in CITATION.read_text().splitlines() if l.startswith("version:"))
    return ".".join(line.split(":", 1)[1].strip().strip('"').split(".")[:2])


def write():
    sq, generated = status_quo()
    v = version()
    OUT = ROOT / f"data/processed/predictions_{v}.json"
    if OUT.exists() and json.loads(OUT.read_text()).get("made") != generated:
        raise SystemExit(f"{OUT.name} already holds version {v}'s forecasts, made earlier; they are not rewritten")
    out = {"version": v, "made": generated, "conditional_on": "today's rules; the forecast world; AI at today's pace",
           "rule": "a forecast outside its margin in two or more of the five years has failed",
           "forecasts": {k: {"what": what, "margin": m, "unit": unit, "why": why, "forecast": sq[k]}
                         for k, what, m, unit, why in FORECASTS}}
    OUT.write_text(json.dumps(out, indent=1))
    for k, what, m, unit, _ in FORECASTS:
        vals = "  ".join(f"{sq[k][y]:.3f}" if unit == "share" else f"{sq[k][y]:,.0f}" for y in YEARS)
        print(f"{what[:52]:52s} {vals}   ± {m:g}{'' if unit == 'share' else ' (relative)'}")
    print(f"wrote {OUT}")


def check():
    rec = json.loads(RECORD.read_text())
    for f in sorted(ROOT.glob("data/processed/predictions_*.json")):
        print(f"== forecasts of version {f.stem.split('_', 1)[1]}")
        check_one(json.loads(f.read_text())["forecasts"], rec)


def check_one(pred, rec):
    for k, p in pred.items():
        misses, seen = 0, 0
        for y, f in p["forecast"].items():
            r = rec.get(k, {}).get(y)
            if r is None:
                continue
            seen += 1
            err = (f - r) if p["unit"] == "share" else (f / r - 1)
            misses += abs(err) > p["margin"]
            print(f"{k:14s} {y}  forecast {f:.4g}  record {r:.4g}  {'MISS' if abs(err) > p['margin'] else 'ok'}")
        if seen:
            print(f"{k:14s} {'FAILED' if misses >= 2 else 'holding'} ({misses} of {seen} years outside the margin)\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    check() if ap.parse_args().check else write()
