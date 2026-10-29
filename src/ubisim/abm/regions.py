"""2.0: two areas, the capital area and the rest of the country, each with its own housing market, and moves between them.

What there is (regions_2025.json; Hagstofa). 64% of people live in the capital area, and its employees earn 11% more
a month (TEK02003, 2025); homes cost more there, by more than the pay. About 4,000 people a year move from the
capital area to the rest of the country and 3,700 the other way (MAN01002, 2025): 1.6% and 2.6% of each area's people.
Arrivals from abroad settle 62-70% in the capital area and emigrants leave it in about the same share.

Where people live. Each person lives in one area (A["capital"]); a couple, their children and an adult living with
them share it. At the start, the better paid are more likely to live in the capital area, as many as make its pay per
employee `pay_ratio` times the rest's (sorting; most of the gap in the Nordic register studies is who lives where).
Arrivals settle in the capital area in the record's share (`arrival_capital_share`), children are born where their
mother lives, and emigrants leave from either area as they come.

Housing. Each area has its own stock of dwellings, counted at the start as the households living there, and its own
price and rent against the market-wide index (macro.update_housing), moved by how full it is against its stock as
each size's is (housing.update_segments): new building goes to each area in proportion to its stock, tilted towards
the one whose price has risen, and in the base year the capital area takes `build_capital_share` of it, more than
its share of the stock (69% of the dwellings completed in 2015-21; IDN03001, IDN03002): homes there sell further
above what they cost to build, so more are built there. The levels are the base population's (homes `value_ratio`
times dearer in the capital area, rents as the cost rules have them); this part moves them against each other.

Moves. Each household moves to the other area at a yearly rate set so that in the status quo's first year the record's
rates come out, higher for the young (`age_profile`, EST, after the usual age schedule of migration: highest in the
twenties, low after fifty). What moves the rate is how much better off the household would be in the other area:
its real income there against here, the cost of housing weighing `housing_share` of what it spends (the CPI's weight)
and its pay in the capital area `mover_pay_premium` higher (EST: about half the observed gap; the rest is sorting).
The rate rises by `elasticity` per unit of that gain in logs (EST 1: a household 10% better off elsewhere moves 10%
more often). The responses in Nordic data are weak — Kornstad et al. (2023) for Norway's regions,
Eliasson et al. (2023) for jobs in Stockholm, where dear housing deters more than pay draws — and most
moves follow study, partners and jobs, which sit in the base rate. In Finland earnings-related unemployment benefit
weakens the pull of pay (Maczulskij et al. 2023): income that does not depend on where one works makes the pay
gap matter less and the housing gap more, which is how a basic income works here. A mover who owns sells and buys
the same size in the other area, the difference passing through savings and the mortgage; pay changes by the premium.

A reform is set against the status quo's base: the scale of the rates comes from its first year. Not modelled: the
areas' own labour markets (pay and unemployment are national, apart from who lives where), demand for local
services, commuting, and the eight regions within the rest of the country.
"""
import numpy as np

from ubisim.abm import housing
from ubisim.abm import policy as pol_rules
from ubisim.abm.population import FULL, INDEP, PART, VENTURE


def _config(p):
    return p.get("regions") or {}


