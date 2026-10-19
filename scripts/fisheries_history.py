"""The fisheries from the quota system's start, and a fund that would have taken part of their rent from 1984
(docs/FISHERIES_PAST.md). Accounting, not agents: the agent model takes over in 2015.

    .venv/bin/python scripts/fisheries_history.py [--capture .5] [--eta .1] [--payout .03] [--crisis pay]
                                                  [--start 1984] [--return-usd .06] [--sweep]

The rent each year, nominal, in million krónur:
  * 1997-2024: fishing's net profit after the imputed cost of capital (Hagstofa SJA08101, the annuity approach: before
    interest and currency losses, so 2008's debt shock is not counted as lost rent), plus processing's net profit
    (SJA08103 line 14), plus the fees actually paid (below), which those profits are after.
  * 1993-96: SJA08107's net-profit margin on the sector's revenue.
  * 1984-92: the margin is from the literature, the sector made losses every year of the 1980s (Althingi 121/s/1175,
    from Þjóðhagsstofnun) and thin margins in the early 1990s. The levels used are EST and marked so.
  * Revenue before 1997 is marine exports (SJA04902), scaled by the sector's revenue against exports in 1997-98.
  * 2025 repeats 2024 in 2025 prices (an EST placeholder until Hagstofa publishes 2025).

The fee paid, observed (v9; compiled from Fiskistofa, Hagstofa and the state accounts, ríkisreikningur, in
data/reference/fisheries, which is not redistributed here: the series built from it is data/processed/fisheries_history.json):
the fishing fee collected each calendar year 2004-2025 (fishing_fees_calendar_total_2004_2025.csv), and the
Development Fund levies 1995-2005 (fishery_levies_1993_2015.csv: on quota, general and the national tax list).
Monitoring and licence fees are cost recovery, not a take on the rent, and are left out. v8 used estimates here,
the 2004-07 ones two years out of place, and from 2012 the government's "1415 Rent" line, an upper bound.

The take. A share `capture` of positive rent goes to a fund from `start`. The fishery's answer is a range, from none
(a tax on pure rent changes no decision) to a slower-growing rent base: the rent is reduced by eta x capture (EST,
0-0.2). The fund is held abroad in dollars, earns `return_usd` a year (nominal, EST: a 60/40 world portfolio has
returned about 6% a year in dollars since 1984; the yearly path is a research item) and pays out `payout` of its value
a year, shared equally among adults (18+).

The capital controls of November 2008 to March 2017 (`crisis`):
  * pay        payouts continue (an inflow, which the controls did not stop);
  * freeze     no payouts 2009-2016; what would have been paid stays invested;
  * repatriate a share `repatriate` of the fund is brought home in 2009 at the crash exchange rate and retires public
               debt; payouts continue on the rest.

Writes data/processed/fisheries_history.json: rent, take, fund, dividend per adult a month in 2025 krónur, the
industry's rent after the take, and the checks against the literature.
"""
import argparse
import itertools
import json
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/hagstofa/fisheries"
OUT = ROOT / "data/processed/fisheries_history.json"
YEARS = list(range(1984, 2026))

# EST: net margin on revenue, after a normal return on capital, where no table reaches. The 1980s were years of
# losses of 1-9% of revenue (Althingi 121/s/1175); 1990-92 lie between those and SJA08107's 2.2% in 1993.
MARGIN_EST = {1984: -.05, 1985: -.03, 1986: -.01, 1987: -.02, 1988: -.06, 1989: -.03, 1990: -.01, 1991: .0, 1992: .01}
REF = ROOT / "data/reference/fisheries"
LEVIES = ("development_fund_fee_quota", "development_fund_fee_general", "development_fund_fee_national_tax_list")


def fees_paid():
    """Observed fees and rent levies, million krónur nominal, by calendar year (0 where none was paid)."""
    import csv
    out = {y: 0.0 for y in YEARS}
    for row in csv.DictReader(open(REF / "fishing_fees_calendar_total_2004_2025.csv")):
        if row["period_type"] == "calendar_year":
            out[int(row["period"])] += float(row["value"])
    for row in csv.DictReader(open(REF / "fishery_levies_1993_2015.csv")):
        if row["period_type"] == "calendar_year" and row["levy"] in LEVIES and row["unit"].startswith("isk_million"):
            out[int(row["period"])] = out.get(int(row["period"]), 0.0) + float(row["value"])
    # 2025: Ríkisreikningur gives the fishing fee as 13.47 ma.kr.; Hagstofa's 5.84 in the file is flagged as unusually
    # low and is contradicted by the state accounts
    out[2025] = 13_470.0
    return out
CONTROLS = range(2009, 2017)


def _load(table):
    ds = json.loads((RAW / f"{table}.json").read_text())
    ds = ds.get("dataset", ds)
    ids, size, vals = ds["id"], ds["size"], ds["value"]
    cats = []
    for i in ids:
        c = ds["dimension"][i]["category"]
        idx = c["index"]
        order = sorted(idx, key=lambda k: idx[k]) if isinstance(idx, dict) else idx
        cats.append([c["label"][k] for k in order])
    if isinstance(vals, dict):
        v = [None] * int(np.prod(size))
        for k, x in vals.items():
            v[int(k)] = x
        vals = v
    return ids, cats, vals, size


