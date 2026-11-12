"""One main-text region per paragraph.

    python paragraphs.py score             score the splitter against the RA's regions in FINAL (test set)
    python paragraphs.py features [pipe]   row pairs inside merged main-text blocks, with the RA's breaks (for fitting)

How the RA split main text (FINAL, 13 books of set A + set C): one region per paragraph on story pages. A region's
last line ends with ":" in 55% of cases (almost never a line inside a region does); the line before a break is short
(median 7 letter heights of space at the left, against 0.1 inside a region), the next paragraph often opens with a
larger word (1.1-1.7 times the body letters) and sometimes after a blank gap. First lines are not indented in these
books. Front matter (approbations, letters, title pages) is split less consistently.

The splitter works on the rows of each main-text region and starts a new paragraph after a row that stops short of
the left margin (> 3 letter heights), after a blank gap (> 1.3 line spacings), or before a row that opens with a
larger word (> 1.5 times its row; > 1.15 with a slightly short row above). Indentation is not used. rules.tidy calls
it in place of the old step that merged stacked main-text boxes into one per column.

Score (`score`, letters in FINAL main-text regions, 880 paragraphs on 239 pages of sets A and C; a paragraph is
matched when one of our regions holds ≥90% of it and ≥90% of that region is it):
                                       RA's lines   our lines (YOLO + fine-tuned Kraken)
  old tidy (stacked boxes merged)         35%          32%
  detector's boxes, overlaps merged       93%          92%
  same + splitter (now used)              94%          92%
  11 story books only, + splitter         97%          95%
Front matter (approbations, title pages) and בית ישראל are where the RA's own splits are least regular and where we
miss most. Not caught without the text: a paragraph that ends at the full margin with ":" (55% of the RA's region
ends have ":" and almost no line inside a region does; after HTR this is the strongest signal).
"""
import sys, csv, re
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from layout_qa import letters
from line_score import assign_baseline

HERE = Path(__file__).parent
IMG = Path.home() / "Documents/Hasidigital-data/layout-test"
RULE = dict(short=3.0, gap=1.3, lift=1.5, weak_lift=1.15, weak_short=1.0)  # fitted on the test set; see breaks()


def rows_of(ls, L, box=None):
    """Lines of one region → rows (dicts: ix line indices, xl, xr, y baseline, lift, P letters on the row, q indices
    of the letters on its lines), top to bottom, and the body letter height. Pieces of one cut line, or of a line that
    bends, form one row. A row is measured on all the ink along its baseline within the box, since a piece of the
    line (often the opening word) may have gone to another region."""
    a = assign_baseline([(None, None, bl) for _, bl in ls], L)
    info = []
    for i, (p, bl) in enumerate(ls):
        y = float(np.median(bl[:, 1])) if isinstance(bl, np.ndarray) and len(bl) >= 2 else float(np.asarray(p)[:, 1].max())
        info.append((y, i, np.where(a == i)[0]))
    info.sort(key=lambda t: t[0])
    h = float(np.median(L[np.concatenate([q for _, _, q in info]), 2])) if any(len(q) for _, _, q in info) else 10.0
    ys = [y for y, _, _ in info]; d = np.diff(ys); d = d[d > 0.5 * h]
    near = 0.5 * float(np.median(d)) if len(d) else 0.5 * h
    rows = []
    for y, i, P in info:
        if rows and y - rows[-1][0][-1] < near: rows[-1][0].append(y); rows[-1][1].append(i); rows[-1][2].append(P)
        else: rows.append([[y], [i], [P]])
    out = []
    for y, ix, Qs in rows:
        q = np.concatenate(Qs); P = L[q]
        if box is not None and len(P) >= 2:
            yb = np.interp(L[:, 0], *zip(*sorted((float(np.median(L[qq, 0])), yy) for yy, qq in zip(y, Qs) if len(qq)))) if len(P) else None
            band = (L[:, 1] < yb + 0.2 * h) & (L[:, 1] > yb - 1.2 * h) & (L[:, 0] > box[0] - h) & (L[:, 0] < box[2] + h)
            if band.sum() >= len(P): P = L[band]
        if len(P) < 2:
            pts = np.vstack([np.asarray(ls[i][0]) for i in ix]); out.append(dict(ix=ix, xl=pts[:, 0].min(), xr=pts[:, 0].max(), y=float(np.median(y)), lift=1.0, P=P, q=q)); continue
        xr = np.percentile(P[:, 0], 99)
        # the opening word against the rest of its row: the second smallest of the four rightmost letters, so that
        # one tall letter (ל) does not count and one small mark (׳) does not hide a large word
        # (fragments of broken letters, under half a letter high, are left out)
        F = P[P[:, 2] > 0.5 * h]
        first = np.sort(F[np.argsort(-F[:, 0])[:4], 2]) if len(F) >= 8 else None
        lift = float(first[1] / np.median(F[:, 2])) if first is not None else 1.0
        out.append(dict(ix=ix, xl=np.percentile(P[:, 0], 1), xr=xr, y=float(np.median(y)), lift=lift, P=P, q=q))
    return out, h


