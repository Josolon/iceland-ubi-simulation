"""Scenarios that fund a borgaralaun without a deficit, changing as little as possible.

    .venv/bin/python scripts/scenarios.py

For each scenario: some levers are fixed (the choices that define it), the financing levers are free within caps,
and the search finds the least disruptive combination that keeps the budget out of deficit from the second year
on. Disruption is the weighted distance of each lever from where it is today — broad taxes everyone pays weigh
most, targeted revenue least — plus penalties for prices, unemployment, the poorest tenth and essential services.

The search runs on the explorer's fitted surface (scripts/surrogate.py); the chosen settings are candidates to be
checked in the model itself. Writes data/processed/scenarios.json.
"""
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from surrogate import Surface  # noqa: E402

OUT = ROOT / "data/processed/scenarios.json"

WORLD = {"tourism_price": 97, "marine_price": 100, "aluminium_price": 108, "import_price": 101}
# what every standard scenario holds: the reference reform's fixed settings
STANDARD_FIXED = {
    **WORLD, "ai": 5, "child_invested": 50, "public_offset": 100, "retraining": 15, "housing": 1000,
    "childcare": 2000, "governance": 0, "church": 0, "culture": 0, "custodianship": 0, "smelters": 0,
    "free_health": 0, "free_internet": 0, "ubi_protected": 100, "gambling_block": 100, "agreements": 0,
"sub_innovation": 0, "minimum_wage": 0, "hours": 100, "taper": 0, "indexation": 0,
    "fund": 0, "fx": 0, "frontier": 0, "infrastructure": 0, "resi_cap": 100, "comm_cap": 100,
    "sick_pay": 0, "prison_ubi": 60, "residence": 50, "capital_controls": 50,
    # v3: leave carried by employers and insurers, the world at the forecasts, the reform's own settings
    "leave_scheme": 100, "leave_top_up": 0, "history_world": 0, "venture_stake": 50, "teen_moveout": 5,
    "green_heat": .5, "agri_startups": 1.5, "free_health": 0, "free_internet": 0,
    # the tax-free part of an estate at the value of a family apartment, so heirs keep the family home
    "inherit_floor": 75,
}
# free levers: (weight, standard cap as (lo, hi) in lever units, or None for the lever's full range)
FREE = {
    "income_tax": (3.0, (90, 110)), "personal_credit": (3.0, (36, 72.5)), "vat": (3.0, (15, 25)),
    "pension_fold": (2.0, None), "prop_tax": (2.0, (0, 50)), "corporate_tax": (2.0, (15, 25)),
    "wealth_tax": (2.0, (0, 50)), "inherit_rate": (1.5, (5, 30)),
    "gift_tax": (.5, None), "exit_tax": (.5, (0, 30)), "fish_rent": (1.0, (24, 50)),
    "vat_input": (1.5, (0, 150)), "customs": (1.0, None), "agri_cut": (1.5, (0, 50)),
    # other subsidies include culture, sport and private media (5.7 of 15.9 ma.kr.), which the standard view keeps
    "sub_heating": (2.0, (0, 50)), "sub_transition": (1.5, None), "sub_transport": (2.0, (0, 50)),
    "sub_other": (1.0, (0, 64)), "per_diem": (.5, None), "enforcement": (.3, None),
    "clawback": (1.0, (0, 20)), "payroll_cut": (3.0, (0, 10)),
}


def build_space(s, fixed, caps=True):
    free = [k for k in FREE if k not in fixed]
    lo = np.array([s.to_x(k, FREE[k][1][0]) if caps and FREE[k][1] else 0.0 for k in free])
    hi = np.array([s.to_x(k, FREE[k][1][1]) if caps and FREE[k][1] else 1.0 for k in free])
    lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)
    w = np.array([FREE[k][0] for k in free])
    today = np.array([s.levers[s.idx[k]]["today"] for k in free], float)
    return free, lo, hi, w, today


