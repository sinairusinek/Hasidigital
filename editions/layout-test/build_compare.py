"""Side-by-side pictures of test pages: Transkribus before the RA (FR-313993 boxes, LA-51962 lines),
our local pipeline (YOLO + rules boxes, Kraken lines cut on the boxes), and the RA's FINAL.
Letters tagged differently from FINAL are ringed in red; detected lines that split, merge or miss a FINAL line
are drawn in red.

    python build_compare.py   → compare/layout-compare.html + compare/img/
"""
import csv, html, collections
from pathlib import Path
import numpy as np, cv2
from layout_qa import read_layout, letters, clean
from ink_score import tag_letters
from line_score import line_polys, assign_baseline, OK, FW

HERE = Path(__file__).parent
IMG = Path.home() / "Documents/Hasidigital-data/layout-test"
OUT = HERE / "compare"; (OUT / "img").mkdir(parents=True, exist_ok=True)
T = "https://app.transkribus.org/collection/49371/doc/{}/edit?pageNr={}"
OURS, OURS_LINES = "yolo+krakenfix-yolo-noext", "krakenfix-yolo-noext"
RED = (30, 30, 220)
COL = {"main-text": (60, 140, 60), "heading": (40, 90, 220), "running-head": (180, 100, 20), "page-number": (170, 40, 160),
       "catch-word": (20, 150, 200), "footnote": (40, 40, 200)}  # BGR, drawn on the paper
NAMES = {"main-text": "main text", "heading": "heading", "running-head": "running head", "page-number": "page number",
         "catch-word": "catch-word", "footnote": "footnote"}
e = html.escape
mp = {r["docId"]: r for r in csv.DictReader(open(HERE.parent / "transkribus-collection-map.tsv"), delimiter="\t")}


def bad_lines(final_lines, det_lines, L):
    """Indexes of detected lines that hold part of a wrongly detected FINAL line."""
    fa, da = assign_baseline(final_lines, L), assign_baseline(det_lines, L); bad = set(); wrong = 0
    for i, (_, lab, _) in enumerate(final_lines):
        if lab in FW: continue
        mine = da[fa == i]
        if len(mine) < 3: continue
        j, n = collections.Counter(mine.tolist()).most_common(1)[0]
        if not (j >= 0 and n / len(mine) >= OK and n / max(1, (da == j).sum()) >= OK):
            wrong += 1; bad |= {k for k in set(mine.tolist()) if k >= 0}
    return bad, wrong


