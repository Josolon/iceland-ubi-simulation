"""Synthetic population of Iceland (1:1) built from data/processed/baseline_2025.json."""
import json
import pathlib

import numpy as np

from ubisim.abm import params as P
from ubisim.abm.params import N_OCC

ROOT = pathlib.Path(__file__).resolve().parents[3]
BASELINE = ROOT / "data/processed/baseline_2025.json"

NONWORK, PART, FULL, VENTURE, INDEP = 0, 1, 2, 3, 4   # INDEP: self-directed work with no employer
IS, EEA, NON_EEA = 0, 1, 2
CHARACTERS = ["Student", "Retiree", "Constrained", "Carer", "Founder", "Guest worker",
              "Mobile professional", "Vocation", "Breadwinner", "Balanced"]

# data_prep label order -> model occupation index
OCC_LABELS = ["Legislators and managers", "Professionals", "Associate professionals", "Clerks",
              "Service and sales workers", "Agricultural and fishery workers",
              "Craft and related trades workers", "Plant and machine operators", "Elementary occupations"]
EARN_LABELS = ["Managers (1)", "Professionals (2)", "Technicians and associate professionals (3)", "Clerks (4)",
               "Service workers and shop and market sales workers (5)", "Craft and related trades workers (7)",
               "Craft and related trades workers (7)", "Plant and machine operators and assemblers (8)",
               "Elementary occupations (9)"]
EDU_LABELS = ["Primary and lower sedondary (ISCED 1+2)", "Upper and post sedondary (ISCED 3+4)",
              "Tertiary (ISCED 5+6+7+8)"]
PCT_LABELS = [("10%", .10), ("20%", .20), ("25% (1st quartile)", .25), ("30%", .30), ("40%", .40),
              ("50% (median)", .50), ("60%", .60), ("70%", .70), ("75% (3rd quartile)", .75), ("80%", .80),
              ("90%", .90)]


def load_baseline(p=None):
    """The base year's data: 2025 unless the parameters name another year (base.year) for the backcast."""
    year = ((p or {}).get("base") or {}).get("year")
    path = ROOT / f"data/processed/baseline_{year}.json" if year else BASELINE
    return json.loads(path.read_text())


def band_of(age):
    """0: 16-24, 1: 25-54, 2: 55-66, 3: 67-74, -1 otherwise."""
    return np.select([(age >= 16) & (age <= 24), (age >= 25) & (age <= 54), (age >= 55) & (age <= 66),
                      (age >= 67) & (age <= 74)], [0, 1, 2, 3], -1)


def wage_quantiles(base):
    """Per occupation: (probabilities, monthly ISK) for inverse-CDF sampling of full-time earnings."""
    out = []
    for lab in EARN_LABELS:
        row = base["earnings_2025"][lab]["Total"]
        ps = [.01] + [q for _, q in PCT_LABELS] + [.99]
        vs = [row["10%"] * .75] + [row[l] for l, _ in PCT_LABELS] + [row["90%"] * 1.45]
        out.append((np.array(ps), np.array(vs) * 1000.0))
    return out


def public_share(base):
    out = []
    for lab in EARN_LABELS:
        d = base["earnings_2025"][lab]
        pub, priv = d["Public sector - total"]["Weighted observations"], d["Private sector"]["Weighted observations"]
        out.append(pub / (pub + priv))
    return np.array(out)


def age_wage_factor(age):
    """Pay by age, against a prime-age worker: what the wage survey shows for the same profession at each age. The
    model applies it as people age, not only when the population is drawn — before 2026-09-26 a 22-year-old kept
    the under-25 rate for life, and average pay sank about 0.6% a year as cohorts aged."""
    age = np.asarray(age)
    return np.select([age < 25, age < 35, age < 55, age < 67], [.72, .93, 1.05, 1.02], .95)


