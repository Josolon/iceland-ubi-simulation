"""Build data/processed/baseline_<year>.json: the calibration targets for the agent-based model.

    PYTHONPATH=src .venv/bin/python -m ubisim.abm.data_prep            # 2025, the model's base year
    PYTHONPATH=src .venv/bin/python -m ubisim.abm.data_prep --year 2015  # a historical starting point

The keys keep their 2025 names (population_2026, earnings_2025, ...) whatever the year, so the population builder
reads any year's file unchanged; `year` in the file says which year it holds. Population and families are counted
on 1 January of the following year, as for 2025.
"""
import argparse
import json
import pathlib
from collections import defaultdict

from ubisim.data.hagstofa import fetch_labels

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "data/processed/baseline_2025.json"
YEAR = 2025

OCCUPATIONS = ["Legislators and managers", "Professionals", "Associate professionals", "Clerks",
               "Service and sales workers", "Agricultural and fishery workers",
               "Craft and related trades workers", "Plant and machine operators", "Elementary occupations"]
EDUCATION = ["Primary and lower sedondary (ISCED 1+2)", "Upper and post sedondary (ISCED 3+4)",
             "Tertiary (ISCED 5+6+7+8)"]
# VIN02004 uses different occupation labels; agricultural workers have no earnings row (use craft).
EARNINGS_OCC = {
    "Legislators and managers": "Managers (1)",
    "Professionals": "Professionals (2)",
    "Associate professionals": "Technicians and associate professionals (3)",
    "Clerks": "Clerks (4)",
    "Service and sales workers": "Service workers and shop and market sales workers (5)",
    "Agricultural and fishery workers": "Craft and related trades workers (7)",
    "Craft and related trades workers": "Craft and related trades workers (7)",
    "Plant and machine operators": "Plant and machine operators and assemblers (8)",
    "Elementary occupations": "Elementary occupations (9)",
}
PERCENTILES = ["10%", "20%", "25% (1st quartile)", "30%", "40%", "50% (median)", "60%", "70%",
               "75% (3rd quartile)", "80%", "90%"]


def age_of(label):
    label = label.strip()
    return 0 if label.startswith("Under") else int(label.split()[0])


def population():
    rows = fetch_labels("MAN43000", {"Ár": [str(YEAR + 1)], "Kyn": ["Males", "Females"],
                                     "Bakgrunnur": ["Total", "Immigrant"], "Aldur": "*"})
    out = defaultdict(lambda: defaultdict(dict))
    for k, v in rows:
        if k["Aldur"].strip() in ("Total", "Unkown") or not v:
            continue
        out[k["Kyn"]][k["Bakgrunnur"]][age_of(k["Aldur"])] = v
    return {sex: {bg: dict(sorted(ages.items())) for bg, ages in d.items()} for sex, d in out.items()}


def employment_by_occupation():
    rows = fetch_labels("VIN01100", {"Ár": [str(YEAR)], "Kyn": ["Males", "Females"],
                                     "Menntun": EDUCATION, "Starfsstétt": OCCUPATIONS})
    out = defaultdict(lambda: defaultdict(dict))
    for k, v in rows:
        out[k["Kyn"]][k["Starfsstétt"]][k["Menntun"]] = v or 0
    return out


def labour_rates():
    groups = ["16-24 years", "25-54 years", "55-74 years", "Males", "Females", "Total"]
    units = ["Activity rate", "Employment rate", "Employed full-time", "Employed part time",
             "Unemployment rate", "Average hours of work", "Full-time hours of work", "Part-time hours of work"]
    rows = fetch_labels("VIN01104", {"Ár": [str(YEAR)], "Skipting": groups, "Eining": units})
    out = defaultdict(dict)
    for k, v in rows:
        out[k["Skipting"]][k["Eining"]] = v
    return out


def inactive():
    rows = fetch_labels("VIN00961", {"Ár": [str(YEAR)], "Kyn": ["Males and females"], "Eining": ["Number"],
                                     "Meginstaða": "*"})
    return {k["Meginstaða"]: v for k, v in rows}


def self_employment():
    rows = fetch_labels("VIN01006", {"Ár": [str(YEAR)], "Eining": ["Percentage"],
                                     "Bakgrunnur": ["Total", "16 to 24 years", "25 to 54 years", "55 to 74 years"],
                                     "Atvinnustétt": ["Self-employed"]})
    return {k["Bakgrunnur"]: v for k, v in rows}


