"""Crawl the Statistics Iceland PxWeb tree and write every table to data/catalog/hagstofa_tables.tsv."""
import json, sys, time, urllib.parse, urllib.request, pathlib

BASE = "https://px.hagstofa.is/pxen/api/v1/en/"
OUT = pathlib.Path(__file__).resolve().parents[1] / "data/catalog/hagstofa_tables.tsv"

def get(path):
    for attempt in range(5):
        try:
            time.sleep(0.4)  # API allows ~30 requests / 10 s
            return json.load(urllib.request.urlopen(BASE + urllib.parse.quote(path), timeout=60))
        except Exception:
            time.sleep(5 * (attempt + 1))
    print("skipped", path, file=sys.stderr)
    return []

def walk(path, trail, rows):
    for node in get(path):
        nid = node.get("id") or node["dbid"]
        sub = f"{path}/{nid}" if path else nid
        if node.get("type", "l") == "l":
            walk(sub, trail + [node["text"].strip()], rows)
        elif node["type"] == "t":
            rows.append((sub, " > ".join(trail), node["text"].strip()))

rows = []
walk("", [], rows)
OUT.write_text("path\tfolder\ttitle\n" + "\n".join("\t".join(r) for r in rows) + "\n")
print(len(rows), "tables")