def build(p, rng=None):
    rng = rng or np.random.default_rng(p["seed"])
    base = load_baseline(p)

    # ---- age, sex, immigrant background
    ages, sexes, immig = [], [], []
    for s, lab in enumerate(["Males", "Females"]):
        tot, imm = base["population_2026"][lab]["Total"], base["population_2026"][lab].get("Immigrant", {})
        for a, n in tot.items():
            n, k = int(n), int(imm.get(a, 0))
            ages.append(np.full(n, int(a))); sexes.append(np.full(n, s))
            immig.append(np.r_[np.ones(min(k, n), bool), np.zeros(n - min(k, n), bool)])
    A = {"age": np.concatenate(ages).astype(np.int16), "sex": np.concatenate(sexes).astype(np.int8),
         "immigrant": np.concatenate(immig)}
    N = len(A["age"])
    age, sex = A["age"], A["sex"]

    mig = p["migration"]
    cit = np.zeros(N, np.int8)
    cit[A["immigrant"]] = np.where(rng.random(A["immigrant"].sum()) < mig["eea_share_of_immigrants"], EEA, NON_EEA)
    A["citizenship"] = cit
    yrs = np.minimum(rng.geometric(1 / 7.0, N) - 1, age)
    A["years_in_iceland"] = np.where(A["immigrant"], yrs, age).astype(np.int16)

    # ---- education and occupation from employed persons by occupation x education x sex
    emp = base["employment_by_occupation_2025"]
    joint = np.zeros((2, N_OCC, 3))
    for s, lab in enumerate(["Males", "Females"]):
        for o, ol in enumerate(OCC_LABELS):
            for e, el in enumerate(EDU_LABELS):
                joint[s, o, e] = emp[lab][ol][el]
    edu = np.zeros(N, np.int8)
    occ = np.zeros(N, np.int8)
    for s in (0, 1):
        m = sex == s
        pe = joint[s].sum(0) / joint[s].sum()
        e = rng.choice(3, m.sum(), p=pe)
        edu[m] = e
        for ei in range(3):
            mm = np.flatnonzero(m)[e == ei]
            po = joint[s, :, ei] / joint[s, :, ei].sum()
            occ[mm] = rng.choice(N_OCC, len(mm), p=po)
    edu[age < 20] = 0
    young = (age >= 20) & (age <= 24) & (edu == 2)
    edu[young & (rng.random(N) < .6)] = 1

    # ---- profession within the occupation group (VIN02001 weights), respecting education requirements
    profs = base["professions_2025"]
    weights = np.array([pr["weight"] or 0 for pr in profs], float)
    groups = np.array([pr["group"] for pr in profs])
    min_edu = np.array(P.trait(2))
    pay = np.array([pr["median_earnings"] or 0 for pr in profs], float)
    group_med = {g: np.average(pay[groups == g], weights=np.maximum(weights[groups == g], 1e-6)) for g in range(9)}
    prof = np.zeros(N, np.int8)
    for g in range(9):
        members = np.flatnonzero(occ == g)
        cand = np.flatnonzero(groups == g)
        if not len(cand):
            continue
        for e in range(3):
            who = members[edu[members] == e]
            if not len(who):
                continue
            # education is a strong preference, not a gate: people do end up in work they are not trained for
            w = np.maximum(weights[cand], 1e-6) * np.where(min_edu[cand] <= e, 1.0, .12)
            prof[who] = rng.choice(cand, len(who), p=w / w.sum())
    A["education"], A["occupation"] = edu, prof
    occ = prof

    # ---- potential full-time monthly earnings
    # pay: the group's earnings distribution, shifted so each profession's median matches the wage survey
    wq = wage_quantiles(base)
    u = np.clip(rng.random(N) * .9 + .05 + .08 * (edu - 1), .02, .98)
    wage = np.zeros(N)
    for o in range(len(profs)):
        m = occ == o
        if not m.any():
            continue
        g = groups[o]
        scale = (pay[o] / group_med[g]) if group_med[g] else 1.0
        wage[m] = np.interp(u[m], *wq[g]) * scale
    age_factor = age_wage_factor(age)
    sex_factor = np.where(sex == 1, .94, 1.04)
    A["base_wage"] = wage * age_factor * sex_factor
    group_public = public_share(base)
    prof_public = np.array([P.PUBLIC_SHARE_OVERRIDE.get(pr["name"], group_public[pr["group"]]) for pr in profs])
    A["public"] = rng.random(N) < prof_public[occ]

    # ---- initial activity status matching VIN01104 / VIN01006 / VIN00961
    lr = base["labour_rates_2025"]
    band = band_of(age)
    emp_band = {0: lr["16-24 years"]["Employment rate"], 1: lr["25-54 years"]["Employment rate"],
                2: lr["55-74 years"]["Employment rate"]}
    part_band = {0: lr["16-24 years"]["Employed part time"], 1: lr["25-54 years"]["Employed part time"],
                 2: lr["55-74 years"]["Employed part time"]}
    sex_emp = np.array([lr["Males"]["Employment rate"], lr["Females"]["Employment rate"]]) / lr["Total"]["Employment rate"]
    sex_part = np.array([lr["Males"]["Employed part time"], lr["Females"]["Employed part time"]]) / lr["Total"]["Employed part time"]
    # within 55-74 the rate falls steeply with age; relative factors normalised to the band average
    old_rel = np.select([age < 60, age < 65, age < 67, age < 70], [1.35, 1.15, .85, .55], .30)
    m5574 = (age >= 55) & (age <= 74)
    old_rel = old_rel / old_rel[m5574].mean()
    rate = np.zeros(N)
    part = np.zeros(N)
    for b, lab in [(0, 0), (1, 1)]:
        mb = band == b
        rate[mb] = emp_band[lab] / 100 * sex_emp[sex[mb]]
        part[mb] = part_band[lab] / 100 * sex_part[sex[mb]]
    rate[m5574] = emp_band[2] / 100 * sex_emp[sex[m5574]] * old_rel[m5574]
    part[m5574] = part_band[2] / 100 * sex_part[sex[m5574]] * np.where(age[m5574] >= 67, 1.8, 1.0)
    # within 16-24: teenagers work less, early twenties more (EST split of the published band rate)
    m1624 = (age >= 16) & (age <= 24)
    young_rel = np.where(age <= 19, .85, 1.12)
    rate[m1624] *= young_rel[m1624] / young_rel[m1624].mean()
    rate, part = np.clip(rate, 0, .97), np.clip(part, 0, .95)
    # The band and sex adjustments above compound, so the 16-74 total comes out above the published rate. Scale the
    # whole schedule onto VIN01104's total (77.8%), keeping the shape across ages and sexes.
    chooser = (age >= 16) & (age <= 74)
    target = base["labour_rates_2025"]["Total"]["Employment rate"] / 100
    if chooser.any() and rate[chooser].mean() > 0:
        rate = np.clip(rate * target / rate[chooser].mean(), 0, .97)
    # The part-time schedule compounds the same way (band × sex, and more part-time past 67), which put the share
    # of the employed working part-time at 28% against VIN01104's 24.3%. Scaled onto the total likewise.
    part_target = base["labour_rates_2025"]["Total"]["Employed part time"] / 100
    expected = (rate * part)[chooser].sum() / max(rate[chooser].sum(), 1e-9)
    if expected > 0:
        part = np.clip(part * part_target / expected, 0, .95)
    working = (rng.random(N) < rate) & chooser
    status = np.where(working, np.where(rng.random(N) < part, PART, FULL), NONWORK).astype(np.int8)
    A["status"] = status
    A["chooser"] = (age >= 16) & (age <= 74)
    # Scale earnings so the synthetic wage bill equals taxable wages 2025 (TEK02001: 2,174.5 bn ISK).
    hours = np.select([status == FULL, status == PART], [1.0, p["behaviour"]["part_time_hours"]], 0.0)
    base_year = p.get("base") or {}
    A["base_wage"] *= base_year.get("WAGE_BILL0", 2174.5) * 1e9 / 12 / (A["base_wage"] * hours).sum()
    # Public-sector share: the earnings survey over-samples the public sector. Rescale so public wages
    # equal general-government compensation of employees 2025 (THJ05143: 709.6 bn) net of employer
    # pension contributions and payroll tax (~18%).
    pub_wages = (A["base_wage"] * hours * A["public"]).sum() * 12
    keep = min(1.0, (p.get("base") or {}).get("PUBLIC_PAYROLL0", 709.6) * 1e9 / 1.18 / pub_wages)
    A["public"] &= rng.random(N) < keep

    sel = base["self_employed_pct_2025"]
    se_rate = np.select([band == 0, band == 1], [sel["16 to 24 years"], sel["25 to 54 years"]], sel["55 to 74 years"]) / 100
    A["self_employed"] = working & (rng.random(N) < se_rate)

    # disabled / long-term ill: LFS inactive disabled + ill, weighted towards older ages
    inact = base["inactive_2025"]
    n_dis = int(inact["Disabled"] + inact["Ill or temporary unable to work"])
    disabled = np.zeros(N, bool)
    # v9: Tryggingastofnun's register sets the number (29,465 in 2025, disability_register_ratio x the survey's
    # inactive disabled and ill); those beyond the survey's inactive count work, part-time on a partial pension
    # (disability_working_share, about a third). v8 drew everyone above the survey's count from part-time workers at any age: 46% of disabled
    # people worked, three quarters of those under 30, and the earnings test took most of their pension.
    total = int(n_dis * p["benefits"].get("disability_register_ratio", 1.0))
    n_work = int(total * p["benefits"].get("disability_working_share", .2))
    cand = np.flatnonzero((status == NONWORK) & (age >= 20) & (age <= 66))
    w = (age[cand] - 15.0) ** 1.5
    disabled[rng.choice(cand, min(len(cand), total - n_work), replace=False, p=w / w.sum())] = True
    cand = np.flatnonzero((status == PART) & (age >= 20) & (age <= 66))
    w = (age[cand] - 15.0) ** 1.5
    disabled[rng.choice(cand, min(len(cand), n_work), replace=False, p=w / w.sum())] = True
    A["disabled"] = disabled
    A["student"] = ((status == NONWORK) & (age >= 16) & (age <= 24)) | ((status == PART) & (age <= 22) & (rng.random(N) < .5))
    A["retired"] = age >= 67
    # Tertiary students, spread evenly across the years of a course so they do not all graduate at once
    # (Hagstofa SKO00000: 19,528 in tertiary education in 2025).
    A["seed_capital"] = np.zeros(N)   # start-of-life money still in hand
    # Support for those out of work is not one national figure: each municipality sets its own scale for
    # fjárhagsaðstoð, and housing and family circumstances add their own. A single amount for everyone made a whole
    # group cross the fixed poverty line in one year (2051 in the status quo, found 2026-10-02). EST spread.
    A["support_factor"] = np.clip(rng.normal(1.0, p["benefits"].get("support_spread", .12), N), .7, 1.3)
    A["study_years"] = np.zeros(N, np.int16)   # years already spent on the course
    # Health, 1 = well. Starts from disability and declines with age; it then responds to how people live.
    # A person's own constitution is part of it for life (`health_offset`): the yearly dynamics move health towards a
    # ceiling that carries it and the disability, as the drawing does. Without them the dynamics pulled every
    # disabled person back towards full health and washed out the spread, and public health spending fell 28% in
    # ten years of the status quo for nothing but that (found 2026-09-26).
    A["health_offset"] = rng.normal(0, .06, N)
    A["health"] = np.clip(1.0 - p["health"]["disability_penalty"] * A["disabled"]
                          - p["health"]["age_gradient"] * np.maximum(age - 40, 0) + A["health_offset"], .05, 1.0)
    A["poverty_years"] = np.zeros(N, np.int16)   # childhood years spent in a poor household
    A["studying"] = np.zeros(N, np.float32)
    yrs = p["education"]["years"]
    pool = np.flatnonzero((age >= 18) & (age <= p["education"]["max_age"]) & (A["education"] < 2))
    want = min(len(pool), int(p["education"]["students_2025"]))
    if want:
        weight = np.where(A["student"][pool], 4.0, 1.0)   # those already flagged as students first
        chosen = rng.choice(pool, want, replace=False, p=weight / weight.sum())
        A["studying"][chosen] = rng.integers(1, yrs + 1, want).astype(np.int16)
        A["student"][chosen] = True

    # ---- couples (MAN07108): ~158k partnered adults, opposite-sex matching within 5-year bins
    fam = base["families_2026"]["Nuclear families, total"]
    couples = fam["Married couple without children"] + fam["Married couple with children"] + \
        fam["Consensual union without children"] + fam["Consensual union with children"]
    # v9: the old-age shares raised so that 60% of those 67+ have a partner, as Hagstofa's register has (1 Jan 2026,
    # 33,391 of 55,424); v8 drew 48%.
    share = np.select([age < 18, age < 25, age < 35, age < 65, age < 80], [0, .10, .50, .70, .78], .58).astype(float)
    adults = age >= 18
    share *= 2 * couples / share[adults].sum()
    partner = np.full(N, -1, np.int32)
    want = rng.random(N) < share
    bins = age // 5
    for b in np.unique(bins[adults]):
        men = np.flatnonzero(want & (sex == 0) & (bins == b))
        women = np.flatnonzero(want & (sex == 1) & (bins == b))
        k = min(len(men), len(women))
        men, women = rng.permutation(men)[:k], rng.permutation(women)[:k]
        partner[men], partner[women] = women, men
    # Older women outnumber older men, so matching within a five-year band left many who should be partnered alone.
    # Those left over from 55 on are matched to a man up to ten years older, as is common (v9).
    for b in sorted(np.unique(bins[adults & (age >= 55)])):
        women = np.flatnonzero(want & (sex == 1) & (bins == b) & (partner < 0))
        men = np.flatnonzero(want & (sex == 0) & (bins > b) & (bins <= b + 2) & (partner < 0))
        k = min(len(men), len(women))
        men, women = rng.permutation(men)[:k], rng.permutation(women)[:k]
        partner[men], partner[women] = women, men
    A["partner"] = partner

    # ---- children (<18) attached to mothers; birth order within family
    n_fam = int(fam["Married couple with children"] + fam["Consensual union with children"] + fam["Mother with children"]
                + fam["Father with children"])
    single_share = (fam["Mother with children"] + fam["Father with children"]) / n_fam
    women = (sex == 1) & (age >= 20) & (age <= 58)
    wpart = np.flatnonzero(women & (partner >= 0))
    wsing = np.flatnonzero(women & (partner < 0))
    fw = lambda idx: np.exp(-((age[idx] - 40.0) / 9) ** 2)
    n_s = int(n_fam * single_share)
    mothers = np.r_[rng.choice(wpart, n_fam - n_s, replace=False, p=fw(wpart) / fw(wpart).sum()),
                    rng.choice(wsing, n_s, replace=False, p=fw(wsing) / fw(wsing).sum())]
    kids_per = rng.choice([1, 2, 3, 4, 5, 6, 7], len(mothers), p=[.44, .37, .14, .035, .01, .004, .001])
    slot_mother, slot_age = [], []
    for mo, k in zip(mothers, kids_per):
        lo, hi = max(0, age[mo] - 44), min(17, age[mo] - 19)
        if hi < lo:
            continue
        ks = np.sort(rng.integers(lo, hi + 1, k))[::-1]
        slot_mother.extend([mo] * k); slot_age.extend(ks)
    slot_mother, slot_age = np.array(slot_mother), np.array(slot_age)
    mother = np.full(N, -1, np.int32)
    child_idx = np.flatnonzero(age < 18)
    for a in range(18):
        ca = rng.permutation(child_idx[age[child_idx] == a])
        sa = rng.permutation(np.flatnonzero(slot_age == a))
        k = min(len(ca), len(sa))
        mother[ca[:k]] = slot_mother[sa[:k]]
        if len(ca) > k:  # unmatched children go to random mothers of plausible age
            ok = mothers[(age[mothers] - a >= 19) & (age[mothers] - a <= 44)]
            mother[ca[k:]] = rng.choice(ok, len(ca) - k)
    A["mother"] = mother
    # children under 18 at home, per mother: household size for housing benefit (kept current in child_transfers)
    kid = (mother >= 0) & (A["age"] < 18)
    A["kids_home"] = np.bincount(mother[kid], minlength=len(mother)).astype(float)
    recompute_birth_order(A)
    assign_living_arrangements(A, p, rng)

    # ---- housing and region
    renter_p = np.select([age < 25, age < 35, age < 45, age < 67], [.55, .45, .25, .12], .08)
    renter_p = np.where(A["immigrant"], np.minimum(renter_p * 2.2, .85), renter_p)
    A["renter"] = rng.random(N) < renter_p
    # 2.0: the better paid more often in the capital area (regions.assign); a household shares its area
    from ubisim.abm import regions
    A["capital"] = regions.assign(A, p, rng)
    # a couple shares tenure
    has_p = partner >= 0
    A["renter"][has_p] = A["renter"][np.where(has_p, np.minimum(np.arange(N), partner), 0)][has_p]
    A["mortgage"] = ~A["renter"] & (age < 60)

    assign_wealth(A, p, rng)

    A["occ_pension"] = np.where(age >= 67, occupational_pension(A, np.arange(N), p, rng), 0.0)
    assign_capital_income(A, p, rng)

    # ---- traits
    b = p["behaviour"]
    A["meaning"] = np.clip(np.array(P.trait(1))[occ] + rng.normal(0, b["meaning_sd"], N), 0, 1)
    sd = b["leisure_sd"]
    A["leisure"] = rng.lognormal(np.log(b["leisure_mean"]) - sd ** 2 / 2, sd, N)
    ent = rng.lognormal(-.18, .6, N) * np.where(edu == 2, 1.3, 1.0) * np.where(sex == 0, 1.3, 1.0) \
        * np.where(A["self_employed"], 2.0, 1.0)
    A["enterprise"] = ent / ent[A["chooser"]].mean()
    mob = rng.lognormal(-.125, .5, N) * np.select([age < 20, age < 35, age < 50], [1.0, 1.5, 1.0], .5) \
        * np.where(A["immigrant"], 1.8, 1.0) * np.where(edu == 2, 1.3, 1.0)
    A["mobility"] = mob / mob[A["chooser"]].mean()
    # pull towards self-directed work: making art and music, writing, studying, caring, building things
    creative = rng.lognormal(-.3, .8, N) * np.where(np.isin(occ, [i for i, pr in enumerate(profs)
                                                                 if pr["name"] in P.CREATIVE_PROFESSIONS]), 2.2, 1.0)
    A["creative"] = creative / creative[A["chooser"]].mean()

    assign_characters(A, p)
    # employment contracts: staggered end years, pay agreed at the market rate of 2025
    lengths = list(p["labour"]["contract_lengths_private"])
    probs = np.array(list(p["labour"]["contract_lengths_private"].values()), float)
    drawn = rng.choice(lengths, N, p=probs / probs.sum())
    A["contract_end"] = np.where(np.isin(A["status"], [PART, FULL]),
                                 rng.integers(1, drawn + 1).astype(np.int16), 0).astype(np.int16)
    A["contract_omega"] = np.ones(N)
    A["contract_start"] = np.zeros(N, np.int16)   # when the current agreement was struck
    A["contract_cpi"] = np.ones(N)                # and the price level it was struck at
    A["contract_tot"] = np.ones(N)                # and the terms of trade it was struck at
    A["contract_ai"] = np.ones(N)                 # and output per hour then (name kept from when it was AI alone)
    # EST: years already in the job, spread over a working life so tenure does not all start at zero
    A["tenure"] = np.where(np.isin(A["status"], [PART, FULL]),
                           np.minimum(rng.exponential(6.0, N), np.maximum(A["age"] - 18, 0)), 0).astype(np.float32)
    A["alive"] = np.ones(N, bool)
    A["origin_year"] = np.zeros(N, np.int16)
    A["venture"] = np.full(N, -1, np.int32)
    A["involuntary"] = np.zeros(N, bool)
    A["underemployed"] = np.zeros(N, bool)   # part-time for want of full-time work, not by choice
    return A


