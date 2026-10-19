"""Cached access to the Statistics Iceland PxWeb API.

    rows = fetch("Efnahagur/fjaropinber/fjarmal_opinber/fjarmal_opinber/THJ05111.px",
                 {"Skipting": ["0", "1"], "Ár": ["2025"]})
    # -> [({"Skipting": "Total revenue", "Ár": "2025"}, 2109882), ...]

Variables omitted from `selection` are returned in full.
"""
import hashlib
import itertools
import json
import pathlib
import time
import urllib.parse
import urllib.request

BASE = "https://px.hagstofa.is/pxen/api/v1/en/"
CACHE = pathlib.Path(__file__).resolve().parents[3] / "data/raw/hagstofa"


def _request(path, body=None):
    url = BASE + urllib.parse.quote(path)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 3:
                raise
            time.sleep(10)


def metadata(path):
    return _request(path)


def table_path(table_id):
    """Resolve e.g. 'VIN01100' to its PxWeb path using the crawled catalogue."""
    catalog = CACHE.parents[1] / "catalog/hagstofa_tables.tsv"
    for line in catalog.read_text().splitlines():
        if line.split("\t")[0].endswith(f"/{table_id}.px"):
            return line.split("\t")[0]
    raise KeyError(table_id)


def fetch_labels(table_id, selection=None, refresh=False):
    """Like fetch(), but takes a table id and selects values by their label text (or '*' for all)."""
    path = table_path(table_id)
    meta = {v["code"]: v for v in metadata(path)["variables"]}
    codes = {}
    for var, labels in (selection or {}).items():
        if labels == "*":
            continue
        lookup = {t.strip(): c for c, t in zip(meta[var]["values"], meta[var]["valueTexts"])}
        codes[var] = [lookup[str(l).strip()] for l in labels]
    return fetch(path, codes, refresh)


def fetch(path, selection=None, refresh=False):
    selection = selection or {}
    key = hashlib.sha1(json.dumps([path, selection], sort_keys=True).encode()).hexdigest()[:16]
    cache_file = CACHE / f"{pathlib.Path(path).stem}_{key}.json"
    if cache_file.exists() and not refresh:
        d = json.loads(cache_file.read_text())
    else:
        codes = [v["code"] for v in metadata(path)["variables"]]
        query = [{"code": c, "selection": {"filter": "item", "values": selection[c]}}
                 for c in codes if c in selection]
        d = _request(path, {"query": query, "response": {"format": "json-stat2"}})
        CACHE.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(d))
    dims = d["id"]
    cats = [d["dimension"][k]["category"] for k in dims]
    orders = [sorted(c["index"], key=c["index"].get) for c in cats]
    return [({dim: cat["label"][code] for dim, cat, code in zip(dims, cats, combo)}, value)
            for combo, value in zip(itertools.product(*orders), d["value"])]
