"""Geometric rules that give our tags to untagged lines (e.g. Kraken's), and a combiner that puts detected lines
into detected regions.

    python rules.py label SUFFIX          SUFFIX lines (untagged) → <suffix>rules.xml with tagged regions
    python rules.py combine REG LINES     REG regions + LINES lines → <reg>+<lines>.xml (each line joins the
                                          region holding its centre; then the footnote rules are applied)
Rules (Hebrew printing, right to left):
- top line, if set apart from the body by a gap or by larger print: running head; a short piece of it at either
  end (<= 4 letters, after a wide gap) is the page number;
- last line, if short and on the left: catch-word;
- lines under a printed rule that lies below the body, or in smaller print at the foot: footnote;
- lines in larger print, or short centred lines set off by space: heading.
"""
import sys, csv, re
from pathlib import Path
import numpy as np
from layout_qa import letters, RULES
from line_score import line_polys, assign
from yolo_regions import regions as yolo_regions, PAGE

HERE = Path(__file__).parent
IMG = Path.home() / "Documents/Hasidigital-data/layout-test"


def box_of(P):
    return (int(P[:, 0].min()), int((P[:, 1] - P[:, 2] / 2).min()), int(P[:, 0].max()), int((P[:, 1] + P[:, 2] / 2).max()))