def earnings():
    """Monthly total earnings percentiles (thousand ISK) for full-time employees, by occupation and sector."""
    rows = fetch_labels("VIN02004", {
        "Ár": [str(YEAR)], "Kyn": ["Total"], "Laun og vinnutími": ["Total earning"],
        "Launþegahópur": ["Total", "Private sector", "Public sector - total"],
        "Starfsstétt": sorted(set(EARNINGS_OCC.values())), "Eining": ["Mean"] + PERCENTILES + ["Weighted observations"]})
    out = defaultdict(lambda: defaultdict(dict))
    for k, v in rows:
        out[k["Starfsstétt"]][k["Launþegahópur"]][k["Eining"]] = v
    return out


def migration():
    rows = fetch_labels("MAN01401", {"Ár": [str(YEAR)], "Kyn": ["Total"], "Aldur": "*",
                                     "Ríkisfang": ["Icelandic citizens", "Foreign citizens"],
                                     "Tegund flutnings": ["Immigration", "Emigration"]})
    out = defaultdict(lambda: defaultdict(dict))
    for k, v in rows:
        if k["Aldur"].strip() == "Total" or not v:
            continue
        out[k["Ríkisfang"]][k["Tegund flutnings"]][age_of(k["Aldur"])] = v
    return out


def enterprises():
    total = "Total business economy including fisheries and excluding financial and insurance activities (NACE no. 03-63, 68-82, 95-96)"
    rows = fetch_labels("FYR09002", {"Atvinnugreinar": [total], "Fjöldi starfsmanna": ["Total"],
                                     "Ár sem starfsemi hófst": ["2016", "2017", "2018", "2019", "2020"],
                                     "Lýsing": "*", "Breytur": ["Number of enterprises",
                                                               "Number of persons employed in the year of birth, annual averages"]})
    out = defaultdict(dict)
    for k, v in rows:
        if v is not None:
            out[k["Ár sem starfsemi hófst"]][f'{k["Lýsing"]} | {k["Breytur"]}'] = v
    return out


def families():
    rows = fetch_labels("MAN07108", {"Ár": [str(YEAR + 1)], "Sveitarfélag": ["Total"], "Kjarnafjölskyldur": "*",
                                     "Fjölskyldugerð": "*"})
    out = defaultdict(dict)
    for k, v in rows:
        out[k["Kjarnafjölskyldur"]][k["Fjölskyldugerð"]] = v
    return out


# Named professions: (name, parent occupation group index, ISCO codes in VIN02001, codes to subtract for a residual)
PROFESSIONS = [
    ("Managers", 0, ["1  Managers"], []),
    ("Doctors", 1, ["2221  Medical doctors"], []),
    ("Nurses and midwives", 1, ["2230  Nursing and midwifery professionals"], []),
    ("Primary and pre-school teachers", 1, ["233  Primary and pre-primary education teaching professionals"], []),
    ("Secondary teachers", 1, ["2320  Secondary education teaching professionals"], []),
    ("Academics", 1, ["2310  College, university and higher education teaching professionals"], []),
    ("Lawyers", 1, ["242  Legal professionals"], []),
    ("Engineers and IT", 1, ["213  Computing professionals", "214  Architects, engineers and related professionals"], []),
    ("Artists and writers", 1, ["245  Writers and creative or performing artists"], []),
    ("Business professionals", 1, ["241  Business professionals"], []),
    ("Other professionals", 1, ["2  Professionals"], ["2221  Medical doctors", "2230  Nursing and midwifery professionals",
        "233  Primary and pre-primary education teaching professionals", "2320  Secondary education teaching professionals",
        "2310  College, university and higher education teaching professionals", "242  Legal professionals",
        "213  Computing professionals", "214  Architects, engineers and related professionals",
        "245  Writers and creative or performing artists", "241  Business professionals"]),
    ("Pilots, officers and controllers", 2, ["314  Ship and aircraft controllers and technicians"], []),
    ("Other associate professionals", 2, ["3  Technicians and associate professionals"], ["314  Ship and aircraft controllers and technicians"]),
    ("Clerks", 3, ["4  Clerks"], []),
    ("Child-care workers", 4, ["5131  Child-care workers"], []),
    ("Care assistants", 4, ["5132  Institution-based personal care workers", "5133  Home-based personal care workers"], []),
    ("Cooks", 4, ["5122  Cooks"], []),
    ("Waiters and bar staff", 4, ["5123  Waiters, waitresses and bartenders"], []),
    ("Retail and other service", 4, ["5  Service workers and shop and market sales workers"],
     ["5131  Child-care workers", "5132  Institution-based personal care workers", "5133  Home-based personal care workers",
      "5122  Cooks", "5123  Waiters, waitresses and bartenders"]),
    ("Fishers and farm workers", 5, [], []),
    ("Fish processing workers", 6, ["7419  Fish processing workers"], []),
    ("Other craft and trades", 6, ["7  Craft and related trades workers"], ["7419  Fish processing workers"]),
    ("Bus and truck drivers", 7, ["832  Motor-vehicle drivers"], []),
    ("Other machine operators", 7, ["8  Plant and machine operators and assemblers"], ["832  Motor-vehicle drivers"]),
    ("Cleaners", 8, ["9132  Helpers and cleaners in offices, hotels and other establishments"], []),
    ("Refuse collectors", 8, ["9161  Garbage collectors"], []),
    ("Other elementary", 8, ["9  Elementary occupations"],
     ["9132  Helpers and cleaners in offices, hotels and other establishments", "9161  Garbage collectors"]),
]


