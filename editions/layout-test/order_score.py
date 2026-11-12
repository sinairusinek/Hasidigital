"""Reading order: how the RA ordered FINAL, and how well a layout's order matches it.

A layout's lines are matched to FINAL lines through the letters they hold (as in line_score.py). Walking the
layout's lines in its reading order gives a sequence of FINAL positions; lines that break the increasing run
(length minus the longest increasing subsequence) are out of order. A page has an order error when any main
text, heading or footnote line is out of order.

    python order_score.py conventions          how FINAL orders furniture, footnotes and columns
    python order_score.py SUFFIX [SUFFIX ...]   order errors per suffix, on the pages all of them have
    python order_score.py reorder SUFFIX        .<suffix>.xml put in our reading order (rules.reading_order) → .<suffix>+order.xml
    python order_score.py flags SUFFIX          order-doubt flags per page, scored against the order errors of SUFFIX

Order-doubt flags (headings and text only; running heads, page numbers and catch-words are not shown on the site):
- footnote above text: a footnote line stands higher than a main-text or heading line, so a tag is probably
  wrong and the text will be read in the wrong place;
- cut without a gap: a Kraken line was cut where it crosses a region border although the letters run on with no
  gap there, so the border probably runs through text (a column box drawn too long).
"""
import bisect, collections, csv, re, sys
from pathlib import Path
import numpy as np
from line_score import assign_baseline, HERE, IMG
from layout_qa import letters

FW = {"running-head", "page-number", "catch-word"}
SAME = {"footnote-continued": "footnote", "paragraph": "main-text", "text": "main-text"}


def ordered_lines(f):
    """[(tag, region box, baseline)] in the file's reading order (document order where none is given)."""
    x = Path(f).read_text(); regs = []
    for k, m in enumerate(re.finditer(r'<TextRegion\b([^>]*)>(.*?)</TextRegion>', x, re.S)):
        a, body = m.group(1), m.group(2)
        ro = re.search(r"readingOrder \{index:(\d+)", a); t = re.search(r"type:([\w-]+)", a)
        tag = SAME.get(t.group(1), t.group(1)) if t else "main-text"
        c = re.search(r'<Coords points="([^"]+)"', body)
        box = np.array([tuple(map(float, q.split(","))) for q in c.group(1).split()]) if c else None
        ls = []
        for j, l in enumerate(re.finditer(r'<TextLine\b([^>]*)>(.*?)</TextLine>', body, re.S)):
            b = re.search(r'<Baseline points="([^"]+)"', l.group(2))
            if b: p = np.array([tuple(map(float, q.split(","))) for q in b.group(1).split()])
            else:  # no baseline: our outlines reach 1.6 letter heights above it and 0.5 below
                c = re.search(r'<Coords points="([^"]+)"', l.group(2))
                if not c: continue
                o = np.array([tuple(map(float, q.split(","))) for q in c.group(1).split()]); y0, y1 = o[:, 1].min(), o[:, 1].max()
                p = np.array([[o[:, 0].min(), y1 - 0.5 / 2.1 * (y1 - y0)], [o[:, 0].max(), y1 - 0.5 / 2.1 * (y1 - y0)]])
            lro = re.search(r"readingOrder \{index:(\d+)", l.group(1))
            ls.append((int(lro.group(1)) if lro else j, p))
        regs.append((int(ro.group(1)) if ro else k, k, tag, box, sorted(ls, key=lambda z: z[0])))
    regs.sort(key=lambda r: (r[0], r[1]))
    return [(tag, box, p) for _, _, tag, box, ls in regs for _, p in ls]


def lis(seq):
    tails = []
    for v in seq:
        i = bisect.bisect_left(tails, v)
        tails[i:i + 1] = [v]
    return len(tails)


def page_order(final_f, auto_lines, L):
    fin = ordered_lines(final_f)
    fa = assign_baseline([(None, None, p) for _, _, p in fin], L)
    da = assign_baseline([(None, None, p) for _, _, p in auto_lines], L)
    seq = []
    for j in range(len(auto_lines)):
        m = fa[(da == j) & (fa >= 0)]
        if len(m) >= 3:
            i = int(np.bincount(m).argmax())
            if not seq or seq[-1][0] != i: seq.append((i, fin[i][0]))
    body = [i for i, t in seq if t not in FW]; allv = [i for i, _ in seq]
    return len(body) - lis(body), len(allv) - lis(allv), len(body)