# The status quo a scenario is held to. Normally the one in the scenario's own world. For the optimistic scenarios
# the windfall or the robots are what pays for the larger payment, so they are held to today's world: the budget
# must do as well as the status quo would do without the windfall (set by `search(..., sq_world=...)`).
SQ_WORLD = {}
# What a scenario is judged by besides the budget. "jobs": unemployment above the status quo's is a cost. "living":
# for the optimistic routes, where a large payment makes being out of work matter far less,
# what counts is whether people live well — wellbeing, hardship and the poorest — and unemployment is only reported.
JUDGE = "jobs"


def evaluate(s, X, ubi):
    keys = ["balance", "cpi", "unemp", "net_d1", "essential_gap", "net_income", "debt", "fte", "wellbeing", "hardship"]
    out = s.eval(X, keys)
    sq = s.status_quo(X, keys)
    if SQ_WORLD:
        # only the budget is held to today's world; prices, jobs and the poorest are set against a status quo that
        # shares the route's world — its fast AI included — so the payment is not charged with what AI does
        Xs = X.copy()
        for k, v in SQ_WORLD.items():
            Xs[:, s.idx[k]] = s.to_x(k, v)
        today = s.status_quo(Xs, ["balance", "debt"])
        sq = {**sq, "balance": today["balance"], "debt": today["debt"]}
    return out, sq


SLACK = 25   # ma.kr.: how far one year may fall behind the status quo's balance


def score(s, X, free, w, today, ubi):
    out, sq = evaluate(s, X, ubi)
    idx = [s.idx[k] for k in free]
    move = ((X[:, idx] - today) ** 2 * w).sum(1)
    y = 9
    # Against the status quo, not against zero: over 2027-35 the reform must do at least as
    # well in total — debt no higher by 2035 — and fall no more than SLACK behind it in any one year.
    gap_y = sq["balance"][:, 1:10] - out["balance"][:, 1:10]     # 2027-35; the surface goes on to 2060
    deficit = np.clip(gap_y.sum(1), 0, None) + np.clip(gap_y - SLACK, 0, None).sum(1)
    prices = np.clip(out["cpi"][:, y] / sq["cpi"][:, y] - 1.05, 0, None)
    unemp = np.clip(out["unemp"][:, y] - sq["unemp"][:, y] - .005, 0, None)
    poor = np.clip(1 - out["net_d1"][:, y] / sq["net_d1"][:, y], 0, None)
    gap = np.clip(out["essential_gap"][:, y] - sq["essential_gap"][:, y] - 1000, 0, None)
    if JUDGE == "living":
        well = np.clip(1 - out["wellbeing"][:, y] / sq["wellbeing"][:, y], 0, None)
        hard = np.clip(out["hardship"][:, y] - sq["hardship"][:, y] - .005, 0, None)
        people = (well * 50) ** 2 + (hard * 100) ** 2
    else:
        people = (unemp * 100) ** 2
    J = move + (deficit / 50) ** 2 * 10 + (prices * 20) ** 2 + people + (poor * 20) ** 2 + (gap / 1000) ** 2
    return J, deficit, out, sq


