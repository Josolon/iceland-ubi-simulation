"""1.1: unpaid care in the family — the time people give a parent, a partner or a disabled child.

Who cares. Iceland's health interview survey of 2019 (EHIS, Eurostat hlth_ehis_ic1e) found a far larger share of
adults caring for a relative at least once a week than the rest of Europe: 22-33% of 16-64 year-olds by age group,
against 8-19% in the EU. Each person has a care tie with the share for their age, picked by a hash of the agent so
it takes no draw from the model's random stream and the population as drawn is untouched; a tie can begin as a
person enters the ages when parents grow old, and ends past them.

How much. Most of that care is light. In EU-SILC 2016 (ilc_ats18) 80% of Iceland's carers gave under ten hours a
week and 6.5% twenty or more — against 61% and 22% in the EU, where formal care is thinner. Carers out of work gave
about an hour a week more than carers in work (7.9 against 6.9 hours, from the bands' midpoints). That gap, not the
level, is what a reform moves: someone who leaves a job gives the hours a carer out of work gives.

What it replaces. Care in the family substitutes for paid help at home, and that substitution fades as need grows
(Bonsang 2009, SHARE: a substitute for paid domestic help, a weak complement to nursing care; Van Houtven and Norton
2004: less home health care, later entry to a nursing home). So hours given beyond the status quo's take the place
of care assistants' hours at `substitution` (EST), and of no other profession's. The status quo is its own
reference, so nothing in it changes; only a reform's departure from it does.

Not modelled: whether a care tie changes the choice to work (the survey shows carers in and out of work in much the
same shares), carers' own health, and long-term care for older people as a sector of its own.
"""
import numpy as np

from ubisim.abm.population import FULL, INDEP, PART, VENTURE


def ties(soc):
    """Who has a care tie this year: the survey's share for their age, picked by a fixed hash of the agent."""
    A, c = soc.A, soc.p["family_care"]
    age = A["age"]
    edges = np.array(c["age_edges"])
    share = np.array(c["weekly_share"])[np.clip(np.searchsorted(edges, age, side="right") - 1, 0, len(edges) - 1)]
    share = np.where((age < edges[0]) | (age >= c["max_age"]), 0.0, share)
    u = (np.arange(len(age)) * 2654435761 % 2 ** 32) / 2 ** 32
    return A["alive"] & (u < share)


def hours(soc):
    """Hours of family care given in a week, all carers together: by whether each carer works, and how much."""
    A, c = soc.A, soc.p["family_care"]
    tied = ties(soc)
    st = A["status"]
    working = np.select([np.isin(st, [FULL, VENTURE]), st == PART, st == INDEP],
                        [1.0, soc.p["behaviour"]["part_time_hours"], soc.p["behaviour"]["independent_hours"]], 0.0)
    h = c["hours_not_working"] + (c["hours_working"] - c["hours_not_working"]) * working
    return float((h * tied).sum())


def replaced_fte(soc):
    """Care assistants' posts that family care beyond the status quo's takes the place of, from last year's hours."""
    if not soc.reference or soc.year < 2 or len(soc.own_history) < soc.year - 1:
        return 0.0
    ref = soc.reference[soc.year - 2] if len(soc.reference) >= soc.year - 1 else None
    own = soc.own_history[soc.year - 2]
    if not ref or "family_care_hours" not in ref or "family_care_hours" not in own:
        return 0.0
    c = soc.p["family_care"]
    # care per carer against the status quo's, for this run's carers: a larger population brings more carers and
    # more people to care for at once, and only the hours each carer gives are the reform's doing
    per = lambda h: h["family_care_hours"] / max(h["family_carers"], 1)
    return c["substitution"] * own["family_carers"] * (per(own) - per(ref)) / c["full_time_week"]


def snapshot(soc):
    hrs = hours(soc)
    return {"family_carers": int(ties(soc).sum()),
            "family_care_hours_week": hrs,
            "family_care_replaced_posts": float(getattr(soc, "family_care_replaced", 0.0))}