def assign_living_arrangements(A, p, rng, only=None):
    """Who lives alone, and with whom the others live (v9). `host` is the adult whose household a single person of
    67+ lives in (-1: none); `lives_alone` marks single adults with no children at home and no host. `only` limits
    the assignment to those indices (people who became single during a run)."""
    b = p["benefits"]
    N = len(A["age"])
    age = A["age"]
    alive = A.get("alive", np.ones(N, bool))
    if "host" not in A:
        A["host"] = np.full(N, -1, np.int32)
        A["lives_alone"] = np.zeros(N, bool)
    single = alive & (age >= 18) & (A["partner"] < 0) & (A["kids_home"] <= 0)
    pool = np.flatnonzero(single) if only is None else np.asarray(only)[single[np.asarray(only)]]
    if not len(pool):
        return
    old = age[pool] >= 67
    young = age[pool] < 30
    home = young & (rng.random(len(pool)) < at_home_share(age[pool], b))
    alone_p = np.where(old, b["living_alone_share_single_67"], b["living_alone_share_single_under67"])
    alone = ~home & (rng.random(len(pool)) < alone_p)
    A["lives_alone"][pool] = alone
    A["host"][pool] = -1
    # single people of 67+ who do not live alone live with a younger household, and young adults at home with a
    # parent-aged one: pooled for poverty and costs
    for guests, lo, hi in ((pool[old & ~alone], 35, 67), (pool[home], 38, 67)):
        hosts = np.flatnonzero(alive & (age >= lo) & (age < hi) & (A["host"] < 0) & ~A["lives_alone"])
        if len(guests) and len(hosts):
            A["host"][guests] = rng.choice(hosts, len(guests))