def label_lines(lines, L, W, H, rules):
    """lines: list of letter arrays (cx, cy, h) per line, in any order. Returns [(tag, letters)] pieces."""
    lines = [l for l in lines if len(l) >= 1]
    if not lines: return []
    allp = np.vstack(lines); bh = float(np.median(allp[:, 2]))
    tx0, tx1 = np.percentile(allp[:, 0], 1), np.percentile(allp[:, 0], 99); tw = tx1 - tx0
    lines.sort(key=lambda l: np.median(l[:, 1]))
    # pieces on the same row (a line split at a wide gap, or two columns) are one row for labelling
    rows = [lines[0]]
    for l in lines[1:]:
        if abs(np.median(l[:, 1]) - np.median(rows[-1][:, 1])) < 0.5 * bh: rows[-1] = np.vstack([rows[-1], l])
        else: rows.append(l)
    lines = rows
    ys = [float(np.median(l[:, 1])) for l in lines]; gaps = np.diff(ys); lead = float(np.median(gaps)) if len(gaps) else bh * 2
    tags = ["main-text"] * len(lines); out = []
    # footnotes: below a printed rule that is under at least a third of the text
    # (a rule may cover one column only; it counts when at least 3 text rows lie above it in its own span)
    feet = [(x0, y, x1) for x0, y, x1 in rules if x1 - x0 > 0.2 * tw
            and sum(1 for P in lines if np.median(P[:, 1]) < y and x0 - bh < np.median(P[:, 0]) < x1 + bh) >= 3]
    foot = np.zeros(len(allp), bool)
    for x0, y, x1 in feet: foot |= (allp[:, 1] > y) & (allp[:, 0] > x0 - bh) & (allp[:, 0] < x1 + bh)
    if foot.any():  # split rows into the footnote part and the rest
        new = []
        for P in lines:
            f = np.zeros(len(P), bool)
            for x0, y, x1 in feet: f |= (P[:, 1] > y) & (P[:, 0] > x0 - bh) & (P[:, 0] < x1 + bh)
            if f.any() and (~f).any(): new += [P[f], P[~f]]
            else: new.append(P)
        lines = sorted(new, key=lambda l: np.median(l[:, 1])); ys = [float(np.median(l[:, 1])) for l in lines]
        gaps = np.diff(ys); tags = ["main-text"] * len(lines)
    def under_rule(P):
        return any((np.median(P[:, 1]) > y) and x0 - bh < np.median(P[:, 0]) < x1 + bh for x0, y, x1 in feet)
    for i, l in enumerate(lines):
        h = float(np.median(l[:, 2])); w = l[:, 0].max() - l[:, 0].min()
        lm, rm = l[:, 0].min() - tx0, tx1 - l[:, 0].max()
        if under_rule(l): tags[i] = "footnote"
        elif h > 1.3 * bh and len(l) >= 3: tags[i] = "heading"
        elif w < 0.7 * tw and lm > 0.1 * tw and rm > 0.1 * tw and abs(lm - rm) < 0.08 * tw and len(l) >= 3: tags[i] = "heading"
    # a catch-word in mid-page (a short row alone on the far left) ends the main text; what follows is footnote
    for i in range(len(lines) // 3, len(lines) - 1):
        l = lines[i]
        if len(l) <= 8 and l[:, 0].max() - l[:, 0].min() < 0.15 * tw and l[:, 0].max() < tx0 + 0.3 * tw:
            tags[i] = "catch-word"
            for k in range(i + 1, len(lines)):
                if tags[k] == "main-text": tags[k] = "footnote"
            break
    # small print at the foot
    for i in range(len(lines) - 1, 0, -1):
        if tags[i] == "main-text" and float(np.median(lines[i][:, 2])) < 0.8 * bh and len(lines[i]) >= 8: tags[i] = "footnote"
        else: break
    # top line: running head (+ page number)
    top = 0
    if len(lines) > 2 and (gaps[0] > 1.25 * lead or float(np.median(lines[0][:, 2])) > 1.2 * bh or len(lines[0]) <= 4):
        l = lines[0][np.argsort(lines[0][:, 0])]
        cut = [0] + [k + 1 for k in range(len(l) - 1) if l[k + 1, 0] - l[k, 0] > 4 * bh] + [len(l)]
        for a, b in zip(cut, cut[1:]):
            seg = l[a:b]
            out.append(("page-number" if len(seg) <= 4 and len(cut) > 2 or len(l) <= 4 else "running-head", seg))
        top = 1
    # last body line: catch-word if short and on the left
    body = [i for i in range(top, len(lines)) if tags[i] != "footnote"]
    if body and "catch-word" not in tags:
        i = body[-1]; l = lines[i]
        if l[:, 0].max() - l[:, 0].min() < 0.25 * tw and l[:, 0].max() < tx0 + 0.5 * tw and len(l) <= 15: tags[i] = "catch-word"
    out += [(tags[i], lines[i]) for i in range(top, len(lines))]
    return out


def regions_xml(pieces, W, H, name):
    regs = []
    for k, (tag, P) in enumerate(pieces):
        x0, y0, x1, y1 = box_of(P)
        regs.append(f'<TextRegion id="r{k}" custom="structure {{type:{tag};}}"><Coords points="{x0},{y0} {x1},{y0} {x1},{y1} {x0},{y1}"/>'
                    f'<TextLine id="r{k}l"><Coords points="{x0},{y0} {x1},{y0} {x1},{y1} {x0},{y1}"/></TextLine></TextRegion>\n')
    return PAGE.format(img=name, W=W, H=H, regions="".join(regs))


def merge_main(pieces):
    """Consecutive main-text lines → one block per run (keeps the region view close to the RA's)."""
    out = []
    for tag, P in pieces:
        if out and tag == out[-1][0] and tag in ("main-text", "footnote"): out[-1] = (tag, np.vstack([out[-1][1], P]))
        else: out.append((tag, P))
    return out


def label(suffix):
    for r in csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t"):
        n = f"{int(r['pageNr']):04d}"; f = HERE / "xml" / r["docId"] / f"{n}.{suffix}.xml"
        if not f.exists(): continue
        try: polys, W, H = line_polys(f)
        except Exception: continue  # not written yet
        img = IMG / r["docId"] / f"{n}.jpg"
        L = letters(img, W, H); a = assign(polys, L, W, H)
        lines = [L[a == i] for i in range(len(polys)) if (a == i).sum() >= 1]
        pieces = label_lines(lines, L, W, H, RULES.get(str(img), ()))
        pieces.sort(key=lambda t: np.median(t[1][:, 1]))
        (f.parent / f"{n}.{suffix}rules.xml").write_text(regions_xml(merge_main(pieces), W, H, img.name))
    print("labelled", suffix)


def combine_page(regs, polys, rules, W, H):
    """Regions [(tag, x0, y0, x1, y1)] + line polygons → [(tag, box, [polygons])]. A main-text region under a
    printed rule or under the catch-word becomes footnote; a line whose centre is in no region gets a main-text
    region of its own (so no text is dropped; the checks flag it)."""
    regs = [list(x) for x in regs]
    cw = [x[2] for x in regs if x[0] == "catch-word"]
    mains = [x for x in regs if x[0] == "main-text"]
    for x in mains:
        above = [m for m in mains if m is not x and m[4] <= x[2] + 0.02 * H]
        if not above: continue
        between = lambda y: max(m[4] for m in above) - 0.02 * H < y < x[2] + 0.01 * H
        under_rule = any(between(y) and min(x1, x[3]) - max(x0, x[1]) > 0.2 * (x[3] - x[1]) for x0, y, x1 in rules)
        if under_rule or (cw and x[2] > min(cw) - 0.005 * H): x[0] = "footnote"
    out = [(tag, (x0, y0, x1, y1), []) for tag, x0, y0, x1, y1 in regs]
    area = lambda b: (b[2] - b[0]) * (b[3] - b[1])
    for p, bl in polys:  # bl: baseline points or anything else (kept alongside the polygon)
        cx, cy = p[:, 0].mean(), p[:, 1].mean()
        hold = [o for o in out if o[1][0] <= cx <= o[1][2] and o[1][1] <= cy <= o[1][3]]
        if hold: min(hold, key=lambda o: area(o[1]))[2].append((p, bl))
        else: out.append(("main-text", (int(p[:, 0].min()), int(p[:, 1].min()), int(p[:, 0].max()), int(p[:, 1].max())), [(p, bl)]))
    return out


def order_boxes(boxes, ov=0.15, hr=1.2, tall=0):
    """Reading order of boxes (x0, y0, x1, y1) on a Hebrew page; returns their indexes. A box that spans the gap
    between two boxes lying side by side (a full-width heading over two columns) starts a band of its own; within
    a band the columns are read right to left, each top to bottom. Pieces of one cut line are side by side too,
    so the same rule reads them right to left. With `tall`, only boxes at least that tall count as lying side by
    side (columns), so pieces of one line that a detector boxed separately do not cut a column into bands."""
    def run(ix):
        if len(ix) <= 1: return list(ix)
        b = {i: boxes[i] for i in ix}
        # side by side: overlapping across by less than `ov` of the narrower box (detected boxes overlap a little)
        apart = lambda i, j: min(b[i][2], b[j][2]) - max(b[i][0], b[j][0]) < ov * min(b[i][2] - b[i][0], b[j][2] - b[j][0])
        over = lambda i, j: not apart(i, j)
        level = lambda i, j: min(b[i][3], b[j][3]) > max(b[i][1], b[j][1])  # share some height
        ht = lambda i: b[i][3] - b[i][1]
        # a heading over two columns is not taller than they are; a column under two pieces of a running head is
        wide = [i for i in ix if any(apart(j, k) and level(j, k) and min(ht(j), ht(k)) >= tall and over(i, j) and over(i, k) and ht(i) <= hr * max(ht(j), ht(k))
                                     for j in ix for k in ix if i not in (j, k) and j < k)]
        if wide:  # bands: each wide box alone, the boxes between two wide boxes together
            out, rest = [], [i for i in ix if i not in wide]
            for w in sorted(wide, key=lambda i: b[i][1]):
                cy = (b[w][1] + b[w][3]) / 2
                above = [i for i in rest if (b[i][1] + b[i][3]) / 2 < cy]
                out += run(above) + [w]; rest = [i for i in rest if i not in above]
            return out + run(rest)
        # columns: split where no box crosses, right to left
        cols, cur, edge = [], [], None
        for i in sorted(ix, key=lambda i: -b[i][2]):
            if cur and b[i][2] - edge < ov * (b[i][2] - b[i][0]): cols.append(cur); cur = []
            cur.append(i); edge = b[i][0] if edge is None or len(cur) == 1 else min(edge, b[i][0])
        cols.append(cur)
        if len(cols) > 1: return [i for c in cols for i in run(c)]
        out = sorted(ix, key=lambda i: (b[i][1] + b[i][3]) / 2)
        for _ in range(len(out)):  # boxes on one row: right to left
            for k in range(len(out) - 1):
                i, j = out[k], out[k + 1]
                if b[j][0] >= b[i][2] - 0.15 * (b[i][2] - b[i][0]) and min(b[i][3], b[j][3]) - max(b[i][1], b[j][1]) > 0.5 * min(ht(i), ht(j)):
                    out[k], out[k + 1] = j, i
        return out
    return run(list(range(len(boxes))))


def reading_order(regions, H, ov=0.15, hr=1.2):
    """Regions [(tag, box, lines)] in the RA's order: page number, then running heads right to left; then text and
    headings, column by column; a catch-word printed above the footnotes ends the column it stands under (on two
    columns each column has its own); then the footnotes; a catch-word below them comes last. Lines inside each
    region are ordered the same way."""
    lbox = lambda p: (p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max())
    regions = [(t, b, [ls[i] for i in order_boxes([lbox(np.asarray(p)) for p, _ in ls], ov, hr)]) for t, b, ls in regions]
    top = [r for r in regions if r[0] in ("running-head", "page-number") and r[1][3] < H / 2]
    notes = [r for r in regions if r[0] == "footnote"]
    # the first footnote line, not the footnote box: boxes often reach up past the catch-word
    note_top = min([np.asarray(p)[:, 1].mean() for r in notes for p, _ in r[2]] or [min([r[1][1] for r in notes] or [H])])
    cw_low = [r for r in regions if r[0] == "catch-word" and (r[1][1] + r[1][3]) / 2 > note_top]
    low_furniture = [r for r in regions if r[0] in ("running-head", "page-number") and r not in top]
    body = [r for r in regions if r not in top and r not in notes and r not in cw_low and r not in low_furniture]
    # order regions by where their lines are, not by their boxes: detected boxes nest (a page-size box around two
    # column boxes holds only the lines no smaller box holds)
    def where(r):
        if not r[2]: return r[1]
        q = np.vstack([np.asarray(p) for p, _ in r[2]]); return (q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max())
    lh = float(np.median([np.ptp(np.asarray(p)[:, 1]) for r in regions for p, _ in r[2]] or [H / 50]))
    pick = lambda rs: [rs[i] for i in order_boxes([where(r) for r in rs], ov, hr, tall=2.5 * lh)]
    top = sorted(top, key=lambda r: (r[0] != "page-number", -r[1][2]))
    return top + pick(body) + pick(notes) + cw_low + low_furniture


def tidy(regions, L, H):
    """Post-correction of regions [(tag, box, lines)] before they are written:
    - each box is fitted to its lines (detected boxes cut off line ends or reach into the next block);
    - boxes of the same tag that still overlap are merged (splitting main text changes nothing in the TEI);
    - main-text boxes directly above one another in a column, nothing between, are merged;
    - boxes that only touch, one above the other, meet halfway;
    - marks on the running-head row that no box holds: up to three letters become the page number (the detector
      misses some); a longer word level with the running head joins it."""
    from layout_qa import overlap
    fit = lambda ls: tuple(np.vstack([np.asarray(p) for p, _ in ls]).min(0)) + tuple(np.vstack([np.asarray(p) for p, _ in ls]).max(0))
    out = [[t, fit(ls) if ls else b, list(ls)] for t, b, ls in regions]
    merged = True
    while merged:
        merged = False
        for i, a in enumerate(out):
            for c in out[i + 1:]:
                if a[0] == c[0] and overlap(a[1], c[1]) > 0.15:
                    a[1] = (min(a[1][0], c[1][0]), min(a[1][1], c[1][1]), max(a[1][2], c[1][2]), max(a[1][3], c[1][3])); a[2] += c[2]
                    out.remove(c); merged = True; break
            if merged: break
    # main-text boxes directly one above the other in the same column, with nothing between, become one box
    lh = float(np.median([np.ptp(np.asarray(q)[:, 1]) for _, _, ls in out for q, _ in ls] or [H / 50]))
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
    # boxes that only touch, one above the other (fitted outlines reach a little above and below the letters): meet halfway
    for a in out:
        for c in out:
            if a is c or not (a[1][1] < c[1][1] < a[1][3] < c[1][3]): continue
            if min(a[1][2], c[1][2]) <= max(a[1][0], c[1][0]) or a[1][3] - c[1][1] > 0.5 * min(a[1][3] - a[1][1], c[1][3] - c[1][1]): continue
            m = (a[1][3] + c[1][1]) / 2; a[1] = (a[1][0], a[1][1], a[1][2], m); c[1] = (c[1][0], m, c[1][2], c[1][3])
    if L is not None and len(L):
        h = float(np.median(L[:, 2])); held = np.zeros(len(L), bool)
        for _, b, _ in out: held |= (L[:, 0] >= b[0] - h) & (L[:, 0] <= b[2] + h) & (L[:, 1] >= b[1] - h) & (L[:, 1] <= b[3] + h)
        tops = [b[1] for t, b, _ in out if t in ("main-text", "heading")]
        band = (L[:, 1] < min(tops or [0.15 * H])) & (L[:, 1] < 0.15 * H) & (L[:, 2] > 0.6 * h) & ~held
        P = L[band][np.argsort(L[band][:, 0])]
        groups = np.split(P, [k + 1 for k in range(len(P) - 1) if P[k + 1, 0] - P[k, 0] > 3 * h]) if len(P) else []
        heads = [r for r in out if r[0] == "running-head"]
        for g in groups:
            x0, x1 = g[:, 0].min() - 0.6 * h, g[:, 0].max() + 0.6 * h; y1 = (g[:, 1] + 0.5 * g[:, 2]).max(); y0 = (g[:, 1] - 0.5 * g[:, 2]).min()
            bl = np.array([[x0, y1], [x1, y1]]).astype(int); poly = np.array([[x0, y0], [x1, y0], [x1, y1 + 0.2 * h], [x0, y1 + 0.2 * h]]).astype(int)
            box = (int(x0), int(y0), int(x1), int(y1 + 0.2 * h))
            level = [r for r in heads if min(r[1][3], box[3]) - max(r[1][1], box[1]) > 0.3 * (box[3] - box[1])]
            if len(g) >= 4 and level:  # a word of the running head set apart from the rest
                r = level[0]; r[1] = (min(r[1][0], box[0]), min(r[1][1], box[1]), max(r[1][2], box[2]), max(r[1][3], box[3])); r[2].append((poly, bl))
            elif len(g) <= 3 and not any(t == "page-number" for t, _, _ in out):  # a page number is at most three letters
                out.append(["page-number", box, [(poly, bl)]])
    return [tuple(r) for r in out]


def page_xml(regions, W, H, name):
    xml = []
    for k, (tag, (x0, y0, x1, y1), ls) in enumerate(reading_order(regions, H)):
        pts = lambda q: " ".join(f"{int(a)},{int(b)}" for a, b in q)
        lx = "".join(f'<TextLine id="r{k}l{j}" custom="readingOrder {{index:{j};}}"><Coords points="{pts(p)}"/>'
                     + (f'<Baseline points="{pts(bl)}"/>' if isinstance(bl, np.ndarray) and len(bl) >= 2 else "") + "</TextLine>"
                     for j, (p, bl) in enumerate(ls))
        xml.append(f'<TextRegion id="r{k}" custom="readingOrder {{index:{k};}} structure {{type:{tag};}}"><Coords points="{int(x0)},{int(y0)} {int(x1)},{int(y0)} {int(x1)},{int(y1)} {int(x0)},{int(y1)}"/>{lx}</TextRegion>\n')
    return PAGE.format(img=name, W=W, H=H, regions="".join(xml))


def combine(reg, lin):
    """Test set: lines from LIN placed in regions from REG → .<reg>+<lin>.xml"""
    for r in csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t"):
        n = f"{int(r['pageNr']):04d}"; d = HERE / "xml" / r["docId"]
        if not (d / f"{n}.{reg}.xml").exists() or not (d / f"{n}.{lin}.xml").exists(): continue
        regs, W, H = yolo_regions(d / f"{n}.{reg}.xml")
        polys, _, _ = line_polys(d / f"{n}.{lin}.xml")
        img = IMG / r["docId"] / f"{n}.jpg"; letters(img, W, H)
        (d / f"{n}.{reg}+{lin}.xml").write_text(page_xml(combine_page(regs, polys, RULES.get(str(img), ()), W, H), W, H, img.name))
    print("combined", reg, lin)


if __name__ == "__main__":
    if sys.argv[1] == "label": label(sys.argv[2])
    else: combine(sys.argv[2], sys.argv[3])
