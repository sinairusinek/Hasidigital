"""Ground truth for a Kraken line model: pages whose lines a person has checked in Transkribus.

Many more pages had their layout corrected than were marked FINAL. A page counts when either
- its latest version is FINAL, DONE or GT, or
- a person changed its lines after the line tool ran (the tool's lines and the latest lines differ), in a book
  where that happened on at least half the pages the tool ran on, so the book went through a layout pass.
Test-set pages and the two pages either side of them are left out.

Inputs (from ~/Documents/Hasidigital-data/kraken-train/: screen.py, fetch_pairs.py, compare.py):
    screen.tsv   every page: status, last line-tool version, later human versions
    compare.tsv  pages edited after the line tool: share of the latest lines that differ from the tool's

    python kraken_gt.py pool      → gt-pool.tsv (here) and a per-book summary
    python kraken_gt.py fetch     → images (long side 2000 px) and line-only PAGE XML in kraken-train/gt/
"""
import csv, collections, json, os, re, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).parent
DATA = Path.home() / "Documents/Hasidigital-data"; KT = DATA / "kraken-train"
FINAL = ("FINAL", "DONE", "GT")
SIDE = 2000


def pool():
    test = {(r["docId"], int(r["pageNr"]) + k) for r in csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t") for k in range(-2, 3)}
    scr = list(csv.DictReader(open(KT / "screen.tsv"), delimiter="\t"))
    cmp = {(r["docId"], r["pageNr"]): r for r in csv.DictReader(open(KT / "compare.tsv"), delimiter="\t")}
    la = collections.Counter(r["docId"] for r in scr if r["auto"])
    edited = collections.Counter(d for (d, _), r in cmp.items() if float(r["changed"]) > 0 and int(r["n_final"]) > 0)
    rows = []
    for r in scr:
        d, n = r["docId"], int(r["pageNr"]); c = cmp.get((d, r["pageNr"]))
        if (d, n) in test or int(r["lines_latest"] or 0) == 0: continue
        if r["status"] in FINAL: why = "final"
        elif c and float(c["changed"]) > 0 and edited[d] >= 0.5 * la[d]: why = "lines corrected, not final"
        else: continue
        rows.append(dict(docId=d, work=r["work"], pageNr=n, status=r["status"], why=why, tsId=r["latest"],
                         changed=c["changed"] if c else "", lines=r["lines_latest"]))
    w = csv.DictWriter(open(HERE / "gt-pool.tsv", "w"), rows[0].keys(), delimiter="\t"); w.writeheader(); w.writerows(rows)
    print(collections.Counter(r["why"] for r in rows), sum(int(r["lines"]) for r in rows), "lines")
    by = collections.defaultdict(collections.Counter)
    for r in rows: by[(r["docId"], r["work"])][r["why"]] += 1
    for (d, wk), c in sorted(by.items(), key=lambda x: -x[1]["lines corrected, not final"]):
        if c["lines corrected, not final"]: print(d, wk[:28], dict(c), "of", la[d], "line-tool pages")


def fetch():
    import requests, cv2
    from concurrent.futures import ThreadPoolExecutor
    pages = {}
    for f in (DATA / "layout-train" / "fulldoc").glob("*.json"):
        for p in json.loads(f.read_text())["pageList"]["pages"]:
            pages[(str(p["docId"]), p["pageNr"])] = (p["url"], {str(t["tsId"]): t["url"] for t in p["tsList"]["transcripts"]})
    s = requests.Session()
    r = s.post("https://transkribus.eu/TrpServer/rest/auth/login", data={"user": os.environ["TRANSKRIBUS_USER"], "pw": os.environ["TRANSKRIBUS_PASS"]}, timeout=60)
    s.cookies.set("JSESSIONID", re.search(r"<sessionId>(.*?)</sessionId>", r.text).group(1))
    out = KT / "gt"; out.mkdir(exist_ok=True)

    def one(r):
        d, n = r["docId"], int(r["pageNr"]); stem = out / f"{d}_{n:04d}"
        if (stem.with_suffix(".xml")).exists(): return
        img_url, ts = pages[(d, n)]
        for _ in range(3):
            try:
                x = s.get(ts[r["tsId"]], timeout=60).text
                im = cv2.imdecode(np.frombuffer(s.get(img_url, timeout=120).content, np.uint8), cv2.IMREAD_COLOR); break
            except Exception as e: err = e
        else: print(d, n, err); return
        H, W = im.shape[:2]; k = min(1.0, SIDE / max(H, W))
        cv2.imwrite(str(stem.with_suffix(".jpg")), cv2.resize(im, None, fx=k, fy=k, interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 90])
        stem.with_suffix(".xml").write_text(lines_only(x, k, stem.with_suffix(".jpg").name, int(W * k), int(H * k)))
    with ThreadPoolExecutor(8) as ex: list(ex.map(one, list(csv.DictReader(open(HERE / "gt-pool.tsv"), delimiter="\t"))))
    print(len(list(out.glob("*.xml"))), "pages in", out)


def lines_only(x, k, img, W, H):
    """The page's baselines and line outlines, scaled by k, in one untyped region per original region."""
    sc = lambda pts: " ".join(f"{round(float(a) * k)},{round(float(b) * k)}" for a, b in (q.split(",") for q in pts.split() if "," in q))
    regs = []
    for m in re.finditer(r"<(?:\w+:)?TextRegion\b.*?</(?:\w+:)?TextRegion>", x, re.S):
        rc = re.search(r'<(?:\w+:)?Coords points="([^"]+)"', m.group(0)); ls = []
        for l in re.finditer(r"<(?:\w+:)?TextLine\b.*?</(?:\w+:)?TextLine>", m.group(0), re.S):
            c = re.search(r'<(?:\w+:)?Coords points="([^"]+)"', l.group(0)); b = re.search(r'<(?:\w+:)?Baseline points="([^"]+)"', l.group(0))
            if c and b: ls.append(f'<TextLine id="l{len(regs)}_{len(ls)}"><Coords points="{sc(c.group(1))}"/><Baseline points="{sc(b.group(1))}"/></TextLine>')
        if rc and ls: regs.append(f'<TextRegion id="r{len(regs)}"><Coords points="{sc(rc.group(1))}"/>{"".join(ls)}</TextRegion>')
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15">'
            f'<Page imageFilename="{img}" imageWidth="{W}" imageHeight="{H}">{"".join(regs)}</Page></PcGts>\n')


if __name__ == "__main__":
    {"pool": pool, "fetch": fetch}[sys.argv[1]]()
