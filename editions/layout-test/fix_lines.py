"""Automatic post-correction of detected lines (Kraken):
- cut a line where it crosses from one region (field) into another, e.g. across a column gutter (Kraken runs
  lines across columns). Wide spaces alone are not used: they also occur inside ordinary lines;
- extend a line's ends over letters that sit on the same baseline just beyond them;
- join pieces Kraken left of one line: same region, same baseline, nothing between them, and the gap is not a
  column gutter (a gutter is a gap that the lines above and below share).
New lines keep Kraken's baseline points (a curved or sloping line stays curved) and get an outline along it.

- add a line for a row of letters that no line holds (Kraken now and then skips a line).

    python fix_lines.py SUFFIX REGIONS [--no-extend] [--join] [--refill]   lines from .<suffix>.xml cut on the
                          regions of .<REGIONS>.xml → .<suffix>fix-<REGIONS>[-noext][-join][-refill].xml
    fix_page(lines, L) is used by run_layout.py.
"""
import csv, sys
from pathlib import Path
import numpy as np
from layout_qa import letters
from line_score import line_polys, assign_baseline
from yolo_regions import PAGE

HERE = Path(__file__).parent
IMG = Path.home() / "Documents/Hasidigital-data/layout-test"
REACH = 1.5  # extend over letters up to this many letter heights beyond an end


def piece(bl, x0, x1):
    """Kraken's baseline between x0 and x1, keeping its inner points."""
    y = lambda x: float(np.interp(x, bl[:, 0], bl[:, 1]))
    mid = [p for p in bl.tolist() if x0 < p[0] < x1]
    return np.array([[x0, y(x0)]] + mid + [[x1, y(x1)]]).astype(int)


def outline(b, h):
    up, dn = 1.6 * h, 0.5 * h
    return np.vstack([b + [0, -up], (b + [0, dn])[::-1]]).astype(int)


def join(pieces, L, h):
    """pieces: [(baseline, region)]. Joins neighbours on one baseline within a region unless the gap is a gutter
    (joining across regions too merged columns back: 11% of lines wrong instead of 4%)."""
    pieces = sorted(pieces, key=lambda p: p[0][:, 0].min())
    out = []
    for b, k in pieces:
        for m, (b2, k2) in enumerate(out):
            if k2 != k or k < 0 or b2[:, 0].max() > b[:, 0].min(): continue
            gx0, gx1 = b2[:, 0].max(), b[:, 0].min(); yb = float(b2[-1, 1])
            if abs(b[0, 1] - yb) > 0.5 * h: continue
            # anything else on this row between them? then they are not neighbours
            if any(o is not b2 and o[:, 0].min() < gx1 and o[:, 0].max() > gx0 and abs(np.interp((gx0 + gx1) / 2, o[:, 0], o[:, 1]) - yb) < 0.5 * h
                   for o, _ in out): continue
            # gutter: the lines above and below near this gap mostly stop there too (in two columns every line has a
            # partner across the gutter), while in one column they run straight through it
            near = [o for o, _ in pieces if o is not b and o is not b2 and 0.5 * h < abs(np.median(o[:, 1]) - yb) < 10 * h
                    and o[:, 0].min() < gx1 + 4 * h and o[:, 0].max() > gx0 - 4 * h]
            through = [o[:, 0].min() < gx0 + 0.3 * h and o[:, 0].max() > gx1 - 0.3 * h for o in near]
            if gx1 - gx0 > 1.0 * h and (not near or np.mean(through) < 0.5): continue
            out[m] = (np.vstack([b2, b]), k); break
        else:
            out.append((b, k))
    return out


def bottoms(P):
    return P[:, 1] + 0.4 * P[:, 2]  # where a letter's baseline runs


def fit(P, h):
    """A baseline through letters: medians of their bottoms in bins about 8 letters wide."""
    P = P[np.argsort(P[:, 0])]; edges = np.linspace(P[0, 0], P[-1, 0], max(2, int((P[-1, 0] - P[0, 0]) / (8 * h)) + 1) + 1)
    pts = [[(a + b) / 2, np.median(bottoms(P[(P[:, 0] >= a) & (P[:, 0] <= b)]))] for a, b in zip(edges[:-1], edges[1:]) if ((P[:, 0] >= a) & (P[:, 0] <= b)).any()]
    pts = np.array(pts)
    if len(pts) == 1: pts = np.array([[P[0, 0], pts[0, 1]], [P[-1, 0], pts[0, 1]]])
    x0, x1 = P[0, 0] - 0.6 * h, P[-1, 0] + 0.6 * h
    return piece(pts, x0, x1) if len(pts) > 1 else None


def refill(bls, L, h, size=(0.4, 4.0)):
    """New baselines for rows of letters that no baseline holds. Kraken now and then skips a line; the gap it
    leaves is a line's height with letters in it. Returns the new baselines only."""
    a = assign_baseline([(None, None, b) for b in bls], L); out = []
    O = L[(a < 0) & (L[:, 2] > size[0] * h) & (L[:, 2] < size[1] * h)]
    if len(O) < 5: return out
    O = O[np.argsort(bottoms(O))]; rows, cur = [], [O[0]]
    for q in O[1:]:
        if bottoms(q[None])[0] - bottoms(np.array(cur)).mean() < 0.5 * h: cur.append(q)
        else: rows.append(np.array(cur)); cur = [q]
    rows.append(np.array(cur))
    for R in rows:
        R = R[np.argsort(R[:, 0])]
        for seg in np.split(R, [k + 1 for k in range(len(R) - 1) if R[k + 1, 0] - R[k, 0] > 3 * h]):
            if len(seg) >= 5 and seg[-1, 0] - seg[0, 0] > 4 * h:
                b = fit(seg, h)
                if b is not None: out.append(b)
    return out