# ------------------------------------------------------------------ the base
def assign(A, p, rng):
    """Each person's area at the start: the better paid more often in the capital area, as many as give the record's
    gap in pay per employee, and smaller households more often, as many as give its persons per household against
    the rest's (MAN07108: 1.80 against 1.88 in 2015, 1.71 against 1.74 in 2025; students, the young and the old in
    flats there, families outside); a couple, children and an adult living with a household share its area. Draws
    one uniform per person, as the old random assignment did, so the rest of the population is drawn the same."""
    N = len(A["age"])
    c = _config(p)
    u = rng.random(N)
    share = c.get("capital_share", p["costs"]["capital_share"])
    if not c:
        cap = u < share
    else:
        employed = np.isin(A["status"], [PART, FULL]) & (A["age"] >= 16)
        rel = A["base_wage"] / max(float(np.median(A["base_wage"][employed])), 1e-9)
        rel = np.clip(rel, .1, 10)
        i = np.arange(N)
        lead = (A["age"] >= 18) & ((A["partner"] < 0) | (i < A["partner"]))   # as housing.households counts them
        if "host" in A:
            lead &= A["host"] < 0
        unit = i.copy()
        unit[A["partner"] >= 0] = np.minimum(i, A["partner"])[A["partner"] >= 0]
        if "host" in A:
            hosted = A["host"] >= 0
            unit[hosted] = unit[A["host"][hosted]]
        kid = (A["mother"] >= 0) & (A["age"] < 18)
        unit[kid] = unit[A["mother"][kid]]
        size = np.bincount(unit, minlength=N)[unit].astype(float)

        def draw(theta, phi):
            """At these tilts, the share drawn so that the area holds `share` of people once households share it."""
            w = rel ** theta * size ** phi
            k = share
            for _ in range(4):
                x = u < np.minimum(k * w / w.mean(), 1.0)
                _share_with_household(A, x)
                k *= share / max(x.mean(), 1e-9)
            return x

        def gap(x):
            return A["base_wage"][employed & x].mean() / max(A["base_wage"][employed & ~x].mean(), 1e-9)

        def persons(x):
            return (x.sum() / max((lead & x).sum(), 1)) / ((~x).sum() / max((lead & ~x).sum(), 1))

        def theta_for(phi):
            lo, hi = 0.0, 3.0
            for _ in range(14):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if gap(draw(mid, phi)) < c["pay_ratio"] else (lo, mid)
            return (lo + hi) / 2

        lo, hi = -3.0, 3.0
        for _ in range(14):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if persons(draw(theta_for(mid), mid)) < c["household_size_ratio"] else (lo, mid)
        phi = (lo + hi) / 2
        return draw(theta_for(phi), phi)
    _share_with_household(A, cap)
    return cap


def _share_with_household(A, cap):
    i = np.arange(len(cap))
    partner = A["partner"]
    has = partner >= 0
    first = np.where(has, np.minimum(i, partner), i)
    cap[has] = cap[first[has]]
    if "host" in A:
        hosted = A["host"] >= 0
        cap[hosted] = cap[A["host"][hosted]]
    kid = (A["mother"] >= 0) & (A["age"] < 18)
    cap[kid] = cap[A["mother"][kid]]


def ensure(soc):
    st = getattr(soc, "regions", None)
    if st is None:
        st = soc.regions = {} if not _config(soc.p) else {
            "factor": np.ones(2), "stock": None, "occ0": None, "total0": None, "last_total": None,
            "scale": None, "to_capital": 0, "from_capital": 0, "gain": np.zeros(2)}
    return st


def _levels(soc):
    """Each area's homes against the rest of the country's, at base prices: [rest, capital]."""
    return np.array([1.0, _config(soc.p)["value_ratio"]])


def factor(soc, idx):
    """Each home's price against the market-wide index by its area: 1 without regions."""
    st = getattr(soc, "regions", None)
    if not st or "capital" not in soc.A:
        return 1.0
    return st["factor"][soc.A["capital"][idx].astype(int)]


def _occupancy(soc, lead=None):
    lead = housing.households(soc) if lead is None else lead
    return np.bincount(soc.A["capital"][lead].astype(int), minlength=2).astype(float)


# ------------------------------------------------------------------ the two markets
def update_market(soc):
    """After the market-wide rent and price and the sizes' factors: each area's price against the other's, from how
    full it is against its own stock."""
    c = _config(soc.p)
    st = ensure(soc)
    if not c:
        return
    hs, m = soc.p["housing_segments"], soc.p["markets"]
    occ = _occupancy(soc)
    total = soc.macro.stock
    if st["stock"] is None:
        st["stock"], st["occ0"] = occ.copy(), occ.copy()
        st["total0"] = st["last_total"] = total
        b = c["build_capital_share"]
        st["tilt"] = np.array([1.0, b / (1 - b) * occ[0] / max(occ[1], 1e-9)])
    added = total - st["last_total"]
    st["last_total"] = total
    units = st["occ0"].sum() / st["total0"]
    if added > 0:
        w = st["stock"] * st["tilt"] * st["factor"] ** hs["construction_split_elasticity"]
        st["stock"] = st["stock"] + added * units * w / w.sum()
    elif added < 0:
        st["stock"] = st["stock"] * (1 + added / max(total - added, 1e-9))
    weight = st["occ0"] * _levels(soc)
    weight = weight / weight.sum()
    tight = occ / np.maximum(st["stock"], 1e-6)
    tight = tight / max(float((weight * tight).sum()), 1e-6)
    target = np.maximum(tight, .05) ** (1 / m["housing_price_elasticity"])
    target = target / float((weight * target).sum())
    a = hs["adjustment"]
    f = st["factor"] ** (1 - a) * target ** a
    st["factor"] = np.clip(f / float((weight * f).sum()), .5, 2.0)
    hs["_area_factor"] = [float(v) for v in st["factor"]]


