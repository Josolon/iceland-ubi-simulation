"""Point the last near round at the page's scenarios and the Guide's start as they now stand.

    .venv/bin/python scripts/set_centers.py

The surface is relied on most at these settings, and they move each time the search runs. Writes
data/processed/emulator_near4_centers.json, in the form build_emulator's --near4-centers reads.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_emulator import KEYS  # noqa: E402

page = json.loads((ROOT / "data/processed/scenarios_page.json").read_text())
guide = json.loads((ROOT / "data/processed/scenarios_guide_page.json").read_text())
out = [{"name": s["name"], "x": {k: s["x"][k] for k in KEYS}} for s in page + guide]
(ROOT / "data/processed/emulator_near4_centers.json").write_text(json.dumps(out, indent=1))
print(f"{len(out)} centres")
