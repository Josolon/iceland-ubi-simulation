"""The housing ladder, older owners' moves, and the state's claims on homes (v10).

Until v10 the housing market was one index: one rent and one price for every dwelling, and nobody moved but
first-time buyers. Older owners never downsized, and the poverty measure, which counts income and not housing
wealth, could put a fifth of pensioners below the line while nearly all of them owned a home worth 60 m kr. outright.

The ladder. Dwellings come in six sizes (SIZES). Every household needs one, from its adults and children, a step more
if it is well off (`need`); it lives in one (A["hclass"], held by both partners of a couple). Each size has a stock,
and its price and rent move against the market-wide index (macro.update_housing) with how full it is
(update_segments). Moves follow the gap between the two, the same rules in every run:

* a crowded household moves up when it can pay for the larger home, less often the dearer that home has become;
* a household with more room than it needs moves down: rarely before old age, more after a partner's death, when
  income falls below the poverty line, and from 55 when those already retired in the same run live on much less
  than those still working (moving before the money runs short). Owners release equity, part
  of it as a lifetime income and the rest as savings;
* young adults leave home sooner when a studio's rent is low against what people their age earn
  (population.update_young);
* new building goes where prices have risen most against the others.

So older owners who leave family houses make them cheaper for families with children, whose moving up frees the
flats below; and downsizers, first-time buyers and young people leaving home compete for the small flats at the
bottom.

Claims on homes. Under policy.floor_loan the pension top-up (benefit_floor) paid to owners 67+ is a loan secured on
the home, up to `floor_loan_ltv` of its equity, repaid when the home is sold or from the estate. Deferred property
tax (policy.defer_pensioner_property_tax) is a claim in the same way. Both are booked as lending, as the government
finance statistics book loans: a financial asset, not spending. What an estate cannot repay is written off.
"""
import numpy as np

from ubisim.abm import regions

SIZES = ("studio", "flat for one or two", "flat for a family with a child", "flat or small house for two children",
         "house for three or four children", "large house")
K = len(SIZES)


# ------------------------------------------------------------------ households
def households(soc):
    """One lead adult per household that holds a dwelling of its own: couples once; an older guest of a younger
    household and a young adult living with their parents are part of their host's."""
    A = soc.A
    i = np.arange(len(A["alive"]))
    lead = A["alive"] & (A["age"] >= 18) & ((A["partner"] < 0) | (i < A["partner"]))
    if "host" in A:
        lead &= A["host"] < 0
    return np.flatnonzero(lead)


def hh_sum(soc, key, idx):
    A = soc.A
    partner = A["partner"][idx]
    return A[key][idx] + np.where(partner >= 0, A[key][np.maximum(partner, 0)], 0)


def hh_value(soc, idx):
    return hh_sum(soc, "home_value", idx)


def need(soc, lead):
    """The size a household needs: a single person under 35 a studio; one older, a couple, or a parent alone with one
    child a small flat; each child more a step up. A household in the top
    `well_off_share` by income or by wealth wants a step more."""
    A, hs = soc.A, soc.p["housing_segments"]
    partner = A["partner"][lead]
    couple = partner >= 0
    pidx = np.maximum(partner, 0)
    kids = np.maximum(A["n_kids"][lead], np.where(couple, A["n_kids"][pidx], 0)) if "n_kids" in A \
        else np.zeros(len(lead), int)
    age = A["age"][lead]
    base = np.select([~couple & (kids == 0) & (age < 35),
                      (kids == 0) | (~couple & (kids == 1)),
                      (couple & (kids == 1)) | (~couple & (kids == 2)),
                      (couple & (kids == 2)) | (~couple & (kids == 3)),
                      kids <= 4],
                     [0, 1, 2, 3, 4], 5)
    if len(lead) > 10:
        rich = np.zeros(len(lead), bool)
        income = getattr(soc, "net_now", None)
        if income is not None and len(income) >= len(A["alive"]):
            inc = income[lead] + np.where(couple, income[pidx], 0)
            rich |= inc >= np.quantile(inc, 1 - hs["well_off_share"])
        worth = np.maximum(hh_sum(soc, "wealth", lead), 0) + hh_value(soc, lead) * soc.macro.house_price
        rich |= worth >= np.quantile(worth, 1 - hs["well_off_share"])
        base = base + rich
    return np.minimum(base, K - 1).astype(np.int8)


