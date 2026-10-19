"""Assemble 2015-2025 for the backcast: what happened (to compare the model with), what came from outside (to
feed it), and the policy calendar (history/policy_calendar.json, kept by hand with its sources).

    .venv/bin/python scripts/build_history.py

Writes data/processed/history_2015_2025.json. Every series is annual; quarterly and monthly tables are averaged
(prices, rates) or summed (flows, passengers) within the year.
"""
import json
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ubisim.data.hagstofa import fetch_labels  # noqa: E402

YEARS = [str(y) for y in range(2014, 2026)]   # 2014 for growth rates into 2015
OUT = ROOT / "data/processed/history_2015_2025.json"
CALENDAR = ROOT / "history/policy_calendar.json"


def annual(rows, key, agg="mean"):
    """Rows keyed by a period label (2015, 2015Q1, 2015M01) -> {year: value}."""
    acc = defaultdict(list)
    for k, v in rows:
        if v is not None:
            acc[k[key][:4]].append(v)
    f = (lambda xs: sum(xs) / len(xs)) if agg == "mean" else sum
    return {y: f(xs) for y, xs in sorted(acc.items()) if y in YEARS and (agg == "mean" or len(xs) in (1, 4, 12))}


def one(table, sel, key="Ár", agg="mean"):
    return annual(fetch_labels(table, sel), key, agg)


def outcomes():
    out = {}
    out["cpi"] = one("VIS01005", {"Year": YEARS, "Index": ["Consumer price index"], "Base": ["Base 1988"]}, "Year")
    out["cpi_less_housing"] = one("VIS01005", {"Year": YEARS, "Index": ["Consumer price index less housing cost "],
                                               "Base": ["Base 1988"]}, "Year")
    out["wage_index"] = one("LAU04200", {"Ár": YEARS, "Eining": ["Annual average"]})
    for unit, name in [("Employment rate", "employment_rate"), ("Unemployment rate", "unemployment_rate"),
                       ("Activity rate", "activity_rate"), ("Average hours of work", "hours")]:
        out[name] = one("VIN01104", {"Ár": YEARS, "Skipting": ["Total"], "Eining": [unit]})
    for item, name in [("Total revenue", "gov_revenue_bn"), ("Total expenditure", "gov_expenditure_bn"),
                       ("Financial balance", "gov_balance_bn"), ("Financial balance % of GDP", "gov_balance_pct_gdp")]:
        out[name] = one("THJ05111", {"Skipting": [item], "Ár": YEARS})
    gdp = fetch_labels("THJ01102", {"Ár": YEARS, "Skipting": "*"})
    for label, name in [("1. Private final consumption expenditure", "consumption_bn"),
                        ("6. Exports of goods and services", "exports_bn"),
                        ("7. Less: Imports of goods and services", "imports_bn"),
                        ("8. Gross Domestic Product", "gdp_bn"), ("11. Balance on current account", "current_account_bn")]:
        out[name] = {k["Ár"]: v for k, v in gdp if k["Skipting"].strip() == label}
    real = fetch_labels("THJ01103", {"Ár": YEARS, "Skipting": "*"})
    gdp_real = {k["Ár"]: v for k, v in real if "gross domestic product" in k["Skipting"].lower()
                and "per capita" not in k["Skipting"].lower()}
    out["gdp_real_index"] = {y: v / gdp_real["2015"] for y, v in sorted(gdp_real.items())} if "2015" in gdp_real else {}
    for item, name in [("33 Liabilities", "gov_liabilities_bn")]:
        out[name] = one("THJ05181", {"Eining": ["Million ISK"], "Skipting": [item], "Ár": YEARS})
    for item, name in [("24 Interest", "gov_interest_bn"), ("21 Compensation of employees", "gov_payroll_bn"),
                       ("27 Social benefits", "gov_social_benefits_bn"), ("25 Subsidies", "gov_subsidies_bn")]:
        out[name] = one("THJ05143", {"Eining": ["Million ISK"], "Skipting": [item], "Ár": YEARS})
    for item, name in [("1131 Recurrent taxes on immovable property", "property_tax_bn"),
                       ("1133 Estate, inheritance, and gift taxes", "inheritance_tax_bn"),
                       ("1111 Payable by individuals", "income_tax_individuals_bn"),
                       ("1112 Payable by corporations", "corporate_tax_bn")]:
        out[name] = one("THJ05132", {"Eining": ["Million ISK"], "Skipting": [item], "Ár": YEARS})
    wages = fetch_labels("TEK02001", {"Atvinnugrein": ["Total"], "Eining": ["Taxable wages"], "Mánuður": "*"})
    out["taxable_wages_bn"] = annual(wages, "Mánuður", "sum")
    pop = fetch_labels("MAN00101", {"Kyn": ["Total"], "Aldur": ["Total"], "Ár": [str(int(y) + 1) for y in YEARS]})
    out["population_end_of_year"] = {str(int(k["Ár"]) - 1): v for k, v in pop}
    ages = fetch_labels("MAN00101", {"Kyn": ["Total"], "Aldur": "*", "Ár": [str(int(y) + 1) for y in YEARS]})
    old = defaultdict(float)
    for k, v in ages:
        lab = k["Aldur"].strip()
        if lab != "Total" and v and not lab.startswith("Under") and int(lab.split()[0]) >= 67:
            old[str(int(k["Ár"]) - 1)] += v
    out["population_67_plus"] = dict(sorted(old.items()))
    mig = fetch_labels("MAN01401", {"Ár": YEARS, "Kyn": ["Total"], "Aldur": ["Total"],
                                    "Ríkisfang": ["Icelandic citizens", "Foreign citizens"],
                                    "Tegund flutnings": ["Immigration", "Emigration"]})
    for k, v in mig:
        who = "icelandic" if k["Ríkisfang"].startswith("Icel") else "foreign"
        out.setdefault(f"{k['Tegund flutnings'].lower()}_{who}", {})[k["Ár"]] = v
    return out


