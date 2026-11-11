"""For finished pages with a PyLaia 52805 version: fetch that version's PAGE XML, the final PAGE XML and the image."""
import json, re, requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
jobs = []
for f in Path("fulldoc").glob("*.json"):
    for p in json.loads(f.read_text())["pageList"]["pages"]:
        ts = sorted(p["tsList"]["transcripts"], key=lambda t: t["timestamp"])
        if ts[-1]["status"] not in ("FINAL", "DONE"): continue
        htr = [t for t in ts if re.search(r"52805", t.get("toolName") or "")]
        if not htr: continue
        d = Path(f"calib/{f.stem}"); d.mkdir(parents=True, exist_ok=True)
        n = f"{p['pageNr']:04d}"
        jobs += [(htr[-1]["url"], d / f"{n}.htr.xml"), (ts[-1]["url"], d / f"{n}.final.xml"),
                 (p["url"].replace("fileType=view", "fileType=orig"), d / f"{n}.jpg")]
jobs = [j for j in jobs if not j[1].exists()]
def get(j):
    for _ in range(3):
        try:
            r = requests.get(j[0], timeout=120); r.raise_for_status(); j[1].write_bytes(r.content); return
        except Exception as e: err = e
    print("FAIL", j[1], err, flush=True)
print(len(jobs), "files", flush=True)
with ThreadPoolExecutor(6) as ex: list(ex.map(get, jobs))
print("done", flush=True)
