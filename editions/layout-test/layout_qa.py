"""Automatic layout checks: which pages need a human look.

Works on any layout given as PAGE XML (Transkribus Field Recognition, or a local tool), plus the page image.
Per page it first applies safe clean-ups (drop boxes with no ink, drop a box nested in another of the same tag),
then raises flags. Book-level habits (does this book have a catch-word, a running head, how many main-text
blocks) come from the automatic output of the whole book itself, so no corrected page is needed.

    python layout_qa.py LAYOUT_SUFFIX [IMAGE_DIR]     e.g.  python layout_qa.py fr
writes qa-<suffix>.tsv (one row per page: clean-ups, flags) for the pages in test-set.tsv.
"""
import csv, re, sys, collections, statistics as st
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np, cv2

HERE = Path(__file__).parent
FW = ("page-number", "running-head", "catch-word")
SCALE_W = 1200  # analyse images at this width


def read_layout(f):
    """Regions as dicts: lab, box (x0,y0,x1,y1), lines (list of boxes); plus image size."""
    root = ET.parse(f).getroot(); ns = root.tag.split("}")[0][1:]; q = lambda t: f"{{{ns}}}{t}"
    def box(el):
        c = el.find(q("Coords"))
        if c is None or not c.get("points"): return None
        pts = [tuple(map(int, xy.split(","))) for xy in c.get("points").split()]
        return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
    regs = []
    for r in root.iter(q("TextRegion")):
        b = box(r)
        if not b: continue
        m = re.search(r"type:([\w-]+)", r.get("custom", ""))
        regs.append(dict(lab=m.group(1) if m else "none", box=b, lines=[x for x in map(box, r.iter(q("TextLine"))) if x]))
    pg = root.find(q("Page"))
    return regs, int(pg.get("imageWidth")), int(pg.get("imageHeight"))


RULES = {}  # img_path -> horizontal printed rules [(x0, y, x1)], filled by letters()


def letters(img_path, W, H):
    """Letter-sized ink blobs, in the PAGE XML's pixel coordinates: array of (cx, cy, h).
    Also records long thin horizontal strokes (printed rules, e.g. above footnotes) in RULES."""
    g = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if g is None: return None
    s = SCALE_W / g.shape[1]
    g = cv2.resize(g, (SCALE_W, int(g.shape[0] * s)), interpolation=cv2.INTER_AREA)
    bg = cv2.medianBlur(g, 51)  # flatten uneven paper
    flat = cv2.divide(g, bg, scale=255)
    _, bw = cv2.threshold(flat, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, _, stats, cent = cv2.connectedComponentsWithStats(bw, connectivity=8)
    hs = stats[1:, cv2.CC_STAT_HEIGHT]; ws = stats[1:, cv2.CC_STAT_WIDTH]; area = stats[1:, cv2.CC_STAT_AREA]
    ok = (hs >= 4) & (hs <= 80) & (ws <= 120) & (area >= 8) & (area <= 0.6 * hs * ws + 1e9)
    # drop blobs touching the image border (book edge, stand, neighbouring page)
    x, y = stats[1:, 0], stats[1:, 1]
    ok &= (x > 2) & (y > 2) & (x + ws < bw.shape[1] - 2) & (y + hs < bw.shape[0] - 2)
    sx, sy = W / bw.shape[1], H / bw.shape[0]
    rule = (ws > 0.2 * bw.shape[1]) & (hs < 0.012 * bw.shape[0]) & (x > 2) & (x + ws < bw.shape[1] - 2)
    RULES[str(img_path)] = [(x[i] * sx, (y[i] + hs[i] / 2) * sy, (x[i] + ws[i]) * sx) for i in np.where(rule)[0]]
    return np.column_stack([cent[1:, 0][ok] * sx, cent[1:, 1][ok] * sy, hs[ok] * sy])


def inside(pts, b, pad=0):
    return (pts[:, 0] >= b[0] - pad) & (pts[:, 0] <= b[2] + pad) & (pts[:, 1] >= b[1] - pad) & (pts[:, 1] <= b[3] + pad)


def overlap(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy / max(1, min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1])))


