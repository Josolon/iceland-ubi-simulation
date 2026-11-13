"""The build's own gate, and what the pages must carry.

    .venv/bin/python -m unittest discover tests
"""
import json
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import build_emulator as be  # noqa: E402
import build_stamp as bs  # noqa: E402


class Stamps(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        (self.dir / "a.js").write_text("one")
        self.patches = [mock.patch.object(bs, "ROOT", self.dir), mock.patch.object(bs, "STAMPS", self.dir / "s.json"),
                        mock.patch.object(bs, "PAGES", ["a.js"]), mock.patch.object(bs, "GUIDED", []),
                        mock.patch.object(bs, "params_fingerprint", lambda: "m1")]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_unrecorded_file_fails(self):
        self.assertEqual(len(bs.stale()), 1)

    def test_recorded_file_passes(self):
        bs.record(["a.js"])
        self.assertEqual(bs.stale(), [])

    def test_file_from_an_earlier_model_fails(self):
        bs.record(["a.js"])
        with mock.patch.object(bs, "params_fingerprint", lambda: "m2"):
            self.assertEqual(len(bs.stale()), 1)

    def test_file_changed_by_hand_fails(self):
        bs.record(["a.js"])
        (self.dir / "a.js").write_text("two")
        self.assertEqual(len(bs.stale()), 1)


class Reference(unittest.TestCase):
    def test_reference_reform_stands_in_the_page_world(self):
        x = be.reference_x()
        for k in be.WORLD:
            self.assertAlmostEqual(x[k], be.default_x(k), msg=k)

    def test_the_round_is_on_and_agreements_end(self):
        x = be.reference_x()
        self.assertEqual((x["haggle"], x["agreements"]), (1.0, 1.0))


class Page(unittest.TestCase):
    def test_no_stale_script_is_loaded(self):
        page = (ROOT / "artifacts/explorer_v3/index.html").read_text()
        for src in re.findall(r'<script src="([^"]+)"', page):
            self.assertTrue((ROOT / "artifacts/explorer_v3" / src).exists(), src)

    def test_guide_options_are_levers_in_range(self):
        """The surface's Guide rounds read each option with a regex (build_emulator.guide_answers_x) that skips a key
        it does not know and clips a value out of range, so a typo would silently change what it was fitted to."""
        page = (ROOT / "artifacts/explorer_v3/index.html").read_text()
        block = page[page.index("const GUIDE = ["):page.index("\n];", page.index("const GUIDE = ["))]
        questions = re.findall(r'id: "(\w+)".*?options: \[(.*?)\]\s*\}', block, re.S)
        self.assertEqual(len(questions), len(re.findall(r'\{ id: "', block)), "a question the parser cannot read")
        ranges = {lv[0]: (lv[3], lv[4]) for lv in be.LEVERS}
        for qid, opts in questions:
            choices = re.findall(r"\{([^{}]*)\}", opts)
            self.assertTrue(choices, f"{qid}: no options")
            for c in choices:
                for k, v in re.findall(r"(\w+):\s*([^,}]+)", c):
                    self.assertIn(k, ranges, f"{qid}: {k} is not a lever")
                    self.assertRegex(v.strip(), r"^-?[\d.]+$", f"{qid}: {k} is not a number")
                    lo, hi = ranges[k]
                    self.assertTrue(lo <= float(v) <= hi, f"{qid}: {k} = {v} outside {lo}-{hi}")

    def test_cards_runs_match_the_notes(self):
        """A scenario's yearly run on the page ends on the 2035 figure its note gives."""
        page = (ROOT / "artifacts/explorer_v3/index.html").read_text()
        scen = json.loads(re.search(r"^const SCENARIOS = (\[.*\]);$", page, re.M).group(1))
        ver = json.loads((ROOT / "data/processed/scenarios_verified.json").read_text())
        names = {s["id"]: s["name"] for s in json.loads((ROOT / "data/processed/scenarios_page.json").read_text())}
        for s in scen:
            self.assertIn("run", s, s["id"])
            v = ver[names[s["id"]]]
            for k in ("balance", "net_income", "fte", "cpi", "debt"):
                self.assertAlmostEqual(s["run"][k][-1], v[k]["model"], delta=abs(v[k]["model"]) * 1e-4, msg=f"{s['id']} {k}")
                self.assertAlmostEqual(s["run"]["sq_" + k][-1], v[k]["status_quo"],
                                       delta=abs(v[k]["status_quo"]) * 1e-4, msg=f"{s['id']} sq {k}")
        guide = json.loads(re.search(r"^const GUIDE_RUN = (.*);$", page, re.M).group(1))
        g = next(iter(json.loads((ROOT / "data/processed/scenarios_guide_start_verified.json").read_text()).values()))
        self.assertAlmostEqual(guide["balance"][-1], g["balance"]["model"], delta=.1)

    def test_guide_record_is_complete(self):
        x = json.loads((ROOT / "data/processed/scenarios_guide_page.json").read_text())[0]["x"]
        self.assertFalse(set(be.KEYS) - set(x))


if __name__ == "__main__":
    unittest.main()
