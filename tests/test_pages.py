"""Both pages in a headless browser: they load without a script error, every example scenario's budget card shows the
model's own 2035 figure, every tab renders, and the tabs whose runs load on demand get them.

    .venv/bin/python -m unittest tests.test_pages

Needs Playwright (`pip install -r requirements-dev.txt`) and a browser: the installed Chrome if there is one,
otherwise Playwright's own Chromium (`python -m playwright install chromium`). Skipped without Playwright, so the rest
of the suite runs anywhere.
"""
import functools
import http.server
import json
import math
import pathlib
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


def card_text(v):
    """The budget card's number as the page writes it (nf: rounded, en thousands separators, ASCII minus)."""
    return f"{math.floor(abs(v) + .5) * (1 if v >= 0 else -1):,}"


@unittest.skipIf(sync_playwright is None, "needs Playwright")
class Pages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass
        handler = functools.partial(Quiet, directory=str(ROOT / "artifacts"))
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch(channel="chrome")
        except Exception:
            cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()

    def open(self, path):
        page = self.browser.new_page(viewport={"width": 1280, "height": 900})
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(f"script error: {e}"))
        page.on("console", lambda m: m.type == "error" and self.errors.append(f"console: {m.text}"))
        page.goto(f"{self.base}/{path}")
        # the cards appear once the surface's kernel weights are in
        page.wait_for_function("() => /\\d/.test(document.querySelector('.vcard .n')?.textContent || '')",
                               timeout=120_000)
        self.addCleanup(page.close)
        return page

    def no_errors(self):
        self.assertEqual(self.errors, [], "\n".join(self.errors))

    def press(self, page, sel):
        """Clicks through the DOM, so a button inside a closed group still counts."""
        page.eval_on_selector(sel, "b => b.click()")

    def budget(self, page):
        return page.locator(".vcard .n").first.inner_text().strip()

    def test_explorer_presets_show_the_models_own_figures(self):
        page = self.open("explorer_v3/index.html")
        ver = json.loads((ROOT / "data/processed/scenarios_verified.json").read_text())
        names = {s["id"]: s["name"] for s in json.loads((ROOT / "data/processed/scenarios_page.json").read_text())}
        ids = page.eval_on_selector_all("[data-preset]", "bs => bs.map(b => b.dataset.preset)")
        scen = [i for i in ids if i in names]
        self.assertEqual(len(scen), len(names), "a published scenario has no button")
        for sid in scen:
            self.press(page, f'[data-preset="{sid}"]')
            want = card_text(ver[names[sid]]["balance"]["model"])
            self.assertEqual(self.budget(page), want, f"{sid}: the budget card is not the model's own 2035 figure")
            self.assertIn("the model's own result", page.locator(".vcard .band").first.inner_text())
        # one lever moved: the surface again, with its band
        page.eval_on_selector("#lev-ubi", "e => { e.value = String(+e.value - 30); "
                                          "e.dispatchEvent(new Event('input', {bubbles: true})); "
                                          "e.dispatchEvent(new Event('change', {bubbles: true})); }")
        self.assertIn("likely within", page.locator(".vcard .band").first.inner_text())
        self.no_errors()

    def test_explorer_tabs_render(self):
        page = self.open("explorer_v3/index.html")
        tabs = page.eval_on_selector_all("[data-tab]", "bs => bs.map(b => b.dataset.tab)")
        self.assertGreater(len(tabs), 5)
        for tab in tabs:
            self.press(page, f'[data-tab="{tab}"]')
            page.wait_for_selector(".panel h2")
        # the long view's runs load on demand, the first time its tab opens
        self.press(page, '[data-tab="timeline"]')
        page.wait_for_function("() => !!window.UBI_TIMELINE", timeout=60_000)
        page.wait_for_selector(".tl-fig svg", timeout=30_000)
        self.press(page, '[data-tab="past"]')
        page.wait_for_function("() => !!window.UBI_PAST_GRID", timeout=60_000)
        self.no_errors()

    def test_long_view_not_loaded_until_asked(self):
        for path in ("explorer_v3/index.html", "guided/index.html"):
            page = self.open(path)
            page.wait_for_timeout(1500)
            for g in ("UBI_TIMELINE", "UBI_PAST_GRID"):
                self.assertFalse(page.evaluate(f"() => !!window.{g}"), f"{path}: {g} loaded before its tab opened")
            self.no_errors()

    def test_guide(self):
        page = self.open("guided/index.html")
        self.assertIn("Question 1 of 35", page.inner_text("body"))
        self.press(page, '[data-gs="preset"]')
        g = next(iter(json.loads((ROOT / "data/processed/scenarios_guide_start_verified.json").read_text()).values()))
        page.wait_for_function(f"() => document.querySelector('.vcard .n')?.textContent.trim() === "
                               f"{json.dumps(card_text(g['balance']['model']))}", timeout=10_000)
        self.no_errors()


if __name__ == "__main__":
    unittest.main()
