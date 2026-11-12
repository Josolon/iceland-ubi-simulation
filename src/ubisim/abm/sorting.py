"""2.1: which profession to work in, chosen in the haggling round (policy.wage_reset).

The first build of the round let everyone decide again whether to work, but not where. Supply could not move
between professions, so the round inverted the pay structure: cooks and clerks ended at about five times their
pay with far more of them than jobs, engineers and managers at less with too few (docs/JOB_TRAITS.md).

Here each person also chooses a profession, among those their education allows. Licensed professions take no
newcomers within the round. A profession is worth what the whole choice is worth in it: the expected best of
not working, part time, full time, a firm or self-directed work, at its pay, its meaning and its strain. What
counts is what a job there adds over doing without one, the surplus (Society.job_surplus). The choice is a logit
with

    value of j for i = scale * log(surplus_ij) + constant[education_i, j] - switch * (j is not i's profession now)

The surplus enters as a log so the constants scale it rather than add to it. A first build added the constants
to the worth itself. A payment shrinks every job's money advantage, and the constants, fitted where pay
differences were large, then dominated: people flowed to today's low-paid professions whatever they paid, and
refuse collectors' pay went to almost nothing. With the log, shrinking every surplus in the same proportion
moves nobody; what moves people is a job losing more of its surplus than the others, as an unpleasant, poorly
paid one does when not working pays.

The constants are fitted so that under today's rules and today's pay the expected number in each profession, at
each level of education, is today's. `switch` is set so that the share who would move in such a round is
`labour.sorting_switch_share`, and `scale` so that a profession's headcount answers its pay against the rest
with `labour.sorting_elasticity`. All three are fitted once, on the status quo; the reform then moves people
only through what it changes in each profession's worth: pay, the payment, taxes, prices. With nothing changed,
nobody moves.

What this cannot tell apart: a profession few people of a given education are in may be one they dislike or one
they cannot get into (talent, hiring, place). The constants hold both, as if the first. docs/REVIEW.md §6.
"""
import numpy as np

from ubisim.abm import params as P
from ubisim.abm.params import N_OCC, OCCUPATIONS

FIELDS = ("occupation", "base_wage", "meaning", "public", "contract_end", "tenure")


def population(soc, reopt):
    """Who chooses a profession in the round: of working age and able to switch, not running a firm or studying.
    Those out of work choose too; their profession is the one they would look for work in."""
    A = soc.A
    ok = (A["age"][reopt] >= 20) & (A["age"][reopt] <= 59) & (A["venture"][reopt] < 0) \
        & ~A["disabled"][reopt] & (A["studying"][reopt] <= 0)
    return reopt[ok]


def open_to(soc, idx, own):
    """Which professions each person may choose: their own, and any other their education allows that is not
    licensed."""
    edu = soc.A["education"][idx]
    lic = np.isin(OCCUPATIONS, P.LICENSED_PROFESSIONS)
    M = (edu[:, None] >= soc.min_edu[None, :]) & ~lic[None, :]
    M[np.arange(len(idx)), own] = True
    return M


def restore(soc, idx, origin):
    for k in FIELDS:
        soc.A[k][idx] = origin[k]


def worth(soc, idx, origin, M, omega, price, per_mother):
    """Each person's log job surplus in each profession open to them (-inf where closed). Someone trying another
    profession keeps their standing within it, less `switch_wage_loss`, on a new contract, as a private employee;
    their sense of the work's meaning moves by the difference in the professions' meaning."""
    A, lab = soc.A, soc.p["labour"]
    traits = np.array(P.trait(1))
    med = soc.occ_median
    own = origin["occupation"]
    V = np.full((len(idx), N_OCC), -np.inf)
    try:
        for j in range(N_OCC):
            r = np.flatnonzero(M[:, j])
            if not len(r):
                continue
            who, o = idx[r], own[r]
            other = o != j
            A["occupation"][who] = j
            A["base_wage"][who] = origin["base_wage"][r] * np.where(
                other, med[j] / np.maximum(med[o], 1e-9) * (1 - lab["switch_wage_loss"]), 1.0)
            A["meaning"][who] = np.where(other, np.clip(origin["meaning"][r] + traits[j] - traits[o], 0, 1),
                                         origin["meaning"][r])
            A["public"][who] = origin["public"][r] & ~other
            A["contract_end"][who] = np.where(other, np.minimum(origin["contract_end"][r], soc.year),
                                              origin["contract_end"][r])
            V[r, j] = np.log(np.maximum(soc.job_surplus(who, omega, price, per_mother), 1e-30))
    finally:
        restore(soc, idx, origin)
    return V