def at_home_share(age, b):
    """The share of single young adults living with their parents, by age (params young_at_home_share)."""
    pts = sorted((int(k), v) for k, v in b.get("young_at_home_share", {"18": 0.0}).items())
    return np.interp(age, [a for a, _ in pts], [v for _, v in pts])


def update_young(A, p, rng, leave_multiplier=1.0):
    """Each year: those turning 18 live at home, with their mother where she is alive and has a home of her own;
    young adults at home leave as the at-home share falls with age (v9), faster when a studio is cheap against what
    their age group earns (v10: `leave_multiplier`, housing.leave_home_multiplier)."""
    if "host" not in A:
        return
    b = p["benefits"]
    age, alive = A["age"], A["alive"]
    turning = np.flatnonzero(alive & (age == 18) & (A["partner"] < 0))
    if len(turning):
        stay = rng.random(len(turning)) < at_home_share(18, b)
        mom = A["mother"][turning]
        ok = stay & (mom >= 0)
        ok[ok] = alive[mom[ok]] & (A["host"][mom[ok]] < 0)
        A["host"][turning[ok]] = mom[ok]
        A["lives_alone"][turning] = False
        rest = turning[~ok]
        if len(rest):
            assign_living_arrangements(A, p, rng, only=rest)
    home = np.flatnonzero(alive & (A["host"] >= 0) & (age > 18) & (age < 67))
    if len(home):
        now, before = at_home_share(age[home], b), at_home_share(age[home] - 1, b)
        leave = rng.random(len(home)) < np.minimum(1, (1 - now / np.maximum(before, 1e-9)) * leave_multiplier)
        out = home[leave]
        A["host"][out] = -1
        A["lives_alone"][out] = rng.random(len(out)) < b["living_alone_share_single_under67"]