def search(s, name, ubi, fixed, caps=True, n=60000, seed=0, weights=None, sq_world=None, quiet=False):
    global SQ_WORLD
    SQ_WORLD = sq_world or {}
    rng = np.random.default_rng(seed)
    base = s.x_from({**fixed, "ubi": ubi})
    free, lo, hi, w, today = build_space(s, fixed, caps)
    if weights:   # a financing mix: cheaper to move some levers than others
        w = w * np.array([weights.get(k, 1.0) for k in free])
    idx = [s.idx[k] for k in free]

    def batch(U):
        X = np.tile(base, (len(U), 1))
        X[:, idx] = U
        return X
    best, bestJ = None, np.inf
    for chunk in range(n // 5000):
        U = lo + rng.random((5000, len(free))) * (hi - lo)
        J, _, _, _ = score(s, batch(U), free, w, today, ubi)
        i = int(np.argmin(J))
        if J[i] < bestJ:
            best, bestJ = U[i], float(J[i])
    for step in (.15, .08, .04, .02, .01):
        for _ in range(4):
            U = np.clip(best + rng.normal(0, step, (5000, len(free))) * (hi - lo), lo, hi)
            J, _, _, _ = score(s, batch(U), free, w, today, ubi)
            i = int(np.argmin(J))
            if J[i] < bestJ:
                best, bestJ = U[i], float(J[i])
    X = batch(best[None, :])
    J, deficit, out, sq = score(s, X, free, w, today, ubi)
    levels = {k: round(float(s.level(k, X[0, s.idx[k]])), 2) for k in free}
    moved = {k: v for k, v in levels.items()
             if abs(X[0, s.idx[k]] - s.levers[s.idx[k]]["today"]) > .02}
    res = {"name": name, "ubi": ubi, "fixed": fixed, "caps": caps, "levels": levels, "moved": moved,
           "x": X[0].tolist(), "disruption": float(J[0]), "deficit_after_year1": float(deficit[0]),
           "balance": out["balance"][0, :10].round(0).tolist(), "debt_2035": float(out["debt"][0, 9]),
           "income_vs_sq": float(out["net_income"][0, 9] / sq["net_income"][0, 9] - 1),
           "poorest_vs_sq": float(out["net_d1"][0, 9] / sq["net_d1"][0, 9] - 1),
           "prices_vs_sq": float(out["cpi"][0, 9] / sq["cpi"][0, 9] - 1),
           "unemployment": float(out["unemp"][0, 9]), "unemployment_sq": float(sq["unemp"][0, 9]),
           "work_vs_sq": float(out["fte"][0, 9] / sq["fte"][0, 9] - 1),
           "essential_gap": float(out["essential_gap"][0, 9]),
           "wellbeing_vs_sq": float(out["wellbeing"][0, 9] / sq["wellbeing"][0, 9] - 1),
           "hardship": float(out["hardship"][0, 9]), "hardship_sq": float(sq["hardship"][0, 9])}
    res["balance_sq"] = sq["balance"][0, :10].round(0).tolist()
    res["vs_sq_2027_35"] = float((out["balance"][0, 1:10] - sq["balance"][0, 1:10]).sum())
    res["sq_world"] = dict(SQ_WORLD)
    SQ_WORLD = {}
    if quiet:
        return res
    ok = f"{res['vs_sq_2027_35']:+.0f} ma.kr. against the status quo over 2027-35"
    print(f"\n{name}: {ubi} þús. — {ok}; disruption {res['disruption']:.2f}")
    print(f"  balance by year: {res['balance']}")
    print(f"  2035: income {100 * res['income_vs_sq']:+.1f}%, poorest tenth {100 * res['poorest_vs_sq']:+.1f}%, "
          f"prices {100 * res['prices_vs_sq']:+.1f}%, unemployment {100 * res['unemployment']:.1f}% "
          f"(sq {100 * res['unemployment_sq']:.1f}%), work {100 * res['work_vs_sq']:+.1f}%, debt {res['debt_2035']:.0f}%")
    print("  moved: " + ", ".join(f"{k} {v}" for k, v in moved.items()))
    return res


# The standard caps keep property tax at +0.5 points and fisheries rent at 50%; they fund about 250 þús. Balancing
# 300 needs at least one of them raised. These are the moderate ways to do it.
MODERATE = {"income_tax": (3.0, (90, 125)), "vat": (3.0, (15, 27)), "payroll_cut": (3.0, (0, 15)),
            "corporate_tax": (2.0, (15, 30))}
MODERATE_300 = {
    "300, property +0.5, fisheries 80%": {**MODERATE, "prop_tax": (2.0, (0, 50)), "fish_rent": (1.0, (24, 80))},
    "300, property +1, fisheries 65%": {**MODERATE, "prop_tax": (2.0, (0, 100)), "fish_rent": (1.0, (24, 65))},
}


def main():
    global FREE
    s = Surface()
    results = []
    for ubi in (200, 250, 300, 350, 400, 450):
        results.append(search(s, f"standard {ubi}", ubi, STANDARD_FIXED, caps=True, seed=ubi))
    base = dict(FREE)
    for name, caps in MODERATE_300.items():
        FREE = {**base, **caps}
        results.append(search(s, name, 300, STANDARD_FIXED, caps=True, seed=5))
        results.append(search(s, name + ", fast AI", 300, {**STANDARD_FIXED, "ai": 15}, caps=True, seed=6))
    FREE = base
    results.append(search(s, "least disruptive 300, agreements kept", 300, STANDARD_FIXED, caps=False, seed=8))
    extreme = {**STANDARD_FIXED, "agreements": 1}
    for ubi in (300, 450, 600):
        results.append(search(s, f"extreme {ubi}", ubi, extreme, caps=False, seed=ubi + 1))
    results.append(search(s, "standard 300, fast AI", 300, {**STANDARD_FIXED, "ai": 15}, caps=True, seed=7))
    OUT.write_text(json.dumps(results, indent=1))
    print(f"\nwrote {OUT}")


if __name__ == "__main__" and len(sys.argv) == 1:
    main()


# Financing mixes: the weight on moving a lever, relative to the default. Lower = the mix leans on it.
MIXES = {
    "balanced": {},
    "labour": {"income_tax": .25, "personal_credit": .25, "pension_fold": .5},
    "property and resources": {"prop_tax": .25, "fish_rent": .25, "wealth_tax": .3, "inherit_rate": .3,
                               "corporate_tax": .5, "gift_tax": .3, "exit_tax": .3},
    "consumption": {"vat": .25, "vat_input": .4, "customs": .5},
}
OUT_V2 = ROOT / "data/processed/scenarios_vs_sq.json"
OUT_V3 = ROOT / "data/processed/scenarios_v3.json"


def main_v3():
    """The v3 standard pictures: each must do at least as well as the status quo's budget over 2027-35."""
    global FREE
    s = Surface()
    base = dict(FREE)
    moderate = {**base, **MODERATE}
    wide = {**base, **MODERATE, "prop_tax": (2.0, (0, 200)), "fish_rent": (1.0, (24, 50)),
            "wealth_tax": (1.5, (0, 100)), "inherit_rate": (1.5, (10, 40)), "vat_input": (1.5, (0, 250)),
            "corporate_tax": (2.0, (15, 30))}
    plan = [
        # name, borgaralaun, what is held fixed, which levers are free, standard caps, financing mix
        ("250, moderate", 250, STANDARD_FIXED, moderate, True, "balanced"),
        ("300, standard", 300, {**STANDARD_FIXED, "fish_rent": 40}, wide, True, "balanced"),
        ("300, fisheries fee as today", 300, {**STANDARD_FIXED, "fish_rent": 24}, wide, True, "balanced"),
        # 80% of each child's payment goes to the family instead of into the fund: the model's fertility response
        # is at its strongest here, so this is the scenario that asks what a birth boom costs and brings
        ("300, children paid to families", 300, {**STANDARD_FIXED, "fish_rent": 40, "child_invested": 20},
         wide, True, "balanced"),
        ("300, world as the last decade", 300, {**STANDARD_FIXED, "fish_rent": 40, "history_world": 1},
         wide, True, "balanced"),
        ("350, balanced mix", 350, {**STANDARD_FIXED, "fish_rent": 50}, wide, True, "balanced"),
        ("400, agreements voided", 400, {**STANDARD_FIXED, "agreements": 1, "fish_rent": 50}, base, True, "balanced"),
    ]
    results = []
    for i, (name, ubi, fixed, free, caps, mix) in enumerate(plan):
        FREE = free
        r = search(s, name, ubi, fixed, caps=caps, seed=300 + i, weights=MIXES[mix])
        r["mix"] = mix
        results.append(r)
    FREE = base
    OUT_V3.write_text(json.dumps(results, indent=1))
    print(f"\nwrote {OUT_V3}")


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "v3":
    main_v3()


def main_vs_sq():
    """Varied scenarios, 250-450 þús., each doing at least as well as the status quo's budget over 2027-35."""
    global FREE
    s = Surface()
    base = dict(FREE)
    moderate_300 = {**base, **MODERATE_300["300, property +1, fisheries 65%"]}
    plan = [
        ("250, moderate", 250, STANDARD_FIXED, {**base, **MODERATE}, True, "balanced"),
        ("300, moderate", 300, STANDARD_FIXED, moderate_300, True, "balanced"),
        ("300, labour taxes", 300, STANDARD_FIXED, base, False, "labour"),
        ("300, property and resources", 300, STANDARD_FIXED, base, False, "property and resources"),
        ("300, moderate, fast AI", 300, {**STANDARD_FIXED, "ai": 15}, moderate_300, True, "balanced"),
        ("350, consumption", 350, STANDARD_FIXED, base, False, "consumption"),
        ("350, balanced mix", 350, STANDARD_FIXED, base, True, "balanced"),
        ("400, balanced mix", 400, STANDARD_FIXED, base, True, "balanced"),
        ("400, agreements voided", 400, {**STANDARD_FIXED, "agreements": 1}, base, True, "balanced"),
        ("450, agreements voided", 450, {**STANDARD_FIXED, "agreements": 1}, base, True, "balanced"),
    ]
    results = []
    for i, (name, ubi, fixed, free, caps, mix) in enumerate(plan):
        FREE = free
        r = search(s, name, ubi, fixed, caps=caps, seed=100 + i, weights=MIXES[mix])
        r["mix"] = mix
        results.append(r)
    FREE = base
    OUT_V2.write_text(json.dumps(results, indent=1))
    print(f"\nwrote {OUT_V2}")


OUT_LIKE = ROOT / "data/processed/scenario_like_users.json"

# A scenario built in the guided version (2026-09-20), as lever levels. Its budget beats the status quo,
# but it comes with shortages in the essential services, rents a quarter above the status quo, prices a third
# higher and a weaker króna. The search below looks for the nearest scenario to this one that keeps the budget and
# loses those costs.
USERS_300 = {
    "ubi": 300, "child_invested": 50, "pension_fold": 100, "income_tax": 85, "personal_credit": 0, "vat": 25,
    "vat_input": 200, "prop_tax": 100, "wealth_tax": 0, "inherit_rate": 10, "inherit_floor": 6.5, "gift_tax": 10,
    "exit_tax": 0, "enforcement": 100, "payroll_cut": 0, "public_offset": 100, "agreements": 1, "minimum_wage": 0,
    "agri_cut": 100, "sub_innovation": 100, "sub_energy": 100, "sub_other": 100, "customs": 100, "fish_rent": 24,
    "governance": 100, "church": 0, "culture": 0, "per_diem": 100, "resi_cap": 100, "comm_cap": 100,
    "custodianship": 0, "housing": 0, "childcare": 0, "retraining": 0, "venture_support": 0, "residence": 100,
    "capital_controls": 100, "prison_ubi": 0, "ubi_protected": 100, "gambling_block": 100, "free_health": 0,
    "free_internet": 0, "smelters": 0, **WORLD, "ai": 5,
}
# What the search may move away from that scenario's choices, and how dearly each move counts. Everything else is
# held where it was, so the result stays recognisably the same scenario.
LIKE_FREE = {
    "income_tax": (4.0, (85, 115)), "personal_credit": (1.5, (0, 72.5)), "vat": (4.0, (18, 28)),
    "vat_input": (1.0, (0, 350)), "prop_tax": (1.0, (0, 200)), "corporate_tax": (1.5, (15, 30)),
    "wealth_tax": (1.5, (0, 100)), "inherit_rate": (1.5, (10, 40)), "fish_rent": (0.8, (24, 80)),
    "agri_cut": (1.0, None), "sub_energy": (1.0, None), "sub_other": (1.0, (0, 64)), "customs": (1.0, None),
    "payroll_cut": (4.0, (0, 15)), "public_offset": (1.0, None), "agreements": (1.0, None),
    "housing": (0.6, (0, 2500)), "childcare": (0.8, (0, 6000)), "retraining": (0.8, (0, 30)),
    "resi_cap": (0.8, None), "comm_cap": (0.8, None),
}


def score_like(s, X, free, w, home):
    """Like `score`, but measured against that scenario, and with its costs added to what counts as a cost."""
    keys = ["balance", "cpi", "unemp", "net_d1", "essential_gap", "net_income", "debt", "fte", "rent", "fx"]
    out, sq = s.eval(X, keys), s.status_quo(X, keys)
    idx = [s.idx[k] for k in free]
    move = ((X[:, idx] - home) ** 2 * w).sum(1)
    y = 9
    gap_y = sq["balance"][:, 1:10] - out["balance"][:, 1:10]     # 2027-35; the surface goes on to 2060
    deficit = np.clip(gap_y.sum(1), 0, None) + np.clip(gap_y - SLACK, 0, None).sum(1)
    # the four costs the scenario carries, each allowed a little room above the status quo
    prices = np.clip(out["cpi"][:, y] / sq["cpi"][:, y] - 1.10, 0, None)
    krona = np.clip(out["fx"][:, y] / sq["fx"][:, y] - 1.10, 0, None)
    rent = np.clip(out["rent"][:, y] / sq["rent"][:, y] - 1.10, 0, None)
    gap = np.clip(out["essential_gap"][:, y] - sq["essential_gap"][:, y] - 500, 0, None)
    unemp = np.clip(out["unemp"][:, y] - sq["unemp"][:, y] - .005, 0, None)
    poor = np.clip(1 - out["net_d1"][:, y] / sq["net_d1"][:, y], 0, None)
    J = move + (deficit / 50) ** 2 * 10 + (prices * 15) ** 2 + (krona * 15) ** 2 + (rent * 15) ** 2 \
        + (gap / 500) ** 2 + (unemp * 100) ** 2 + (poor * 20) ** 2
    return J, deficit, out, sq


def main_like_users():
    """The nearest scenario to the built one that keeps its budget and drops its costs."""
    s = Surface()
    home_x = s.x_from(USERS_300)
    free = list(LIKE_FREE)
    lo = np.array([s.to_x(k, LIKE_FREE[k][1][0]) if LIKE_FREE[k][1] else 0.0 for k in free])
    hi = np.array([s.to_x(k, LIKE_FREE[k][1][1]) if LIKE_FREE[k][1] else 1.0 for k in free])
    lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)
    w = np.array([LIKE_FREE[k][0] for k in free])
    idx = [s.idx[k] for k in free]
    home = home_x[idx].copy()
    rng = np.random.default_rng(11)

    def batch(U):
        X = np.tile(home_x, (len(U), 1))
        X[:, idx] = U
        return X
    best, bestJ = home.copy(), float(score_like(s, batch(home[None, :]), free, w, home)[0][0])
    print(f"the built scenario scores {bestJ:.2f}")
    for _ in range(20):
        U = lo + rng.random((5000, len(free))) * (hi - lo)
        J, _, _, _ = score_like(s, batch(U), free, w, home)
        i = int(np.argmin(J))
        if J[i] < bestJ:
            best, bestJ = U[i], float(J[i])
    for step in (.15, .08, .04, .02, .01):
        for _ in range(6):
            U = np.clip(best + rng.normal(0, step, (5000, len(free))) * (hi - lo), lo, hi)
            J, _, _, _ = score_like(s, batch(U), free, w, home)
            i = int(np.argmin(J))
            if J[i] < bestJ:
                best, bestJ = U[i], float(J[i])
    for tag, U in (("the built scenario", home), ("the nearest one without the costs", best)):
        X = batch(U[None, :])
        J, deficit, out, sq = score_like(s, X, free, w, home)
        y = 9
        print(f"\n{tag}: budget {float((out['balance'][0, 1:10] - sq['balance'][0, 1:10]).sum()):+.0f} ma.kr. over 2027-35,"
              f" debt {out['debt'][0, y]:.0f}% of GDP")
        print(f"  2035: income {100 * (out['net_income'][0, y] / sq['net_income'][0, y] - 1):+.1f}%,"
              f" poorest tenth {100 * (out['net_d1'][0, y] / sq['net_d1'][0, y] - 1):+.1f}%,"
              f" prices {100 * (out['cpi'][0, y] / sq['cpi'][0, y] - 1):+.1f}%,"
              f" króna {100 * (out['fx'][0, y] / sq['fx'][0, y] - 1):+.1f}%,"
              f" rents {100 * (out['rent'][0, y] / sq['rent'][0, y] - 1):+.1f}%,"
              f" services short {out['essential_gap'][0, y]:.0f} (sq {sq['essential_gap'][0, y]:.0f}),"
              f" unemployment {100 * out['unemp'][0, y]:.1f}%")
        if tag.startswith("the nearest"):
            levels = {k: round(float(s.level(k, X[0, s.idx[k]])), 2) for k in free}
            changed = {k: (USERS_300.get(k), v) for k, v in levels.items()
                       if abs(X[0, s.idx[k]] - home_x[s.idx[k]]) > .02}
            print("  changed from it: " + ", ".join(f"{k} {a} -> {b}" for k, (a, b) in changed.items()))
            OUT_LIKE.write_text(json.dumps({"name": "300, in the same spirit", "x": X[0].tolist(), "levels": levels,
                                            "changed": {k: b for k, (a, b) in changed.items()}}, indent=1))
            print(f"wrote {OUT_LIKE}")


