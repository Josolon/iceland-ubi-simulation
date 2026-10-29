"""Fetch the Hagstofa tables the known limits need (VALIDATION.md §5): regions, the capital stock, the financial
sector's balance sheets. Writes one JSON per subject to data/reference/.

    .venv/bin/python scripts/fetch_limits_data.py

Each file keeps the table codes it came from, the query, and the date fetched. Values are as Hagstofa gives them.
"""
import datetime
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
API = "https://px.hagstofa.is/pxen/api/v1/en/"
YEARS = [str(y) for y in range(2015, 2026)]
REGIONS = ["1", "2", "3", "4", "5", "6", "7", "8"]


def query(path, selection):
    """POST a json-stat2 query; return {(value codes...): number} keyed in the table's variable order."""
    body = {"query": [{"code": c, "selection": {"filter": "item", "values": v}} for c, v in selection.items()],
            "response": {"format": "json-stat2"}}
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=60))
    dims = d["id"]
    cats = [sorted(d["dimension"][k]["category"]["index"].items(), key=lambda kv: kv[1]) for k in dims]
    labels = {k: d["dimension"][k]["category"]["label"] for k in dims}
    out, sizes = {}, d["size"]
    for flat, val in enumerate(d["value"]):
        idx, rem = [], flat
        for s in reversed(sizes):
            idx.append(rem % s)
            rem //= s
        key = tuple(cats[j][i][0] for j, i in enumerate(reversed(idx)))
        out[key] = val
    return dims, labels, out


def nest(dims, labels, out, keep):
    """Turn flat results into nested dicts by the dimensions in `keep`, labelled."""
    res = {}
    for key, val in out.items():
        node = res
        names = [labels[d][k] for d, k in zip(dims, key) if d in keep]
        for n in names[:-1]:
            node = node.setdefault(n, {})
        node[names[-1]] = val
    return res


def save(name, source, data):
    f = ROOT / "data/reference" / name
    f.write_text(json.dumps({"source": source, "fetched": datetime.date.today().isoformat(), **data},
                            indent=1, ensure_ascii=False))
    print("wrote", f)


def regions():
    pop = query("Ibuar/mannfjoldi/2_byggdir/Byggdakjarnarhverfi/MAN03250.px",
                {"Landshlutar": ["Total", "Capital region", "Southwest", "West", "Westfjords", "Northwest",
                                 "Northeast", "East", "South"], "Aldur": ["-1"], "Kyn": ["0"],
                 "Ár": ["2015", "2020", "2025", "2026"]})
    wages = query("Samfelag/launogtekjur/3_tekjur/0_stadgreidsla/TEK02003.px",
                  {"Mánuður": [f"2025M{m:02d}" for m in range(1, 13)], "Búseta": ["0"] + REGIONS,
                   "Atvinnugrein": ["0"], "Eining": ["0", "1"]})
    labour = query("Samfelag/vinnumarkadur/vinnumarkadsrannsokn/3_arstolur/VIN01104.px",
                   {"Skipting": ["0", "3", "4", "5", "6"], "Eining": ["0", "1", "3", "4", "5"], "Ár": YEARS})
    moves = query("Ibuar/buferlaflutningar/buferlaflinnanlands/buferlaflinnanlands/MAN01002.px",
                  {"Kyn": ["0"], "Ár": YEARS, "Aldur": ["-1"], "Brottflutningssvæði": REGIONS + ["X"],
                   "Aðflutningssvæði": REGIONS + ["X"]})
    prices = query("Efnahagur/visitolur/1_vnv/3_greiningarvisitolur/VIS01106.px",
                   {"Month": [f"{y}M12" for y in range(2015, 2026)], "Index": ["RI_cap_mult", "RI_cap_single",
                                                                              "RI_outside_cap", "RI_total"]})
    save("regions_2025.json",
         "Hagstofa MAN03250 (population by region, 1 January), TEK02003 (taxable wages and employees by residence, "
         "monthly, 2025; m.kr.), VIN01104 (labour force survey by region, %, hours), MAN01002 (moves between "
         "regions and abroad, all ages), VIS01106 (residential property price index, December)",
         {"population": nest(*pop, keep={"Landshlutar", "Ár"}),
          "taxable_wages_2025": nest(*wages, keep={"Búseta", "Eining", "Mánuður"}),
          "labour_force_survey": nest(*labour, keep={"Skipting", "Eining", "Ár"}),
          "migration": nest(*moves, keep={"Ár", "Brottflutningssvæði", "Aðflutningssvæði"}),
          "house_price_index": nest(*prices, keep={"Month", "Index"})})


def capital():
    k = query("Efnahagur/thjodhagsreikningar/fjarmunamyndun_fjarmunaeign/fjarmunaeign/THJ03204.px",
              {"Mælikvarði": ["0", "2"], "Atvinnugrein": ["0"], "Skipting": ["0", "1"],
               "Ár": [str(y) for y in range(1995, 2026)]})
    # 2.0: the business sector's own stock, apart from dwellings and the government's
    kb = query("Efnahagur/thjodhagsreikningar/fjarmunamyndun_fjarmunaeign/fjarmunaeign/THJ03204.px",
               {"Mælikvarði": ["0", "2"], "Atvinnugrein": ["46", "47", "48"], "Skipting": ["0", "1"],
                "Ár": [str(y) for y in range(1995, 2026)]})
    save("capital_stock.json",
         "Hagstofa THJ03204: net capital stock and its consumption, all industries and by sector (business, "
         "residential, government), current and constant prices, m.kr.",
         {"stock": nest(*k, keep={"Mælikvarði", "Skipting", "Ár"}),
          "by_sector": nest(*kb, keep={"Atvinnugrein", "Mælikvarði", "Skipting", "Ár"})})
    # 2.0: business investment against GDP, for the capital stock's check (LIMITS.md §4)
    inv = query("Efnahagur/thjodhagsreikningar/fjarmunamyndun_fjarmunaeign/fjarmunamyndun/THJ03106.px",
                {"Mælikvarði": ["0", "2"], "Atvinnugrein": ["0"], "Ár": [str(y) for y in range(1995, 2026)]})
    gdp = query("Efnahagur/thjodhagsreikningar/landsframl/1_landsframleidsla/THJ01102.px",
                {"Skipting": ["11"], "Ár": [str(y) for y in range(1995, 2026)]})
    save("business_investment.json",
         "Hagstofa THJ03106 (business sector investment, all assets, current and constant prices, m.kr.) and "
         "THJ01102 (GDP, current prices, m.kr.)",
         {"investment": nest(*inv, keep={"Mælikvarði", "Ár"}), "gdp": nest(*gdp, keep={"Ár"})})


def finance():
    sectors = ["S11", "S12", "S121", "S122", "S124", "S128", "S129", "S13", "S14", "S2"]
    inst = ["FA0", "FA2", "FA3", "FA4", "FA5", "FA6", "FL0", "FL2", "FL3", "FL4", "FL5", "FL6", "BF90"]
    f = query("Efnahagur/thjodhagsreikningar/fjarmalareikningar/fjarmalareikningar/THJ10001.px",
              {"Efnahagsgeirar": sectors, "Ár": [str(y) for y in range(2015, 2026)], "Fjármálagerningar": inst,
               "Mælikvarði": ["Stocks 31/12"]})
    save("financial_accounts.json",
         "Hagstofa THJ10001: financial accounts, stocks at 31 December by sector and instrument, m.kr.",
         {"stocks": nest(*f, keep={"Efnahagsgeirar", "Ár", "Fjármálagerningar"})})


if __name__ == "__main__":
    regions()
    capital()
    finance()
