"""1.1: the career ladder — experience, first jobs, and what machines do to them.

Experience is built by working. Each person carries the years they have worked and how far they stand from where
people of their age and schooling stood in the base year (`exp_gap`): a year out of work while others work puts
them behind, a year studying keeps them where they were. Pay follows the gap (`careers.return_per_year`), so a cohort
that could not find first jobs earns less for years after — the scarring found for those who start work in a
slump (Kahn 2010; Oreopoulos, von Wachter and Heisz 2012) — and output follows the experience of those working.
At the start every gap is zero, so the base year and its calibration are untouched.

First jobs. Where machines take entry-level work faster than the rest of a profession's work
(automation.junior_hiring), fewer juniors are taken on: someone with less than `entry_years` of experience who
takes a new job is turned away with the share of hiring that has gone, and looks again next year, as anyone out of
work involuntarily does. Experienced workers are not let go for it; what is lost is the ladder's bottom rung. The
state can pay part of a junior's wage in the professions where this happens (`policy.junior_wage_subsidy`), which
makes a junior cheaper against the machine.

Indicators, not forecasts: people of 20-29 neither working, studying nor disabled, how often a junior who looks for a first job
finds one, the earnings of the young against the middle-aged, the spread of pay, the share of workers in the
professions office AI reaches most.
"""
import numpy as np

from ubisim.abm.population import FULL, INDEP, PART, VENTURE

AGES = np.arange(16, 67)


def work_years(soc, status):
    """A year's experience by status: a full-time job or a firm one year, part-time and self-directed work less."""
    b = soc.p["behaviour"]
    return np.select([status == FULL, status == VENTURE, status == PART, status == INDEP],
                     [1.0, 1.0, b["part_time_hours"], b["independent_hours"]], 0.0)


def ensure(soc):
    """Experience for the population as drawn, and provisional rates of gaining it (model.calibrate replaces them with
    the base year's as a year of the status quo runs them, rates())."""
    A, c = soc.A, soc.p["careers"]
    n = len(A["alive"])
    if "experience" not in A:
        start = np.where(A["education"] >= 2, 23.0, 18.0)
        A["experience"] = (np.clip(A["age"] - start, 0, 50) * c["initial_work_share"]).astype(np.float32)
        A["exp_gap"] = np.zeros(n, np.float32)
    soc.exp_rate0 = rates(soc)
    reset_year(soc)


def rates(soc):
    """Years of experience gained in a year, by age and schooling, among those not disabled and not studying, as
    the society stands at the end of a year — after the year's separations, which the population as drawn has not
    had (measured on it, every age fell short of its own base year by 3-13% of a year in the first year)."""
    A = soc.A
    live = A["alive"] & ~A["disabled"] & (A["age"] >= 16) & (A["age"] <= 66)
    rate = np.zeros((len(AGES), 3))
    yrs = work_years(soc, A["status"])
    for e in range(3):
        for k, a in enumerate(AGES):
            m = live & (A["age"] == a) & (np.minimum(A["education"], 2) == e) & (A["studying"] <= 0)
            rate[k, e] = float(yrs[m].mean()) if m.sum() >= 5 else np.nan
        col = rate[:, e]                    # a thin cell takes its neighbours' rate
        good = ~np.isnan(col)
        rate[:, e] = np.interp(np.arange(len(AGES)), np.flatnonzero(good), col[good]) if good.any() else 0.0
    return rate


def reset_year(soc):
    soc.junior_seekers = 0
    soc.junior_turned_away = 0
    soc.junior_subsidy_bn = 0.0


def wage_factor(soc, idx):
    """Pay against the person's own, for experience gained or lost since the base year."""
    A, c = soc.A, soc.p["careers"]
    if "exp_gap" not in A:
        return 1.0
    return np.clip(1 + c["return_per_year"] * A["exp_gap"][idx], c["min_factor"], c["max_factor"])


def junior_hiring(soc):
    """Share of juniors each profession takes on, with any wage subsidy for them."""
    h = soc.automation.junior_hiring()
    s = junior_subsidy_rate(soc)
    if s > 0:
        # a junior paid partly by the state costs the firm less against the machine
        h = 1 - (1 - h) * (1 - s) ** soc.p["automation"]["wage_sensitivity"]
    return h


def junior_subsidy_rate(soc):
    pol = soc.p["policy"]
    return min(float(pol.get("junior_wage_subsidy", 0.0)), .9) if pol["regime"] == "platform" else 0.0


def is_junior(soc, idx):
    return soc.A["experience"][idx] < soc.p["careers"]["entry_years"]


