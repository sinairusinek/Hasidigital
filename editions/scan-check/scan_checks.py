#!/usr/bin/env python3
"""Series check of page scans before any layout or HTR run: image measurements only, no OCR, no credits.

For every page of the Transkribus docs given (default: all docs uploaded since 2026-11-01 in
editions/transkribus-collection-map.tsv) it measures letter height, sharpness, contrast, skew, warp,
pages without text, duplicate pages, two-page spreads, cropped text, dark scanner borders and coloured areas (stamps, tears),
then writes one row per page and one row per book.

Needs OpenCV, which is not in the project venv (pip install opencv-python-headless numpy scipy).

    python scan_checks.py IMG_DIR FULLDOC_DIR          # IMG_DIR/<docId>/<pageNr:04d>.jpg, FULLDOC_DIR/<docId>.json

Outputs editions/scan-check/scan-pages.tsv and scan-books.tsv. The flags mark hard defects; how the
thresholds were set is in the comment above them.
"""
import csv
import html
import json
import pickle
import sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
MAP = REPO / "editions" / "transkribus-collection-map.tsv"
OUT = Path(__file__).resolve().parent

# Page flags for hard defects. Set 2026-11-11 against 1,331 finished pages read by PyLaia 52805
# (scan measurements vs the RA's corrections): no measurement predicts HTR error well (|rho| <= 0.3),
# so flags sit near the 5th/95th percentile of finished pages rather than at a CER cut-off.
MIN_CONTRAST = 100      # grey levels between 5th and 95th percentile (pages below 100: a third over 5% CER)
MAX_SKEW = 1.5          # degrees
MAX_WARP = 1.5          # degrees between left and right half skew (1.0 flagged straight pages)
MIN_SHARP = 0.05        # normalised Laplacian variance, see sharpness(); ~5th percentile
MAX_CUT = 30            # letter-sized blobs touching the image edge; ~95th percentile
MAX_COLOUR = 0.05       # share of page off the paper's colour: tape, stamps, tears
DUP_CORR = 0.97         # correlation of 64x64 page thumbnails (a 64-bit hash matched different text pages)
MIN_RUN = 3             # consecutive pages before a size or line-spacing change counts as a series break


def thumb(img):
    t = cv2.resize(img, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    t -= t.mean()
    return t / (np.linalg.norm(t) or 1)


def runs(mask, min_run):
    """Indices that sit in a run of at least min_run consecutive True values."""
    out, start = set(), None
    for i, m in enumerate(list(mask) + [False]):
        if m and start is None:
            start = i
        elif not m and start is not None:
            if i - start >= min_run:
                out.update(range(start, i))
            start = None
    return out


def best_angle(bw):
    """Angle (degrees) that maximises the variance of the row projection: the text-line direction."""
    h, w = bw.shape
    best, best_v = 0.0, -1
    for a in np.arange(-4, 4.01, 0.25):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1)
        v = cv2.warpAffine(bw, m, (w, h)).sum(1).astype(float).var()
        if v > best_v:
            best, best_v = a, v
    return float(best)


def line_spacing(small, angle, scale):
    """Text-line pitch in original pixels: first autocorrelation peak of the deskewed row projection."""
    h, w = small.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1)
    prof = cv2.warpAffine(small, m, (w, h)).sum(1).astype(float)
    prof -= prof.mean()
    ac = np.correlate(prof, prof, "full")[len(prof) - 1:]
    if ac[0] <= 0:
        return float("nan")
    ac /= ac[0]
    lo, hi = 6, min(200, len(ac) - 1)
    peaks = [i for i in range(lo, hi) if ac[i] > ac[i - 1] and ac[i] >= ac[i + 1] and ac[i] > 0.15]
    return float(peaks[0] * scale) if peaks else float("nan")


def sharpness(g, bw, line_px):
    """Laplacian variance near ink, after scaling text lines to 40 px and dividing by contrast^2,
    so the number does not depend on scan resolution or ink density."""
    if not line_px or line_px != line_px:
        return float("nan")
    f = 40 / line_px
    gs = cv2.resize(g, None, fx=f, fy=f, interpolation=cv2.INTER_AREA).astype(np.float32)
    ms = cv2.resize(bw, (gs.shape[1], gs.shape[0]), interpolation=cv2.INTER_NEAREST)
    ms = cv2.dilate(ms, np.ones((5, 5), np.uint8)) > 0
    if ms.sum() < 1000:
        return float("nan")
    lap = cv2.Laplacian(gs, cv2.CV_32F)
    c = np.percentile(gs, 95) - np.percentile(gs, 5)
    return float(lap[ms].var() / max(c, 1) ** 2)