def series(table, **sel):
    """{year: value} for the cells matching `sel` (dimension code → label); other dimensions must be single."""
    ids, cats, vals, size = _load(table)
    out = {}
    for combo in itertools.product(*[range(s) for s in size]):
        labs = [cats[d][c] for d, c in enumerate(combo)]
        if all(sel.get(ids[d]) in (None, labs[d]) for d in range(len(ids))):
            flat = 0
            for d, c in enumerate(combo):
                flat = flat * size[d] + c
            year = next(l for d, l in enumerate(labs) if ids[d] in ("Ár", "Year"))
            if vals[flat] is not None:
                out[int(year)] = float(vals[flat])
    return out


def adults():
    """Residents aged 18 and over, 1 January of each year (MAN00101)."""
    ids, cats, vals, size = _load("MAN00101")
    ages, years = cats[1], [int(y) for y in cats[2]]
    out = {}
    for j, y in enumerate(years):
        tot = 0.0
        for i, a in enumerate(ages):
            if a == "Total":
                continue
            n = 0 if a.strip().startswith("Under") else int(a.strip().split()[0])
            if n >= 18:
                tot += vals[i * size[2] + j] or 0
        out[y] = tot
    return out


def cpi():
    """Consumer prices, annual average, spliced across Hagstofa's bases and set to 2025 = 1."""
    s = {}
    for base in ("Base 1939", "Base 1968", "Base 1981", "Base 1984", "Base 1988"):
        b = series("VIS01005", Index="Consumer price index", Base=base)
        if not s:
            s = dict(b)
            continue
        common = [y for y in b if y in s]
        if common:
            r = s[common[-1]] / b[common[-1]]
            s.update({y: v * r for y, v in b.items()})
    return {y: v / s[2025] for y, v in s.items()}


def usd_per_isk():
    """Dollars per króna from GDP per head in both (THJ01401); 2025 carried from 2024 (EST)."""
    isk = series("THJ01401", **{"Mælikvarði": "Thousand ISK"})
    usd = series("THJ01401", **{"Mælikvarði": "USD, current exchange rate"})
    r = {y: usd[y] / (isk[y] * 1000) for y in isk if y in usd}
    r[2025] = r[max(r)]
    return r


def rent_base(prices):
    """Rent before any take, million krónur nominal, with its revenue, the fees in it and where each year comes from."""
    F = lambda item: series("SJA08101", **{"Tekju- og gjaldaliðir": item, "Tegund skipa": "Total"})
    P = lambda item: series("SJA08103", **{"Tekju- og gjaldaliðir": item, "Tegund vinnslu": "Total"})
    f_rev, f_net = F("1. Operating revenues"), F("Net profit, after imputed cost of capital")
    p_rev, p_raw, p_net = P("1. Operating revenues"), P("2.1 Raw fish"), P("14. Net profit")
    margin93 = {y: v / 100 for y, v in series("SJA08107", Tegund="1. Fishing and fish processing, total").items()}
    exports = series("SJA04902", **{"Afurðaflokkur": "Total", "Eining": "Value"})
    paid = fees_paid()
    revenue = {y: f_rev[y] + p_rev[y] - p_raw[y] for y in f_rev}            # the sector, its own fish counted once
    scale = np.mean([revenue[y] / exports[y] for y in (1997, 1998)])
    out = {}
    for y in YEARS:
        fee = paid.get(y, 0.0)
        if y in f_net:
            rev, profit, src = revenue[y], f_net[y] + p_net[y], "Hagstofa SJA08101+08103"
        elif y in margin93:
            rev = exports[y] * scale
            profit, src = margin93[y] * rev, "SJA08107 margin on exports (SJA04902)"
        elif y in MARGIN_EST:
            rev = exports[y] * scale
            profit, src = MARGIN_EST[y] * rev, "EST margin (Althingi 121/s/1175) on exports"
        else:                                                                  # 2025
            rev = revenue[2024] * prices[2025] / prices[2024]
            profit, src = (f_net[2024] + p_net[2024]) / revenue[2024] * rev, "EST: 2024 in 2025 prices"
        out[y] = {"revenue": rev, "profit": profit, "fee": fee, "rent": profit + fee, "source": src}
    return out