def shares(V, scale, const, switch, edu, own):
    """Choice probabilities over professions."""
    X = scale * V + const[edu] - switch * (np.arange(N_OCC)[None, :] != own[:, None])
    X = np.where(np.isfinite(V), X, -np.inf)
    X -= X.max(1, keepdims=True)
    E = np.exp(X)
    return E / E.sum(1, keepdims=True)


def fit_constants(V, scale, switch, edu, own, rounds=300, start=None):
    """Constants per education level and profession that make the expected headcounts today's. `start`: constants
    to begin from (a nearby fit), which only saves rounds."""
    target = np.zeros((3, N_OCC))
    np.add.at(target, (edu, own), 1.0)
    level = (np.arange(3)[:, None] == edu[None, :]).astype(float)
    const = np.where(target > 0, 0.0 if start is None else start, -50.0)
    for _ in range(rounds):
        S = shares(V, scale, const, switch, edu, own)
        got = level @ S
        step = np.where(target > 0, np.log(np.maximum(target, 1e-9) / np.maximum(got, 1e-9)), 0.0)
        const += step
        if np.abs(step).max() < 1e-4:
            break
    return const


def calibrate(soc, idx, origin, M, omega, price, per_mother):
    """Fit scale, switching cost and constants on today's rules: the worths are computed with the reform's
    policy set aside for the status quo's, at today's pay. Returns them and the status quo's shares."""
    lab, pol = soc.p["labour"], soc.p["policy"]
    saved = pol["regime"]
    pol["regime"] = "status_quo"
    try:
        V0 = worth(soc, idx, origin, M, omega, price, per_mother)
        # how each worth answers 5% more pay in that profession (a profession's pay moves only its own column)
        V1 = worth(soc, idx, origin, M, omega * 1.05, price, per_mother)
    finally:
        pol["regime"] = saved
    edu, own = soc.A["education"][idx], origin["occupation"]
    open_to = np.isfinite(V0)
    dV = np.divide(np.subtract(V1, V0, out=np.zeros_like(V0), where=open_to), np.log(1.05))
    # scale and switching cost are two numbers, fitted on a sample; the constants on everyone
    sub = np.sort(np.random.default_rng(7).choice(len(idx), min(len(idx), 12000), replace=False))
    v, e, o, g = V0[sub], edu[sub], own[sub], dV[sub]
    scale, switch, avg, moving, c = 1.0, 3.0, 0.0, 0.0, None

    def movers(switch, c):
        c = fit_constants(v, scale, switch, e, o, rounds=40, start=c)
        S = shares(v, scale, c, switch, e, o)
        return 1 - S[np.arange(len(sub)), o].mean(), c, S

    prev, hi0 = None, 40.0
    for _ in range(12):
        # the switching cost is in the same units as scale × worth, so it grows with scale: widen the bracket
        # until it holds the target
        lo, hi = 0.0, hi0
        while hi < 1e5:
            moving, c, S = movers(hi, c)
            if moving <= lab["sorting_switch_share"]:
                break
            lo, hi = hi, hi * 2
        for _ in range(10):     # to 1/1024 of the bracket
            switch = (lo + hi) / 2
            moving, c, S = movers(switch, c)
            lo, hi = (switch, hi) if moving > lab["sorting_switch_share"] else (lo, switch)
        heads = S.sum(0)
        # own-pay elasticity of a profession's expected headcount, averaged over professions by size
        el = scale * (S * (1 - S) * g).sum(0) / np.maximum(heads, 1e-9)
        avg = float(np.average(el, weights=heads))
        # the elasticity rises ever more slowly with the scale, so step on the log-log secant once there are
        # two points (the plain ratio step crawls)
        miss = np.log(lab["sorting_elasticity"] / max(avg, 1e-9))
        bend = 1.0 if prev is None else np.clip((np.log(avg) - prev[1]) / (np.log(scale) - prev[0]), .1, 2.0)
        if abs(miss) < .01:
            break
        prev = (np.log(scale), np.log(avg))
        new = scale * float(np.exp(np.clip(miss / bend, -2.0, 2.0)))
        hi0 = max(40.0, 1.5 * switch * new / scale)
        scale = new
    const = fit_constants(V0, scale, switch, edu, own, start=c)
    soc.sorting_fit = {"scale": float(scale), "switch": float(switch), "elasticity": avg, "moving": float(moving)}
    return scale, switch, const, shares(V0, scale, const, switch, edu, own), dV