def conventions():
    c = collections.Counter(); n = 0
    for r in csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t"):
        f = HERE / "xml" / r["docId"] / f"{int(r['pageNr']):04d}.final.xml"
        if not f.exists() or r["set"] == "B": continue
        ls = ordered_lines(f); tags = [t for t, _, _ in ls]; n += 1
        if not tags: continue
        first = tags[0]; c[f"first line: {first}"] += 1; c[f"last line: {tags[-1]}"] += 1
        if "catch-word" in tags:
            i = tags.index("catch-word"); after = set(tags[i + 1:])
            c["catch-word: " + ("last" if not after else "before " + "/".join(sorted(after)))] += 1
        if "footnote" in tags and "main-text" in tags:
            lf, lm = max(i for i, t in enumerate(tags) if t == "main-text"), min(i for i, t in enumerate(tags) if t == "footnote")
            c["footnotes " + ("after all main text" if lm > lf else "interleaved with main text")] += 1
        # two columns: main-text lines side by side; is the right one read first?
        mains = [(i, p) for i, (t, _, p) in enumerate(ls) if t == "main-text"]
        for (i, p), (j, q) in zip(mains, mains[1:]):
            if q[:, 0].max() < p[:, 0].min() and abs(np.median(q[:, 1]) - np.median(p[:, 1])) > 3 * 40:
                c["column jump right→left (upward)"] += 1
            if q[:, 0].min() > p[:, 0].max() and np.median(q[:, 1]) < np.median(p[:, 1]):
                c["column jump left→right (upward)"] += 1
    print(n, "pages"); [print(f"  {v:4d}  {k}") for k, v in sorted(c.items())]


def main(sufs):
    rows = [r for r in csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t") if r["set"] != "B"
            and all((HERE / "xml" / r["docId"] / f"{int(r['pageNr']):04d}.{s}.xml").exists() for s in sufs + ["final"])]
    tot = {s: collections.Counter() for s in sufs}; per = []
    for r in rows:
        d = HERE / "xml" / r["docId"]; n = f"{int(r['pageNr']):04d}"
        L = letters(IMG / r["docId"] / f"{n}.jpg", *size(d / f"{n}.final.xml"))
        row = dict(set=r["set"], docId=r["docId"], pageNr=r["pageNr"])
        for s in sufs:
            body, allv, nb = page_order(d / f"{n}.final.xml", ordered_lines(d / f"{n}.{s}.xml"), L)
            t = tot[s]; t["pages"] += 1; t["body lines"] += nb; t["body out"] += body; t["all out"] += allv
            t["pages body wrong"] += body > 0; t["pages any wrong"] += allv > 0; row[s] = body
        per.append(row)
    for s in sufs:
        t = tot[s]
        print(f"{s:42s} {t['pages']} pages: body order wrong on {t['pages body wrong']} pages "
              f"({t['body out']}/{t['body lines']} lines out of place); with furniture {t['pages any wrong']} pages")
    w = csv.DictWriter(open(HERE / "order-scores.tsv", "w"), per[0].keys(), delimiter="\t"); w.writeheader(); w.writerows(per)


def size(f):
    m = re.search(r'imageWidth="(\d+)" imageHeight="(\d+)"', Path(f).read_text()); return int(m.group(1)), int(m.group(2))


def reorder(suffix):
    from rules import page_xml
    for f in (HERE / "xml").glob(f"*/*.{suffix}.xml"):
        x = f.read_text(); W, H = size(f); regs = []
        for m in re.finditer(r'<TextRegion\b([^>]*)>(.*?)</TextRegion>', x, re.S):
            t = re.search(r"type:([\w-]+)", m.group(1)); c = re.search(r'<Coords points="([^"]+)"', m.group(2))
            q = np.array([tuple(map(float, z.split(","))) for z in c.group(1).split()])
            ls = []
            for l in re.finditer(r'<TextLine\b[^>]*>(.*?)</TextLine>', m.group(2), re.S):
                lc = re.search(r'<Coords points="([^"]+)"', l.group(1)); b = re.search(r'<Baseline points="([^"]+)"', l.group(1))
                arr = lambda g: np.array([tuple(map(float, z.split(","))) for z in g.split()]).astype(int)
                if lc: ls.append((arr(lc.group(1)), arr(b.group(1)) if b else None))
            regs.append((t.group(1) if t else "main-text", (q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()), ls))
        img = re.search(r'imageFilename="([^"]+)"', x).group(1)
        f.with_name(f.name.replace(f".{suffix}.xml", f".{suffix}+order.xml")).write_text(page_xml(regs, W, H, img))