def simulate(base, capture=.5, eta=.1, payout=.03, crisis="pay", repatriate=.3, start=1984, return_usd=.06,
             P=None, FX=None, N=None):
    """The fund, year by year. Money in million krónur nominal unless named otherwise."""
    fund_usd, rows = 0.0, {}
    for y in YEARS:
        b = base[y]
        rent = b["rent"] * (1 - eta * capture) if y >= start else b["rent"]
        take = max(0.0, capture * max(rent, 0.0) - b["fee"]) if y >= start else 0.0   # the fee stays the state's (as the model)
        repat = 0.0
        fund_usd *= 1 + return_usd
        if crisis == "repatriate" and y == 2009:
            repat = repatriate * fund_usd / FX[y]
            fund_usd *= 1 - repatriate
        paid_usd = 0.0 if (crisis == "freeze" and y in CONTROLS) else payout * fund_usd
        fund_usd += take * FX[y] - paid_usd
        paid = paid_usd / FX[y]
        per_adult = paid * 1e6 / N[y] / 12 / P[y]                                # krónur of 2025 a month
        rows[y] = {"rent": rent, "take": take, "industry_after_take": rent - take - b["fee"], "fund_isk": fund_usd / FX[y],
                   "fund_2025_isk": fund_usd / FX[y] / P[y], "paid": paid, "dividend_per_adult_month_2025": per_adult,
                   "repatriated": repat, "fund_usd_m": fund_usd}
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", type=float, default=.5)
    ap.add_argument("--eta", type=float, default=.1)
    ap.add_argument("--payout", type=float, default=.03)
    ap.add_argument("--crisis", default="pay", choices=["pay", "freeze", "repatriate"])
    ap.add_argument("--repatriate", type=float, default=.3)
    ap.add_argument("--start", type=int, default=1984)
    ap.add_argument("--return-usd", type=float, default=.06)
    a = ap.parse_args()
    P, FX, N = cpi(), usd_per_isk(), adults()
    base = rent_base(P)
    common = dict(P=P, FX=FX, N=N)

    print("the rent, million krónur nominal (and in ma.kr. of 2025)")
    for y in YEARS:
        b = base[y]
        print(f"  {y}  revenue {b['revenue']:9,.0f}  rent {b['rent']:9,.0f}  ({b['rent'] / P[y] / 1e3:6.1f} ma.kr. 2025)"
              f"  fee {b['fee']:7,.0f}  {b['source']}")

    # checks against the literature: Agnarsson et al. (2020), 2008-17, rent about 380 m USD a year, about 17% of exports
    usd = np.mean([base[y]["rent"] * FX[y] for y in range(2008, 2018)])
    share = np.mean([base[y]["rent"] / base[y]["revenue"] for y in range(2008, 2018)])
    print(f"\ncheck 2008-17: rent {usd:,.0f} m USD a year (literature ~380), {100 * share:.1f}% of sector revenue "
          f"(literature ~17% of exports)")

    run = simulate(base, a.capture, a.eta, a.payout, a.crisis, a.repatriate, a.start, a.return_usd, **common)
    print(f"\nthe fund: {100 * a.capture:.0f}% of the rent from {a.start}, eta {a.eta}, payout {100 * a.payout:.1f}% a year, "
          f"{100 * a.return_usd:.0f}% in dollars, capital controls: {a.crisis}")
    for y in YEARS:
        r = run[y]
        if y % 3 == 0 or y in (2008, 2009, 2015, 2025):
            print(f"  {y}  take {r['take'] / P[y] / 1e3:6.1f}  fund {r['fund_2025_isk'] / 1e3:7.0f} ma.kr. 2025  "
                  f"dividend {r['dividend_per_adult_month_2025']:7,.0f} kr./month per adult")

    variants = {}
    for crisis in ("pay", "freeze", "repatriate"):
        for capture in (.33, .5, .7, 1.0):
            for eta in (0.0, .1, .2):
                r = simulate(base, capture, eta, a.payout, crisis, a.repatriate, a.start, a.return_usd, **common)
                variants[f"{crisis}|{capture}|{eta}"] = {
                    "fund_2015_bn_2025": r[2015]["fund_2025_isk"] / 1e3, "fund_2025_bn_2025": r[2025]["fund_2025_isk"] / 1e3,
                    "dividend_2015": r[2015]["dividend_per_adult_month_2025"],
                    "dividend_2025": r[2025]["dividend_per_adult_month_2025"],
                    "repatriated_2009_bn": r[2009]["repatriated"] / 1e3}
    print("\nfund in 2015 and 2025 (ma.kr. of 2025) and the dividend in 2025 (kr./month per adult), eta 0.1:")
    for crisis in ("pay", "freeze", "repatriate"):
        print("  " + crisis.ljust(11) + "  ".join(
            f"{int(100 * c)}%: {variants[f'{crisis}|{c}|0.1']['fund_2015_bn_2025']:5.0f}/"
            f"{variants[f'{crisis}|{c}|0.1']['fund_2025_bn_2025']:5.0f} ma.kr., {variants[f'{crisis}|{c}|0.1']['dividend_2025']:6,.0f} kr."
            for c in (.33, .5, .7, 1.0)))
    out = {"years": YEARS, "settings": vars(a), "base": {str(y): base[y] for y in YEARS},
           "cpi_2025": {str(y): P[y] for y in YEARS}, "usd_per_isk": {str(y): FX[y] for y in YEARS},
           "adults": {str(y): N[y] for y in YEARS}, "run": {str(y): run[y] for y in YEARS}, "variants": variants,
           "checks": {"rent_usd_2008_17": usd, "rent_share_2008_17": share}}
    OUT.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