def assign_wealth(A, p, rng):
    """Household wealth: savings and other assets (`wealth`), and a home with a mortgage. Totals from 206% of GDP of
    net worth outside pensions; the spread fitted by family to the tax returns (1.1, see below)."""
    w = p["wealth"]
    N = len(A["age"])
    age, partner = A["age"], A["partner"]
    total = w["net_worth_excl_pensions_pct_gdp"] / 100 * (p.get("base") or {}).get("GDP0", 4941.2) * 1e9
    adults = age >= 20
    age_curve = np.clip((age - 20) / 40.0, .05, 1.4)
    raw = age_curve * (A["base_wage"] / np.median(A["base_wage"])) ** 1.3 * rng.lognormal(-w["wealth_sd"] ** 2 / 2, w["wealth_sd"], N)
    raw = np.where(adults, raw, 0) * np.where(A["immigrant"], np.minimum(1, (A["years_in_iceland"] + 1) / 15), 1)
    # The top of a wealth distribution is Pareto, not lognormal: a lognormal put 13-16% of net wealth with the
    # richest 1%, where tax-return data put 20-25%, and a wealth tax above 100 m.kr. found half the base the
    # auðlegðarskattur did (2026-09-26). Those above `pareto_from` keep their order and take a Pareto tail from
    # there; the total is still pinned to the national figure below. 1.1: from the 90th percentile, not the 99th —
    # from the 99th the richest tenth of families held 34% of net worth, against 50% in the tax returns.
    alpha = w.get("pareto_alpha")
    if alpha and adults.sum() > 100:
        q = np.quantile(raw[adults], w.get("pareto_from", .99))
        top = np.flatnonzero(adults & (raw > q))
        rank = (np.argsort(np.argsort(raw[top])) + .5) / len(top)        # 0 = the least of the top, 1 = the most
        raw[top] = q * (1 - rank * .99) ** (-1 / alpha)
        k = w.get("top_share_valuation", 1.0)
        if k != 1.0:
            raw[adults & (raw > np.quantile(raw[adults], .99))] *= k
    A["wealth"] = raw / raw.sum() * total * w["liquid_share"]
    # 1.1: an adult living in someone else's home (a young adult with their parents, an older guest) owns none of
    # it; they were given a home of their own as owners, which no household in the housing ladder held
    hosted = A["host"] >= 0 if "host" in A else np.zeros(N, bool)
    A["renter"][hosted] = True                  # and rent when they leave (housing._place_new)
    A["mortgage"][hosted] = False
    owners = adults & ~A["renter"]
    value = np.where(A["capital"], 1.25, .8) * (A["base_wage"] / np.median(A["base_wage"])) ** .3 \
        * rng.lognormal(-w["home_value_sd"] ** 2 / 2, w["home_value_sd"], N)
    # 1.1: `home_value` is all the real estate a household holds — its home, and for the wealthiest a second home or
    # flats let out. In the tax returns the richest tenth of families hold 174 m.kr. of real estate each, against
    # 102 m.kr. in the next tenth; without this the model gave them 107. It rises with savings and other assets
    # against the median adult's (no draw of its own)
    rel = A["wealth"] / max(float(np.median(A["wealth"][adults])), 1.0)
    value = value * np.clip(rel, .2, 50) ** w["home_value_wealth_elasticity"]
    ltv = np.where(A["mortgage"], np.clip(.65 - (age - 25) / 70, .1, .8), 0.0)
    share = np.where(partner >= 0, .5, 1.0)  # couples hold half each
    home = np.where(owners, value * share, 0.0)
    equity_raw = home * (1 - ltv)
    scale = total * (1 - w["liquid_share"]) / max(equity_raw.sum(), 1)
    A["home_value"] = home * scale
    A["mortgage_debt"] = A["home_value"] * ltv