def occupancy(soc):
    A = soc.A
    lead = households(soc)
    c = A["hclass"][lead]
    return np.bincount(c[c >= 0], minlength=K).astype(float)


def factors(soc):
    """Each size's price and rent against the market-wide index."""
    f = getattr(soc, "size_factor", None)
    return np.ones(K) if f is None else f


def price_factor(soc, idx):
    """Each home's price against the base year's, by its size and (2.0) its area."""
    A = soc.A
    if "hclass" not in A:
        return soc.macro.house_price * regions.factor(soc, idx)
    c = A["hclass"][idx]
    return soc.macro.house_price * np.where(c >= 0, factors(soc)[np.maximum(c, 0)], 1.0) * regions.factor(soc, idx)


def _publish(soc):
    """The rent factors, where the cost rules read them (policy.housing_cost)."""
    soc.p["housing_segments"]["_rent_factor"] = [float(v) for v in factors(soc)]


# ------------------------------------------------------------------ the base
def ensure(soc):
    """Sizes for the population as drawn, and the ladder's base state. Run once, on the base population, so every
    scenario copies the same base. Renters live in the size they need, at most `largest_let` (few large homes are
    let); owners fill the rest of each size's stock (`stock_shares`) in order of their homes' value."""
    A, hs = soc.A, soc.p["housing_segments"]
    if "hclass" in A:
        return
    n = len(A["alive"])
    A["hclass"] = np.full(n, -1, np.int8)
    A["equity_annuity"] = np.zeros(n)            # monthly, 2025 krónur, for life (passes to a surviving partner)
    A["lien"] = np.zeros(n)                      # the state's claim on the home, 2025 krónur
    A["widowed_at"] = np.full(n, -99, np.int16)
    lead = households(soc)
    v = hh_value(soc, lead)
    owner = v > 0
    nd = need(soc, lead)
    cls = np.full(len(lead), -1, np.int8)
    cls[~owner] = np.minimum(nd[~owner], hs["largest_let"])
    share = np.asarray(hs["stock_shares"], float)
    share = share / share.sum()
    want = np.maximum(share * len(lead) - np.bincount(cls[~owner], minlength=K), 0)
    want = want / max(want.sum(), 1) * owner.sum()
    order = np.flatnonzero(owner)[np.argsort(v[owner], kind="stable")]
    edges = np.round(np.cumsum(want)).astype(int)
    cls[order] = np.minimum(np.searchsorted(edges, np.arange(len(order)), side="right"), K - 1)
    _set_class(soc, lead, cls)
    occ = occupancy(soc)
    soc.size_occ0 = occ
    soc.size_stock = occ.copy()                  # dwellings by size, counted as the households in them at the start
    soc.size_factor = np.ones(K)
    value = np.array([float(v[owner & (cls == j)].mean()) if (owner & (cls == j)).any() else np.nan for j in range(K)])
    for j in range(K):                           # a size no owner holds takes its neighbour's value, a step apart
        if np.isnan(value[j]):
            known = np.flatnonzero(~np.isnan(value))
            near = known[np.argmin(np.abs(known - j))]
            value[j] = value[near] * hs["value_step"] ** (j - near)
    soc.size_value = value                       # an average home of each size, 2025 krónur at base prices
    w = occ * value
    soc.size_weight = w / w.sum()                # value weights: the factors average to the market-wide index
    soc.size_stock_total0 = None
    soc.retired_gap0 = None
    soc.studio_cost0 = None
    _publish(soc)
    reset_year(soc)


def _set_class(soc, lead, cls):
    A = soc.A
    A["hclass"][lead] = cls
    partner = A["partner"][lead]
    has = partner >= 0
    A["hclass"][partner[has]] = np.asarray(cls)[has]


def reset_year(soc):
    soc.moves_up = 0
    soc.moves_down = 0
    soc.downsizers = 0                           # owner households with someone 67+ moving down
    soc.anticipating = 0                         # owners moving down at 55-66
    soc.equity_released = 0.0                    # 2025 krónur
    soc.claims_new = 0.0
    soc.claims_repaid = 0.0
    soc.claims_written_off = 0.0
    soc.heirs_moved_in = 0                       # 1.1: heirs who took over a family home tax-free


