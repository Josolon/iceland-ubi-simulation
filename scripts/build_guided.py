"""Write the guided build of the explorer: the same page and data, opening on a sequence of questions whose
answers set the levers, with an optional survey that pools everyone's answers.

    .venv/bin/python scripts/build_guided.py

Reads artifacts/explorer_v3/, writes artifacts/guided/ (the page and a copy of the data files).
"""
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC, OUT = ROOT / "artifacts/explorer_v3", ROOT / "artifacts/guided"


def main():
    page = (SRC / "index.html").read_text()
    swaps = [('const MODE = "explorer";', 'const MODE = "guided";'),
             ("<title>Borgaralaun Explorer</title>", "<title>Borgaralaun Guide</title>"),
             ('<h1>Borgaralaun <span>Explorer</span> <small class="ver">1.0.1</small></h1>',
              '<h1>Borgaralaun <span>Guide</span></h1>'),
             ]
    for old, new in swaps:
        if page.count(old) != 1:
            raise SystemExit(f"expected exactly one {old!r} in the explorer page")
        page = page.replace(old, new)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(page)
    for name in ("data.js", "levers.js", "emulator.js", "emulator_k.js", "emulator_k2.js", "emulator_k3.js", "emulator_pay.js", "births.js", "past.js", "timeline.js", "past_grid.js"):
        if (SRC / name).exists():
            shutil.copyfile(SRC / name, OUT / name)
    print(f"wrote {OUT / 'index.html'} and its data")


if __name__ == "__main__":
    main()
