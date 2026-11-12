"""The Guide's start: read it on the surface, move it, and write it into the page.

    .venv/bin/python scripts/guide_start.py                           # the start as it stands, 2035 on the surface
    .venv/bin/python scripts/guide_start.py --set vat=26 fish_rent=50  # in the lever's own units, without saving
    .venv/bin/python scripts/guide_start.py --set vat=26 --write       # save it and put it in the page

The start is the package the page says balances the budget, so it moves with every model change. Its record is
data/processed/scenarios_guide_page.json, every lever filled in: a lever left out of the page's GUIDE_START would
fall back to today's value there and to the default in anything read from the file. Run this after the first surface
of a rebuild; scripts/rebuild_all.sh second then verifies the start in the model.
"""
import argparse
import json
import pathlib
import re
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_emulator as be  # noqa: E402

PAGE = ROOT / "artifacts/explorer_v3/index.html"
FILE = ROOT / "data/processed/scenarios_guide_page.json"
SHOW = ("balance", "net_income", "child_poverty", "essential_gap", "fte")
YEARS = (2030, 2035, 2045)


def surface():
    emu = json.loads((ROOT / "artifacts/explorer_v3/emulator.js").read_text().split("=", 1)[1].rstrip().rstrip(";"))
    for f in be.KERNEL_FILES:
        t = (ROOT / "artifacts/explorer_v3" / f).read_text()
        for o, a in json.loads(t[t.index("window.UBI_EMU, ") + 16:].rstrip().rstrip(";").rstrip(")")).items():
            emu["coeffs"][o]["kernel"]["alpha"] = a
    return emu


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", nargs="*", default=[], help="key=value in the lever's own units")
    ap.add_argument("--write", action="store_true", help="save the start and put it in the page")
    a = ap.parse_args()
    emu = surface()
    L = {l["key"]: l for l in emu["meta"]["levers"]}
    was = json.loads(FILE.read_text())[0]["x"]
    x = {k: was.get(k, L[k]["today"] if L[k]["today"] is not None else be.default_x(k)) for k in be.KEYS}
    for k in be.WORLD:
        x[k] = be.default_x(k)
    x["agreements"], x["haggle"] = 1.0, 1.0
    for s in a.set:
        k, v = s.split("=")
        x[k] = min(1.0, max(0.0, (float(v) - L[k]["lo"]) / (L[k]["hi"] - L[k]["lo"])))
    raw = json.loads((ROOT / "data/processed/emulator_runs.json").read_text())
    X_fit = np.array(raw["X"], float)[:-raw["test"]]
    terms = be.base_terms(len(be.KEYS))
    at = np.array([[x[k] for k in be.KEYS]], float)
    yl = emu["meta"]["year_list"]
    for o in SHOW:
        y = be.surface_at(emu["coeffs"][o], terms, at.copy(), X_fit)[0]
        print(f"{o:15s}", "  ".join(f"{t}: {y[yl.index(t)]:,.3f}" for t in YEARS))
    if a.write:
        FILE.write_text(json.dumps([{"id": "B", "name": "Guide start as the Guide shows it", "x": x}], indent=1))
        text = PAGE.read_text()
        text, n = re.subn(r"const GUIDE_START = \{[^\n]*\};", lambda _: "const GUIDE_START = " + json.dumps(
            {k: round(v, 6) for k, v in x.items()}) + ";", text)
        assert n == 1, "no GUIDE_START in the page"
        PAGE.write_text(text)
        print("written")


if __name__ == "__main__":
    main()
