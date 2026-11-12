"""Ground truth and training for a Kraken text-recognition (HTR) model, as a free local alternative to Transkribus
HTR 52805. Pages: the FINAL, DONE and GT pages of gt-pool.tsv (kraken_gt.py: test-set pages and two either side are
already left out), whose text a person has checked. Images are kraken_gt.py's (kraken-train/gt/, long side 2000 px).

    python kraken_htr.py fetch    → kraken-train/htr/<doc>_<page>.xml: lines with their text, scaled to those images
    python kraken_htr.py split    → htr/train.txt, htr/val.txt (5% of pages, whole pages, for validation)
then (kraken venv):
    ketos compile -f page -F htr/train.txt -o htr/train.arrow; ketos compile -f page -F htr/val.txt -o htr/val.arrow
    ketos -d mps train -f binary -t htr/train.lst -e htr/val.lst --base-dir R -B 16 --augment -o htr/model
"""
import csv, html, json, os, random, re, sys
from pathlib import Path
from kraken_gt import HERE, KT, FINAL

OUT = KT / "htr"


def with_text(x, k, img, W, H):
    """The page's lines (outline, baseline, text of the line itself, not of its words), scaled by k."""
    sc = lambda pts: " ".join(f"{round(float(a) * k)},{round(float(b) * k)}" for a, b in (q.split(",") for q in pts.split() if "," in q))
    regs = []
    for m in re.finditer(r"<(?:\w+:)?TextRegion\b.*?</(?:\w+:)?TextRegion>", x, re.S):
        ls = []
        for l in re.finditer(r"<(?:\w+:)?TextLine\b.*?</(?:\w+:)?TextLine>", m.group(0), re.S):
            body = re.sub(r"<(?:\w+:)?Word\b.*?</(?:\w+:)?Word>", "", l.group(0), flags=re.S)
            c = re.search(r'<(?:\w+:)?Coords points="([^"]+)"', body); b = re.search(r'<(?:\w+:)?Baseline points="([^"]+)"', body)
            t = re.findall(r"<(?:\w+:)?Unicode>(.*?)</(?:\w+:)?Unicode>", body, re.S)
            text = html.unescape(t[-1]).strip() if t else ""
            if c and b and text:
                ls.append(f'<TextLine id="l{len(regs)}_{len(ls)}"><Coords points="{sc(c.group(1))}"/><Baseline points="{sc(b.group(1))}"/>'
                          f'<TextEquiv><Unicode>{html.escape(text, quote=False)}</Unicode></TextEquiv></TextLine>')
        if ls: regs.append(f'<TextRegion id="r{len(regs)}"><Coords points="0,0 {W},0 {W},{H} 0,{H}"/>{"".join(ls)}</TextRegion>')
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15">'
            f'<Page imageFilename="../gt/{img}" imageWidth="{W}" imageHeight="{H}">{"".join(regs)}</Page></PcGts>\n'), sum(1 for _ in re.finditer("<TextLine", "".join(regs)))


def fetch():
    import requests, cv2
    from concurrent.futures import ThreadPoolExecutor
    from kraken_gt import DATA
    urls = {}
    for f in (DATA / "layout-train" / "fulldoc").glob("*.json"):
        for p in json.loads(f.read_text())["pageList"]["pages"]:
            urls.update({str(t["tsId"]): t["url"] for t in p["tsList"]["transcripts"]})
    s = requests.Session()
    r = s.post("https://transkribus.eu/TrpServer/rest/auth/login", data={"user": os.environ["TRANSKRIBUS_USER"], "pw": os.environ["TRANSKRIBUS_PASS"]}, timeout=60)
    s.cookies.set("JSESSIONID", re.search(r"<sessionId>(.*?)</sessionId>", r.text).group(1))
    OUT.mkdir(exist_ok=True)

    def one(r):
        stem = f"{r['docId']}_{int(r['pageNr']):04d}"; dst = OUT / f"{stem}.xml"; img = KT / "gt" / f"{stem}.jpg"
        if dst.exists() or not img.exists(): return 0
        for _ in range(3):
            try: x = s.get(urls[r["tsId"]], timeout=60).text; break
            except Exception as e: err = e
        else: print(stem, err); return 0
        W0 = int(re.search(r'imageWidth="(\d+)"', x).group(1)); h, w = cv2.imread(str(img)).shape[:2]
        page, n = with_text(x, w / W0, img.name, w, h)
        if n: dst.write_text(page)
        return n
    rows = [r for r in csv.DictReader(open(HERE / "gt-pool.tsv"), delimiter="\t") if r["status"] in FINAL]
    with ThreadPoolExecutor(8) as ex: n = sum(ex.map(one, rows))
    print(len(rows), "pages asked;", len(list(OUT.glob("*.xml"))), "pages with text;", n, "new lines")


def split():
    fs = sorted(str(f) for f in OUT.glob("*.xml")); random.Random(0).shuffle(fs); k = len(fs) // 20
    (OUT / "val.txt").write_text("\n".join(fs[:k]) + "\n"); (OUT / "train.txt").write_text("\n".join(fs[k:]) + "\n")
    print(len(fs) - k, "train pages,", k, "validation pages")


if __name__ == "__main__":
    {"fetch": fetch, "split": split}[sys.argv[1]]()