def analyse(job):
    doc, page, path = job
    color = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if color is None:
        return {"docId": doc, "page": page, "error": "unreadable"}
    g = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    r = {"docId": doc, "page": page, "w": w, "h": h, "error": ""}

    # dark scanner border: an edge strip much darker than the page
    strip = max(3, w // 100)
    edges = [g[:, :strip], g[:, -strip:], g[:strip, :], g[-strip:, :]]
    r["dark_border"] = int(sum(e.mean() < 70 for e in edges))

    r["bitonal"] = int(len(np.unique(g[::4, ::4])) <= 4)
    r["contrast"] = float(np.percentile(g, 95) - np.percentile(g, 5))
    # flatten the paper (yellowing, shadows, tape) before binarising, or its texture counts as ink
    q = cv2.resize(g, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
    bg = cv2.resize(cv2.medianBlur(cv2.morphologyEx(q, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8)), 21), (w, h))
    flat = np.clip(g.astype(np.float32) / np.maximum(bg, 1) * 255, 0, 255).astype(np.uint8)
    _, bw = cv2.threshold(cv2.GaussianBlur(flat, (3, 3), 0), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # ignore a dark border when measuring ink
    inner = bw[h // 30: -h // 30, w // 30: -w // 30]
    r["ink"] = float(inner.mean() / 255)

    n, _, st, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    hs, ws, ar = st[1:, 3], st[1:, 2], st[1:, 4]
    x0, y0 = st[1:, 0], st[1:, 1]
    letters = (hs >= 4) & (hs < h * 0.05) & (ws < w * 0.08) & (ar >= 10)
    r["n_letters"] = int(letters.sum())
    r["letter_h"] = float(np.median(hs[letters])) if letters.sum() > 50 else float("nan")
    # letter-sized blobs cut by the image edge: text cropped off
    touch = (x0 <= 1) | (y0 <= 1) | (x0 + ws >= w - 1) | (y0 + hs >= h - 1)
    r["cut_letters"] = int((letters & touch).sum())

    small = cv2.resize(inner, (1000, int(1000 * inner.shape[0] / inner.shape[1])), interpolation=cv2.INTER_AREA)
    r["skew"] = best_angle(small)
    r["line_px"] = line_spacing(small, r["skew"], inner.shape[1] / 1000)
    half = small.shape[1] // 2
    r["warp"] = abs(best_angle(small[:, :half]) - best_angle(small[:, half:]))

    # two-page spread: a landscape image
    # (an empty middle gutter alone also fired on two-column pages, so only landscape images count)
    r["spread"] = int(w > h * 1.05)

    r["sharp"] = sharpness(g, bw, r["line_px"])

    # colour that differs from the page's own paper: stamps, tape, a torn corner showing the background
    lab = cv2.cvtColor(cv2.resize(color, (w // 4, h // 4), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2LAB).astype(np.float32)
    paper = lab[..., 0] > np.median(lab[..., 0])
    pa, pb = np.median(lab[..., 1][paper]), np.median(lab[..., 2][paper])
    dev = np.hypot(lab[..., 1] - pa, lab[..., 2] - pb)
    r["stamp"] = float(((dev > 18) & (lab[..., 0] > 60)).mean())
    r["thumb"] = thumb(flat)
    return r


def flags(r):
    f = []
    if r["error"]:
        return ["unreadable"]
    if r["ink"] < 0.004 or r["n_letters"] < 40:
        return ["no_text"]
    # covers, endpapers and blank paper with texture: heavy "ink" and no sharp letter edges.
    # None of the 1,331 calibration text pages meets this.
    sharp = r["sharp"] if r["sharp"] == r["sharp"] else 0
    if r["ink"] > 0.25 or sharp < 0.01 or (r["ink"] > 0.2 and sharp < 0.04):
        return ["no_text"]
    if r["contrast"] < MIN_CONTRAST:
        f.append("low_contrast")
    if r["sharp"] == r["sharp"] and r["sharp"] < MIN_SHARP:
        f.append("blurred")
    if abs(r["skew"]) > MAX_SKEW:
        f.append("skewed")
    # warp is measured but not flagged: at any threshold it fired on straight pages (work 6)
    if r["w"] > r["h"] * 1.05:
        f.append("two_page_spread")
    if r["cut_letters"] > MAX_CUT:
        f.append("text_cut_at_edge")
    if r["stamp"] > MAX_COLOUR:
        f.append("coloured_area")  # stamp, torn corner or background showing
    if r["bitonal"]:
        f.append("bitonal")
    return f


def main():
    img_dir, fulldoc_dir = Path(sys.argv[1]), Path(sys.argv[2])
    docs = {row["docId"]: row for row in csv.DictReader(open(MAP, encoding="utf-8"), delimiter="\t")
            if row["uploaded"] >= "2026-11-01"}
    cache = img_dir / "_measurements.pkl"   # measuring takes ~5 min; delete the cache when images change
    if cache.exists():
        rows = pickle.loads(cache.read_bytes())
    else:
        jobs = [(d, int(p.stem), p) for d in docs for p in sorted((img_dir / d).glob("*.jpg"))]
        with Pool(10) as pool:
            rows = pool.map(analyse, jobs, chunksize=8)
        cache.write_bytes(pickle.dumps(rows))
    rows.sort(key=lambda r: (r["docId"], r["page"]))

    by_doc = defaultdict(list)
    for r in rows:
        by_doc[r["docId"]].append(r)
    for d, rs in by_doc.items():
        # duplicates within a book (pages without text excluded)
        for r in rs:
            r["flags"] = flags(r)
        txt = [r for r in rs if not r["error"] and "no_text" not in r["flags"]]
        if txt:
            sim = np.triu(np.stack([r["thumb"] for r in txt]) @ np.stack([r["thumb"] for r in txt]).T, 1)
            for i, j in zip(*np.where(sim > DUP_CORR)):
                if not any(x.startswith("duplicate_of_") for x in txt[j]["flags"]):
                    txt[j]["flags"].append(f"duplicate_of_{txt[i]['page']}")
        # series break: a run of pages with a different image size, e.g. a merged printing or another scan.
        # Line spacing is not used: it jumped on two-column pages and small-print footnotes.
        wmed = np.median([r["w"] for r in rs if not r["error"]])
        size_off = [not r["error"] and "no_text" not in r["flags"] and abs(r["w"] - wmed) > 0.2 * wmed for r in rs]
        for i in runs(size_off, MIN_RUN):
            rs[i]["flags"].append("size_differs")

    cols = ["docId", "page", "w", "h", "line_px", "letter_h", "contrast", "sharp", "skew", "warp", "ink", "n_letters",
            "cut_letters", "dark_border", "stamp", "bitonal", "spread", "error"]
    with open(OUT / "scan-pages.tsv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f, delimiter="\t")
        wr.writerow(["work_nu", "work"] + cols + ["flags"])
        for r in rows:
            m = docs[r["docId"]]
            wr.writerow([m["work_nu"], m["work"]] + [round(r[c], 4) if isinstance(r.get(c), float) else r.get(c, "")
                                                   for c in cols] + [" ".join(r["flags"])])

    with open(OUT / "scan-books.tsv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f, delimiter="\t")
        wr.writerow(["docId", "work_nu", "work", "pages", "median_w", "median_line_px", "median_contrast",
                     "median_sharp", "bitonal_share", "pages_flagged", "flag_counts", "verdict"])
        for d, rs in by_doc.items():
            ok = [r for r in rs if not r["error"]]
            fc = Counter(fl.split("_of_")[0] for r in rs for fl in r["flags"])
            wr.writerow([d, docs[d]["work_nu"], docs[d]["work"], len(rs),
                         int(np.median([r["w"] for r in ok])),
                         round(float(np.nanmedian([r["line_px"] for r in ok])), 1),
                         round(float(np.median([r["contrast"] for r in ok])), 1),
                         round(float(np.nanmedian([r["sharp"] for r in ok])), 4),
                         round(sum(r["bitonal"] for r in ok) / max(len(ok), 1), 2),
                         sum(1 for r in rs if [x for x in r["flags"] if x != "no_text"]),
                         "; ".join(f"{k} {v}" for k, v in fc.most_common()),
                         " | ".join(t for t, _ in verdict(rs))])
    write_report(by_doc, docs, fulldoc_dir)
    print(len(rows), "pages,", len(by_doc), "docs")


def pages_with(rs, flag):
    return [r for r in rs if any(f.startswith(flag) for f in r["flags"])]


def verdict(rs):
    """Plain-language findings for one book: (text, pages to show). Empty list = nothing to do.
    Checked by eye on contact sheets (2026-11-11): "text_cut_at_edge" almost always means the photo also shows
    the neighbouring page, the copy stand or the page-block edge, with the text intact, so it calls for
    automatic cropping, not a person. Only damage that can lose text is left for a person to look at."""
    n = len(rs)
    out = []
    dup = pages_with(rs, "duplicate_of_")
    if dup:
        pairs = ", ".join(f"{[f for f in r['flags'] if f.startswith('duplicate_of_')][0][13:]}={r['page']}" for r in dup)
        out.append((f"CHECK: same page scanned twice (image pages {pairs}); drop the repeats before layout", dup))
    size = pages_with(rs, "size_differs")
    if size:
        out.append((f"CHECK: image pages {size[0]['page']}–{size[-1]['page']} differ in size from the rest; "
                    "another scan or printing merged in?", size))
    textual = [r for r in rs if "no_text" not in r["flags"]]
    damaged = [r for r in textual if "two_page_spread" in r["flags"] or (r["sharp"] == r["sharp"] and r["sharp"] < 0.03)]
    frame = [r for r in textual if "text_cut_at_edge" in r["flags"] or "coloured_area" in r["flags"]]
    if len(frame) > 0.1 * n:
        out.append((f"AUTO: crop to the page before layout; {len(frame)} of {n} photos also show the neighbouring page, "
                    "copy stand, background or tape", frame))
    else:
        damaged += [r for r in textual if "coloured_area" in r["flags"]]   # isolated: tears, tape, stamps
    skew = pages_with(rs, "skewed")
    if len(skew) > 0.1 * n:
        out.append((f"AUTO: deskew before layout ({len(skew)} of {n} pages rotated)", skew))
    if damaged:
        damaged.sort(key=lambda r: r["page"])
        out.append((f"CHECK: {len(damaged)} pages with possible text loss (tear, tape, stamp, blur or a two-page spread)", damaged))
    lowc = pages_with(textual, "low_contrast")
    if len(lowc) > 0.2 * n:
        out.append((f"NOTE: faint print or dark paper on {len(lowc)} of {n} pages; expect more OCR errors", lowc))
    return out


def write_report(by_doc, docs, fulldoc_dir):
    """editions/scan-check/scan-report.html: only the books with findings, with thumbnails linking to the page image."""
    urls = {}
    for d in by_doc:
        f = fulldoc_dir / f"{d}.json"
        if f.exists():
            for p in json.loads(f.read_text())["pageList"]["pages"]:
                urls[(d, p["pageNr"])] = (p["thumbUrl"], p["url"])
    items, clean = [], []
    for d, rs in sorted(by_doc.items(), key=lambda x: float(docs[x[0]]["work_nu"] or 0)):
        v = verdict(rs)
        name = f'{html.escape(docs[d]["work"])} <span class="meta">work {docs[d]["work_nu"]} · doc {d} · {len(rs)} pages</span>'
        if not v:
            clean.append(name)
            continue
        block = [f'<section><h2>{name}</h2>']
        for text, pages in v:
            thumbs = "".join(
                f'<a href="{urls.get((d, r["page"]), ("", ""))[1]}" title="image page {r["page"]}: {html.escape(" ".join(r["flags"]))}">'
                f'<img loading="lazy" src="{urls.get((d, r["page"]), ("", ""))[0]}"><span>{r["page"]}</span></a>'
                for r in pages[:8])
            more = f'<span class="more">+{len(pages) - 8} more</span>' if len(pages) > 8 else ""
            block.append(f'<div class="finding"><p>{html.escape(text)}</p><div class="thumbs">{thumbs}{more}</div></div>')
        items.append("".join(block) + "</section>")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scan Check</title><style>
:root{{--bg:#fff;--fg:#1d1d1f;--muted:#6e6e73;--line:#e5e5ea;--card:#f7f7f9}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1c1c1e;--fg:#f2f2f7;--muted:#a1a1a6;--line:#3a3a3c;--card:#2c2c2e}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,system-ui,sans-serif;max-width:1100px;margin:0 auto;padding:16px}}
h1{{font-size:22px}} h2{{font-size:17px;margin:0 0 6px}} .meta{{color:var(--muted);font-weight:400;font-size:13px}}
section{{border-top:1px solid var(--line);padding:14px 0}} .finding p{{margin:6px 0}}
.thumbs{{display:flex;flex-wrap:wrap;gap:6px;align-items:flex-end}} .thumbs a{{display:flex;flex-direction:column;align-items:center;color:var(--muted);font-size:12px;text-decoration:none}}
.thumbs img{{height:120px;background:var(--card);border:1px solid var(--line)}} .more{{color:var(--muted);font-size:13px}}
.clean{{color:var(--muted)}}
</style></head><body>
<h1>Scan check of the new books</h1>
<p>Image measurements only, before any layout or HTR. {len(items)} of {len(by_doc)} books have findings; the rest are listed at the end.
<b>CHECK</b> needs a person; <b>AUTO</b> is a preprocessing step the pipeline can do; <b>NOTE</b> is information.
Thumbnails open the page image; the number under each is the image page in Transkribus.</p>
{"".join(items)}
<section class="clean"><h2>No findings</h2><p>{"<br>".join(clean)}</p></section>
</body></html>"""
    (OUT / "scan-report.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
