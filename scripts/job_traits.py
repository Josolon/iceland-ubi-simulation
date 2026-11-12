"""Meaning and unpleasantness of the model's 27 professions, from what the people doing them say (2.1).

Source: ISSP 2015, Work Orientations IV (GESIS ZA6770, doi:10.4232/1.12848), the Icelandic sample and the
other four Nordic ones. The data are free but need a GESIS account, so they are not in the repository: put
ZA6770_v2-1-0.dta in data/raw/issp2015/.

    python scripts/job_traits.py            # writes data/processed/job_traits.json and prints the table

Items (agreement 1 = strongly agree .. 5 = strongly disagree; frequency 1 = always .. 5 = never):
  meaning       v25 my job is interesting, v27 I can help other people, v28 my job is useful to society,
                v49 I am proud of the type of work I do
  unpleasantness  v30 hard physical work, v31 stressful, v38 the job's demands interfere with family life,
                and unsocial hours: v33 weekends, v35 a schedule that changes or is set at short notice

Each item is scored 0-1, worst or best answer at the ends. Unpleasantness is the mean of four parts, physical,
stress, family and hours, the last being the mean of weekends and an irregular schedule. Each profession's
Icelandic mean is shrunk towards the Nordic one by the weight its sample earns (empirical Bayes: n / (n + k),
with k the ratio of the within-profession to the between-country variance); a thin Nordic cell is shrunk
the same way towards its ISCO major group. The scores are then put on the
range the model's judgements used, by matching their mean and spread, so the size of the preference weights
fitted to them still applies. The ordering is what the survey changes; docs/JOB_TRAITS.md has the method.
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ubisim.abm.params import PROFESSION_TRAITS  # noqa: E402

DATA = ROOT / "data/raw/issp2015/ZA6770_v2-1-0.dta"
OUT = ROOT / "data/processed/job_traits.json"
NORDIC = ["IS", "NO", "SE", "DK", "FI"]


def profession(isco):
    """The model's profession for a four-digit ISCO-08 code, or None (armed forces, missing)."""
    if not isco or isco >= 9990 or isco < 1000:
        return None
    s = f"{int(isco):04d}"
    one, two, three = s[0], s[:2], s[:3]
    if one == "1":
        return "Managers"
    if one == "2":
        if three == "221":
            return "Doctors"
        if three == "222":
            return "Nurses and midwives"
        if s in ("2341", "2342", "2352"):
            return "Primary and pre-school teachers"
        if s in ("2320", "2330", "2351") or three in ("232", "233"):
            return "Secondary teachers"
        if three in ("231", "211", "213") or s in ("2632", "2633"):
            return "Academics"
        if three == "261":
            return "Lawyers"
        if three in ("214", "215", "216") or two == "25":
            return "Engineers and IT"
        if three in ("264", "265"):
            return "Artists and writers"
        if three in ("241", "242", "243") or s == "2631":
            return "Business professionals"
        return "Other professionals"
    if one == "3":
        if s in ("3221", "3222"):
            return "Nurses and midwives"
        if three == "315":
            return "Pilots, officers and controllers"
        if two == "35":
            return "Engineers and IT"
        if three == "343":
            return "Artists and writers"
        return "Other associate professionals"
    if one == "4":
        return "Clerks"
    if one == "5":
        if s == "5311":
            return "Child-care workers"
        if three == "532":
            return "Care assistants"
        if three == "512":
            return "Cooks"
        if three == "513":
            return "Waiters and bar staff"
        return "Retail and other service"
    if one == "6":
        return "Fishers and farm workers"
    if one == "7":
        return "Fish processing workers" if s == "7511" else "Other craft and trades"
    if one == "8":
        if s == "8160":
            return "Fish processing workers"
        if three == "833":
            return "Bus and truck drivers"
        return "Other machine operators"
    if one == "9":
        if s == "9411":
            return "Cooks"
        if three in ("911", "912"):
            return "Cleaners"
        if three == "921":
            return "Fishers and farm workers"
        if three == "961":
            return "Refuse collectors"
        return "Other elementary"
    return None


def scored(d):
    """Each item on 0-1, missing answers as NaN."""
    def agree(c):      # 1 strongly agree .. 5 strongly disagree -> 1 .. 0
        x = d[c].where(d[c].between(1, 5))
        return (5 - x) / 4

    def often(c):      # 1 always .. 5 never -> 1 .. 0
        x = d[c].where(d[c].between(1, 5))
        return (5 - x) / 4
    irregular = d["v35"].where(d["v35"].between(1, 3)).map({1: 0.0, 2: 1.0, 3: 1.0})
    out = pd.DataFrame({
        "interesting": agree("v25"), "helps": agree("v27"), "useful": agree("v28"), "proud": agree("v49"),
        "physical": often("v30"), "stress": often("v31"), "family": often("v38"),
        "weekends": often("v33"), "irregular": irregular,
    })
    out["meaning"] = out[["interesting", "helps", "useful", "proud"]].mean(1, skipna=True)
    out["hours"] = out[["weekends", "irregular"]].mean(1, skipna=True)
    out["unpleasant"] = out[["physical", "stress", "family", "hours"]].mean(1, skipna=True)
    return out


