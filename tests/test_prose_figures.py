"""Figures written into the text, checked against what they describe.

    .venv/bin/python -m unittest tests.test_prose_figures

The pages, the lever notes and the README state some of the model's results in words: the status quo's
inflation, the surface's error, the reference reform's 2035 figures. Nothing tied those words to the numbers, so a
rebuild could leave them stale, and three were found wrong before 2.1.0. Each check here finds the figure where the
text states it and recomputes it from the file it comes from. A figure must be right to the precision it is written
at: "265" must lie within half a unit of the value, "2.6" within 0.05.

Facts quoted from outside sources (the public wage bill in 2025, farm support in 2024) are not checked: they change
only when the sources do. When a check fails, correct the text, or, if the text's figure is the right one, find out
why the data moved.
"""
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from ubisim.abm import params as P  # noqa: E402

PAGE = (ROOT / "artifacts/explorer_v3/index.html").read_text()
README = (ROOT / "README.md").read_text()
VALIDATION = (ROOT / "docs/VALIDATION.md").read_text()


def js_object(path):
    s = (ROOT / path).read_text()
    return json.loads(s[s.find("{"):s.rfind("}") + 1])


EMU = js_object("artifacts/explorer_v3/emulator.js")
DATA = js_object("artifacts/explorer_v3/data.js")
VER = json.loads((ROOT / "data/processed/scenarios_verified.json").read_text())
GUIDE_VER = json.loads((ROOT / "data/processed/scenarios_guide_start_verified.json").read_text())
REF = VER["300 þús., reference reform"]
NOTES = {lv["key"]: lv["note"] for lv in EMU["meta"]["levers"]}
PAR = P.DEFAULTS


def number(text):
    return float(text.replace(",", "").replace("−", "-").replace("+", ""))


def flat(text):
    return re.sub(r"\s+", " ", text)