def assign_capital_income(A, p, rng):
    """Capital income as the tax returns have it, by wealth rank within age group (v9; params `benefits`)."""
    b = p["benefits"]
    N = len(A["age"])
    scale = (p.get("base") or {}).get("krona_scale", 1.0)
    adults = A["age"] >= 18
    old = adults & (A["age"] >= 67)
    ci = np.zeros(N)
    total_month = b["capital_income_total_bn"] * 1e9 / 12 * scale
    old_month = b["capital_income_67_month"] * scale * old.sum()
    for grp, amount in ((old, old_month), (adults & ~old, max(total_month - old_month, 0.0))):
        idx = np.flatnonzero(grp)
        if not len(idx):
            continue
        shares = np.sort(rng.lognormal(0, b["capital_income_sigma"], len(idx)))
        order = np.argsort(A["wealth"][idx] + 1e-6 * rng.random(len(idx)))      # by wealth rank
        ci[idx[order]] = shares / shares.sum() * amount
    A["capital_income"] = ci
    # what each person's savings yield in capital income, so it follows their wealth through a run
    A["capital_income_rate"] = np.where(A["wealth"] > 1.0, ci * 12 / np.maximum(A["wealth"], 1.0), 0.0)


def occupational_pension(A, idx, p, rng):
    """Occupational pension at retirement: a replacement rate on earnings, scaled by years contributed in Iceland
    for immigrants. The replacement rate is set so the 67+ mean lands near 280,000 ISK (EST)."""
    b = p["benefits"]
    years = np.where(A["immigrant"][idx], np.minimum(A["years_in_iceland"][idx], 40) / 40, 1.0)
    sd = b.get("occupational_pension_sd", .35)
    noise = rng.lognormal(-.5 * sd ** 2, sd, len(idx))
    return b["occupational_pension_replacement"] * A["base_wage"][idx] * years * noise