# ------------------------------------------------------------------ moves
def _households(soc):
    """Each household's lead, and every living person's household (-1 for none)."""
    A = soc.A
    lead = housing.households(soc)
    of = np.full(len(A["alive"]), -1)
    of[lead] = lead
    partner = A["partner"][lead]
    of[partner[partner >= 0]] = lead[partner >= 0]
    if "host" in A:
        hosted = np.flatnonzero(A["alive"] & (A["host"] >= 0))
        of[hosted] = of[A["host"][hosted]]
    kid = np.flatnonzero(A["alive"] & (A["mother"] >= 0) & (A["age"] < 18))
    of[kid] = of[A["mother"][kid]]
    of[~A["alive"]] = -1
    return lead, of


def _gain(soc, lead, c):
    """How much better off each household would be in the other area, in logs: its pay there, and the cost of
    housing there against here."""
    A, p = soc.A, soc.p
    cap = A["capital"][lead]
    partner = A["partner"][lead]
    net = soc.net_now[lead] + np.where(partner >= 0, soc.net_now[np.maximum(partner, 0)], 0)
    r = np.where(cap, 1 / (1 + c["mover_pay_premium"]), 1 + c["mover_pay_premium"])
    delta = np.zeros(len(lead))
    bx = soc.benefit_index()
    for who, pos in ((lead, np.arange(len(lead))), (partner[partner >= 0], np.flatnonzero(partner >= 0))):
        working = np.isin(A["status"][who], [PART, FULL, VENTURE, INDEP])
        j, k = who[working], pos[working]
        if not len(j):
            continue
        g = soc.current_gross(j)
        on = g > 0
        j, k, g = j[on], k[on], g[on]
        if not len(j):
            continue
        pa = A["partner"][j]
        pinc = np.where(pa >= 0, soc.net_now[np.maximum(pa, 0)], 0)
        w = np.ones(len(j), bool)
        moved = pol_rules.net_income(A, j, g * r[k], w, p, pinc, soc.price, bx)["net"]
        here = pol_rules.net_income(A, j, g, w, p, pinc, soc.price, bx)["net"]
        np.add.at(delta, k, moved - here)
    # against at least a fifth of the median household's: a household with next to no income this year (just arrived,
    # just formed) would otherwise read a job's pay in the other area as a gain of many times its income
    floor = .2 * max(float(np.median(net)), 1.0)
    pay = np.log(np.maximum(net + delta, floor) / np.maximum(net, floor))
    costs = p["costs"]
    rent_ratio = costs["housing_renter_capital"] / costs["housing_renter_other"]
    level = np.where(A["renter"][lead], rent_ratio, c["value_ratio"])
    f = ensure(soc)["factor"]
    dear_here = np.where(cap, level * f[1] / f[0], 1 / level * f[0] / f[1])
    return np.clip(pay + c["housing_share"] * np.log(dear_here), -.5, .5)