def clean(regs, L):
    """Safe clean-ups that need no human: empty boxes, and a box mostly inside another box of the same tag."""
    done = []
    if L is not None:
        keep = []
        for r in regs:
            # a catch-word or page number can be one or two letters
            if inside(L, r["box"]).sum() < (1 if r["lab"] in ("catch-word", "page-number") else 3): done.append(f"drop empty {r['lab']}")
            else: keep.append(r)
        regs = keep
    regs = sorted(regs, key=lambda r: -(r["box"][2]-r["box"][0]) * (r["box"][3]-r["box"][1]))
    keep = []
    for r in regs:
        if any(k["lab"] == r["lab"] and overlap(r["box"], k["box"]) > 0.8 for k in keep): done.append(f"drop nested {r['lab']}")
        else: keep.append(r)
    # overlapping main-text blocks are merged: splitting main text changes nothing in the TEI
    merged = True
    while merged:
        merged = False
        for i, a in enumerate(keep):
            for b in keep[i+1:]:
                if a["lab"] == b["lab"] == "main-text" and overlap(a["box"], b["box"]) > 0.15:
                    a["box"] = (min(a["box"][0], b["box"][0]), min(a["box"][1], b["box"][1]), max(a["box"][2], b["box"][2]), max(a["box"][3], b["box"][3]))
                    a["lines"] = a["lines"] + b["lines"]; keep.remove(b); done.append("merge main-text"); merged = True; break
            if merged: break
    return keep, done


def print_lines(P):
    """Group letters (cx, cy, h) into printed lines; returns a list of (top y, median letter height, n letters)."""
    if len(P) < 5: return []
    P = P[np.argsort(P[:, 1])]; h = np.median(P[:, 2]); out, cur = [], [P[0]]
    for p in P[1:]:
        if p[1] - cur[-1][1] > 0.6 * h: out.append(np.array(cur)); cur = [p]
        else: cur.append(p)
    out.append(np.array(cur))
    return [(c[:, 1].min(), float(np.median(c[:, 2])), len(c)) for c in out if len(c) >= 4]