# ------------------------------------------------------------------ prices and building
def update_segments(soc):
    """After the market-wide rent and price are set: how full each size is against its own stock moves its price
    against the others'. New building goes to each size in proportion to its stock, tilted towards the sizes whose
    prices have risen."""
    ensure(soc)
    hs, m = soc.p["housing_segments"], soc.p["markets"]
    total = soc.macro.stock
    if soc.size_stock_total0 is None:
        soc.size_stock_total0 = total
        soc.size_last_total = total
    added = total - soc.size_last_total
    soc.size_last_total = total
    units = soc.size_occ0.sum() / soc.size_stock_total0
    if added > 0:
        w = soc.size_occ0 * soc.size_factor ** hs["construction_split_elasticity"]
        soc.size_stock = soc.size_stock + added * units * w / w.sum()
    elif added < 0:
        soc.size_stock = soc.size_stock * (1 + added / max(total - added, 1e-9))
    # Conversions: when the size below has become dear against this one, owners divide or rebuild — a house into
    # flats, a flat into two smaller ones. A share of each size's stock moves a step down, in proportion to how far
    # the smaller size's factor has risen above its own. The stock is otherwise rebuilt only as fast as the market
    # adds dwellings, about 0.5% a year, too slow to follow a population that has grown older and lives in smaller
    # households (2026-10-14).
    f = soc.size_factor
    conv = hs["conversion_rate"] * np.maximum(f[:-1] / f[1:] - 1, 0) * soc.size_stock[1:]
    soc.size_stock[1:] -= conv
    soc.size_stock[:-1] += conv
    soc.size_converted = float(conv.sum())
    occ = occupancy(soc)
    base = np.maximum(soc.size_occ0, 1)
    tight = (occ / base) / np.maximum(soc.size_stock / base, 1e-6)
    # against the market as a whole: a shortage of dwellings overall is already in the market-wide rent and price
    # (macro.update_housing); a size's own factor moves only with how much fuller it is than the rest
    tight = tight / max(float((soc.size_weight * tight).sum()), 1e-6)
    target = np.maximum(tight, .05) ** (1 / m["housing_price_elasticity"])
    target = target / float((soc.size_weight * target).sum())
    a = hs["adjustment"]
    f = soc.size_factor ** (1 - a) * target ** a
    soc.size_factor = np.clip(f / float((soc.size_weight * f).sum()), .4, 2.5)
    _publish(soc)


# ------------------------------------------------------------------ signals
def annuity_factor(age, r):
    """Yearly payment per króna for the rest of a life from `age` (remaining years after Hagstofa's life tables,
    about 19 at 67, EST)."""
    years = np.maximum(4.0, 19.0 - .85 * (np.asarray(age, float) - 67))
    return r / (1 - (1 + r) ** -years)


def _equivalised(soc, idx):
    hh = soc.household_real_income(idx, getattr(soc, "per_mother_now", None))
    _, equiv = soc.housing_costs(idx)
    return hh / equiv


def _income_gap(soc, lead):
    """How far each household's income per equivalent adult is below last year's poverty line, as a share of it."""
    line = getattr(soc, "poverty_line_last", None)
    if line is None or not len(lead):
        return np.zeros(len(lead))
    return np.clip((line - _equivalised(soc, lead)) / line, 0, 1)


def retired_gap(soc):
    """How much less those just retired live on than those still working near the end of their careers, in this run:
    1 - median income per equivalent adult at 67-74 / at 55-66. What someone of 60 can see coming."""
    A = soc.A
    lead = households(soc)
    age = A["age"][lead]
    old, near = lead[(age >= 67) & (age < 75)], lead[(age >= 55) & (age < 67)]
    if not len(old) or not len(near):
        return 0.0
    return 1 - float(np.median(_equivalised(soc, old))) / max(float(np.median(_equivalised(soc, near))), 1.0)


def studio_cost(soc):
    """A studio's rent against what people of 20-29 earn, in real terms."""
    A = soc.A
    young = A["alive"] & (A["age"] >= 20) & (A["age"] < 30)
    earn = float(np.median(soc.net_now[young])) / max(soc.price, .1) if young.any() else 1.0
    return soc.macro.rent * factors(soc)[0] / max(earn, 1.0)


def leave_home_multiplier(soc):
    """Young adults leave home faster when a studio is cheap against what their age group earns, and later when it
    is dear (population.update_young)."""
    if "hclass" not in soc.A or getattr(soc, "net_now", None) is None:
        return 1.0
    now = studio_cost(soc)
    if soc.studio_cost0 is None:
        soc.studio_cost0 = now
    e = soc.p["housing_segments"]["leave_home_elasticity"]
    return float(np.clip((now / max(soc.studio_cost0, 1e-12)) ** -e, .5, 2.0))


