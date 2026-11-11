import csv, json, requests, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
MAP = "/Users/sinairusinek/Documents/GitHub/Hasidigital/editions/transkribus-collection-map.tsv"
new = [r for r in csv.DictReader(open(MAP, encoding="utf-8"), delimiter="\t") if (r["docId"] in sys.argv[1:] if sys.argv[1:] else r["uploaded"] >= "2026-11-01")]
jobs = []
for r in new:
    for p in json.loads(Path(f"fulldoc/{r['docId']}.json").read_text())["pageList"]["pages"]:
        out = Path(f"img/{r['docId']}/{p['pageNr']:04d}.jpg"); out.parent.mkdir(parents=True, exist_ok=True)
        if not out.exists() or out.stat().st_size == 0: jobs.append((p["url"].replace("fileType=view", "fileType=orig"), out))
def get(j):
    url, out = j
    for _ in range(3):
        try:
            r = requests.get(url, timeout=120); r.raise_for_status(); out.write_bytes(r.content); return
        except Exception as e: err = e
    print("FAIL", out, err, flush=True)
print(len(jobs), "to fetch", flush=True)
with ThreadPoolExecutor(8) as ex: list(ex.map(get, jobs))
print("done", flush=True)
