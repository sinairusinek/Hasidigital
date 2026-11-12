"""Local layout for one book, in place of Transkribus Field Recognition + line detection.

    python run_layout.py DOCID [--pages 1-40]

Steps: page-instructions (skip pages; works on hold are refused) → deskew and crop each image →
YOLO regions (model trained on all tagged books) + Kraken lines, cut where they cross from one region into
another (Kraken runs lines across columns) → footnote rules → back to the original
image's coordinates → PAGE XML → automatic checks. Nothing is sent to Transkribus.
Output in ~/Documents/Hasidigital-data/books/<doc>/: img/, prep/, layout/<page>.xml, flags.tsv.
"""
import csv, json, os, re, subprocess, sys, requests
from pathlib import Path
import numpy as np, cv2

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "scan-check"))
from scan_checks import best_angle
from layout_qa import letters, RULES, clean, page_flags, book_habits
from rules import combine_page, page_xml
from line_score import line_polys
from fix_lines import fix_page
from yolo_regions import CLASSES, DATA

TRP = "https://transkribus.eu/TrpServer/rest"
HOLD = {"3": "waits for a better scan", "77": "waits for a better scan", "43": "waits for Gadi", "11": "waits for Gadi"}
MODEL = DATA / "yolo" / "runs" / "fold0" / "weights" / "best.pt"
KRAKEN = DATA / ".venv-kraken" / "bin" / "kraken"


def session():
    s = requests.Session()
    r = s.post(f"{TRP}/auth/login", data={"user": os.environ["TRANSKRIBUS_USER"], "pw": os.environ["TRANSKRIBUS_PASS"]}, timeout=60)
    s.cookies.set("JSESSIONID", re.search(r"<sessionId>(.*?)</sessionId>", r.text).group(1))
    return s


def instructions(doc):
    rows = [r for r in csv.DictReader(open(HERE.parent / "scan-check" / "page-instructions.tsv"), delimiter="\t") if r["docId"] == doc]
    skip = {int(r["image_page"]) for r in rows if r["action"] == "skip"}
    return skip, rows