def pair_features(rows, h, L):
    """For each pair of consecutive rows: short (space left of the upper row, letter heights), indent (space right of
    the lower row), gap (in line spacings), blank (no letters between them), lift (opening word of the lower row)."""
    if len(rows) < 2: return []
    body = [r for r in rows if len(r["P"]) >= 5] or rows
    cl, cr = np.percentile([r["xl"] for r in body], 20), np.percentile([r["xr"] for r in body], 80)
    ys = [r["y"] for r in rows]; sp = float(np.median(np.diff(ys))) if len(ys) > 2 else ys[1] - ys[0]
    out = []
    for a, b in zip(rows, rows[1:]):
        between = (L[:, 1] > a["y"] + 0.3 * h) & (L[:, 1] < b["y"] - 1.3 * h) & (L[:, 0] > cl) & (L[:, 0] < cr)
        out.append(dict(short=(a["xl"] - cl) / h, indent=(cr - b["xr"]) / h, gap=(b["y"] - a["y"]) / sp,
                        blank=between.sum() <= 2, lift=b["lift"]))
    return out


def breaks(rows, h, L, rule=RULE):
    """Indices k where a new paragraph starts at row k: the row above stops short of the left margin, a blank gap,
    or a larger opening word (a smaller lift counts with a slightly short row above or a slightly wide gap). An
    indented row is not used: most of these books do not indent, and the tail of a quoted verse is often set apart
    from the right margin inside a paragraph."""
    # rows with hardly any full-size letters (a row of vowel marks or dots that got a line of its own) stay with the
    # row above and are not measured
    body = [k for k, r in enumerate(rows) if (r["P"][:, 2] > 0.5 * h).sum() >= 3] if len(rows) else []
    if len(body) < 2: return []
    out = []
    for k, f in zip(body[1:], pair_features([rows[k] for k in body], h, L)):
        gap = f["blank"] and f["gap"] > rule["gap"]
        if (f["short"] > rule["short"] or gap or f["lift"] > rule["lift"]
                or (f["lift"] > rule["weak_lift"] and (f["short"] > rule["weak_short"] or (f["blank"] and f["gap"] > 1.12)))):
            out.append(k)
    return out


def split(regions, L, rule=RULE):
    """[(tag, box, lines)] → the same, with every main-text region cut into paragraphs. The cut between two
    paragraphs lies halfway between the last row of one and the first row of the next. The detector's own borders
    are kept: joining stacked boxes first and cutting only by the rule lost borders that the RA drew at paragraph
    ends with no mark in the geometry (a ":" at the full margin)."""
    if L is None or not len(L): return regions
    out = []
    for tag, box, ls in regions:
        if tag != "main-text" or len(ls) < 2: out.append((tag, box, ls)); continue
        rows, h = rows_of(ls, L, box)
        ks = breaks(rows, h, L, rule)
        if not ks: out.append((tag, box, ls)); continue
        parts = np.split(np.arange(len(rows)), ks)
        bot = lambda r: max(np.asarray(ls[i][0])[:, 1].max() for i in r["ix"])
        top = lambda r: min(np.asarray(ls[i][0])[:, 1].min() for i in r["ix"])
        y = box[1]
        for j, part in enumerate(parts):
            y1 = box[3] if j == len(parts) - 1 else (bot(rows[part[-1]]) + top(rows[parts[j + 1][0]])) / 2
            y1 = max(y1, y + 1)
            out.append((tag, (box[0], int(y), box[2], int(y1)), [ls[i] for k in part for i in rows[k]["ix"]]))
            y = y1
    return out


