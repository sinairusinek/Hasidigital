"""Automatic post-correction of detected lines (Kraken):
- cut a line where it crosses from one region (field) into another, e.g. across a column gutter (Kraken runs
  lines across columns). Wide spaces alone are not used: they also occur inside ordinary lines;
- extend a line's ends over letters that sit on the same baseline just beyond them.
New lines get a baseline piece and an outline built around it.

    python fix_lines.py SUFFIX REGIONS [--no-extend]   lines from .<suffix>.xml cut on the regions of .<REGIONS>.xml
                                                      → .<suffix>fix-<REGIONS>.xml (test set)
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


def fix_page(lines, L, boxes=(), extend=True):
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
        if bl is None or len(bl) < 2: out.append((poly, bl)); continue
        bl = bl[np.argsort(bl[:, 0])]
        P = L[a == i]
        if len(P) < 3: out.append((poly, bl)); continue
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
            nb = np.array([[x0, y(x0)], [x1, y(x1)]]).astype(int)
            up, dn = 1.6 * h, 0.5 * h
            pg = np.array([[x0, y(x0) - up], [x1, y(x1) - up], [x1, y(x1) + dn], [x0, y(x0) + dn]]).astype(int)
            out.append((pg, nb))
    return out


def write(lines, W, H, name):
    pts = lambda p: " ".join(f"{int(x)},{int(y)}" for x, y in p)
    tl = "".join(f'<TextLine id="l{i}"><Coords points="{pts(p)}"/>' + (f'<Baseline points="{pts(b)}"/>' if b is not None else "") + "</TextLine>"
                 for i, (p, b) in enumerate(lines))
    return PAGE.format(img=name, W=W, H=H, regions=f'<TextRegion id="r0" custom="structure {{type:main-text;}}"><Coords points="0,0 {W},0 {W},{H} 0,{H}"/>{tl}</TextRegion>\n')


if __name__ == "__main__":
    s, rg = sys.argv[1], sys.argv[2]; ext = "--no-extend" not in sys.argv
    from layout_qa import read_layout
    for r in csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t"):
        n = f"{int(r['pageNr']):04d}"; f = HERE / "xml" / r["docId"] / f"{n}.{s}.xml"
        if not f.exists(): continue
        g = f.parent / f"{n}.{rg}.xml"
        if not g.exists(): continue
        lines, W, H = line_polys(f, True); img = IMG / r["docId"] / f"{n}.jpg"
        boxes = [x["box"] for x in read_layout(g)[0]]
        out = f.parent / f"{n}.{s}fix-{rg}{'' if ext else '-noext'}.xml"
        out.write_text(write(fix_page(lines, letters(img, W, H), boxes, ext), W, H, img.name))
    print("fixed", s, "on", rg)