def drivers():
    out = {}
    exp = fetch_labels("UTA05003", {"Skipting": "*", "Ársfjórðungur": "*"})
    for label, name in [("Revenues of foreign travellers", "tourism_revenue_bn"),
                        ("Exports of marine products", "marine_exports_bn"),
                        ("Thereof exports of aluminium and aluminum products", "aluminium_exports_bn"),
                        ("Exports of goods and services", "exports_total_bn")]:
        out[name] = annual([(k, v) for k, v in exp if k["Skipting"].strip() == label], "Ársfjórðungur", "sum")
    # departures of foreign citizens through Keflavík: the one series that runs through the whole period
    passengers = fetch_labels("SAM02001", {"Ríkisfang": ["Foreigners"], "Mánuður": "*"})
    out["foreign_passengers"] = annual(passengers, "Mánuður", "sum")
    marine = fetch_labels("SJA06100", {"Item": ["Index"], "Category": ["Price index of marine products"], "Month": "*"})
    out["marine_price_index"] = annual(marine, "Month")
    world = json.loads((ROOT / "history/world_prices.json").read_text())
    out["aluminium_usd_t"], out["brent_usd_bbl"] = world["aluminium_usd_t"], world["brent_usd_bbl"]
    out["partner_inflation_pct"] = world["partner_inflation_pct"]
    return out


def main():
    out, drv = outcomes(), drivers()
    # Hagstofa reports these in millions of krónur; the model speaks in ma.kr.
    for part in (out, drv):
        for k in part:
            if k.endswith("_bn"):
                part[k] = {y: v / 1000 for y, v in part[k].items()}
    data = {"years": [int(y) for y in YEARS if y >= "2015"], "outcomes": out, "drivers": drv,
            "policy": json.loads(CALENDAR.read_text()) if CALENDAR.exists() else None,
            "sources": "Hagstofa PxWeb: TEK02001 THJ05181 THJ05143 THJ05132 VIS01005 LAU04200 VIN01104 THJ05111 THJ01102 THJ01103 MAN00101 MAN01401 "
                       "UTA05003 SAM02001 SJA06100; policy calendar: see history/policy_calendar.json"}
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    for part in ("outcomes", "drivers"):
        for k, v in data[part].items():
            print(f"{part:9s} {k:28s} {len(v):3d} years  {min(v) if v else '-'}-{max(v) if v else '-'}")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