# ------------------------------------------------------------------ moves
def choose_size(soc, lo, hi, rng):
    """A size between lo and hi for each household: each step above lo is worth less (`extra_room_penalty`), and
    each size is dearer or cheaper by its factor (`size_price_elasticity`). At the base year's prices most take lo;
    when the size they need has become dear, more take the one above, as people do when small flats are scarce."""
    hs = soc.p["housing_segments"]
    f = factors(soc)
    lo, hi = np.asarray(lo, int), np.maximum(np.asarray(hi, int), np.asarray(lo, int))
    steps = np.arange(3)
    k = np.minimum(lo[:, None] + steps[None, :], K - 1)
    ok = k <= hi[:, None]
    w = np.exp(-hs["extra_room_penalty"] * steps[None, :]) * f[k] ** -hs["size_price_elasticity"] * ok
    w = w / w.sum(1, keepdims=True)
    pick = (rng.random(len(lo))[:, None] > np.cumsum(w, 1)).sum(1)
    return k[np.arange(len(lo)), np.minimum(pick, 2)]


def _down_hazard(soc, age):
    d = soc.p["downsizing"]
    return np.interp(age, [45, 55, 67, 75, 85, 95],
                     [d["hazard_under_55"], d["hazard_under_55"], d["hazard_67"], d["hazard_75"], d["hazard_85"],
                      d["hazard_85"]])


def _place_new(soc):
    """Households without a home on the ladder (new couples, young people leaving home, arrivals, anyone whose
    household ended) rent the size they need, at most `largest_let`; anyone who owns takes the size nearest their
    home's value."""
    A = soc.A
    lead = households(soc)
    new = lead[A["hclass"][lead] < 0]
    if not len(new):
        return
    v = hh_value(soc, new)
    nd = need(soc, new).astype(int)
    let = soc.p["housing_segments"]["largest_let"]
    cls = choose_size(soc, np.minimum(nd, let), np.minimum(nd + 2, max(let, 0) + 1), soc.rng).astype(np.int8)
    own = v > 0
    if own.any():
        cls[own] = np.argmin(np.abs(v[own][:, None] - soc.size_value[None, :]), axis=1)
    # 1.1: a household placed without a home of its own rents, and pays rent (policy.housing_cost)
    rent = new[~own]
    pa = A["partner"][rent]
    for who in (rent, pa[pa >= 0]):
        A["renter"][who] = True
        A["mortgage"][who] = False
    _set_class(soc, new, cls)


def _set_home(soc, lead, value, mortgage, cls):
    """A household's new home: its value (2025 krónur at base prices) and mortgage, held half each by a couple."""
    A = soc.A
    partner = A["partner"][lead]
    has = partner >= 0
    share = np.where(has, .5, 1.0)
    for who, part in ((lead, np.ones(len(lead), bool)), (np.maximum(partner, 0), has)):
        w = who[part]
        A["home_value"][w] = (value * share)[part]
        A["mortgage_debt"][w] = (mortgage * share)[part]
        A["mortgage"][w] = (mortgage > 0)[part]
    _set_class(soc, lead, cls)


def _clear_claims(soc, lead):
    A = soc.A
    pa = A["partner"][lead]
    A["lien"][lead] = 0.0
    A["lien"][pa[pa >= 0]] = 0.0


