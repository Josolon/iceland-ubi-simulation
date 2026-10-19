"""The three-way shortage, needs-driven social staffing, the leave scheme and the second status quo, in one run.

    .venv/bin/python scripts/new_features_check.py

Each is switched off and on against the same calibrated society, so what is read is the feature's own effect.
"""
import pickle
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ubisim.abm import model  # noqa: E402
from build_explorer_data import calibrated  # noqa: E402

PLATFORM = {"regime": "platform", "ubi_adult": 300_000}


def run(base, over, years=10):
    soc = model.scenario(pickle.loads(base), over)
    rows = [soc.step() for _ in range(years)]
    return rows[-1]


def line(tag, r):
    print(f"{tag:42s} gap {r['essential_services_gap']:7.0f}  unmet {100 * r['essential_service_unmet']:5.1f}%"
          f"  load {r['essential_workload']:.3f}  premium {r['public_shortage_premium']:.3f}"
          f"  distress {r['social_distress_index']:.3f}  leave saved {r['acc_leave_saved']:6.1f}"
          f"  balance {r['balance_bn']:7.1f}  cpi {r['cpi']:.3f}  employment {r['employment_rate_16_74']:.3f}", flush=True)


def main():
    base = pickle.dumps(calibrated(1.0, recalibrate=False))
    line("status quo", run(base, {"policy": {"regime": "status_quo"}}))
    line("status quo, world as the last decade", run(base, {"policy": {"regime": "status_quo"},
                                                            "markets": {"history_like": 1.0}}))
    line("platform 300", run(base, {"policy": PLATFORM}))
    line("platform 300, leave to employers", run(base, {"policy": {**PLATFORM, "state_leave_ended": 1.0}}))
    line("platform 300, leave + world as last decade", run(base, {"policy": {**PLATFORM, "state_leave_ended": 1.0},
                                                                  "markets": {"history_like": 1.0}}))
    line("platform 300, no workload feedback", run(base, {"policy": PLATFORM,
                                                          "labour": {"workload_disamenity": 0.0}}))
    line("platform 300, staffing ignores need", run(base, {"policy": PLATFORM, "labour": {
        "social_need_share": {"Clerks": 0.0, "Other associate professionals": 0.0, "Other professionals": 0.0,
                              "Lawyers": 0.0, "Managers": 0.0}}}))
    line("platform 300, no shortage premium", run(base, {"policy": PLATFORM,
                                                         "labour": {"public_shortage_pay_speed": 0.0}}))


if __name__ == "__main__":
    main()