def prep(src, dst):
    """Deskew (if over 0.5°) and crop to the text with a margin. Returns the 2x3 matrix taking prepped
    coordinates back to the original image."""
    im = cv2.imread(str(src)); g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY); h, w = g.shape
    small = cv2.resize(g, (1000, int(1000 * h / w)), interpolation=cv2.INTER_AREA)
    _, bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    a = best_angle(bw[bw.shape[0] // 30: -bw.shape[0] // 30, bw.shape[1] // 30: -bw.shape[1] // 30])
    M = cv2.getRotationMatrix2D((w / 2, h / 2), a if abs(a) >= 0.5 else 0, 1)
    rot = cv2.warpAffine(im, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
    cv2.imwrite(str(dst), rot)
    L = letters(dst, w, h)
    if L is not None and len(L) > 100:
        x0, x1 = np.percentile(L[:, 0], [0.5, 99.5]); y0, y1 = np.percentile(L[:, 1], [0.5, 99.5])
        x0, x1 = int(max(0, x0 - 0.05 * w)), int(min(w, x1 + 0.05 * w)); y0, y1 = int(max(0, y0 - 0.04 * h)), int(min(h, y1 + 0.04 * h))
    else:
        x0, y0, x1, y1 = 0, 0, w, h
    cv2.imwrite(str(dst), rot[y0:y1, x0:x1])
    back = cv2.invertAffineTransform(M)  # rotated → original
    shift = np.array([[1, 0, x0], [0, 1, y0], [0, 0, 1]], float)
    return (np.vstack([back, [0, 0, 1]]) @ shift)[:2], (w, h)


def to_orig(T, pts):
    pts = np.asarray(pts, float)
    return np.column_stack([pts, np.ones(len(pts))]) @ T.T


def main():
    doc = sys.argv[1]
    base = DATA / "books" / doc
    for sub in ("img", "prep", "layout", "kraken"): (base / sub).mkdir(parents=True, exist_ok=True)
    mp = {r["docId"]: r for r in csv.DictReader(open(HERE.parent / "transkribus-collection-map.tsv"), delimiter="\t")}
    work = mp.get(doc, {}).get("work_nu", "")
    if work.split(".")[0] in HOLD: sys.exit(f"work {work} {HOLD[work.split('.')[0]]}; not run")
    skip, notes = instructions(doc)
    s = session()
    full = s.get(f"{TRP}/collections/49371/{doc}/fulldoc", params={"nrOfTranscripts": 1}, headers={"Accept": "application/json"}, timeout=180).json()
    pages = full["pageList"]["pages"]
    if "--pages" in sys.argv:
        a, b = map(int, sys.argv[sys.argv.index("--pages") + 1].split("-")); pages = [p for p in pages if a <= p["pageNr"] <= b]
    pages = [p for p in pages if p["pageNr"] not in skip]
    for p in pages:
        f = base / "img" / f"{p['pageNr']:04d}.jpg"
        if not f.exists(): f.write_bytes(requests.get(p["url"].replace("fileType=view", "fileType=orig"), timeout=180).content)
    T = {p["pageNr"]: prep(base / "img" / f"{p['pageNr']:04d}.jpg", base / "prep" / f"{p['pageNr']:04d}.jpg") for p in pages}
    # Kraken lines, 4 processes
    todo = [p["pageNr"] for p in pages if not (base / "kraken" / f"{p['pageNr']:04d}.xml").exists()]
    procs = []
    for k in range(4):
        args = [x for n in todo[k::4] for x in ("-i", str(base / "prep" / f"{n:04d}.jpg"), str(base / "kraken" / f"{n:04d}.xml"))]
        if args: procs.append(subprocess.Popen([str(KRAKEN), "-x", *args, "segment", "-bl", "-d", "horizontal-rl"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    for pr in procs: pr.wait()
    # YOLO regions
    from ultralytics import YOLO
    model = YOLO(str(MODEL)); out = {}
    for p in pages:
        n = p["pageNr"]; T_, (W, H) = T[n]
        res = model.predict(str(base / "prep" / f"{n:04d}.jpg"), imgsz=1024, conf=0.25, device="mps", verbose=False)[0]
        regs = []
        for b, c in zip(res.boxes.xyxy.tolist(), res.boxes.cls.tolist()):
            q = to_orig(T_, [(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])])
            regs.append((CLASSES[int(c)], q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()))
        try: polys, _, _ = line_polys(base / "kraken" / f"{n:04d}.xml", True)
        except Exception: polys = []
        polys = [(to_orig(T_, pts), lab, to_orig(T_, bl) if bl is not None else None) for pts, lab, bl in polys]
        img = base / "img" / f"{n:04d}.jpg"; L = letters(img, W, H)
        polys = fix_page(polys, L, [r[1:] for r in regs], extend=False, joined=True, refilled=True)  # [(polygon, baseline)]
        regions = combine_page(regs, polys, RULES.get(str(img), ()), W, H)
        (base / "layout" / f"{n:04d}.xml").write_text(page_xml(regions, W, H, img.name))
        rr = [dict(lab=t, box=b, lines=[(int(q[:, 0].min()), int(q[:, 1].min()), int(q[:, 0].max()), int(q[:, 1].max())) for q, _ in ls]) for t, b, ls in regions]
        rr, done = clean(rr, L)
        out[n] = (rr, L, W, H, done, RULES.get(str(img), ()))
    habit = book_habits([v[0] for v in out.values()])
    with open(base / "flags.tsv", "w") as fh:
        fh.write("pageNr\tcleanups\tflags\n")
        for n, (rr, L, W, H, done, rl) in out.items():
            fh.write(f"{n}\t{'; '.join(done)}\t{'; '.join(page_flags(rr, L, W, H, habit, rl))}\n")
    nflag = sum(1 for l in open(base / "flags.tsv").read().splitlines()[1:] if l.split("\t")[2])
    print(f"{doc} (work {work}): {len(pages)} pages, {nflag} flagged; skipped {sorted(skip)}; notes: {[r['action'] for r in notes]}")


if __name__ == "__main__":
    main()