def step_moves(soc):
    """This year's moves up and down the ladder."""
    ensure(soc)
    A, rng, p = soc.A, soc.rng, soc.p
    d, u, m = p["downsizing"], p["upscaling"], p["markets"]
    reset_year(soc)
    _place_new(soc)
    hp, f = soc.macro.house_price, factors(soc)
    lead = households(soc)
    if not len(lead):
        return
    cur, nd = A["hclass"][lead].astype(int), need(soc, lead).astype(int)
    partner = A["partner"][lead]
    pidx = np.maximum(partner, 0)
    age = np.maximum(A["age"][lead], np.where(partner >= 0, A["age"][pidx], 0))
    v = hh_value(soc, lead)
    owner = v > 0
    hp = hp * regions.factor(soc, lead) * np.ones(len(lead))    # 2.0: each household's area's prices
    # 1.1: an heir who took over the family home tax-free lives in it for ten years (model.heir_moves_in)
    free = A["home_lock"][lead] <= soc.year if "home_lock" in A else np.ones(len(lead), bool)
    # --- moving up: crowded households of working age, when they can pay, less often the dearer the larger home;
    # and households with the room they need trading up a size when the larger home has become cheap against their
    # own — the substitution that keeps the sizes' prices together when one empties (without it, homes freed by
    # deaths found no buyers and the status quo's family houses fell a fifth against flats, 2026-10-14)
    crowded = (cur >= 0) & (cur < nd) & (age < 67) & free
    rel_next = f[np.minimum(cur + 1, K - 1)] / f[np.maximum(cur, 0)]
    trade = (cur >= 0) & (cur == nd) & (cur < K - 1) & (age >= 25) & (age < 60) & (rel_next < 1) & free
    up = np.flatnonzero(crowded | trade)
    if len(up):
        target = np.where(crowded[up], choose_size(soc, nd[up], nd[up] + 1, rng), cur[up] + 1)
        dear = (f[target] / f[cur[up]]) ** -u["price_response"]
        rate = np.where(crowded[up], u["hazard"] * np.minimum(target - cur[up], 2) * dear,
                        u["trade_up_rate"] * (dear - 1))
        go = rng.random(len(up)) < np.minimum(rate, .6)
        U, t = up[go], target[go]
        own = owner[U]
        if own.any():
            Lo, to = lead[U][own], t[own]
            hu = hp[U][own]
            cost = soc.size_value[to] * hu * f[to]
            sale = v[U][own] * hu * f[cur[U][own]]
            debt = hh_sum(soc, "mortgage_debt", Lo) + hh_sum(soc, "lien", Lo)
            savings = np.maximum(hh_sum(soc, "wealth", Lo), 0)
            equity = sale * (1 - d["transaction_cost"]) - debt
            pa = A["partner"][Lo]
            inc = soc.net_now[Lo] + np.where(pa >= 0, soc.net_now[np.maximum(pa, 0)], 0)
            # savings make up the deposit where the sale does not, and the rest is borrowed within the lending
            # limits: households keep what they can of their savings (draining them first, as v10's first draft
            # did, took 0.02 off the income effect at 100 þús.); a sale worth more than the new home leaves the rest
            # in savings
            use = np.clip(u["deposit"] * cost - equity, 0, savings)
            borrow = np.maximum(cost - equity - use, 0)
            surplus = np.maximum(equity - cost, 0)
            able = (equity + savings >= u["deposit"] * cost) \
                & (borrow * m["mortgage_payment_rate"] <= m["first_home_dsti"] * inc / max(soc.price, .1))
            Lo, to, borrow, use, pa, surplus = Lo[able], to[able], borrow[able], use[able], pa[able], surplus[able]
            has = pa >= 0
            w_lead = np.minimum(np.maximum(A["wealth"][Lo], 0), use)
            A["wealth"][Lo] -= w_lead
            A["wealth"][pa[has]] -= (use - w_lead)[has]
            A["wealth"][Lo] += np.where(has, surplus / 2, surplus)
            A["wealth"][pa[has]] += surplus[has] / 2
            _clear_claims(soc, Lo)
            _set_home(soc, Lo, soc.size_value[to].astype(float), borrow, to.astype(np.int8))
            soc.moves_up += int(len(Lo))
        if (~own).any():
            _set_class(soc, lead[U][~own], t[~own].astype(np.int8))
            soc.moves_up += int((~own).sum())
    # --- moving down: more room than needed
    down = np.flatnonzero((cur > nd) & (age >= 45) & free)
    if not len(down):
        return
    a = age[down]
    L = lead[down]
    h = _down_hazard(soc, a)
    widowed = (partner[down] < 0) & (A["widowed_at"][L] >= soc.year - 1)
    h = h * np.where(widowed, d["widowed_multiplier"], 1.0)
    h = h * (1 + d["income_gap_response"] * _income_gap(soc, L))
    # seeing the money run short: from 55, by how much more the retired fall short of the working in this run than at
    # the start
    gap = retired_gap(soc)
    if soc.retired_gap0 is None:
        soc.retired_gap0 = gap
    near = (a >= 55) & (a < 67)
    h = h * np.where(near, 1 + d["anticipation_response"] * max(gap - soc.retired_gap0, 0.0), 1.0)
    # a dearer smaller home frees less money: fewer make the move when the size they would go to has risen against
    # their own (without this the status quo's older households piled into the small flats, which doubled in price
    # against the rest in twelve years, 2026-10-14)
    t0 = np.maximum(nd[down], cur[down] - d["max_steps_down"])
    h = h * (f[t0] / f[cur[down]]) ** -d["price_response"]
    own = owner[down]
    # 1.1: where the home passes tax-free to an heir who lives in it, selling it turns exempt equity into taxable cash
    p_occ, _ = soc.home_exemption()
    if p_occ > 0:
        cost = p_occ * soc.inheritance_rules()[0] * p["inheritance"]["valuation_share"]
        h = np.where(own, h * max(0.0, 1 - p["inheritance"]["downsize_deterrence"] * cost), h)
    sale = v[down] * hp[down] * f[cur[down]]
    worth = sale - hh_sum(soc, "mortgage_debt", L) - hh_sum(soc, "lien", L)
    h = np.where(own & (worth < d["min_equity"]), 0.0, h)
    h = np.where(own, h, h * d["renter_share"])
    go = rng.random(len(down)) < np.minimum(h, .9)
    if not go.any():
        return
    D = down[go]
    L, a, own = lead[D], age[D], owner[D]
    lo = np.maximum(nd[D], cur[D] - d["max_steps_down"])
    t = choose_size(soc, lo, cur[D] - 1, rng).astype(int)
    if own.any():
        Lo, to, ao = L[own], t[own], a[own]
        hd = hp[D][own]
        sale = (v[D] * hp[D] * f[cur[D]])[own]
        buy = np.minimum(soc.size_value[to] * hd * f[to], (1 - d["min_release"]) * sale)
        cash = sale - buy - d["transaction_cost"] * sale
        db = hh_sum(soc, "mortgage_debt", Lo)
        cl = hh_sum(soc, "lien", Lo)
        repay = np.clip(cash, 0, db)
        cash, db = cash - repay, db - repay
        back = np.clip(cash, 0, cl)
        cash = np.maximum(cash - back, 0)
        soc.claims_repaid += float(back.sum())
        _clear_claims(soc, Lo)
        A["lien"][Lo] = cl - back                  # what the sale did not cover stays on the new home
        _set_home(soc, Lo, buy / (hd * f[to]), db, to.astype(np.int8))
        A["equity_annuity"][Lo] += d["annuitised_share"] * cash \
            * annuity_factor(np.maximum(ao, 60), d["annuity_real_rate"]) / 12
        rest = (1 - d["annuitised_share"]) * cash
        pa = A["partner"][Lo]
        has = pa >= 0
        A["wealth"][Lo] += np.where(has, rest / 2, rest)
        A["wealth"][pa[has]] += rest[has] / 2
        soc.equity_released += float(cash.sum())
        soc.downsizers += int((ao >= 67).sum())
        soc.anticipating += int(((ao >= 55) & (ao < 67)).sum())
    if (~own).any():
        _set_class(soc, L[~own], t[~own].astype(np.int8))
    soc.moves_down += int(go.sum())