def recompute_birth_order(A):
    """Birth order by age within each mother's children; kids counts for every adult."""
    N = len(A["age"])
    mother = A["mother"]
    alive = A.get("alive", np.ones(N, bool))
    kids = np.flatnonzero((mother >= 0) & (A["age"] < 18) & alive)
    order = np.zeros(N, np.int8)
    if len(kids):
        srt = kids[np.lexsort((-A["age"][kids].astype(int), mother[kids]))]
        m = mother[srt]
        start = np.r_[True, m[1:] != m[:-1]]
        grp = np.cumsum(start) - 1
        first = np.flatnonzero(start)
        order[srt] = np.arange(len(srt)) - first[grp] + 1
    A["birth_order"] = order
    n_kids = np.bincount(mother[kids], minlength=N) if len(kids) else np.zeros(N, int)
    young = kids[A["age"][kids] < 6]
    n_young = np.bincount(mother[young], minlength=N) if len(young) else np.zeros(N, int)
    partner = A["partner"]
    hp = partner >= 0
    A["n_kids"] = n_kids + np.where(hp, n_kids[np.where(hp, partner, 0)], 0) * (A["sex"] == 0)
    A["n_young_kids"] = n_young + np.where(hp, n_young[np.where(hp, partner, 0)], 0) * (A["sex"] == 0)
    teens = kids[A["age"][kids] >= 14]
    n_teens = np.bincount(mother[teens], minlength=N) if len(teens) else np.zeros(N, int)
    A["n_teens"] = n_teens + np.where(hp, n_teens[np.where(hp, partner, 0)], 0) * (A["sex"] == 0)