def regions_of(f):
    x = Path(f).read_text(); regs = []
    for m in re.finditer(r'<TextRegion\b([^>]*)>(.*?)</TextRegion>', x, re.S):
        t = re.search(r"type:([\w-]+)", m.group(1)); c = re.search(r'<Coords points="([^"]+)"', m.group(2))
        q = np.array([tuple(map(float, z.split(","))) for z in c.group(1).split()])
        ls = [np.array([tuple(map(float, z.split(","))) for z in lc.split()]) for lc in re.findall(r'<TextLine\b[^>]*><Coords points="([^"]+)"', m.group(2))]
        regs.append((t.group(1) if t else "main-text", (q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()), [(l, None) for l in ls]))
    return regs


def note_above(regs, H):
    ys = lambda tags: [np.asarray(p)[:, 1].mean() for t, _, ls in regs if t in tags for p, _ in ls]
    fn, mt = ys(("footnote",)), ys(("main-text", "heading"))
    return bool(fn and mt and min(fn) < max(mt) - 0.03 * H)


def cuts_without_gap(lines, boxes, L):
    """Places where a line passes from one box into another with no gap between the letters on either side."""
    a = assign_baseline(lines, L); h = float(np.median(L[:, 2])); n = 0
    order = sorted(enumerate(boxes), key=lambda kb: -(kb[1][2] - kb[1][0]) * (kb[1][3] - kb[1][1]))
    for i in range(len(lines)):
        P = L[a == i]
        if len(P) < 6: continue
        P = P[np.argsort(P[:, 0])]; reg = np.full(len(P), -1)
        for k, b in order: reg[(P[:, 0] >= b[0]) & (P[:, 0] <= b[2]) & (P[:, 1] >= b[1]) & (P[:, 1] <= b[3])] = k
        gap = P[1:, 0] - P[:-1, 0] - 0.3 * (P[1:, 2] + P[:-1, 2])
        n += int(np.sum((reg[1:] != reg[:-1]) & (reg[1:] >= 0) & (reg[:-1] >= 0) & (gap < h)))
    return n


def flags(suffix):
    from line_score import line_polys
    from layout_qa import read_layout
    main([suffix]); err = {(r["docId"], r["pageNr"]): int(r[suffix]) for r in csv.DictReader(open(HERE / "order-scores.tsv"), delimiter="\t")}
    rows = []
    for (d, n), e in err.items():
        nn = f"{int(n):04d}"; x = HERE / "xml" / d; W, H = size(x / f"{nn}.{suffix}.xml")
        L = letters(IMG / d / f"{nn}.jpg", W, H)
        kl, _, _ = line_polys(x / f"{nn}.kraken.xml", True)
        cut = cuts_without_gap(kl, [r["box"] for r in read_layout(x / f"{nn}.yolo.xml")[0]], L)
        rows.append(dict(docId=d, pageNr=n, order_errors=e, footnote_above_text=int(note_above(regions_of(x / f"{nn}.{suffix}.xml"), H)), cuts_without_gap=cut))
    w = csv.DictWriter(open(HERE / f"order-flags-{suffix}.tsv", "w"), rows[0].keys(), delimiter="\t"); w.writeheader(); w.writerows(rows)
    bad = [r for r in rows if r["order_errors"]]; big = [r for r in rows if r["order_errors"] >= 5]
    for name, fl in (("footnote above text", lambda r: r["footnote_above_text"]), ("cut without gap", lambda r: r["cuts_without_gap"] >= 1),
                     ("either", lambda r: r["footnote_above_text"] or r["cuts_without_gap"] >= 1),
                     ("either (2+ cuts)", lambda r: r["footnote_above_text"] or r["cuts_without_gap"] >= 2)):
        print(f"{name:20s} flags {sum(map(bool, map(fl, rows))):3d}/{len(rows)}; catches {sum(map(bool, map(fl, bad)))}/{len(bad)} pages with an order error, "
              f"{sum(map(bool, map(fl, big)))}/{len(big)} with 5+ lines out of place")


if __name__ == "__main__":
    if sys.argv[1] == "conventions": conventions()
    elif sys.argv[1] == "reorder": reorder(sys.argv[2])
    elif sys.argv[1] == "flags": flags(sys.argv[2])
    else: main(sys.argv[1:])
