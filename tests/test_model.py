"""Faults found in the 2.1 assessment, kept found. Runs a few years from the calibrated base.

    .venv/bin/python -m unittest discover tests
"""
import pathlib
import pickle
import sys
import unittest

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from ubisim.abm import model  # noqa: E402
from ubisim.abm.population import FULL, PART  # noqa: E402

PICKLE = ROOT / "data/processed/calibrated_spirit1.pkl"


@unittest.skipUnless(PICKLE.exists(), "needs a calibrated base")
class StatusQuo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.soc = model.scenario(pickle.loads(PICKLE.read_bytes()), {})
        cls.rows = [cls.soc.step() for _ in range(4)]

    def adults(self):
        A = self.soc.A
        return A, A["alive"] & (A["age"] >= 18)

    def test_arrivals_do_not_arrive_disabled(self):
        A, adult = self.adults()
        just_in = adult & (A["origin_year"] == self.soc.year) & (A["age"] > 25)
        if just_in.sum() > 50:
            self.assertLess(A["disabled"][just_in].mean(), .02)

    def test_self_employment_holds(self):
        A = self.soc.A
        working = A["alive"] & np.isin(A["status"], [PART, FULL])
        self.assertGreater(A["self_employed"][working].mean(), .05)

    def test_savings_move_into_other_assets(self):
        A, adult = self.adults()
        self.assertGreater(A["other_assets"][adult].sum(), 0)

    def test_new_measures_are_reported(self):
        last = self.rows[-1]
        for k in ("poverty_after_housing", "child_poverty_anchored", "lost_over_5", "lost_over_10", "gained_over_5",
                  "poverty_women", "poverty_men", "poverty_foreign", "poverty_native"):
            self.assertTrue(np.isfinite(last[k]), k)
            self.assertTrue(0 <= last[k] <= 1, k)

    def test_exported_payments_are_small_and_positive(self):
        self.assertGreater(self.soc.exported_payments(), 0)
        self.assertLess(self.soc.exported_payments(), 30)


if __name__ == "__main__":
    unittest.main()