OUT_HIGH = ROOT / "data/processed/scenarios_high.json"
# The question: how high a payment could be carried on openly optimistic assumptions. Each
# route is a world the search may not change; the question is the largest payment whose budget still does as well
# as today's status quo — the status quo *without* the windfall or the robots, since they are what pays.
TODAYS_WORLD = {"windfall": 0, "ai": 5}
HIGH = [
    # name, id, what the route holds fixed
    ("A robot dividend", "robots", {"ai": 15, "robot_stake": 60, "clawback": 30}),
    ("A resource windfall", "windfall", {"windfall": 500}),
    ("Windfall and robot dividend", "planned", {"ai": 15, "robot_stake": 60, "clawback": 30, "windfall": 500,
                                              "frontier": 100, "infrastructure": 100, "fund": 30}),
]


def main_high():
    """The largest payment each optimistic route carries, 50 þús. at a time from 250, then the scenario at it."""
    global FREE, JUDGE
    JUDGE = "living"
    s = Surface()
    base = dict(FREE)
    wide = {**base, **MODERATE, "prop_tax": (2.0, (0, 200)), "fish_rent": (1.0, (24, 50)),
            "wealth_tax": (1.5, (0, 100)), "inherit_rate": (1.5, (10, 40)), "vat_input": (1.5, (0, 250)),
            "corporate_tax": (2.0, (15, 30))}
    FREE = wide
    results = []
    top = s.levers[s.idx["ubi"]]["hi"]
    for i, (name, sid, route) in enumerate(HIGH):
        fixed = {**STANDARD_FIXED, "fish_rent": 50, **route}
        best = None
        for ubi in range(250, int(top) + 1, 50):
            # the random search is rugged at these corners: the best of two seeds, each with a large first pass
            r = min((search(s, name, ubi, fixed, caps=True, n=60000, seed=400 + 10 * i + k, sq_world=TODAYS_WORLD,
                            quiet=True) for k in range(2)), key=lambda q: q["disruption"])
            # how high the budget allows: what it does to jobs and the poorest is reported, not a condition (a
            # low payment can leave the poorest below today's benefits; a high one lifts them)
            ok = r["deficit_after_year1"] < 25
            print(f"  {name} {ubi}: {r['vs_sq_2027_35']:+.0f} ma.kr. vs today's status quo, "
                  f"unemployment {100 * r['unemployment']:.1f}% (sq {100 * r['unemployment_sq']:.1f}%), "
                  f"wellbeing {100 * r['wellbeing_vs_sq']:+.1f}%, hardship {100 * r['hardship']:.1f}% "
                  f"(sq {100 * r['hardship_sq']:.1f}%), poorest {100 * r['poorest_vs_sq']:+.1f}% "
                  f"{'ok' if ok else 'no'}", flush=True)
            if not ok:
                break
            best = ubi
        if best is None:
            print(f"{name}: not even 250 þús.")
            continue
        r = search(s, f"{best}, {name.lower()}", best, fixed, caps=True, seed=500 + i, sq_world=TODAYS_WORLD)
        r["id"], r["route"], r["max_ubi"] = f"{sid}{best}", route, best
        results.append(r)
    FREE, JUDGE = base, "jobs"
    OUT_HIGH.write_text(json.dumps(results, indent=1))
    print(f"\nwrote {OUT_HIGH}")


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "high":
    main_high()
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "vs_sq":
    main_vs_sq()
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "like":
    main_like_users()
