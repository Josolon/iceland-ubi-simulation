"""Which model made each file the pages read, and the gate on it.

    .venv/bin/python scripts/build_stamp.py record artifacts/explorer_v3/data.js ...   # after a builder has run
    .venv/bin/python scripts/build_stamp.py check                                      # exits non-zero if any is stale
    .venv/bin/python scripts/build_stamp.py done STEP / mark STEP                      # scripts/rebuild_all.sh's steps

data.js went a release and a half behind the rest of the page because nothing said it had to be rebuilt. Each file is
recorded with the fingerprint of the model code and parameters that made it (build_explorer_data.params_fingerprint)
and a hash of its contents, so that the gate fails on a file left over from an earlier model and on a file changed
by hand since it was built.
"""
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from build_explorer_data import params_fingerprint  # noqa: E402

STAMPS = ROOT / "data/processed/build_stamps.json"
STEPS = ROOT / "data/processed/build_steps.json"
PAGES = ["artifacts/explorer_v3/index.html", *[f"artifacts/explorer_v3/{n}" for n in (
    "data.js", "emulator.js", "emulator_k.js", "emulator_k2.js", "emulator_k3.js", "emulator_pay.js", "births.js",
    "past.js", "past_grid.js", "timeline.js")]]
GUIDED = [p.replace("explorer_v3", "guided") for p in PAGES]


def digest(path):
    h = hashlib.sha1()
    with open(ROOT / path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


def load(path):
    return json.loads(path.read_text()) if path.exists() else {}


def record(paths):
    stamps = load(STAMPS)
    for p in paths:
        stamps[p] = {"model": params_fingerprint(), "sha": digest(p)}
    STAMPS.write_text(json.dumps(stamps, indent=1, sort_keys=True) + "\n")


def stale():
    stamps, now, bad = load(STAMPS), params_fingerprint(), []
    for p in PAGES + GUIDED:
        s = stamps.get(p)
        if not (ROOT / p).exists():
            bad.append(f"{p}: missing")
        elif not s:
            bad.append(f"{p}: no record of what built it")
        elif s["model"] != now:
            bad.append(f"{p}: built by model {s['model']}, the model is now {now}")
        elif s["sha"] != digest(p):
            bad.append(f"{p}: changed since it was built")
    return bad


def main():
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "record":
        record(args)
    elif cmd == "check":
        bad = stale()
        print("\n".join(bad) if bad else f"all {len(PAGES + GUIDED)} page files are from model {params_fingerprint()}")
        sys.exit(1 if bad else 0)
    elif cmd == "done":
        sys.exit(0 if load(STEPS).get(args[0]) == params_fingerprint() else 1)
    elif cmd == "mark":
        steps = load(STEPS)
        steps[args[0]] = params_fingerprint()
        STEPS.write_text(json.dumps(steps, indent=1) + "\n")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
