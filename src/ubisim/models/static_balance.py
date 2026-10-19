"""Static (first-round) fiscal balance of a UBI in Iceland, with the reform's financing sources.
All amounts in billion ISK per year, 2025 prices. No behavioural, price or growth effects:
this is the gap the dynamic model has to close.

Sources: Hagstofa PxWeb (THJ05111, THJ05132, THJ05143, THJ05161, THJ05165, MAN00101, SJA08109),
HMS fasteignamat 2026, Skatturinn persónuafsláttur 2026, Landssamtök lífeyrissjóða.
Items marked EST are estimates to be replaced by data or by the dynamic model.
"""
POP_TOTAL, POP_CHILD = 394_324, 84_881          # 1 Jan 2026 (MAN00101)
GDP_2025, DEFICIT_2025 = 4955.6, -120.1         # THJ05111
SOCIAL_BENEFITS_2025 = 358.6                    # D.27 (THJ05143), all replaced by UBI
# v9: each from its primary source, named beside it
PROPERTY_VALUE_2026 = 17_467.6                  # HMS fasteignamat 2026; was 17,300
AGRI_SUBSIDIES_2024, ALL_SUBSIDIES_2024 = 19.66, 75.0   # THJ05161
CUSTOMS_2025 = 7.717                            # trade_customs_2025.csv
# The non-agricultural subsidies, grouped (gov_items_2025.csv). "Other" leaves out cultural services (12.64 of
# 17.35), which the culture lever carries; innovation and film are kept unless their own lever cuts them.
SUBSIDY_GROUPS = [("innovation", "innovation and film", 21.7),
                  ("heating", "rural heating", 6.33),
                  ("transition", "energy-transition grants", 10.43),
                  ("transport", "buses and regional routes", 10.52),
                  ("other", "media, waste and other (culture apart)", 12.64)]
PERS_AFSL_YEAR = 869_898 / 1e9                  # bn ISK per person, 2026
PUBLIC_PAYROLL_2025 = 709.6                     # D.1 compensation of employees (THJ05143)
FISHERIES_PROFIT = (46.2, 72.8, 84.9)           # SJA08109 profit after 6% capital cost, 2024/2023/2022
PENSION_ASSETS = 7_854.5                        # common pension assets, end-2025: 159% of GDP (pension_funds_2025.csv);
                                                # was 187% (2022, EST)
TAXABLE_WAGES_2025 = 2174.5                     # TEK02001, sum of months
INCOME_TAX_INDIVIDUALS_2025, CORPORATE_TAX_2025 = 693.3, 148.0   # THJ05132
CORPORATE_TAX_RATE = 0.20
# Travel per diems (dagpeningar): 12.65 bn received, 12.30 bn deducted tax-free in income year 2016
# (Skatturinn álagning I_B1_c, wages 1,019 bn). Scaled to 2025 by taxable wages.
# v9: what ending them saves is 9.2 ma.kr. (state spending 2.5 + the tax deduction 6.7; gov_items_2025.csv), not the
# ~13 the formula below gave; scaled to that
PER_DIEM_2025 = 12.65 * TAXABLE_WAGES_2025 / 1018.7 * 9.2 / 13.0

# Child UBI: share INVESTED in the start-of-life fund by birth order (the reform's schedule).
# The invested share protects children: parents cannot live off many children's UBI.
CHILD_SCHEDULES = {
    "graduated": {1: .5, 2: .5, 3: .6, 4: .7, 5: .7, 6: .8, 7: .9},
    "90_from_3rd": {1: .5, 2: .5, 3: .9, 4: .9, 5: .9, 6: .9, 7: .9},
}
CHILD_BIRTH_ORDER_SHARE = {1: .42, 2: .33, 3: .16, 4: .06, 5: .02, 6: .007, 7: .003}  # EST placeholder