def page_flags(regs, L, W, H, habit, rules=()):
    f = []
    cnt = collections.Counter(r["lab"] for r in regs)
    main = [r for r in regs if r["lab"] == "main-text"]
    # 1. text outside every box: missing region (the RA's most common hand-drawn fix)
    if L is not None and len(L):
        out = np.ones(len(L), bool)
        for r in regs: out &= ~inside(L, r["box"], pad=0.01 * W)
        body = np.median(L[:, 2])
        lost = L[out & (L[:, 2] > 0.5 * body)]
        # only ink that forms a row of letter-sized marks: printed ornaments break into curls of every size
        n = sum(k for _, hh, k in print_lines(lost) if 0.6 * body < hh < 1.6 * body and k >= 5)
        if n >= 12: f.append(f"text outside boxes ({n} letters)")
    # 2. the page furniture this book normally has
    for lab in FW:
        if cnt[lab] > 1 and not (lab == "running-head" and cnt[lab] == 2 and habit.get("rh2")): f.append(f"{cnt[lab]} {lab}")
        if cnt[lab] == 0 and habit[lab] >= 0.7 and not cnt["heading"]: f.append(f"no {lab}")
    # 3. main text: missing, overlapping blocks, more blocks than the book usually has
    if not main: f.append("no main-text")
    # 4a. a main-text block that starts under a printed rule or under the catch-word is probably a footnote
    cw = [r["box"][1] for r in regs if r["lab"] == "catch-word"]
    for r in main:
        b = r["box"]; others = [m for m in main if m is not r and m["box"][3] <= b[1] + 0.02 * H]
        if not others: continue
        if any(y < b[1] + 0.01 * H and y > max(m["box"][3] for m in others) - 0.02 * H and min(x1, b[2]) - max(x0, b[0]) > 0.2 * (b[2] - b[0])
               for x0, y, x1 in rules):
            f.append("main-text under a printed rule (footnote?)"); break
        if cw and b[1] > min(cw) - 0.005 * H: f.append("main-text under the catch-word (footnote?)"); break
    # 4. print size inside main text: smaller print at the foot = an untagged footnote; larger print = a heading
    if L is not None and len(L):
        body = [pl for r in main for pl in print_lines(L[inside(L, r["box"])])]
        if len(body) >= 4:
            bh = np.median([h for _, h, n in body])
            low = sorted(body)[-3:]
            if sum(h < 0.8 * bh for _, h, n in low) >= 2: f.append("small print at foot of main text (footnote?)")
            if any(h > 1.4 * bh and n >= 5 for _, h, n in body): f.append("large print inside main text (heading?)")
            for r in regs:
                if r["lab"] == "heading":
                    hl = print_lines(L[inside(L, r["box"])])
                    if len(hl) >= 3 and np.median([h for _, h, n in hl]) < 1.1 * bh: f.append("body-size print in a heading"); break
    # 5. headings: too many, or a heading box as wide and tall as body text
    if cnt["heading"] > 3: f.append(f"{cnt['heading']} headings")
    for r in regs:
        if r["lab"] == "heading" and (r["box"][3] - r["box"][1]) > 0.15 * H: f.append("tall heading"); break
    # 6. page furniture placed off its band (page-number/running-head belong at the top, catch-word at the bottom)
    for r in regs:
        cy = (r["box"][1] + r["box"][3]) / 2
        if r["lab"] in ("page-number", "running-head") and cy > 0.25 * H: f.append(f"{r['lab']} not at top"); break
        if r["lab"] == "catch-word" and cy < 0.7 * H: f.append("catch-word not at bottom"); break
    # 7. lines, when the layout has them
    lines = [(l, r) for r in regs for l in r["lines"]]
    if lines:
        for r in regs:
            if r["lab"] in ("main-text", "heading", "footnote") and not r["lines"]: f.append(f"{r['lab']} without lines"); break
        for r in main:
            ws = [l[2] - l[0] for l in r["lines"]]
            if len(ws) >= 5:
                m = st.median(ws)
                if sum(w > 1.15 * m for w in ws) >= 1: f.append("line wider than its block"); break
    return f


def book_habits(pages):
    """pages: list of region lists (after clean-up) for one book."""
    n = len(pages)
    h = {lab: sum(any(r["lab"] == lab for r in p) for p in pages) / n for lab in FW}
    h["main_mode"] = collections.Counter(sum(r["lab"] == "main-text" for r in p) for p in pages).most_common(1)[0][0]
    h["rh2"] = sum(sum(r["lab"] == "running-head" for r in p) == 2 for p in pages) / n > 0.5
    return h


def main():
    suffix = sys.argv[1]
    img_dir = Path(sys.argv[2] if len(sys.argv) > 2 else Path.home() / "Documents/Hasidigital-data/layout-test")
    pages = [r for r in csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t")
             if (HERE / "xml" / r["docId"] / f"{int(r['pageNr']):04d}.{suffix}.xml").exists()]
    data = {}
    for r in pages:
        n = f"{int(r['pageNr']):04d}"
        regs, W, H = read_layout(HERE / "xml" / r["docId"] / f"{n}.{suffix}.xml")
        L = letters(img_dir / r["docId"] / f"{n}.jpg", W, H)
        regs, done = clean(regs, L)
        data[(r["docId"], n)] = (regs, L, W, H, done)
    habits = {d: book_habits([v[0] for k, v in data.items() if k[0] == d]) for d in {k[0] for k in data}}
    out = csv.writer(open(HERE / f"qa-{suffix}.tsv", "w"), delimiter="\t")
    out.writerow(["docId", "pageNr", "cleanups", "flags"])
    for (d, n), (regs, L, W, H, done) in data.items():
        out.writerow([d, int(n), "; ".join(done), "; ".join(page_flags(regs, L, W, H, habits[d], RULES.get(str(img_dir / d / f"{n}.jpg"), ())))])
    print("wrote", HERE / f"qa-{suffix}.tsv", len(data), "pages")


if __name__ == "__main__":
    main()