def assign_characters(A, p):
    age, st = A["age"], A["status"]
    ent_top = A["enterprise"] >= np.quantile(A["enterprise"][A["chooser"]], .9)
    mob_top = A["mobility"] >= np.quantile(A["mobility"][A["chooser"]], .75)
    lowpay_occ = np.isin(A["occupation"], [4, 5, 7, 8])
    rules = [
        A["student"],
        A["retired"],
        A["disabled"],
        (A["n_young_kids"] > 0) & ((st != 2) | (A["leisure"] > np.median(A["leisure"]))),
        ent_top | A["self_employed"],
        A["immigrant"] & (A["years_in_iceland"] < 5) & lowpay_occ,
        (A["education"] == 2) & mob_top,
        A["meaning"] >= .6,
        A["meaning"] < .4,
    ]
    char = np.full(len(age), len(CHARACTERS) - 1, np.int8)
    for i in reversed(range(len(rules))):
        char[rules[i]] = i
    char[age < 16] = -1
    A["character"] = char
    for ci, name in enumerate(CHARACTERS):
        mult = p["characters"].get(name, {})
        m = char == ci
        for trait in ("enterprise", "leisure", "mobility"):
            A[trait][m] *= mult.get(trait, 1.0)
        A["meaning"][m] = np.clip(A["meaning"][m] * mult.get("meaning", 1.0), 0, 1)
