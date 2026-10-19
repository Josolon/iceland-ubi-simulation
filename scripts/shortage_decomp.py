"""Why the reform's public-service shortage is larger than the status quo's: profession moves switched off
piece by piece, same calibrated society, same world.

    .venv/bin/python scripts/shortage_decomp.py
"""
import pickle
import sys
import pathlib
from concurrent.futures import ProcessPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ubisim.abm import model  # noqa: E402
from build_explorer_data import calibrated  # noqa: E402

P = {"regime": "platform", "ubi_adult": 300_000}
CASES = [
    ("status quo", {"policy": {"regime": "status_quo"}}),
    ("status quo, no profession moves", {"policy": {"regime": "status_quo"}, "labour": {"occupation_mobility": 0.0}}),
    ("platform 300", {"policy": P}),
    ("platform, no profession moves", {"policy": P, "labour": {"occupation_mobility": 0.0}}),
    ("platform, no extra moves from security", {"policy": P, "labour": {"occupation_mobility_security": 0.0}}),
    ("platform, moves ignore pay", {"policy": P, "labour": {"occupation_pay_pull": 0.0}}),
    ("platform, moves ignore empty posts", {"policy": P, "labour": {"occupation_shortage_pull": 0.0}}),
    ("platform, no public job cut", {"policy": {**P, "public_payroll_cut": 0.0}}),
]
_BASE = None


def load(blob):
    global _BASE
    _BASE = blob


def run(case):
    name, over = case
    soc = model.scenario(pickle.loads(_BASE), over)
    rows = [soc.step() for _ in range(10)]
    r = rows[-1]
    return name, r


def main():
    blob = pickle.dumps(calibrated(1.0, recalibrate=False))
    with ProcessPoolExecutor(4, initializer=load, initargs=(blob,)) as ex:
        for name, r in ex.map(run, CASES):
            print(f"{name:42s} gap {r['essential_services_gap']:6.0f}  health {100 * r['health_service_unmet']:4.1f}%"
                  f"  teaching {100 * r['teaching_service_unmet']:4.1f}%  premium {r['public_shortage_premium']:.3f}"
                  f"  employment {r['employment_rate_16_74']:.3f}  balance {r['balance_bn']:6.1f}", flush=True)


if __name__ == "__main__":
    main()
