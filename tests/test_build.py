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

    def test_guide_record_is_complete(self):
        x = json.loads((ROOT / "data/processed/scenarios_guide_page.json").read_text())[0]["x"]
        self.assertFalse(set(be.KEYS) - set(x))


if __name__ == "__main__":
    unittest.main()
