"""Download the test set: original image (outside the repo), and per page the PAGE XML of the last
Field Recognition 313993 version (.fr), the last LA 51962 version (.la), and the FINAL version (.final).

Usage: python fetch_test_set.py FULLDOC_DIR [IMAGE_DIR]   (default image dir ~/Documents/Hasidigital-data/layout-test)
"""
import csv, json, re, sys, requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

HERE = Path(__file__).parent
FULLDOC = Path(sys.argv[1])
IMG = Path(sys.argv[2] if len(sys.argv) > 2 else Path.home() / "Documents/Hasidigital-data/layout-test")
TOOLS = {"fr": r"Field Recognition.*313993", "la": r"LA.*51962"}

jobs = []
for r in csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t"):
    doc, n = r["docId"], int(r["pageNr"])
    p = next(p for p in json.loads((FULLDOC / f"{doc}.json").read_text())["pageList"]["pages"] if p["pageNr"] == n)
    ts = sorted(p["tsList"]["transcripts"], key=lambda t: t["timestamp"])
    x = HERE / "xml" / doc; x.mkdir(parents=True, exist_ok=True); (IMG / doc).mkdir(parents=True, exist_ok=True)
    jobs.append((p["url"].replace("fileType=view", "fileType=orig"), IMG / doc / f"{n:04d}.jpg"))
    if ts[-1]["status"] in ("FINAL", "DONE"): jobs.append((ts[-1]["url"], x / f"{n:04d}.final.xml"))
    for k, pat in TOOLS.items():
        v = [t for t in ts if re.search(pat, t.get("toolName") or "")]
        if v: jobs.append((v[-1]["url"], x / f"{n:04d}.{k}.xml"))

jobs = [j for j in jobs if not j[1].exists()]
def get(j):
    for _ in range(3):
        try:
            r = requests.get(j[0], timeout=180); r.raise_for_status(); j[1].write_bytes(r.content); return
        except Exception as e: err = e
    print("FAIL", j[1], err, flush=True)
print(len(jobs), "files", flush=True)
with ThreadPoolExecutor(6) as ex: list(ex.map(get, jobs))
print("done", flush=True)