def stack(regions, L):
    """Main-text boxes directly one above the other in the same column, with nothing between, become one block (the
    old tidy step; kept for comparison and for fitting the rule). Returns the blocks and {id(line polygon): index of
    the box it came from}."""
    from layout_qa import overlap
    out = [[t, b, list(ls)] for t, b, ls in regions]
    was = {id(p): k for k, (_, _, ls) in enumerate(regions) for p, _ in ls}
    lh = float(np.median([np.ptp(np.asarray(q)[:, 1]) for _, _, ls in out for q, _ in ls] or [50]))
    merged = True
    while merged:
        merged = False
        for a in out:
            for c in out:
                if a is c or a[0] != "main-text" or c[0] != "main-text" or not (-lh < c[1][1] - a[1][3] < lh) or c[1][1] <= a[1][1]: continue
                xo = min(a[1][2], c[1][2]) - max(a[1][0], c[1][0])
                if xo < 0.8 * min(a[1][2] - a[1][0], c[1][2] - c[1][0]): continue
                box = (min(a[1][0], c[1][0]), a[1][1], max(a[1][2], c[1][2]), c[1][3])
                if any(o is not a and o is not c and overlap(o[1], box) > 0.3 for o in out): continue
                a[1] = box; a[2] += c[2]; out.remove(c); merged = True; break
            if merged: break
    return [tuple(r) for r in out], was


# ---------- scoring against FINAL ----------

def read_regions(f):
    """PAGE XML → [(tag, box, [(polygon, baseline)])], W, H."""
    root = ET.parse(f).getroot(); ns = root.tag.split("}")[0][1:]; q = lambda t: f"{{{ns}}}{t}"
    pg = root.find(q("Page")); W, H = int(pg.get("imageWidth")), int(pg.get("imageHeight")); out = []
    pts = lambda s: np.array([tuple(map(int, xy.split(","))) for xy in s.split()])
    for r in root.iter(q("TextRegion")):
        m = re.search(r"type:([\w-]+)", r.get("custom", "")); tag = m.group(1) if m else "main-text"
        c = r.find(q("Coords"))
        if c is None or not c.get("points"): continue
        b = pts(c.get("points")); ls = []
        for l in r.iter(q("TextLine")):
            lc, lb = l.find(q("Coords")), l.find(q("Baseline"))
            if lc is None or not lc.get("points") or lb is None or not lb.get("points"): continue
            p, bl = pts(lc.get("points")), pts(lb.get("points"))
            if len(p) >= 3 and len(bl) >= 2: ls.append((p, bl))
        out.append(("main-text" if tag == "none" else tag, (b[:, 0].min(), b[:, 1].min(), b[:, 0].max(), b[:, 1].max()), ls))
    return out, W, H


def letter_regions(regions, L):
    """Region index of each letter (-1 = none), through the lines' baselines."""
    flat = [(k, bl) for k, (_, _, ls) in enumerate(regions) for _, bl in ls]
    a = assign_baseline([(None, None, bl) for _, bl in flat], L)
    return np.array([flat[i][0] if i >= 0 else -1 for i in a])


def compare(final, ours, L):
    """Paragraphs = FINAL main-text regions with ≥20 letters that are main text in ours too. A paragraph is matched
    when one of our main-text regions holds ≥90% of those letters and ≥90% of that region's letters are in it. Returns (paragraphs, matched, split
    (spread over several of ours), joined (shares a region of ours with another paragraph))."""
    fr, orr = letter_regions(final, L), letter_regions(ours, L)
    fmain = [k for k, r in enumerate(final) if r[0] == "main-text"]; omain = {k for k, r in enumerate(ours) if r[0] == "main-text"}
    n = m = sp = jo = 0
    both = np.isin(orr, list(omain))  # letters that are main text in ours too: tag errors are scored elsewhere (ink_score)
    for k in fmain:
        sel = (fr == k) & both
        if sel.sum() < 20: continue
        n += 1
        mine = orr[sel]; ids, cnt = np.unique(mine[np.isin(mine, list(omain))], return_counts=True)
        if not len(ids): sp += 1; continue
        j = ids[cnt.argmax()]
        inj = (orr == j) & np.isin(fr, fmain)
        ok = cnt.max() >= 0.9 * sel.sum() and cnt.max() >= 0.9 * inj.sum()
        m += ok
        if not ok:
            if cnt.max() < 0.9 * sel.sum(): sp += 1
            if cnt.max() < 0.9 * inj.sum(): jo += 1
    return n, m, sp, jo


