"""Can the reading repair badly cut lines? Splits are the commonest line error of our pipeline (a line cut in two
pieces, usually at a box border). Two ways to merge pieces back, scored like the other line methods:

    geometric: merge two pieces that sit on the same baseline with a gap under GAP letter heights;
    reading:   merge only a piece the model called "part of a line" with its nearest piece on the same baseline
               (gap under 3 letter heights).

    python line_merge.py MODEL PAGES.tsv   → .merge-geo.xml and .merge-<MODEL>.xml, then line_score on both
"""
import csv, sys, subprocess
from pathlib import Path
import numpy as np, cv2
from htr_test import our_lines, numbered_lines, OUT, HERE, IMG
from layout_qa import letters
from fix_lines import write

GAP = 1.0


def merge(lines, h, pick, gap):
    """Repeatedly join a piece chosen by pick(i) with its nearest neighbour on the same baseline."""
    ls = [dict(poly=l["poly"], bl=l["bl"], pick=pick(i)) for i, l in enumerate(lines)]
    while True:
        best = None
        for i, a in enumerate(ls):
            if not a["pick"]: continue
            for j, b in enumerate(ls):
                if i == j: continue
                ya, yb = np.median(a["bl"][:, 1]), np.median(b["bl"][:, 1])
                if abs(ya - yb) > 0.5 * h: continue
                g = max(b["bl"][:, 0].min() - a["bl"][:, 0].max(), a["bl"][:, 0].min() - b["bl"][:, 0].max())
                if g < gap * h and (best is None or g < best[0]): best = (g, i, j)
        if best is None: return [(l["poly"], l["bl"]) for l in ls]
        _, i, j = best; a, b = ls[i], ls[j]
        bl = np.vstack([a["bl"], b["bl"]]); bl = bl[np.argsort(bl[:, 0])]
        poly = cv2.convexHull(np.vstack([a["poly"], b["poly"]]).astype(np.int32))[:, 0]
        ls = [l for k, l in enumerate(ls) if k not in (i, j)] + [dict(poly=poly, bl=bl, pick=a["pick"] and b["pick"])]


def main():
    model, pages_f = sys.argv[1], sys.argv[2]
    pages = [(r["docId"], int(r["pageNr"])) for r in csv.DictReader(open(pages_f), delimiter="\t")]
    read = False
    for doc, n in pages:
        ls = our_lines(doc, n); img = IMG / doc / f"{n:04d}.jpg"
        im = cv2.imread(str(img)); H, W = im.shape[:2]; L = letters(img, W, H); h = float(np.median(L[:, 2]))
        d = HERE / "xml" / doc
        (d / f"{n:04d}.merge-geo.xml").write_text(write(merge(ls, h, lambda i: True, GAP), W, H, img.name))
        f = OUT / f"comb-{model}-{doc}_{n:04d}.txt"
        if f.exists():
            read = True
            said = numbered_lines(f.read_text(), "PROBLEMS")
            part = {i - 1 for i, v in said.items() if "part" in v}
            (d / f"{n:04d}.merge-{model}.xml").write_text(write(merge(ls, h, lambda i: i in part, 3.0), W, H, img.name))
    subprocess.run([sys.executable, "line_score.py", "merge-geo"] + ([f"merge-{model}"] if read else []))
    # the unmerged lines on the same pages, from the full-set table (re-scoring them here would overwrite it)
    keep = {(d, str(n)) for d, n in pages}
    xs = [r for r in csv.DictReader(open(HERE / "line-krakenfix-yolo-noext.tsv"), delimiter="\t") if (r["docId"], r["pageNr"]) in keep]
    w, t = sum(int(r["wrong"]) for r in xs), sum(int(r["lines"]) for r in xs)
    print(f"unmerged: {len(xs)} pages, body lines {t}, wrong {w} ({w/max(1,t):.1%}); pages with >10% lines wrong {sum(float(r['share']) > 0.10 for r in xs)}")


if __name__ == "__main__":
    main()
