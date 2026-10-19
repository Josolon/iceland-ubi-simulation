"""Who draws which benefit in the status quo, and what it costs — to check against Tryggingastofnun, the
Unemployment Insurance Fund and the municipalities.

    .venv/bin/python scripts/benefit_recipients.py

Prints recipients and yearly cost (ma.kr., 2025 krónur) of the old-age pension, the disability pension and the
prime-age support that stands in for unemployment benefit and municipal assistance, with the support split by
who receives it: those looking for work, students, and everyone else out of work.
"""
import pickle
import sys
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ubisim.abm import model  # noqa: E402
from build_explorer_data import calibrated  # noqa: E402


def main():
    soc = model.scenario(pickle.loads(pickle.dumps(calibrated(1.0, recalibrate=False))),
                         {"policy": {"regime": "status_quo"}})
    soc.step()
    A, p = soc.A, soc.p
    idx = np.flatnonzero(A["alive"] & (A["age"] >= 18))
    gross = soc.current_gross(idx)
    working = np.isin(A["status"][idx], [model.PART, model.FULL])
    partner = A["partner"][idx]
    pinc = np.where(partner >= 0, soc.current_gross(np.where(partner >= 0, partner, 0)), 0.0)
    ben, bx = p["benefits"], soc.benefit_index(soc.price)
    age, dis = A["age"][idx], A["disabled"][idx]
    retired = age >= 67
    occ_pen = A["occ_pension"][idx] * soc.price
    tr = np.where(retired, np.maximum(0, ben["tr_old_age_full"] * bx - ben["tr_clawback"] * (
        np.maximum(0, occ_pen - ben["tr_general_exemption"] * bx) + np.maximum(0, gross - ben["tr_work_exemption"] * bx))), 0)
    dp = np.where(dis & ~retired, np.maximum(0, ben["disability_pension"] * bx - ben["tr_clawback"] * np.maximum(
        0, gross - ben["disability_work_exemption"] * bx)), 0)
    prime = ~working & ~retired & ~dis & (age >= 20)
    sup = np.where(prime & (pinc < ben["nonwork_support_partner_cutoff"] * bx), ben["nonwork_support"] * bx, 0)
    yr = lambda v: float(v.sum() * 12 / soc.price / 1e9)
    print(f"{'benefit':38s} {'recipients':>10s} {'ma.kr./yr':>10s}")
    print(f"{'old-age pension (TR)':38s} {(tr > 0).sum():10,d} {yr(tr):10.1f}")
    print(f"{'disability pension':38s} {(dp > 0).sum():10,d} {yr(dp):10.1f}")
    studying = A["studying"][idx] > 0
    looking = A["involuntary"][idx]
    for name, m in [("support: looking for work", (sup > 0) & looking),
                    ("support: students", (sup > 0) & studying & ~looking),
                    ("support: others out of work", (sup > 0) & ~studying & ~looking)]:
        print(f"{name:38s} {m.sum():10,d} {yr(sup * m):10.1f}")
    print(f"{'support, all':38s} {(sup > 0).sum():10,d} {yr(sup):10.1f}")


if __name__ == "__main__":
    main()