def ration_first_jobs(soc, took_job):
    """Juniors taking a new job where machines took the entry-level work: some are turned away."""
    A, rng = soc.A, soc.rng
    if not len(took_job) or "experience" not in A:
        return took_job[:0]
    juniors = took_job[is_junior(soc, took_job)]
    soc.junior_seekers += int(len(juniors))
    h = junior_hiring(soc)
    if not len(juniors) or h.min() >= 1 - 1e-9:
        return juniors[:0]
    away = juniors[rng.random(len(juniors)) >= h[A["occupation"][juniors]]]
    soc.junior_turned_away += int(len(away))
    return away


def accrue(soc):
    """A year's experience, and where it leaves each person against the base year's path."""
    A = soc.A
    if "experience" not in A:
        return
    live = np.flatnonzero(A["alive"] & ~A["disabled"] & (A["age"] >= 16) & (A["age"] <= 66))
    yrs = work_years(soc, A["status"][live])
    A["experience"][live] += yrs.astype(np.float32)
    k = np.clip(A["age"][live], 16, 66) - 16
    expected = soc.exp_rate0[k, np.minimum(A["education"][live], 2)]
    # a year studying keeps a person on their path; the degree's premium is paid on finishing (step_education)
    change = np.where(A["studying"][live] > 0, 0.0, yrs - expected)
    c = soc.p["careers"]
    A["exp_gap"][live] = np.clip(A["exp_gap"][live] + change, -c["max_gap"], c["max_gap"] / 2).astype(np.float32)


def output_factor(soc):
    """Output per hour against the base year, from the experience of those working."""
    A, c = soc.A, soc.p["careers"]
    if "exp_gap" not in A:
        return 1.0
    w = A["alive"] & np.isin(A["status"], [PART, FULL, VENTURE])
    if not w.any():
        return 1.0
    hrs = work_years(soc, A["status"][w])
    gap = float(np.average(A["exp_gap"][w], weights=np.maximum(hrs, 1e-6)))
    return float(np.clip(1 + c["return_per_year"] * gap, c["min_factor"], c["max_factor"]))


def subsidy_cost(soc, idx, gross):
    """What paying part of juniors' wages costs this year, ma.kr. of today: juniors in the professions where machines
    take entry-level work (automation.junior_hiring below 1)."""
    s = junior_subsidy_rate(soc)
    A = soc.A
    if s <= 0 or "experience" not in A:
        return 0.0
    squeezed = soc.automation.junior_hiring() < 1 - 1e-6
    w = np.isin(A["status"][idx], [PART, FULL]) & is_junior(soc, idx) & squeezed[A["occupation"][idx]] \
        & ~A["public"][idx]
    return float(s * gross[w].sum() * 12 / 1e9)


def snapshot(soc):
    A = soc.A
    if "experience" not in A:
        return {}
    alive = A["alive"]
    age = A["age"]
    # 20-29: under 20 most are at upper-secondary school, which the model does not follow year by year
    young = alive & (age >= 20) & (age <= 29)
    working = np.isin(A["status"], [PART, FULL, VENTURE, INDEP])
    neet = young & ~working & (A["studying"] <= 0) & ~A["disabled"]
    gross = getattr(soc, "_gross_by_agent", None)
    ratio = np.nan
    p90_50 = p50_10 = np.nan
    if gross is not None:
        emp = alive & np.isin(A["status"], [PART, FULL]) & (gross > 0)
        hrs = work_years(soc, A["status"])
        hourly = np.where(emp, gross / np.maximum(hrs, 1e-6), 0.0)
        y, m = emp & (age >= 25) & (age <= 34), emp & (age >= 45) & (age <= 54)
        if y.any() and m.any():
            ratio = float(hourly[y].mean() / hourly[m].mean())
        if emp.sum() > 20:
            q10, q50, q90 = np.percentile(hourly[emp], [10, 50, 90])
            p90_50, p50_10 = float(q90 / q50), float(q50 / max(q10, 1.0))
    exposed = soc.automation.exposure_ai >= .4
    workers = alive & np.isin(A["status"], [PART, FULL])
    seekers = max(int(soc.junior_seekers), 1)
    return {"neet_rate": float(neet.sum() / max(young.sum(), 1)),
            # the share not working, studying or not: what the labour force survey's figure can be set against
            # (quality_check), since the model follows tertiary courses only
            "not_employed_20_29": float((young & ~working).sum() / max(young.sum(), 1)),
            "junior_hire_rate": 1 - soc.junior_turned_away / seekers if soc.junior_seekers else 1.0,
            "juniors_turned_away": int(soc.junior_turned_away),
            "experience_gap_25_34": float(A["exp_gap"][alive & (age >= 25) & (age <= 34)].mean()),
            "young_to_midlife_pay": ratio, "wage_p90_p50": p90_50, "wage_p50_p10": p50_10,
            "ai_exposed_worker_share": float((workers & exposed[A["occupation"]]).sum() / max(workers.sum(), 1)),
            "junior_subsidy_bn": float(soc.junior_subsidy_bn),
            "experience_output_factor": output_factor(soc)}
