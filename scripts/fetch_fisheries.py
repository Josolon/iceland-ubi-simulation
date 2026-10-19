"""Fetch the fisheries accounts the counterfactual from the quota system's start needs (Hagstofa PxWeb), slowly.

    .venv/bin/python scripts/fetch_fisheries.py

Writes the table metadata and the full tables as JSON-stat under data/raw/hagstofa/fisheries/.
"""
import json
import pathlib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/hagstofa/fisheries"
ROOT_API = "https://px.hagstofa.is:443/pxen/api/v1/en/"     # the plain host rate-limits; this one did not
BASE = ROOT_API + "Atvinnuvegir/sjavarutvegur/"
TABLES = {
    "SJA08101": "afkomasja/SJA08101.px",   # operating accounts of fishing 1997-
    "SJA08103": "afkomasja/SJA08103.px",   # operating accounts of fish processing 1997-
    "SJA08104": "afkomasja/SJA08104.px",   # balance sheet of fishing and processing 1997-
    "SJA08107": "afkomasja/SJA08107.px",   # net profit in fishing and processing 1993-
    "SJA09005": "aflatolur/fiskveidisvaedi/SJA09005.px",   # catch of Icelandic vessels 1945-
    "SJA04902": "utf/SJA04902.px",                          # marine exports by product 1979-1998
}
# National series for the counterfactual from the quota system's start: path, and a selection by variable code
# (anything not named is taken whole)
NATIONAL = {
    "MAN00101": ("Ibuar/mannfjoldi/1_yfirlit/yfirlit_mannfjolda/MAN00101.px",
                 {"Kyn": ["Total"], "Ár": [str(y) for y in range(1980, 2027)]}),        # population by age, both sexes
    "VIS01005": ("Efnahagur/visitolur/1_vnv/1_vnv/VIS01005.px", {}),              # CPI, annual averages
    "THJ01401": ("Efnahagur/thjodhagsreikningar/landsframl/1_landsframleidsla/THJ01401.px", {}),   # GDP per capita
    "THJ05132": ("Efnahagur/fjaropinber/fjarmal_opinber/fjarmal_opinber/THJ05132.px", {}),         # revenue detail
}


def get(url, body=None, tries=6):
    for i in range(tries):
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception as exc:
            print(f"  {url.rsplit('/', 1)[-1]}: {exc}; waiting", flush=True)
            time.sleep(20 * (i + 1))
    raise SystemExit(f"could not fetch {url}")


def fetch(name, url, select=None):
    if (OUT / f"{name}.json").exists():
        print(f"{name}: kept", flush=True)
        return
    meta = get(url)
    (OUT / f"{name}_meta.json").write_text(json.dumps(meta, indent=1))
    time.sleep(8)
    select = select or {}
    query = {"query": [{"code": v["code"], "selection": ({"filter": "item", "values": select[v["code"]]}
                                                         if v["code"] in select else {"filter": "all", "values": ["*"]})}
                       for v in meta["variables"]],
             "response": {"format": "json-stat2"}}
    data = get(url, query)
    (OUT / f"{name}.json").write_text(json.dumps(data))
    print(f"{name}: {meta.get('title', '')}", flush=True)
    time.sleep(8)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, path in TABLES.items():
        fetch(name, BASE + path)
    for name, (path, select) in NATIONAL.items():
        fetch(name, ROOT_API + path, select)


def _old_main():
    for name, path in TABLES.items():
        meta = get(BASE + path)
        (OUT / f"{name}_meta.json").write_text(json.dumps(meta, indent=1))
        time.sleep(8)
        query = {"query": [{"code": v["code"], "selection": {"filter": "all", "values": ["*"]}} for v in meta["variables"]],
                 "response": {"format": "json-stat2"}}
        data = get(BASE + path, query)
        (OUT / f"{name}.json").write_text(json.dumps(data))
        print(f"{name}: {meta.get('title', '')}", flush=True)
        time.sleep(8)


if __name__ == "__main__":
    main()
