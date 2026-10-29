"""Parameters for starting the model in a past year and walking it through what actually happened.

    from history_params import base_overrides, calendar_overrides

base_overrides(2015) gives the parameter overrides that make 2015 the base year: its population file, its national
figures, its tax rules, and the settings written in 2025 krónur carried back to that year's krónur. The carrying
back is explicit — each block says what it is scaled by:

  c  the CPI against 2025 (prices, living costs, benefits, amounts in krónur written in the code)
  w  the wage index against 2025 (costs that follow pay: a student place, a childcare place)
  g  nominal GDP against 2025 (public spending lines, and the estimated sums in ma.kr.)

calendar_overrides(year) gives what changes in a given year: that year's tax rules, in the base year's krónur
(deflated by the actual CPI, so a threshold that kept pace with prices stays put in real terms), and the outside
world — what tourists, fish and aluminium earned, and what oil cost — as real indices against the base year.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data/processed/history_2015_2025.json"
# Þjóðskrá, fasteignamat 2016 (assessed at 2015 prices): all property, and the residential count
PROPERTY_VALUE = {2015: 5755.0}
DWELLINGS = {2015: 127_502}
# Hagstofa MAN05101 / MAN05210
BIRTHS, DEATHS = {2015: 4129}, {2015: 2178}
# Hagstofa THJ03204 against THJ01102: the business sector's net capital stock over GDP, current prices
CAPITAL_TO_GDP = {2015: 1.285}
REGIONS = ROOT / "data/reference/regions_2025.json"
FUEL_SHARE_OF_IMPORTS = .10        # EST: how much of what Iceland imports is oil and fuel


def load():
    return json.loads(HISTORY.read_text())


def _ratio(series, year, ref="2025"):
    return series[str(year)] / series[ref]


def _scaled(block, k, threshold=1000):
    """Every number in a block above `threshold` (i.e. an amount in krónur, not a rate) times k."""
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    return {key: (v * k if num(v) and abs(v) > threshold
                  else [x * k for x in v] if isinstance(v, list) and v and all(num(x) and abs(x) > threshold for x in v)
                  else v)
            for key, v in block.items()}


def base_overrides(year=2015):
    from ubisim.abm import params as P
    h = load()
    o, d, pol = h["outcomes"], h["drivers"], h["policy"]
    y = str(year)
    c, w, g = _ratio(o["cpi"], year), _ratio(o["wage_index"], year), _ratio(o["gdp_bn"], year)
    D = P.DEFAULTS
    marine = d["marine_exports_bn"][y] / d["marine_exports_bn"]["2023"]    # the fisheries block is 2023's
    alu = d["aluminium_exports_bn"][y] / d["aluminium_exports_bn"]["2025"]
    tax = pol["income_tax"][y]
    over = {
        "base": {
            "year": year, "GDP0": o["gdp_bn"][y], "C0": o["consumption_bn"][y], "X0": o["exports_bn"][y],
            "M0": o["imports_bn"][y], "CA0": o["current_account_bn"][y], "DEBT0": o["gov_liabilities_bn"][y],
            "INTEREST0": o["gov_interest_bn"][y], "PROPERTY_VALUE0": PROPERTY_VALUE[year],
            "PROPERTY_TAX0": o["property_tax_bn"][y], "WAGE_BILL0": o["taxable_wages_bn"][y],
            "PUBLIC_PAYROLL0": o["gov_payroll_bn"][y], "DEFICIT0": o["gov_balance_bn"][y],
            "REVENUE0": o["gov_revenue_bn"][y], "EXPENDITURE0": o["gov_expenditure_bn"][y],
            "INFLATION0": o["cpi"][y] / o["cpi"][str(year - 1)] - 1,
            "krona_scale": c, "static_scale": g,
            "ratios": {"cpi": c, "wages": w, "gdp": g},
        },
        "policy": {
            "income_tax_brackets": tax["brackets"], "personal_credit": tax["personal_credit"],
            "payroll_tax": pol["payroll_tax"][y], "pension_contrib_employer": pol["employer_pension"][y],
            "state_seed_money": D["policy"]["state_seed_money"] * c,
            "net_wealth_tax_threshold": D["policy"]["net_wealth_tax_threshold"] * c,
            "inheritance_tax_floor": pol["inheritance_floor"][y],
            "public_dwelling_cost_m_isk": D["policy"]["public_dwelling_cost_m_isk"] * c,
            "ubi_taper_start": D["policy"]["ubi_taper_start"] * c,
        },
        "benefits": _scaled(D["benefits"], c),
        "costs": _scaled(D["costs"], c),
        "health": {"public_spending_bn": D["health"]["public_spending_bn"] * g},
        "schooling": {"spending_bn": D["schooling"]["spending_bn"] * g},
        "crime": {"responsive_spending_bn": D["crime"]["responsive_spending_bn"] * g,
                  "substance_threshold": D["crime"]["substance_threshold"] * c,
                  "prison_cost_per_day": D["crime"]["prison_cost_per_day"] * c},
        "education": {"cost_per_student_bn": D["education"]["cost_per_student_bn"] * w},
        "childcare": {"cost_per_place_bn": D["childcare"]["cost_per_place_bn"] * w},
        "demography": {"births_per_year": BIRTHS[year], "deaths_per_year": DEATHS[year]},
        "markets": {"dwellings0": DWELLINGS[year]},
        "fisheries": {k: D["fisheries"][k] * marine for k in ("revenue0", "intermediate0", "compensation0",
                                                               "capital_cost0")},
        "energy": {"smelter_net_export_bn_per_twh": D["energy"]["smelter_net_export_bn_per_twh"] * alu},
        "inheritance": {"floor_today": pol["inheritance_floor"][y]},
        "ventures": _scaled({k: D["ventures"][k] for k in ("profit_scale", "capital_reference", "profit_cap")}, c),
        "wealth": {},
        "gambling": {"foreign_losses_bn": D["gambling"]["foreign_losses_bn"] * g},
        "enforcement": {k: D["enforcement"][k] * g for k in ("evasion_bn", "benefit_admin_saved_bn")},
        "free_services": {k: D["free_services"][k] * g for k in ("health_out_of_pocket_bn", "internet_household_bn")},
        "property_ownership": {"custodian_admin_bn": D["property_ownership"]["custodian_admin_bn"] * g},
        "capital": {"stock_to_gdp": CAPITAL_TO_GDP[year]},
        "regions": regions_base(year),
    }
    return over


def _regions_year(year):
    rg = json.loads(REGIONS.read_text())
    y = str(year)
    m, cap = rg["migration"][y], "From capital area"
    out = sum(v for k, v in m[cap].items() if k not in ("To capital area", "To foreign countries"))
    into = sum(v.get("To capital area", 0) for k, v in m.items() if k not in (cap, "From abroad"))
    ab = m["From abroad"]
    abroad_cap = ab.get("To capital area", 0)
    abroad_all = sum(v for k, v in ab.items() if k != "To foreign countries")
    return rg, out, into, abroad_cap / abroad_all


def regions_base(year):
    """The areas in the base year (MAN03250 and MAN07108, 1 January; MAN01002 that year). Pay by area is published
    from 2025 only, and its ratio is kept."""
    rg, out, into, arrivals = _regions_year(year)
    pop = rg["population"]
    capital, total = pop["Capital region"][str(year)], pop["Total"][str(year)]
    persons, units = (rg["families"][k] for k in ("persons", "units"))
    per = lambda a: persons[a][str(year)] / units[a][str(year)]
    rest = ((persons["Total"][str(year)] - persons["Capital region"][str(year)])
            / (units["Total"][str(year)] - units["Capital region"][str(year)]))
    return {"capital_share": capital / total, "move_rate_from_capital": out / capital,
            "move_rate_to_capital": into / (total - capital), "arrival_capital_share": arrivals,
            "household_size_ratio": per("Capital region") / rest}


def benefit_scale(h, year, base_year=2015):
    """How much more generous benefits were, in real terms, than in the base year: real social benefits per
    person aged 67 and over (the pension reform of 2017 and later rises). 2020-21 are interpolated between 2019
    and 2022: their spike is COVID unemployment benefit, which the model pays out itself."""
    o = h["outcomes"]
    per = lambda y: o["gov_social_benefits_bn"][y] / o["cpi"][y] / o["population_67_plus"][y]
    if year in (2020, 2021):
        a, b = per("2019"), per("2022")
        return (a + (b - a) * (year - 2019) / 3) / per(str(base_year))
    return per(str(year)) / per(str(base_year))


def calendar_overrides(year, base_year=2015):
    """What was different in `year`, as overrides on a run based in `base_year`."""
    h = load()
    o, d, pol = h["outcomes"], h["drivers"], h["policy"]
    y, b = str(year), str(base_year)
    price = o["cpi"][y] / o["cpi"][b]                    # actual prices since the base year
    real = lambda s: (s[y] / o["cpi"][y]) / (s[b] / o["cpi"][b])
    tax = pol["income_tax"][y]
    # partners' prices against the 2.5% trend the model carries, and oil against partners' prices
    foreign = 1.0
    for yy in range(base_year + 1, year + 1):
        foreign *= (1 + d["partner_inflation_pct"][str(yy)] / 100) / 1.025
    level = foreign * 1.025 ** (year - base_year)          # partners' price level since the base year
    brent = (d["brent_usd_bbl"][y] / d["brent_usd_bbl"][b]) / level
    # Levels are the record's, so the model's own indexation to wages is switched off: applied on top, it indexed
    # every benefit twice, by the record's real rise and again by the model's wages (found 2026-09-26: pensions
    # 8% and support to those out of work a third too generous by 2025). Pensions and disability follow the
    # record's real benefits per pensioner, which carry the 2017 reform; support to people of working age follows
    # the wage index, as unemployment benefit did.
    k = benefit_scale(h, year, base_year)
    kw = real(o["wage_index"])
    # support for people of working age — unemployment benefit, social assistance, housing benefit, child
    # benefit — follows the wage index; pensions and disability the record's real benefits per pensioner
    working_age = ("nonwork_", "child_", "unemployment_", "social_assistance_", "housing_benefit_")
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    benefits = {}
    for key, v in base_overrides(base_year)["benefits"].items():
        f = kw if key.startswith(working_age) else k
        if num(v) and abs(v) > 1000:
            benefits[key] = v * f
        elif isinstance(v, list) and v and all(num(x) and abs(x) > 1000 for x in v):
            benefits[key] = [x * f for x in v]
    benefits["wage_indexation"] = 0.0
    return {
        "regions": {"arrival_capital_share": _regions_year(year)[3]},    # where that year's arrivals settled
        "benefits": benefits,
        "policy": {"income_tax_brackets": [[lo / price, r] for lo, r in tax["brackets"]],
                   "personal_credit": tax["personal_credit"] / price,
                   # the record's own thresholds, year by year: the model's yearly rise is switched off
                   "threshold_index": 1.0, "threshold_real_growth": 0.0,
                   "payroll_tax": pol["payroll_tax"][y], "pension_contrib_employer": pol["employer_pension"][y]},
        "inheritance": {"floor_today": pol["inheritance_floor"][y] / price},
        "trade": {"price": {"tourism": real(d["tourism_revenue_bn"]), "marine": real(d["marine_exports_bn"]),
                            "aluminium": real(d["aluminium_exports_bn"]), "other": 1.0},
                  "import_price": foreign * (1 + FUEL_SHARE_OF_IMPORTS * (brent - 1))},
        "history": {"crisis_support_bn": pol["crisis_support_pct_gdp"].get(y, 0.0) / 100 * o["gdp_bn"][y] / price,
                    "job_retention": pol["job_retention"].get(y, 0.0)},
    }