class Figures(unittest.TestCase):
    def near(self, quoted, value, where):
        """`quoted` as written; right if the value rounds to it at the precision it is written at."""
        q = number(quoted)
        d = len(quoted.split(".")[1]) if "." in quoted else 0
        self.assertLessEqual(abs(q - value), .5 * 10 ** -d + 1e-9,
                             f"{where} says {quoted}; the data give {value:,.{d + 2}f}")

    def find(self, text, pattern, where, count=None):
        found = re.findall(pattern, flat(text))
        self.assertTrue(found, f"{where}: no text matches {pattern!r}; the sentence was rewritten, so move the check")
        if count is not None:
            self.assertEqual(len(found), count, f"{where}: {pattern!r} found {len(found)} times, expected {count}")
        return found

    # ---------------------------------------------------------------- the surface (page intro and footer)
    def test_surface_run_count(self):
        for runs in self.find(PAGE, r"fitted to ([\d,]+) (?:of its runs|runs of the model)", "page", 2):
            self.assertEqual(round(EMU["meta"]["draws"], -2), number(runs), f"page says {runs} runs")

    def test_surface_held_out_error(self):
        sets, err = self.find(PAGE, r"On ([\d,]+) sets of Guide answers kept out of the fit, its 2035 budget misses "
                                    r"the model's by ([\d,]+) ma\.kr\.", "page footer", 1)[0]
        self.assertEqual(EMU["meta"]["holdout"]["runs"], number(sets))
        self.near(err, EMU["meta"]["difference_error_2035"], "page footer")

    def test_surface_at_the_scenarios(self):
        gaps = [v["balance"]["surface"] - v["balance"]["model"] for v in VER.values()]
        for where, text in (("page footer", PAGE), ("docs/VALIDATION.md", VALIDATION)):
            lo, hi, avg = self.find(text, r"between (\d+) below and (\d+) above the model, (\d+) on average", where, 1)[0]
            self.near(lo, -min(gaps), where)
            self.near(hi, max(gaps), where)
            self.near(avg, sum(map(abs, gaps)) / len(gaps), where)

    def test_profession_count(self):
        n = self.find(PAGE, r"([\d,]+) professions, one year at a time", "page intro", 1)[0]
        self.assertEqual(len(DATA["meta"]["professions"]), number(n))

    # ---------------------------------------------------------------- the status quo
    def test_status_quo_inflation_to_2030(self):
        cpi = EMU["status_quo"]["cpi"]
        years = EMU["meta"]["year_list"]
        upto = years.index(2030) + 1
        infl = [100 * (c / p - 1) for c, p in zip(cpi[:upto], [1.0] + cpi[:upto - 1])]
        for lo, hi in self.find(PAGE, r"the model (?:still )?has prices rising (\d+\.\d)-(\d+\.\d)% a year to 2030",
                                "page"):
            self.near(lo, min(infl), "page")
            self.near(hi, max(infl), "page")

    # ---------------------------------------------------------------- lever notes and labels
    def test_free_health_care(self):
        fs = PAR["free_services"]
        part, whole = self.find(NOTES["free_health"], r"about (\d+) of the (\d+) ma\.kr\.", "free_health note", 1)[0]
        self.near(part, fs["health_service_copay_bn"], "free_health note")
        self.near(whole, fs["health_out_of_pocket_bn"], "free_health note")
        label = self.find(PAGE, r"free_health: v => .*?of the (\d+) ma\.kr\. in fees", "free_health slider label", 1)[0]
        self.near(label, fs["health_service_copay_bn"], "free_health slider label")

    def test_free_internet(self):
        cost = self.find(NOTES["free_internet"], r"about (\d+) ma\.kr\. a year", "free_internet note", 1)[0]
        self.near(cost, PAR["free_services"]["internet_state_cost_bn"], "free_internet note")

    # ---------------------------------------------------------------- the README's results
    def test_readme_table(self):
        rows = {"Public balance, ma.kr. a year": ("balance", 1),
                "Net public debt, % of GDP": ("debt", 1),
                "Household income after tax and transfers, þús. a month": ("net_income", 1e-3),
                "Work per adult, full-time equivalents": ("fte", 1),
                "Unemployment": ("unemp", 100),
                "Price level, 2025 = 1": ("cpi", 1),
                "Child poverty": ("child_poverty", 100),
                "Poverty against a fixed 2025 line": ("poverty_anchored", 100),
                "Essential public services short, full-time posts": ("essential_gap", 1)}
        for label, (key, scale) in rows.items():
            reform, sq = self.find(README, re.escape(f"| {label} | ") + r"([−\d.,]+)%? \| ([−\d.,]+)%? \|",
                                   f"README table, {label}", 1)[0]
            self.near(reform, scale * REF[key]["model"], f"README table, {label}, reform")
            self.near(sq, scale * REF[key]["status_quo"], f"README table, {label}, status quo")

    def test_readme_text(self):
        sd = self.find(README, r"the budget's spread between them is ±(\d+) ma\.kr\.", "README", 1)[0]
        self.near(sd, REF["balance"]["sd_vs_status_quo"], "README, spread between runs")
        # the named scenarios at 250 and 300 þús. in the page's own world, other than the reference reform
        same_world = [v["balance"]["model"] for n, v in VER.items()
                      if n.startswith(("250", "300")) and "reference" not in n
                      and v["balance"]["status_quo"] == REF["balance"]["status_quo"]]
        lo, hi = self.find(README, r"named scenarios come to ([+−]\d+) to ([+−]\d+) in 2035", "README", 1)[0]
        self.near(lo, min(same_world), "README, scenarios that keep up")
        self.near(hi, max(same_world), "README, scenarios that keep up")
        gs = self.find(README, r"Guide's start, at \d+ þús\., to ([+−]\d+)", "README", 1)[0]
        self.near(gs, next(iter(GUIDE_VER.values()))["balance"]["model"], "README, the Guide's start")
        work, prices = self.find(README, r"Work per adult is about (\d+)% lower and the price level about (\d+)% higher",
                                 "README", 1)[0]
        self.near(work, -100 * (REF["fte"]["model"] / REF["fte"]["status_quo"] - 1), "README, work")
        self.near(prices, 100 * (REF["cpi"]["model"] / REF["cpi"]["status_quo"] - 1), "README, prices")
        posts, sq_posts = self.find(README, r"about ([\d,]+) posts against ([\d,]+)\)", "README", 1)[0]
        # "about 1,400": right to the hundred; "1,260": to the ten
        self.assertLessEqual(abs(number(posts) - REF["essential_gap"]["model"]), 50, "README, posts short")
        self.assertLessEqual(abs(number(sq_posts) - REF["essential_gap"]["status_quo"]), 5, "README, posts short (sq)")


if __name__ == "__main__":
    unittest.main()