def begin(soc, reopt, per_mother, omega, price):
    """At the start of the round, before the agreements end: who chooses, what they start from, and the choice
    fitted on today's rules."""
    idx = population(soc, reopt)
    origin = {k: soc.A[k][idx].copy() for k in FIELDS}
    M = open_to(soc, idx, origin["occupation"])
    scale, switch, const, S0, dV = calibrate(soc, idx, origin, M, omega, price, per_mother)
    soc._sorting = {"idx": idx, "origin": origin, "M": M, "scale": scale, "switch": switch, "const": const,
                    "S0": S0, "dV": dV, "draw": soc.rng.random(len(idx)), "draw2": soc.rng.random(len(idx)), "S": None}



def expected_heads(st, S):
    """Each profession's expected headcount among those choosing, if they chose by the shares S: the moves
    reallocate makes, in expectation over the draws."""
    own, S0 = st["origin"]["occupation"], st["S0"]
    rows = np.arange(len(own))
    leave_p = np.clip(1 - S[rows, own] / np.maximum(S0[rows, own], 1e-12), 0, 1)
    gain = np.maximum(S - S0, 0)
    gain[rows, own] = 0
    tot = gain.sum(1)
    leave_p = np.where(tot > 0, leave_p, 0.0)
    return np.bincount(own, weights=1 - leave_p, minlength=N_OCC) \
        + (gain * (leave_p / np.maximum(tot, 1e-300))[:, None]).sum(0)


def anticipated_moves(soc, omega):
    """How many more people each profession would have, if pay were omega and everyone chose at it: the worths of
    the last sweep, moved by how each answers its profession's pay. 0 before the first sweep. The choice counted
    on is the undamped one, where the sweeps are headed: counting the damped one, half of which is last sweep's
    choice whatever the pay, left supply that no pay could lower, and pay fell to the bottom of its range
    (refuse collectors to 0.02 times today's rate, 2026-10-30)."""
    st = soc._sorting
    if st.get("V") is None:
        return np.zeros(N_OCC)
    V = st["V"] + st["dV"] * (np.log(np.maximum(omega, 1e-9)) - st["at"])[None, :]
    S = shares(V, st["scale"], st["const"], st["switch"], soc.A["education"][st["idx"]], st["origin"]["occupation"])
    return expected_heads(st, S) - st["heads"]

def reallocate(soc, omega, price, per_mother, damping=None):
    """Choose professions at this round's pay and move people accordingly, from where they started the round.
    Each person's draw is the same in every sweep, so the allocation moves only as the shares do."""
    st = soc._sorting
    idx = st["idx"]
    # the contracts the round ended stay ended
    origin = dict(st["origin"], contract_end=np.minimum(st["origin"]["contract_end"], soc.year))
    restore(soc, idx, origin)
    V = worth(soc, idx, origin, st["M"], omega, price, per_mother)
    edu, own = soc.A["education"][idx], origin["occupation"]
    S = shares(V, st["scale"], st["const"], st["switch"], edu, own)
    d = soc.p["labour"]["sorting_damping"] if damping is None else damping
    if st["S"] is not None:
        S = (1 - d) * st["S"] + d * S
    st["S"], st["V"], st["at"] = S, V, np.log(np.maximum(omega, 1e-9))
    st["heads"] = expected_heads(st, S)
    # Who moves: only what the reform changed. A person leaves with the share by which their own profession's
    # pull fell against the status quo's, and goes where the pull rose.
    rows = np.arange(len(idx))
    S0 = st["S0"]
    leave_p = np.clip(1 - S[rows, own] / np.maximum(S0[rows, own], 1e-12), 0, 1)
    gain = np.maximum(S - S0, 0)
    gain[rows, own] = 0
    tot = gain.sum(1)
    leave = (st["draw"] < leave_p) & (tot > 0)
    pos = st["draw"] / np.maximum(leave_p, 1e-12) * tot
    dest = np.minimum((np.cumsum(gain, 1) < pos[:, None]).sum(1), N_OCC - 1)
    dest = np.where(leave, dest, own)
    moved = dest != own
    who, to, frm = idx[moved], dest[moved], own[moved]
    A, lab = soc.A, soc.p["labour"]
    traits = np.array(P.trait(1))
    med = soc.occ_median
    pub_share = soc.D0_pub / np.maximum(soc.D0_pub + soc.D0_priv, 1e-9)
    A["base_wage"][who] *= med[to] / np.maximum(med[frm], 1e-9) * (1 - lab["switch_wage_loss"])
    A["meaning"][who] = np.clip(A["meaning"][who] + traits[to] - traits[frm], 0, 1)
    A["occupation"][who] = to
    A["public"][who] = st["draw2"][moved] < pub_share[to]
    A["tenure"][who] = 0
    st["moved"] = int(moved.sum())
    st["flows"] = np.histogram2d(frm, to, bins=[np.arange(N_OCC + 1)] * 2)[0]
    return st["moved"]