def step_moves(soc):
    """This year's moves between the two areas."""
    c = _config(soc.p)
    st = ensure(soc)
    if not c:
        return
    A, rng = soc.A, soc.rng
    st["to_capital"] = st["from_capital"] = 0
    lead, of = _households(soc)
    if not len(lead):
        return
    cap = A["capital"][lead]
    size = np.bincount(np.searchsorted(lead, of[of >= 0]), minlength=len(lead)).astype(float)
    age = A["age"][lead]
    gain = _gain(soc, lead, c)
    st["gain"] = np.array([gain[~cap].mean() if (~cap).any() else 0.0, gain[cap].mean() if cap.any() else 0.0])
    raw = np.interp(age, c["age_profile"][0], c["age_profile"][1]) * np.exp(c["elasticity"] * gain)
    if st["scale"] is None:
        first = soc.reference[0] if soc.reference else {}
        if "region_scale_capital" in first:
            st["scale"] = np.array([first["region_scale_rest"], first["region_scale_capital"]])
        else:
            rates = np.array([c["move_rate_to_capital"], c["move_rate_from_capital"]])
            people = np.array([size[~cap].sum(), size[cap].sum()])
            moved = np.array([(raw * size)[~cap].sum(), (raw * size)[cap].sum()])
            st["scale"] = rates * people / np.maximum(moved, 1e-9)
    rate = np.minimum(st["scale"][cap.astype(int)] * raw, .5)
    go = rng.random(len(lead)) < rate
    if not go.any():
        return
    movers = np.flatnonzero(np.isin(of, lead[go]))
    leaving = A["capital"][movers].copy()
    _sell_and_buy(soc, movers, leaving, c)
    adult = A["age"][movers] >= 16
    A["base_wage"][movers[adult]] *= np.where(leaving[adult], 1 / (1 + c["mover_pay_premium"]),
                                              1 + c["mover_pay_premium"])
    A["capital"][movers] = ~leaving
    st["from_capital"], st["to_capital"] = int(leaving.sum()), int((~leaving).sum())


def _sell_and_buy(soc, who, leaving, c):
    """Owners sell their home and buy one of the same size in the other area; what is left over repays the mortgage
    and goes to savings, what is short is borrowed."""
    A = soc.A
    own = A["home_value"][who] > 0
    j, out = who[own], leaving[own]
    if not len(j):
        return
    f = ensure(soc)["factor"]
    hp = soc.macro.house_price
    fs = housing.factors(soc)[np.maximum(A["hclass"][j], 0)] if "hclass" in A else 1.0
    ratio = np.where(out, 1 / c["value_ratio"], c["value_ratio"])
    old = A["home_value"][j] * hp * fs * f[out.astype(int)]
    new_value = A["home_value"][j] * ratio
    new = new_value * hp * fs * f[(~out).astype(int)]
    cash = old * (1 - soc.p["downsizing"]["transaction_cost"]) - new
    repay = np.clip(cash, 0, A["mortgage_debt"][j])
    A["mortgage_debt"][j] += np.maximum(-cash, 0) - repay
    A["wealth"][j] += np.maximum(cash, 0) - repay
    A["home_value"][j] = new_value
    A["mortgage"][j] = A["mortgage_debt"][j] > 0


def settle_arrivals(soc, new):
    """Arrivals from abroad settle in the capital area in the record's share. A hash of the person, so it draws
    nothing from the run's random numbers."""
    c = _config(soc.p)
    if not c or not len(new):
        return
    k = (np.asarray(new) * 2246822519 + 3266489917) % 1000
    soc.A["capital"][new] = k < c["arrival_capital_share"] * 1000


# ------------------------------------------------------------------ what to report
def accounts(soc):
    st = getattr(soc, "regions", None)
    if not st or st.get("scale") is None:
        return {}
    return {"region_scale_rest": float(st["scale"][0]), "region_scale_capital": float(st["scale"][1])}


def snapshot(soc):
    st = getattr(soc, "regions", None)
    if not st:
        return {}
    A = soc.A
    alive = A["alive"]
    employed = alive & np.isin(A["status"], [PART, FULL]) & (A["age"] >= 16)
    cap = A["capital"]
    pay = (A["base_wage"][employed & cap].mean() / max(A["base_wage"][employed & ~cap].mean(), 1e-9)
           if (employed & cap).any() and (employed & ~cap).any() else np.nan)
    f = st["factor"]
    return {"capital_area_share": float(cap[alive].mean()) if alive.any() else np.nan,
            "moves_to_capital": int(st["to_capital"]), "moves_from_capital": int(st["from_capital"]),
            "capital_area_price_factor": float(f[1] / f[0]),
            "capital_area_home_price_ratio": float(_config(soc.p)["value_ratio"] * f[1] / f[0]),
            "capital_area_pay_ratio": float(pay),
            # how much better off, in logs, the average household would be in the other area
            "gain_moving_to_capital": float(st["gain"][0]), "gain_leaving_capital": float(st["gain"][1])}