# ------------------------------------------------------------------ claims on homes
def floor_lending(soc, idx, floor_paid):
    """The part of this year's top-up lent against homes under policy.floor_loan: paid to owners 67+, up to
    `floor_loan_ltv` of their equity less what is already claimed. Returns the people and the amounts, 2025 krónur a
    year. Pure: the accounts read it, and accrue_claims books it once a year."""
    A, pol = soc.A, soc.p["policy"]
    if pol["regime"] != "platform" or not pol.get("floor_loan", 0.0) or "lien" not in A or not len(idx):
        return np.zeros(0, int), np.zeros(0)
    own = (A["home_value"][idx] > 0) & (A["age"][idx] >= 67) & (np.asarray(floor_paid) > 0)
    j = idx[own]
    paid = np.asarray(floor_paid)[own] * 12 / max(soc.price, .1)
    equity = np.maximum(A["home_value"][j] * price_factor(soc, j) - A["mortgage_debt"][j], 0)
    room = np.maximum(pol.get("floor_loan_ltv", .5) * equity - A["lien"][j], 0)
    return j, np.minimum(paid, room)


def accrue_claims(soc):
    """Once a year, after the accounts: claims carry the state's long real rate, and this year's lending (the
    top-up lent, as the accounts took it) and the deferred property tax are added."""
    A, pol = soc.A, soc.p["policy"]
    ensure(soc)
    r = max(float(getattr(soc.macro, "r_long", 0.0)), 0.0)
    A["lien"] *= 1 + r
    j, lend = getattr(soc, "_lending", (np.zeros(0, int), np.zeros(0)))
    if len(j):
        A["lien"][j] += lend
        soc.claims_new += float(lend.sum())
    soc._lending = (np.zeros(0, int), np.zeros(0))
    if pol["regime"] == "platform" and pol.get("defer_pensioner_property_tax", 0.0):
        payer = np.flatnonzero(A["alive"] & ~A["renter"] & (A["age"] >= 18) & ((A["partner"] < 0) | (A["sex"] == 1)))
        payer = payer[soc.property_deferred(payer)]
        if len(payer):
            _, _, owner_tax = soc.macro.housing_costs()
            deferred = owner_tax * soc.home_value_weight(payer) * 12         # 2025 krónur a year
            A["lien"][payer] += deferred
            soc.claims_new += float(deferred.sum())