def fix_page(lines, L, boxes=(), extend=True, joined=False, refilled=False):
    """lines: [(polygon, tag, baseline)]; L: letters; boxes: region boxes (x0, y0, x1, y1).
    Returns [(polygon, baseline)]."""
    def region_of(P):
        r = np.full(len(P), -1)
        for k, b in sorted(enumerate(boxes), key=lambda kb: -(kb[1][2] - kb[1][0]) * (kb[1][3] - kb[1][1])):
            r[(P[:, 0] >= b[0]) & (P[:, 0] <= b[2]) & (P[:, 1] >= b[1]) & (P[:, 1] <= b[3])] = k  # smallest box wins
        return r
    a = assign_baseline(lines, L); out = []
    taken = a >= 0
    for i, (poly, _, bl) in enumerate(lines):
        if bl is None or len(bl) < 2: continue
        bl = bl[np.argsort(bl[:, 0])]
        P = L[a == i]
        if len(P) < 3: out.append((bl, -1, float(np.median(L[:, 2])))); continue
        h = float(np.median(P[:, 2]))
        P = P[np.argsort(P[:, 0])]
        reg = region_of(P)
        cuts = [k + 1 for k in range(len(P) - 1) if reg[k] != reg[k + 1] and reg[k] >= 0 and reg[k + 1] >= 0]
        for seg in np.split(P, cuts):
            if len(seg) == 0: continue
            x0, x1 = seg[0, 0] - 0.6 * h, seg[-1, 0] + 0.6 * h
            y = lambda x: float(np.interp(x, bl[:, 0], bl[:, 1]))
            # extend over unassigned letters on this baseline just past either end
            for side in ((-1, 1) if extend else ()):
                while True:
                    edge = x0 if side < 0 else x1
                    cand = (~taken) & (np.abs(L[:, 0] - edge) < REACH * h) & ((L[:, 0] < edge) if side < 0 else (L[:, 0] > edge))
                    cand &= np.abs(y(edge) - (L[:, 1] + 0.4 * L[:, 2])) < 0.6 * h
                    if not cand.any(): break
                    xs = L[cand, 0]; taken |= cand
                    if side < 0: x0 = xs.min() - 0.6 * h
                    else: x1 = xs.max() + 0.6 * h
            out.append((piece(bl, x0, x1), int(np.bincount(region_of(seg) + 1).argmax()) - 1, h))
    hh = float(np.median(L[:, 2]))
    if refilled:  # new lines for skipped rows first, so that a piece of a line can then be joined to the rest of it
        new = refill([b for b, _, _ in out], L, hh)
        out += [(b, int(region_of(np.array([[b[:, 0].mean(), b[:, 1].mean() - 0.5 * hh]]))[0]), hh) for b in new]
    if joined:
        out = [(b, k, hh) for b, k in join([(b, k) for b, k, _ in out if b is not None], L, hh)] + [o for o in out if o[0] is None]
    return [(outline(b, h), b) if b is not None and len(b) > 1 and b.ndim == 2 else (None, b) for b, k, h in out]


def write(lines, W, H, name):
    pts = lambda p: " ".join(f"{int(x)},{int(y)}" for x, y in p)
    tl = "".join(f'<TextLine id="l{i}"><Coords points="{pts(p)}"/>' + (f'<Baseline points="{pts(b)}"/>' if b is not None else "") + "</TextLine>"
                 for i, (p, b) in enumerate(lines))
    return PAGE.format(img=name, W=W, H=H, regions=f'<TextRegion id="r0" custom="structure {{type:main-text;}}"><Coords points="0,0 {W},0 {W},{H} 0,{H}"/>{tl}</TextRegion>\n')


if __name__ == "__main__":
    s, rg = sys.argv[1], sys.argv[2]; ext = "--no-extend" not in sys.argv; jn = "--join" in sys.argv; rf = "--refill" in sys.argv
    from layout_qa import read_layout
    for r in csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t"):
        n = f"{int(r['pageNr']):04d}"; f = HERE / "xml" / r["docId"] / f"{n}.{s}.xml"
        if not f.exists(): continue
        g = f.parent / f"{n}.{rg}.xml"
        if not g.exists(): continue
        lines, W, H = line_polys(f, True); img = IMG / r["docId"] / f"{n}.jpg"
        boxes = [x["box"] for x in read_layout(g)[0]]
        out = f.parent / f"{n}.{s}fix-{rg}{'' if ext else '-noext'}{'-join' if jn else ''}{'-refill' if rf else ''}.xml"
        out.write_text(write(fix_page(lines, letters(img, W, H), boxes, ext, jn, rf), W, H, img.name))
    print("fixed", s, "on", rg)
