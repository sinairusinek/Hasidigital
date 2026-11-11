"""Score a layout the way the TEI sees it: every letter on the page gets the tag of the box it sits in
('outside' if none). A page has a consequential error when at least MIN_LETTERS letters get a different tag
than in FINAL. Splitting or merging main-text blocks changes nothing here, so it is not counted.

    python ink_score.py SUFFIX     → ink-<suffix>.tsv and totals
"""
import csv, sys, collections
from pathlib import Path
import numpy as np
from layout_qa import read_layout, letters, clean, inside

HERE = Path(__file__).parent
IMG = Path.home() / "Documents/Hasidigital-data/layout-test"
MIN_LETTERS = 10
# tags the TEI treats alike: a continued footnote is a footnote; 'none'/'paragraph'/'text' are untagged text
SAME = {"footnote-continued": "footnote", "paragraph": "main-text", "text": "main-text", "none": "main-text"}


def tag_letters(regs, L):
    """Tag of the smallest box holding each letter."""
    tags = np.array(["outside"] * len(L), dtype=object); area = np.full(len(L), np.inf)
    for r in regs:
        b = r["box"]; a = (b[2] - b[0]) * (b[3] - b[1]); m = inside(L, b) & (a < area)
        tags[m] = SAME.get(r["lab"], r["lab"]); area[m] = a
    return tags


def score_page(auto_regs, final_regs, L):
    fin = tag_letters(final_regs, L); aut = tag_letters(auto_regs, L)
    keep = fin != "outside"  # letters the RA left outside every box are noise (stamps, shelf marks)
    errs = collections.Counter(f"{f}→{a}" for f, a in zip(fin[keep], aut[keep]) if f != a)
    return int(keep.sum()), errs


def main():
    suffix = sys.argv[1]
    rows = []
    for t in csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t"):
        d = HERE / "xml" / t["docId"]; n = f"{int(t['pageNr']):04d}"
        if not (d / f"{n}.{suffix}.xml").exists() or not (d / f"{n}.final.xml").exists(): continue
        ar, W, H = read_layout(d / f"{n}.{suffix}.xml"); fr, _, _ = read_layout(d / f"{n}.final.xml")
        L = letters(IMG / t["docId"] / f"{n}.jpg", W, H)
        ar, _ = clean(ar, L)
        total, errs = score_page(ar, fr, L)
        bad = sum(errs.values())
        rows.append(dict(set=t["set"], docId=t["docId"], pageNr=t["pageNr"], letters=total, wrong=bad,
                         error=int(bad >= MIN_LETTERS), kinds="; ".join(f"{k} {v}" for k, v in errs.most_common() if v >= 3)))
    w = csv.DictWriter(open(HERE / f"ink-{suffix}.tsv", "w"), rows[0].keys(), delimiter="\t"); w.writeheader(); w.writerows(rows)
    e = sum(r["error"] for r in rows)
    print(f"{suffix}: {len(rows)} pages; pages with a consequential error {e} ({e/len(rows):.0%}); "
          f"letters wrongly tagged {sum(r['wrong'] for r in rows)}/{sum(r['letters'] for r in rows)} "
          f"({sum(r['wrong'] for r in rows)/max(1,sum(r['letters'] for r in rows)):.2%})")
    kinds = collections.Counter()
    for r in rows:
        for k in r["kinds"].split("; "):
            if k: kinds[k.rsplit(" ", 1)[0]] += int(k.rsplit(" ", 1)[1])
    print("  letters by kind:", kinds.most_common(10))


if __name__ == "__main__":
    main()