# ---------------------------------------------------------------- the costs of governing
# Hagstofa THJ05142 (COFOG 0111, executive and legislative organs) puts the whole apparatus — parliament,
# ministers, the ministries' running costs and the presidency — at 16.1 ma.kr. in 2025. The split below is EST
# within that total; the total itself is not.
#
# They are listed separately because they are what gets argued about, and the argument should be had with the
# magnitudes visible: the whole package, church funding included, is worth about 14 ma.kr. a year against a
# residual gap near 358. That is not a reason against doing any of it. It is a reason not to call it financing.
EXECUTIVE_LEGISLATIVE_2025 = 16.1   # THJ05142, COFOG 0111
GOVERNANCE = {
    "Alþingi, operations": 6.4,          # EST split of the 16.1 above
    "þingfararkaup, 63 members": 1.1,    # EST: 63 x ~1.4 m ISK a month, base pay only
    "Ministers' salaries": 0.30,         # EST: 12 x ~2.1 m ISK a month
    "Presidency": 0.42,                  # EST: Embætti forseta Íslands
    "Political party funding": 0.73,     # EST: framlög til stjórnmálaflokka
    "Rural travel support (Loftbrú etc.)": 1.35,   # EST: air and commuting support, replaced by the UBI
    "Foreign service, reduced": 2.10,    # EST: the share of embassy costs a Zoom-era service can drop
}

# Church and registered religious bodies. Sóknargjöld are collected through the income tax system and handed on
# per registered member, so ending them leaves the money with the state rather than costing it anything to
# collect — the contribution simply folds into general taxation. The National Church also receives a separate
# contribution under the 2019 agreement. EST figures, of the right order.
CHURCH = {
    # v9: scaled to 7.98 ma.kr. in all, cemeteries (1.59) kept (gov_items_2025.csv)
    "Sóknargjöld, all registered bodies": 3.60 * 7.98 / 7.75,
    "National Church contribution": 3.70 * 7.98 / 7.75,
    "Kirkjumálasjóður and equalisation": 0.45 * 7.98 / 7.75,
}


P = dict(
    ubi_month=300_000,          # ISK per resident per month, not taxable (the reference amount)
    child_schedule="graduated", # key of CHILD_SCHEDULES
    child_invested_flat=0.5,    # one share for every child; None to use the schedule above
    child_fund_cpi_indexed=True,# child gets paid-in principal at 18, CPI-indexed or nominal; returns fund UBI
    cpi_inflation=0.03,         # used only for the nominal-principal memo
    vat_flat25_gain=90,         # EST: +60..120 from 24%/11% -> flat 25%
    pers_afsl_users=270_000,    # EST: people fully using persónuafsláttur
    # financing levers
    pension_real_return=0.030,  # real return on pension-fund assets redirected to UBI
    pension_return_share=1.0,   # share of that return redirected (occupational pensions replaced by UBI)
    # Mandatory pension contributions (today 4% employee + 11.5% employer):
    #   "social_security": kept as 15.5% contributions to the UBI fund, split equally employee/employer
    #   "cut": abolished; replaced by higher income tax and corporate tax (levers below)
    pension_contribution_mode="social_security",
    contribution_rate=0.155,
    income_tax_increase=0.0,    # "cut" mode: relative increase in personal income tax revenue
    corporate_tax_rate=0.20,    # "cut" mode: new corporate tax rate
    vat_input_restriction_gain=200,  # EST (100..350): input VAT reclaimable only on value-chain inputs
    per_diem_abolished=True,    # per diems abolished; companies pay documented travel
    per_diem_tax_rate=0.40,     # EST: average marginal income tax on former tax-free per diems
    per_diem_conversion=0.5,    # EST: share converted to receipt-based reimbursement (stays untaxed)
    per_diem_public_share=0.35, # EST: share of per diems paid by the public sector (saved outright)
    pension_topup_cost=0.0,     # transition top-up max(0, accrued pension - UBI); needs pension distribution data
    prop_tax_extra_pp=1.0,      # extra property tax, percentage points of fasteignamat
    prop_price_response=-0.10,  # EST: property value change caused by the tax (capitalisation)
    fisheries_rent_capture=0.8, # share of fisheries profit above 6% cost of capital captured
    other_subsidies_cut=1.0,    # share of non-agricultural subsidies cut
    public_payroll_cut=0.20,    # share of public payroll removed
    # Governing costs (see GOVERNANCE): the share of each line removed.
    parliament_cut=0.25,        # a smaller, cheaper parliament
    mp_pay_cut=0.25,            # þingfararkaup reduced
    minister_pay_cut=0.25,
    presidency_cut=0.80,        # a smaller presidential office
    party_funding_cut=1.0,
    rural_travel_cut=1.0,       # people have the UBI and can choose to spend it on travelling
    foreign_service_cut=1.0,
    # Ministers barred from sitting in parliament means MORE paid people, not fewer: the alternates take their
    # seats, so twelve ministers are added on top of 63 members rather than drawn from among them.
    ministers_outside_parliament=True,
    # Separation of church and state: no religious body is funded. What was collected as sóknargjöld stays with
    # the state, folded into general taxation rather than handed on.
    church_funding_cut=1.0,
    payroll_tax_loss=0.35,      # EST: income tax lost per krona of removed public pay (before re-employment)
)


