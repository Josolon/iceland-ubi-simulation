"""2.0: hours within a job — how much of a full or part-time week people work, and how a reform moves it.

The choice of status (out of work, part time at 55%, full time, a firm, independent work) is the large margin and
is made in the choice model. Within a job people can also shorten or lengthen their week a little: a four-day week,
a shorter day, more or less overtime. That margin is this part.

What moves it. Two things, each set against the person under today's rules at the same pay. What is left of a
little more pay after tax, contributions and withdrawn benefits (1 - the marginal rate): hours rise with it with the
compensated elasticity `elasticity` (EST 0.15: Chetty 2012 bounds the intensive elasticity from micro studies at
0.33 once frictions are allowed for, and observed responses are smaller since most jobs fix hours). And income that
does not depend on hours, which buys time off: hours fall by `income_effect` for each unit of extra income after tax
as a share of income today (EST 0.04). In the trial of Vivalt, Rhodes, Bartik, Broockman, Krause and Miller (NBER
w32719) $1,000 a month, some 40% of income, cut hours by 1.3 a week, mostly through people leaving work
(participation fell 2-4 points), which the choice model carries; within the job that leaves at most about 2%.

How fast. Hours move a share `speed` of the way to their target in a year (EST): a change of week needs the
employer's consent or a new contract. They stay within `lowest` and `highest` of the standard week.

The status quo is its own reference and nothing in it moves. Not modelled: hours of founders and independent work,
which have no employer and are set apart, and hours set by collective agreements (`policy.full_time_hours_factor`,
the four-day-week lever), which multiplies these.
"""
import numpy as np

from ubisim.abm import informal
from ubisim.abm import policy as pol_rules
from ubisim.abm.population import FULL, PART


def ensure(A):
    if "hours_scale" not in A:
        A["hours_scale"] = np.ones(len(A["alive"]), np.float32)
    return A["hours_scale"]


def factor(soc, who):
    """Each person's week against the standard one: 1 in the status quo."""
    if soc.p["policy"]["regime"] != "platform" or "hours_scale" not in soc.A:
        return 1.0
    return soc.A["hours_scale"][who]


def update(soc):
    """A year's move towards the hours each worker would choose, from the reform's rates and income against today's."""
    c = soc.p.get("hours") or {}
    if not c or soc.p["policy"]["regime"] != "platform":
        return
    A, p = soc.A, soc.p
    h = ensure(A)
    j = np.flatnonzero(A["alive"] & (A["age"] >= 16) & np.isin(A["status"], [PART, FULL]))
    if not len(j):
        return
    gross = soc.current_gross(j)
    on = gross > 0
    j, g = j[on], gross[on]
    working = np.ones(len(j), bool)
    partner = A["partner"][j]
    pinc = np.where(partner >= 0, soc.net_now[np.where(partner >= 0, partner, 0)], 0)
    bx = soc.benefit_index()
    sq = {**p, "policy": {**p["policy"], "regime": "status_quo"}}
    m_now = informal._marginal(A, j, g, working, p, pinc, soc.price, bx)
    m_sq = informal._marginal(A, j, g, working, sq, pinc, soc.price, bx)
    net_now = pol_rules.net_income(A, j, g, working, p, pinc, soc.price, bx)["net"]
    net_sq = pol_rules.net_income(A, j, g, working, sq, pinc, soc.price, bx)["net"]
    keep = np.maximum(1 - m_now, .05) / np.maximum(1 - m_sq, .05)
    richer = (net_now - net_sq) / np.maximum(net_sq, .2 * g)
    target = np.clip(keep ** c["elasticity"] * (1 - c["income_effect"] * richer), c["lowest"], c["highest"])
    h[j] = h[j] + c["speed"] * (target - h[j])


def snapshot(soc):
    A = soc.A
    if "hours_scale" not in A or soc.p["policy"]["regime"] != "platform":
        return {"hours_within_job": 1.0}
    w = A["alive"] & np.isin(A["status"], [PART, FULL])
    return {"hours_within_job": float(A["hours_scale"][w].mean()) if w.any() else 1.0}
