"""Score detected text lines against FINAL, letter by letter.

Each letter on the page belongs to at most one FINAL line and one detected line: the line whose baseline runs
just under it (baselines are what HTR reads; line outlines differ by tool, and some older FINAL outlines sit
half a line off the print). A FINAL line is correct when one detected line holds at least 85% of its letters and at least 85%
of that detected line's letters belong to it (so splits, merges and misses all count as wrong).

    python line_score.py SUFFIX [SUFFIX ...]   → line-<suffix>.tsv; totals over the pages every suffix has
"""
import csv, sys, collections
from pathlib import Path
import numpy as np, cv2
import xml.etree.ElementTree as ET
from layout_qa import letters

HERE = Path(__file__).parent
IMG = Path.home() / "Documents/Hasidigital-data/layout-test"
OK = 0.85
FW = {"page-number", "running-head", "catch-word"}


def line_polys(f, baselines=False):
    """[(polygon points, region tag)] for every TextLine."""
    import re
    root = ET.parse(f).getroot(); ns = root.tag.split("}")[0][1:]; q = lambda t: f"{{{ns}}}{t}"
    pg = root.find(q("Page")); W, H = int(pg.get("imageWidth")), int(pg.get("imageHeight")); out = []
    for r in root.iter(q("TextRegion")):
        m = re.search(r"type:([\w-]+)", r.get("custom", "")); lab = m.group(1) if m else "none"
        for l in r.iter(q("TextLine")):
            c = l.find(q("Coords"))
            if c is None or not c.get("points"): continue
            pts = np.array([tuple(map(int, xy.split(","))) for xy in c.get("points").split()])
            if len(pts) < 3: continue
            b = l.find(q("Baseline"))
            bl = np.array([tuple(map(int, xy.split(","))) for xy in b.get("points").split()]) if b is not None and b.get("points") else None
            out.append((pts, lab, bl) if baselines else (pts, lab))
    return out, W, H


def assign(polys, L, W, H, s=0.25):
    """Index of the line holding each letter (-1 = none); later lines drawn over earlier ones."""
    mask = np.full((int(H * s) + 1, int(W * s) + 1), -1, np.int32)
    for i, (p, _) in enumerate(polys):
        cv2.fillPoly(mask, [(p * s).astype(np.int32)], int(i))
    x = np.clip((L[:, 0] * s).astype(int), 0, mask.shape[1] - 1); y = np.clip((L[:, 1] * s).astype(int), 0, mask.shape[0] - 1)
    return mask[y, x]


def assign_baseline(lines, L):
    """Index of the line whose baseline lies just under each letter (-1 = none)."""
    best = np.full(len(L), np.inf); idx = np.full(len(L), -1)
    for i, (_, _, bl) in enumerate(lines):
        if bl is None or len(bl) < 2: continue
        bl = bl[np.argsort(bl[:, 0])]
        inx = (L[:, 0] >= bl[0, 0] - 0.5 * L[:, 2]) & (L[:, 0] <= bl[-1, 0] + 0.5 * L[:, 2])
        d = np.interp(L[:, 0], bl[:, 0], bl[:, 1]) - L[:, 1]  # baseline below the letter centre: d > 0
        ok = inx & (d > -0.4 * L[:, 2]) & (d < 1.3 * L[:, 2]) & (np.abs(d) < best)
        best[ok] = np.abs(d[ok]); idx[ok] = i
    return idx


def score(final_f, det_f, img, body_only=True):
    fp, W, H = line_polys(final_f, True); dp, _, _ = line_polys(det_f, True)
    L = letters(img, W, H)
    fa, da = assign_baseline(fp, L), assign_baseline(dp, L)
    good = bad = 0
    for i, (_, lab, _) in enumerate(fp):
        if body_only and lab in FW: continue
        mine = da[fa == i]
        if len(mine) < 3: continue
        c = collections.Counter(mine.tolist()); j, n = c.most_common(1)[0]
        ok = j >= 0 and n / len(mine) >= OK and n / max(1, (da == j).sum()) >= OK
        good += ok; bad += not ok
    return good, bad


def main():
    suffixes = sys.argv[1:]
    pages = [r for r in csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t")
             if all((HERE / "xml" / r["docId"] / f"{int(r['pageNr']):04d}.{s}.xml").exists() for s in suffixes + ["final"])]
    for s in suffixes:
        rows = []
        for r in pages:
            n = f"{int(r['pageNr']):04d}"; d = HERE / "xml" / r["docId"]
            g, b = score(d / f"{n}.final.xml", d / f"{n}.{s}.xml", IMG / r["docId"] / f"{n}.jpg")
            rows.append(dict(set=r["set"], docId=r["docId"], pageNr=r["pageNr"], lines=g + b, wrong=b, share=round(b / max(1, g + b), 3)))
        w = csv.DictWriter(open(HERE / f"line-{s}.tsv", "w"), rows[0].keys(), delimiter="\t"); w.writeheader(); w.writerows(rows)
        tot = sum(r["lines"] for r in rows); wr = sum(r["wrong"] for r in rows); bigp = sum(r["share"] > 0.10 for r in rows)
        print(f"{s}: {len(rows)} pages, body lines {tot}, wrong {wr} ({wr/max(1,tot):.1%}); pages with >10% lines wrong {bigp} ({bigp/len(rows):.0%})")
        for st in sorted({r['set'] for r in rows}):
            xs = [r for r in rows if r["set"] == st]
            print(f"   set {st}: {len(xs)} pages, wrong {sum(r['wrong'] for r in xs)}/{sum(r['lines'] for r in xs)}, pages >10% {sum(r['share'] > 0.10 for r in xs)}")


if __name__ == "__main__":
    main()