def draw(img, regs, lines, L, wrong_letters, red_lines, name):
    im = cv2.imread(str(img)); over = im.copy(); t = max(3, im.shape[1] // 400)
    for r in sorted(regs, key=lambda r: -(r["box"][2] - r["box"][0]) * (r["box"][3] - r["box"][1])):
        x0, y0, x1, y1 = map(int, r["box"]); c = COL.get(r["lab"], (90, 90, 90))
        cv2.rectangle(over, (x0, y0), (x1, y1), c, -1)
    im = cv2.addWeighted(over, 0.22, im, 0.78, 0)
    for r in regs:
        x0, y0, x1, y1 = map(int, r["box"]); cv2.rectangle(im, (x0, y0), (x1, y1), COL.get(r["lab"], (90, 90, 90)), t)
    for k, (_, _, bl) in enumerate(lines):
        if bl is None or len(bl) < 2: continue
        cv2.polylines(im, [bl.astype(np.int32)], False, RED if k in red_lines else (70, 70, 70), t if k in red_lines else max(2, t // 2))
    for x, y, h in L[wrong_letters]:
        cv2.circle(im, (int(x), int(y)), int(max(6, 0.7 * h)), RED, max(2, t // 2))
    k = 1300 / max(im.shape[:2])
    cv2.imwrite(str(OUT / "img" / name), cv2.resize(im, None, fx=k, fy=k, interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 70])
    return name


def pick():
    """Per book: our worst page and our most typical page (median letters wrong)."""
    ours = list(csv.DictReader(open(HERE / f"ink-{OURS}.tsv"), delimiter="\t"))
    by = collections.defaultdict(list)
    for r in ours:
        if r["set"] == "A": by[r["docId"]].append(r)
    out = []
    for doc, rs in by.items():
        rs = sorted(rs, key=lambda r: int(r["wrong"]))
        out += [(doc, int(rs[len(rs) // 2]["pageNr"]), "typical page"), (doc, int(rs[-1]["pageNr"]), "our worst page")]
    return out


cards, totals = [], collections.Counter()
for doc, n, why in pick():
    d = HERE / "xml" / doc; p = f"{n:04d}"; img = IMG / doc / f"{p}.jpg"
    fin, W, H = read_layout(d / f"{p}.final.xml"); L = letters(img, W, H)
    fl, _, _ = line_polys(d / f"{p}.final.xml", True)
    ft = tag_letters(fin, L); keep = ft != "outside"
    panels = []
    for key, title, rf, lf in (("tr", "Transkribus, before the RA", "fr", "la"), ("our", "Our local pipeline", OURS, OURS_LINES)):
        regs, _, _ = read_layout(d / f"{p}.{rf}.xml"); regs, _ = clean(regs, L)
        wl = keep & (tag_letters(regs, L) != ft)
        lines = line_polys(d / f"{p}.{lf}.xml", True)[0] if (d / f"{p}.{lf}.xml").exists() else []
        red, nw = bad_lines(fl, lines, L) if lines else (set(), None)
        nb = sum(1 for _, lab, _ in fl if lab not in FW)
        totals[key + "_letters"] += int(wl.sum())
        sub = f"{int(wl.sum())} letters with the wrong tag" + (f" · {nw} of {nb} lines wrong" if nw is not None else " · no line version on this page")
        panels.append((title, draw(img, regs, lines, L, wl, red, f"{doc}_{p}_{key}.jpg"), sub))
    panels.append(("RA's final", draw(img, fin, fl, L, np.zeros(len(L), bool), set(), f"{doc}_{p}_final.jpg"), "the target"))
    w = mp.get(doc, {}); link = T.format(doc, n)
    figs = "".join(f'''<figure><figcaption><b>{e(t)}</b><span>{e(s)}</span></figcaption>
<button type="button" class="zoom" data-src="img/{f}" data-link="{e(link)}" data-cap="{e(t)} — p. {n}"><img loading="lazy" src="img/{f}" alt="{e(t)}, image page {n}"></button></figure>''' for t, f, s in panels)
    cards.append(f'''<article class="cmp"><header><span class="tag check">{e(why)}</span><h3><span dir="rtl" lang="he">{e(w.get("work", doc))}</span>
<span class="meta">work {e(w.get("work_nu", ""))} · doc {doc} · p. {n}</span></h3><a href="{e(link)}" target="_blank" rel="noopener">Open in Transkribus</a></header>
<div class="row">{figs}</div></article>''')

legend = "".join(f'<span><i style="background:rgb({c[2]},{c[1]},{c[0]})"></i>{NAMES[k]}</span>' for k, c in COL.items())
t = open(HERE.parent / "scan-check" / "review" / "review_template.html").read()
css = t[t.index("<style>"): t.index("</style>")] + """
.wrap { max-width: 1280px; }
.cmp { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 14px 16px; display: grid; gap: 10px; min-width: 0; }
.row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
@media (max-width: 720px) { .row { grid-template-columns: 1fr; } }
.row figure { justify-items: stretch; align-content: start; }
.row figcaption { display: grid; gap: 1px; font-size: 13px; } .row figcaption span { color: var(--muted); }
.row img { width: 100%; height: auto; display: block; }
.key { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: var(--muted); margin-top: 12px; }
.key i { display: inline-block; width: 12px; height: 12px; border-radius: 2px; margin-right: 6px; vertical-align: -1px; }
.key .ring { background: none; border: 2px solid rgb(220,30,30); border-radius: 50%; }
</style>"""
body = f'''<div class="wrap">
  <h1>Layout Compare</h1>
  <p class="lede">Two test pages from each of the 13 books: the page where our pipeline does typically, and the page where it does worst.
  Every picture is from a book the model never saw in training. Left: what Transkribus produced before the RA touched it.
  Middle: our local pipeline. Right: the RA's corrected version, which is the target. Click a picture to enlarge it.</p>
  <div class="key">{legend}<span><i class="ring"></i>letter tagged differently from the RA</span><span>red baseline: a line split, merged or missed</span></div>
  <div class="stack">
{chr(10).join(cards)}
  </div>
</div>
'''
viewer = t[t.index('<div class="viewer"'): t.index("<script>")]
s1 = t.index("<script>"); script = t[s1: t.index("</script>", s1) + 9]
(OUT / "layout-compare.html").write_text('<title>Layout Compare</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
                                         + t[t.index("<link"): t.index("<style>")] + css + "\n" + body + viewer + script + "\n")
print(len(cards), "pages;", dict(totals), "; images", sum(f.stat().st_size for f in (OUT / "img").glob("*.jpg")) // 1_000_000, "MB")