def pipeline_regions(d, n, img, W, H):
    """Our pipeline on a test page, as run_layout builds it before Claude's relabel: YOLO boxes + the fine-tuned
    Kraken lines (cut, joined, refilled) + footnote rules."""
    from rules import combine_page
    from layout_qa import RULES
    from line_score import line_polys
    from yolo_regions import regions as yolo_regions
    regs, _, _ = yolo_regions(d / f"{n}.yolo.xml")
    polys, _, _ = line_polys(d / f"{n}.krakenftfix-yolo-noext-join-refill.xml", True)
    return combine_page(regs, [(p, bl) for p, _, bl in polys if bl is not None], RULES.get(str(img), ()), W, H)


PIPE = "yolo+krakenftfix-yolo-noext-join-refill"


def pages():
    """Test pages (sets A and C) with main text in FINAL: (docId, page, FINAL regions, letters, W, H)."""
    for r in csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t"):
        if r["set"] not in ("A", "C"): continue
        n = f"{int(r['pageNr']):04d}"; d = HERE / "xml" / r["docId"]
        if not (d / f"{n}.final.xml").exists(): continue
        final, W, H = read_regions(d / f"{n}.final.xml"); final = [x for x in final if x[2]]
        if not any(t == "main-text" for t, _, _ in final): continue
        yield r["docId"], n, final, letters(IMG / r["docId"] / f"{n}.jpg", W, H), W, H


def features(src="final"):
    """Every pair of consecutive rows in the merged main-text blocks, with whether the RA started a new region there
    → stdout (for fitting the rule)."""
    from rules import tidy
    print("docId\tpage\tra_break\tshort\tindent\tgap\tblank\tlift")
    for doc, n, final, L, W, H in pages():
        regs = final if src == "final" else pipeline_regions(HERE / "xml" / doc, n, IMG / doc / f"{n}.jpg", W, H)
        fr = letter_regions(final, L)
        for tag, box, ls in tidy(regs, L, H, main="columns"):
            if tag != "main-text" or len(ls) < 2: continue
            rows, h = rows_of(ls, L, box)
            reg = [np.bincount(fr[r["q"]][fr[r["q"]] >= 0]).argmax() if (fr[r["q"]] >= 0).sum() >= 3 else -1 for r in rows]
            for k, f in enumerate(pair_features(rows, h, L), 1):
                if reg[k - 1] < 0 or reg[k] < 0: continue
                print(f"{doc}\t{n}\t{int(reg[k - 1] != reg[k])}\t{f['short']:.2f}\t{f['indent']:.2f}\t{f['gap']:.2f}\t{int(f['blank'])}\t{f['lift']:.2f}")


def score(rule=RULE, sufs=("final", PIPE)):
    from rules import tidy
    import collections
    tot = collections.defaultdict(lambda: np.zeros(4, int)); book = collections.defaultdict(lambda: np.zeros(4, int))
    rows = []
    for doc, n, final, L, W, H in pages():
        for suf in sufs:
            regs = final if suf == "final" else pipeline_regions(HERE / "xml" / doc, n, IMG / doc / f"{n}.jpg", W, H)
            cols = tidy(regs, L, H, main="columns"); kept = tidy(regs, L, H, main=None)
            for name, rr in (("as detected", regs), ("columns (old tidy)", cols), ("columns + split", split(cols, L, rule)),
                             ("detected boxes", kept), ("detected + split", split(kept, L, rule))):
                c = np.array(compare(final, rr, L)); tot[(suf, name)] += c
                if name == "detected + split": book[(suf, doc)] += c
                rows.append((suf, name, doc, n, *c))
    for (suf, name), c in tot.items():
        print(f"{suf:45s} {name:18s} paragraphs {c[0]:4d}  matched {c[1]:4d} ({c[1] / c[0]:.0%})  split {c[2]:3d}  joined {c[3]:3d}")
    for (suf, doc), c in sorted(book.items()):
        print(f"  {suf[:12]:12s} {doc:9s} {c[1]:3d}/{c[0]:3d}  split {c[2]:3d}  joined {c[3]:3d}")
    with open(HERE / "paragraph-scores.tsv", "w") as fh:
        fh.write("lines\tregions\tdocId\tpage\tparagraphs\tmatched\tsplit\tjoined\n")
        for x in rows: fh.write("\t".join(map(str, x)) + "\n")


if __name__ == "__main__":
    if sys.argv[1] == "score": score()
    elif sys.argv[1] == "features": features(*sys.argv[2:3])