def child_invested_share(schedule="graduated", flat=None):
    """Average share of child payments invested. A flat share treats every child alike; the graduated schedule
    invests more of each additional child's, which the flat option deliberately drops."""
    if flat is not None:
        return float(flat)
    invested = CHILD_SCHEDULES[schedule]
    return sum(CHILD_BIRTH_ORDER_SHARE[k] * invested[k] for k in invested)


def run(p=P):
    gross = POP_TOTAL * p["ubi_month"] * 12 / 1e9
    prop_base = PROPERTY_VALUE_2026 * (1 + p["prop_price_response"])
    cut = PUBLIC_PAYROLL_2025 * p["public_payroll_cut"]
    items = {
        "UBI gross cost": -gross,
        "Social benefits replaced": SOCIAL_BENEFITS_2025,
        "Persónuafsláttur abolished (EST)": p["pers_afsl_users"] * PERS_AFSL_YEAR,
        "VAT flat 25% (EST)": p["vat_flat25_gain"],
        "Agriculture subsidies cut": AGRI_SUBSIDIES_2024 * p.get("agriculture_subsidy_cut", 1.0),
        "Customs abolished": -CUSTOMS_2025 * (1 - p.get("customs_kept", 0.0)),
        "Existing 2025 deficit": DEFICIT_2025,
        "Pension-fund returns": PENSION_ASSETS * p["pension_real_return"] * p["pension_return_share"],
        "Pension contributions → UBI fund": (TAXABLE_WAGES_2025 * p["contribution_rate"]
                                             if p["pension_contribution_mode"] == "social_security" else 0.0),
        "Income tax increase": INCOME_TAX_INDIVIDUALS_2025 * p["income_tax_increase"],
        "Corporate tax change": CORPORATE_TAX_2025 * (p["corporate_tax_rate"] / CORPORATE_TAX_RATE - 1),
        "VAT input credit restricted (EST)": p["vat_input_restriction_gain"],
        "Pensioner transition top-up": -p["pension_topup_cost"],
        "Per diems abolished (EST)": (PER_DIEM_2025 * (p["per_diem_public_share"]
                                      + (1 - p["per_diem_public_share"]) * (1 - p["per_diem_conversion"]) * p["per_diem_tax_rate"])
                                      if p["per_diem_abolished"] else 0.0),
        "Extra property tax": prop_base * p["prop_tax_extra_pp"] / 100,
        "Fisheries resource rent": FISHERIES_PROFIT[1] * p["fisheries_rent_capture"],
        "Other subsidies cut": (ALL_SUBSIDIES_2024 - AGRI_SUBSIDIES_2024) * p["other_subsidies_cut"],
        **{f"Subsidies cut: {name}": amount * p.get(f"subsidy_cut_{key}", 0.0) for key, name, amount in SUBSIDY_GROUPS},
        "Public payroll cut (net of lost tax)": cut * (1 - p["payroll_tax_loss"]),
        "Alþingi, smaller and cheaper": GOVERNANCE["Alþingi, operations"] * p["parliament_cut"],
        "þingfararkaup reduced": GOVERNANCE["þingfararkaup, 63 members"] * p["mp_pay_cut"],
        "Ministers' pay reduced": GOVERNANCE["Ministers' salaries"] * p["minister_pay_cut"],
        "Presidency made formulaic": GOVERNANCE["Presidency"] * p["presidency_cut"],
        "Party funding ended": GOVERNANCE["Political party funding"] * p["party_funding_cut"],
        "Rural travel support ended": GOVERNANCE["Rural travel support (Loftbrú etc.)"] * p["rural_travel_cut"],
        "Foreign service reduced": GOVERNANCE["Foreign service, reduced"] * p["foreign_service_cut"],
        "Church and religious funding ended": sum(CHURCH.values()) * p["church_funding_cut"],
        # a cost, not a saving: twelve more salaries once ministers cannot also be members
        "Ministers seated outside parliament": (-GOVERNANCE["þingfararkaup, 63 members"] / 63 * 12
                                                if p["ministers_outside_parliament"] else 0.0),
    }
    invested = POP_CHILD * p["ubi_month"] * 12 / 1e9 * child_invested_share(p["child_schedule"],
                                                                            p.get("child_invested_flat"))
    # Steady state: ~18 cohorts of deposits, average deposit held ~9 years.
    fund_assets = invested * 9
    real_return = fund_assets * p["pension_real_return"]
    memo = {
        "Child UBI invested per year": invested,
        "Start-of-life fund assets, steady state": fund_assets,
        "Fund return to UBI, steady state (real)": real_return,
    }
    if not p["child_fund_cpi_indexed"]:
        memo["  + inflation erosion kept by UBI"] = fund_assets * p["cpi_inflation"]
    return items, sum(items.values()), memo


