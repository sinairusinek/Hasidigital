"""Baseline to beat: how much the RA changed the Transkribus output on the test set.

Regions: last Field Recognition 313993 version (.fr) against FINAL. A region is kept if a FINAL region overlaps
it with IoU >= 0.5; then it is relabelled if the tag differs, and redrawn if IoU < 0.9. A deleted region that
touches no FINAL region is "stray" (a box on empty paper); one that does is a split or merge.
Lines: last LA 51962 version (.la) against FINAL, matched by line id (a kept line keeps its id; box overlap is
too strict for thin line boxes whose outline the RA nudged).
Writes baseline-pages.tsv (per page) and prints the totals.
"""
import csv, re, collections
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).parent

def page(f):
    root = ET.parse(f).getroot(); ns = root.tag.split("}")[0][1:]; q = lambda t: f"{{{ns}}}{t}"
    def box(el):
        c = el.find(q("Coords"))
        if c is None or not c.get("points"): return None
        pts = [tuple(map(int, xy.split(","))) for xy in c.get("points").split()]
        return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
    regs, lines = [], []
    for r in root.iter(q("TextRegion")):
        m = re.search(r"type:([\w-]+)", r.get("custom", ""))
        b = box(r)
        if b: regs.append((m.group(1) if m else "none", b))
        lines += [b for b in map(box, r.iter(q("TextLine"))) if b]
    return regs, lines

def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy; u = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - i
    return i / u if u else 0

def match(auto, final):
    """Greedy best-IoU matching; returns pairs (i, j, iou) and the unmatched indices on both sides."""
    cand = sorted(((iou(a, b), i, j) for i, a in enumerate(auto) for j, b in enumerate(final)), reverse=True)
    ua, uf, pairs = set(), set(), []
    for s, i, j in cand:
        if s < 0.5: break
        if i in ua or j in uf: continue
        ua.add(i); uf.add(j); pairs.append((i, j, s))
    return pairs, [i for i in range(len(auto)) if i not in ua], [j for j in range(len(final)) if j not in uf]

def line_ids(f):
    return set(re.findall(r'<TextLine id="([^"]+)"', Path(f).read_text()))

def main():
    rows = []
    for t in csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t"):
        d = HERE / "xml" / t["docId"]; n = f"{int(t['pageNr']):04d}"
        fin = d / f"{n}.final.xml"
        if not fin.exists(): continue
        fr, fl = page(fin)
        row = dict(set=t["set"], docId=t["docId"], pageNr=t["pageNr"], final_regions=len(fr), final_lines=len(fl))
        if (d / f"{n}.fr.xml").exists():
            ar, _ = page(d / f"{n}.fr.xml")
            pairs, da, af = match([b for _, b in ar], [b for _, b in fr])
            stray = sum(1 for i in da if not any(iou(ar[i][1], b) > 0 for _, b in fr))
            row.update(fr_regions=len(ar), relabelled=sum(ar[i][0] != fr[j][0] for i, j, _ in pairs),
                       redrawn=sum(s < 0.9 for *_, s in pairs), deleted_stray=stray, deleted_split=len(da) - stray, added=len(af))
            row["region_fix"] = ("none" if not (row["relabelled"] or row["deleted_split"] or row["added"] or stray)
                                 else "stray only" if not (row["relabelled"] or row["deleted_split"] or row["added"]) else "real")
        if (d / f"{n}.la.xml").exists():
            ida, idf = line_ids(d / f"{n}.la.xml"), line_ids(fin)
            row.update(la_lines=len(ida), lines_kept=len(ida & idf), lines_deleted=len(ida - idf), lines_added=len(idf - ida),
                       line_change=round((len(ida - idf) + len(idf - ida)) / max(1, len(idf)), 3))
        rows.append(row)

    keys = list(dict.fromkeys(k for r in rows for k in r))
    w = csv.DictWriter(open(HERE / "baseline-pages.tsv", "w"), keys, delimiter="\t", restval=""); w.writeheader(); w.writerows(rows)

    A = [r for r in rows if "region_fix" in r]
    c = collections.Counter(r["region_fix"] for r in A)
    print(f"Regions, FR 313993 vs FINAL ({len(A)} pages): " + ", ".join(f"{k} {v} ({v/len(A):.0%})" for k, v in c.most_common()))
    for k in ("fr_regions", "relabelled", "redrawn", "deleted_stray", "deleted_split", "added"):
        print(f"  {k}: {sum(r[k] for r in A)}")
    L = [r for r in rows if "line_change" in r]
    if L:
        big = sum(r["line_change"] > 0.10 for r in L)
        print(f"Lines, LA 51962 vs FINAL ({len(L)} pages): lines {sum(r['la_lines'] for r in L)} auto / {sum(r['final_lines'] for r in L)} final; "
              f"deleted {sum(r['lines_deleted'] for r in L)}, added {sum(r['lines_added'] for r in L)}; pages with >10% lines changed: {big} ({big/len(L):.0%})")
    print("Per book (regions real-fix pages / pages):")
    for doc in dict.fromkeys(r["docId"] for r in A):
        xs = [r for r in A if r["docId"] == doc]
        print(f"  {doc}: {sum(r['region_fix']=='real' for r in xs)}/{len(xs)}")

if __name__ == "__main__":
    main()