def professions():
    """Median full-time earnings and employment weights per named profession (VIN02001, 2025)."""
    codes = sorted({c for _, _, inc, exc in PROFESSIONS for c in inc + exc})
    rows = fetch_labels("VIN02001", {"Ár": [str(YEAR)], "Kyn": ["Total"], "Starf": codes,
                                     "Laun og vinnutími": ["Total earnings"], "Eining": ["Median", "Weighted observations"]})
    d = {}
    for k, v in rows:
        d.setdefault(k["Starf"], {})[k["Eining"]] = v
    # Hagstofa suppresses a few cells in early years (waiters, 2014-2017). Carry them from the nearest year that has
    # them, as a ratio to their occupation group in both pay and numbers, and say so in the file.
    imputed = []
    for code, cell in d.items():
        if cell.get("Median") is not None and cell.get("Weighted observations") is not None:
            continue
        group = next(c for c in codes if c.split()[0] == code.split()[0][0])
        for y in range(YEAR + 1, 2026):
            near = {}
            for k, v in fetch_labels("VIN02001", {"Ár": [str(y)], "Kyn": ["Total"], "Starf": [code, group],
                                                  "Laun og vinnutími": ["Total earnings"],
                                                  "Eining": ["Median", "Weighted observations"]}):
                near.setdefault(k["Starf"], {})[k["Eining"]] = v
            if all(v is not None for v in near.get(code, {None: None}).values()):
                for unit in ("Median", "Weighted observations"):
                    cell[unit] = d[group][unit] * near[code][unit] / near[group][unit]
                imputed.append(f"{code}: from {y}, as a ratio to {group}")
                break
    professions.imputed = imputed
    out = []
    for name, group, inc, exc in PROFESSIONS:
        n = sum(d[c]["Weighted observations"] for c in inc) - sum(d[c]["Weighted observations"] for c in exc)
        if inc:
            pay = sum(d[c]["Median"] * d[c]["Weighted observations"] for c in inc) / max(sum(d[c]["Weighted observations"] for c in inc), 1)
            if exc:  # residual of a group: medians are not additive, so use the group's own median
                pay = d[inc[0]]["Median"]
        else:
            n, pay = None, None  # filled from the labour force survey / sector data
        out.append({"name": name, "group": group, "weight": n, "median_earnings": pay})
    return out


def main():
    global YEAR, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2025)
    YEAR = ap.parse_args().year
    OUT = ROOT / f"data/processed/baseline_{YEAR}.json"
    data = {
        "year": YEAR,
        "population_2026": population(),
        "employment_by_occupation_2025": employment_by_occupation(),
        "labour_rates_2025": labour_rates(),
        "inactive_2025": inactive(),
        "self_employed_pct_2025": self_employment(),
        "earnings_2025": earnings(),
        "migration_2025": migration(),
        "enterprise_births": enterprises(),
        "families_2026": families(),
        "professions_2025": professions(),
        "imputed": getattr(professions, "imputed", []),
        "sources": "Hagstofa PxWeb: MAN43000 VIN01100 VIN01104 VIN00961 VIN01006 VIN02004 MAN01401 FYR09002 MAN07108",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
