"""Write the guided build of the explorer: the same page and data, opening on a sequence of questions whose
answers set the levers, with an optional survey that pools everyone's answers.

    .venv/bin/python scripts/build_guided.py

Reads artifacts/explorer_v3/, writes artifacts/guided/: the page, and links to the explorer's data files. Until 2.1
the data files were copied, so every rebuild put about 60 MB into the repository twice; the site build takes them
from artifacts/explorer_v3/ in any case (scripts/vercel_build.sh), and the links serve the local preview.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC, OUT = ROOT / "artifacts/explorer_v3", ROOT / "artifacts/guided"


def main():
    page = (SRC / "index.html").read_text()
    swaps = [('const MODE = "explorer";', 'const MODE = "guided";'),
             ("<title>Borgaralaun Explorer</title>", "<title>Borgaralaun Guide</title>"),
             ]
    for old, new in swaps:
        if page.count(old) != 1:
            raise SystemExit(f"expected exactly one {old!r} in the explorer page")
        page = page.replace(old, new)
    # the heading, whatever the version it carries
    page, n = re.subn(r'<h1>Borgaralaun <span>Explorer</span> <small class="ver">[^<]*</small></h1>',
                      '<h1>Borgaralaun <span>Guide</span></h1>', page)
    if n != 1:
        raise SystemExit("expected exactly one Explorer heading with its version in the explorer page")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(page)
    for name in ("data.js", "emulator.js", "emulator_k.js", "emulator_k2.js", "emulator_k3.js", "emulator_pay.js", "births.js", "past.js", "timeline.js", "past_grid.js"):
        if (SRC / name).exists():
            dst = OUT / name
            if dst.is_symlink() or dst.exists():
                dst.unlink()
            dst.symlink_to(pathlib.Path("../explorer_v3") / name)
    print(f"wrote {OUT / 'index.html'} and its data")


if __name__ == "__main__":
    main()