def shrink(df, col):
    """Icelandic mean per profession, shrunk towards the Nordic one; returns (value, n Iceland, weight)."""
    g = df.dropna(subset=[col])
    w = g["WEIGHT"]
    def wmean(x):
        return np.average(x[col], weights=w.loc[x.index]) if len(x) else np.nan
    nordic = g.groupby("prof").apply(wmean)
    within = g.groupby("prof")[col].var().mean()
    # a thin Nordic cell (refuse collectors: two people) leans on its ISCO major group, by the same rule
    major = g.groupby("major").apply(wmean)
    n_n = g.groupby("prof").size()
    parent = g.groupby("prof")["major"].agg(lambda x: x.mode().iloc[0])
    between_major = ((nordic - major.reindex(parent.reindex(nordic.index)).values) ** 2 - within / n_n).mean()
    k_major = within / max(between_major, 1e-4)
    w_n = n_n / (n_n + k_major)
    nordic = w_n * nordic + (1 - w_n) * major.reindex(parent.reindex(nordic.index)).values
    by_country = g.groupby(["prof", "c_alphan"]).apply(wmean).unstack()
    # the spread of countries' means about the Nordic one, less what sampling alone would give
    n_c = g.groupby(["prof", "c_alphan"]).size().unstack()
    between = ((by_country.sub(nordic, axis=0)) ** 2 - within / n_c).stack().mean()
    k = within / max(between, 1e-4)
    ice = g[g["c_alphan"] == "IS"]
    n_is = ice.groupby("prof").size().reindex(nordic.index).fillna(0)
    m_is = ice.groupby("prof").apply(wmean).reindex(nordic.index)
    wt = n_is / (n_is + k)
    value = (wt * m_is.fillna(0) + (1 - wt) * nordic)
    return value, n_is, wt, k


def rescale(new, old):
    """New scores on the old judgements' mean and spread, kept in 0-1."""
    z = (new - new.mean()) / new.std()
    return np.clip(old.mean() + z * old.std(), 0.02, 0.98)


def main():
    d = pd.read_stata(DATA, convert_categoricals=False,
                      columns=["c_alphan", "ISCO08", "WEIGHT", "v25", "v27", "v28", "v49", "v30", "v31",
                               "v33", "v35", "v38", "v44", "v2"])
    d = d[d["c_alphan"].isin(NORDIC)].copy()
    d["prof"] = d["ISCO08"].map(profession)
    d = d.dropna(subset=["prof"])
    d["major"] = (d["ISCO08"] // 1000).astype(int)
    s = scored(d)
    for c in ("meaning", "unpleasant"):
        d[c] = s[c]
    d["satisfied"] = (7 - d["v44"].where(d["v44"].between(1, 7))) / 6
    names = list(PROFESSION_TRAITS)
    mean_m, n_is, wt_m, k_m = shrink(d, "meaning")
    mean_u, _, wt_u, k_u = shrink(d, "unpleasant")
    sat, _, _, _ = shrink(d, "satisfied")
    mean_m, mean_u, sat = mean_m.reindex(names), mean_u.reindex(names), sat.reindex(names)
    old = pd.DataFrame(PROFESSION_TRAITS, index=["disamenity", "meaning", "edu"]).T
    traits = pd.DataFrame({
        "disamenity": rescale(mean_u, old["disamenity"]).round(2),
        "meaning": rescale(mean_m, old["meaning"]).round(2),
        "raw_unpleasant": mean_u.round(3), "raw_meaning": mean_m.round(3), "satisfied": sat.round(3),
        "n_iceland": n_is.reindex(names).astype(int),
        "n_nordic": d.groupby("prof").size().reindex(names).astype(int),
        "weight_iceland": wt_m.reindex(names).round(2),
        "judged_disamenity": old["disamenity"], "judged_meaning": old["meaning"],
    })
    pd.set_option("display.width", 200)
    print(traits.to_string())
    print(f"\nshrinkage k: meaning {k_m:.0f}, unpleasantness {k_u:.0f}")
    print("correlation with the judgements: disamenity %.2f, meaning %.2f" % (
        traits["disamenity"].corr(traits["judged_disamenity"]), traits["meaning"].corr(traits["judged_meaning"])))
    print("correlation with job satisfaction: unpleasantness %.2f, meaning %.2f" % (
        mean_u.corr(sat), mean_m.corr(sat)))
    OUT.write_text(json.dumps({
        "source": "ISSP 2015 Work Orientations IV (GESIS ZA6770 v2.1.0), Iceland shrunk towards the Nordic pool",
        "method": "scripts/job_traits.py; docs/JOB_TRAITS.md",
        "shrinkage_k": {"meaning": round(float(k_m), 1), "unpleasant": round(float(k_u), 1)},
        "professions": {n: {k: (None if pd.isna(v) else (float(v) if not isinstance(v, (int, np.integer)) else int(v)))
                            for k, v in traits.loc[n].items()} for n in names},
    }, indent=1, ensure_ascii=False))
    print("wrote", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
