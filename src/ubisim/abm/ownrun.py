"""2.1: the owner-run form of the trades households buy from (params "owner_run").

When pay is set by what it takes to get people to do a job, an employer whose staff cost more sells less, and
in a restaurant, a shop or a cleaning firm the employer's margin is thin enough that some close. The customers do
not stop wanting a meal or a haircut. Part of what employers drop is taken up by people running the business
themselves: a family inn, a cook with a small place of their own, a driver with their own van. The owner keeps what
an absentee owner took and pays the rent, and works without a boss.

The form exists today in every one of these trades (the labour survey's self-employed shares, below), so the
model does not invent it. What the reform changes is how much of the trade's work takes it:

* The share of a trade's work done on own account starts at today's and rises as employers are priced out,
  towards `max_share`: s = s0 * v + (max_share - s0 * v) * (1 - wage_rel ** -opening), for wage_rel above 1,
  where wage_rel is the profession's pay against what it produces, as labour demand reads it, and v the rent
  term below.
* An hour sold by an owner costs the customer less than an employer's hour of the same pay, by the share of the
  gross operating surplus that is the owner's return over capital costs (`margin_kept`), so the trade's demand
  for work falls less than employers' alone would: D = D0 * [(1 - s) w ** -e + s (w / a) ** -e], normalised to
  today's at today's share and pay.
* Rent is a larger part of an owner's margin than of the takings. Cheaper commercial space (the cap on owning it,
  policy.commercial_ownership_cap) widens the margin by rent's share of takings times the fall in rent, and the
  share who can make a go of it with it (v).
* Owner-run work is less strain: the trade's disamenity falls with the share of it done on own account beyond
  today's (`strain_relief`).

Data: today's shares are Eurostat's labour-force survey for Iceland, self-employed by occupation (lfsa_esgais,
2022-24: service and sales workers 5.6%, elementary 5.7%, machine operators and drivers 16.9%, craft workers
21.6%; by activity, lfsa_esgan2, accommodation and food is 8.9%, most of it guesthouses); the margins are gross operating surplus over employee benefits expense by
activity in Eurostat's structural business statistics for Iceland (sbs_ovw_act), 2023-24. Restaurants and bars
(I56) 0.18, retail (G47) 0.37 and personal services (S96) 0.46, cleaning (N81) 0.23, land transport (H49) 0.52,
construction (F) 0.53. Rent is about a tenth of a restaurant's takings, and purchases half of them, so about a fifth
of its value added, which is what `rent_share` counts.

At today's rules every term is exactly today's: s = s0 and a cheaper hour that was already there.
"""
import numpy as np

from ubisim.abm.params import OCCUPATIONS, N_OCC


def _arrays(p):
    o = p["owner_run"]
    s0, mu, rent = np.zeros(N_OCC), np.zeros(N_OCC), np.zeros(N_OCC)
    for name, t in o["trades"].items():
        j = OCCUPATIONS.index(name)
        s0[j], mu[j], rent[j] = t["share"], t["margin"], t["rent_share"]
    return o, s0, mu, rent


def rent_relief(soc):
    """How far commercial rent sits below today's, as the cap on owning commercial space brings it (0 today)."""
    po = soc.p["property_ownership"]
    com = getattr(soc.macro, "commercial_rent", 1 + po["commercial_markup"]) / (1 + po["commercial_markup"])
    return float(np.clip(1 - com, -.5, .5))


def terms(soc, wage_rel):
    """Own-account share of each trade's work, the price advantage of an owner's hour, and today's of both."""
    o, s0, mu, rent = _arrays(soc.p)
    if not o["enabled"]:
        return np.zeros(N_OCC), np.ones(N_OCC), np.zeros(N_OCC), np.ones(N_OCC)
    kept = o["margin_kept"] * mu
    saved = rent * (1 + mu) * rent_relief(soc)
    v = np.where(kept > 0, (kept + saved) / np.maximum(kept, 1e-9), 1.0)
    w = np.maximum(np.asarray(wage_rel, float), 1e-9)
    base = np.minimum(s0 * v, o["max_share"])
    opened = (o["max_share"] - base) * np.clip(1 - w ** -o["opening"], 0, 1)
    share = np.where(s0 > 0, base + opened, 0.0)
    adv = (1 + mu) / np.maximum((1 + mu - kept) * (1 - rent * rent_relief(soc)), 1e-9)
    adv0 = (1 + mu) / (1 + mu - kept)
    return share, adv, s0, adv0


def demand_factor(soc, wage_rel, elasticity):
    """Private demand for each profession's work against today's, with the trades' owner-run part: wage_rel ** -e
    where there is none."""
    share, adv, s0, adv0 = terms(soc, wage_rel)
    w = np.maximum(np.asarray(wage_rel, float), 1e-9)
    soc.own_share = share
    mixed = (1 - share) * w ** -elasticity + share * (w / adv) ** -elasticity
    norm = (1 - s0) + s0 * adv0 ** elasticity
    return np.where(s0 > 0, mixed / norm, w ** -elasticity)


def strain_factor(soc):
    """What owner-run work takes off each profession's disamenity, as a factor (1 today)."""
    o, s0, _, _ = _arrays(soc.p)
    share = np.asarray(getattr(soc, "own_share", s0), float)
    return 1 - o["strain_relief"] * np.clip(share - s0, 0, 1)


def heads(soc):
    """People in the trades working on their own account, by profession: the share of those working there."""
    from ubisim.abm.model import PART, FULL
    A = soc.A
    o, s0, _, _ = _arrays(soc.p)
    share = np.asarray(getattr(soc, "own_share", s0), float)
    working = A["alive"] & np.isin(A["status"], [PART, FULL])
    return share * np.bincount(A["occupation"][working], minlength=N_OCC)