def settle_estates(soc, dead):
    """At death: a partner takes over the home, its claim and the income from released equity."""
    A = soc.A
    if "lien" not in A or not len(dead):
        return
    heirs = A["partner"][dead]
    has = heirs >= 0
    np.add.at(A["lien"], heirs[has], A["lien"][dead[has]])
    np.add.at(A["equity_annuity"], heirs[has], A["equity_annuity"][dead[has]])
    A["lien"][dead[has]] = 0.0
    A["equity_annuity"][dead] = 0.0
    if has.any():
        A["widowed_at"][heirs[has]] = soc.year


def recover_from_estates(soc, alone, estate):
    """Claims repaid from estates with no partner, before tax; what an estate cannot cover is written off."""
    A = soc.A
    if "lien" not in A or not len(alone):
        return estate
    claim = A["lien"][alone]
    back = np.minimum(claim, np.maximum(estate, 0))
    soc.claims_repaid += float(back.sum())
    soc.claims_written_off += float((claim - back).sum())
    A["lien"][alone] = 0.0
    return estate - back


def write_off_leavers(soc, idx):
    """Anyone who leaves: a claim not settled from an estate is written off (emigrants), and the dwelling leaves the
    ladder with them."""
    A = soc.A
    if "lien" not in A or not len(idx):
        return
    soc.claims_written_off += float(A["lien"][idx].sum())
    A["lien"][idx] = 0.0
    A["equity_annuity"][idx] = 0.0
    A["hclass"][idx] = -1


def snapshot(soc):
    A = soc.A
    if "hclass" not in A:
        return {}
    alive = A["alive"]
    f = factors(soc)
    occ = occupancy(soc)
    base = np.maximum(soc.size_occ0, 1)
    tight = (occ / base) / np.maximum(soc.size_stock / base, 1e-6)
    lead = households(soc)
    nd = need(soc, lead)
    cur = A["hclass"][lead]
    return {**{f"housing_price_size{j}": float(soc.macro.house_price * f[j]) for j in range(K)},
            **{f"housing_tightness_size{j}": float(tight[j]) for j in range(K)},
            **{f"housing_factor_size{j}": float(f[j]) for j in range(K)},
            "housing_studio_rent_index": float(soc.macro.rent * f[0]),
            "dwellings_converted": float(getattr(soc, "size_converted", 0.0)),
            "housing_crowded_share": float(np.mean(cur < nd)) if len(lead) else np.nan,
            "housing_spare_room_share": float(np.mean(cur > nd)) if len(lead) else np.nan,
            "moves_up": int(soc.moves_up), "moves_down": int(soc.moves_down),
            "downsizers": int(soc.downsizers), "downsizers_anticipating": int(soc.anticipating),
            "equity_released_bn": float(soc.equity_released / 1e9),
            "equity_annuity_bn": float(A["equity_annuity"][alive].sum() * 12 / 1e9),
            "claims_outstanding_bn": float(A["lien"][alive].sum() / 1e9),
            "claims_new_bn": float(soc.claims_new / 1e9),
            "claims_repaid_bn": float(soc.claims_repaid / 1e9),
            "claims_written_off_bn": float(soc.claims_written_off / 1e9),
            "heirs_moved_in": int(getattr(soc, "heirs_moved_in", 0)),
            "homes_held_by_heirs": int(((A["home_lock"] > soc.year) & alive).sum()) if "home_lock" in A else 0}