def breakeven_ubi(p=P):
    """UBI (ISK/month) at which the static balance is zero, holding all other levers fixed."""
    items, bal, _ = run(p)
    offsets = bal - items["UBI gross cost"]
    return offsets * 1e9 / POP_TOTAL / 12


if __name__ == "__main__":
    items, bal, memo = run()
    for k, v in items.items():
        print(f"{k:40s}{v:9.1f}")
    print(f"{'BALANCE':40s}{bal:9.1f}   ({bal / GDP_2025:.1%} of GDP)")
    for sched in CHILD_SCHEDULES:
        _, _, m = run({**P, "child_schedule": sched})
        print(f"\nChild schedule '{sched}' (invested share {child_invested_share(sched):.0%}):")
        for k, v in m.items():
            print(f"  memo: {k:42s}{v:8.1f}")
    print(f"\nStatic break-even UBI with these levers: {breakeven_ubi():,.0f} ISK/month")

    print("\nUBI level sweep (all other levers as above)")
    for ubi in range(150_000, 500_001, 50_000):
        print(f"  {ubi:>7,} ISK/month  balance {run({**P, 'ubi_month': ubi})[1]:8.1f}")

    high = {**P, "pension_real_return": .035, "prop_tax_extra_pp": 2.0, "fisheries_rent_capture": 1.0,
            "public_payroll_cut": .30, "vat_flat25_gain": 120}
    items, bal, _ = run(high)
    print(f"\nHigh-end financing (3.5% pension return, +2pp property tax, full fisheries rent, 30% payroll cut):"
          f"\n  balance at 450k {bal:.1f}; break-even UBI {breakeven_ubi(high):,.0f} ISK/month")

    print("\nContribution modes and VAT input restriction")
    for label, ch in [("contributions kept, no VAT restriction", dict(vat_input_restriction_gain=0)),
                      ("contributions kept, VAT restriction 200", {}),
                      ("contributions cut, no replacement", dict(pension_contribution_mode="cut")),
                      ("cut + income tax +30% + CIT 30%", dict(pension_contribution_mode="cut",
                                                               income_tax_increase=.30, corporate_tax_rate=.30))]:
        q = {**P, **ch}
        print(f"  {label:42s} balance {run(q)[1]:8.1f}  break-even {breakeven_ubi(q):>9,.0f}")
