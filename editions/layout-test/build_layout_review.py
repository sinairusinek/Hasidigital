"""Layout Review page for books run through run_layout.py: only the flagged pages, each drawn with its boxes,
with "fine / needs fixing" and a note saved to the artifact's db (collection `answers`, doc `<docId>-<page>`).
Style and save logic come from ../scan-check/review/review_template.html.

    python build_layout_review.py DOCID [DOCID ...] [--all] [--out DIR] [--title TITLE]   → DIR/layout-review.html + img/
                                          (default DIR layout-review; --all shows every page, not only flagged ones)
Each box carries its place in the reading order.
"""
import csv, html, sys
from pathlib import Path
import cv2
from layout_qa import read_layout
from yolo_regions import DATA

HERE = Path(__file__).parent
ALL = "--all" in sys.argv
OUT = HERE / (sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "layout-review"); (OUT / "img").mkdir(parents=True, exist_ok=True)
DOCS = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] not in ("--out", "--title")]
T = "https://app.transkribus.org/collection/49371/doc/{}/edit?pageNr={}"
COL = {"main-text": (60, 140, 60), "heading": (40, 90, 220), "running-head": (180, 100, 20), "page-number": (170, 40, 160),
       "catch-word": (20, 150, 200), "footnote": (40, 40, 200)}  # BGR, drawn on the paper
NAMES = {"main-text": "main text", "heading": "heading", "running-head": "running head", "page-number": "page number",
         "catch-word": "catch-word", "footnote": "footnote"}
e = html.escape
mp = {r["docId"]: r for r in csv.DictReader(open(HERE.parent / "transkribus-collection-map.tsv"), delimiter="\t")}


def overlay(doc, n):
    name = f"{doc}_{n:04d}.jpg"
    regs, W, H = read_layout(DATA / "books" / doc / "layout" / f"{n:04d}.xml")
    im = cv2.imread(str(DATA / "books" / doc / "img" / f"{n:04d}.jpg")); s = im.shape[1] / W
    t = max(3, im.shape[1] // 500)
    for k, r in enumerate(regs, 1):  # page_xml writes regions in reading order
        x0, y0, x1, y1 = [int(v * s) for v in r["box"]]; c = COL.get(r["lab"], (90, 90, 90))
        cv2.rectangle(im, (x0, y0), (x1, y1), c, t)
        cv2.rectangle(im, (x1 - 16 * t, y0), (x1, y0 + 11 * t), c, -1)
        cv2.putText(im, str(k), (x1 - 15 * t, y0 + 9 * t), cv2.FONT_HERSHEY_SIMPLEX, t / 3.2, (255, 255, 255), max(1, t // 2 + 1))
        for l in r["lines"]:
            cv2.line(im, (int(l[0] * s), int(l[3] * s)), (int(l[2] * s), int(l[3] * s)), c, max(1, t // 2))
    k = 1100 / max(im.shape[:2])
    cv2.imwrite(str(OUT / "img" / name), cv2.resize(im, None, fx=k, fy=k, interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 72])
    return name


def plain(flag):
    return (flag.replace("text outside boxes", "text outside every box").replace("(footnote?)", "— a footnote?")
            .replace("(heading?)", "— a heading?"))


TITLE = sys.argv[sys.argv.index("--title") + 1] if "--title" in sys.argv else "Layout Review"
LEDE = ("The new local pipeline ran on this book without Transkribus: boxes from our trained detector, lines from the Kraken model "
        "fine-tuned on our corrected pages, tags corrected by Claude from the page images, then the reading order. Every page is "
        "shown; the number in each box's corner is its place in the reading order, and the list above each page gives the automatic "
        "flags (most pages have none). Mark each page fine or needing a fix. Answers save as you go, and I read them from here."
        if ALL else "The local layout (boxes from our trained detector, lines from Kraken) ran on the books below without Transkribus. "
        "The automatic checks picked out only these pages; everything else passed. Mark each page fine or needing a fix. Answers save "
        "as you go, and I read them from here.")
cards, books = [], []
for doc in DOCS:
    rows = list(csv.DictReader(open(DATA / "books" / doc / "flags.tsv"), delimiter="\t"))
    flagged = [r for r in rows if r["flags"] or ALL]
    w = mp.get(doc, {})
    books.append(f'<li><span dir="rtl" lang="he">{e(w.get("work", doc))}</span> (work {e(w.get("work_nu", ""))}): '
                 f'{sum(1 for r in rows if r["flags"])} of {len(rows)} pages flagged</li>')
    for r in flagged:
        n = int(r["pageNr"]); img = overlay(doc, n); i = f"{doc}-{n}"
        fl = "".join(f"<li>{e(plain(f))}</li>" for f in r["flags"].split("; ") if f) or "<li>no flags</li>"
        cards.append(f'''<article class="issue" id="p{i}">
<header><span class="tag check">p. {n}</span><h3><span dir="rtl" lang="he">{e(w.get("work", ""))}</span> <span class="meta">doc {doc}</span></h3><span class="saved" data-saved="{i}"></span></header>
<ul class="flags">{fl}</ul>
<div class="gallery"><figure class="big"><button type="button" class="zoom" data-src="img/{img}" data-link="{e(T.format(doc, n))}" data-cap="Image page {n}" aria-label="Enlarge image page {n}"><img loading="lazy" src="img/{img}" alt="Image page {n} with its layout boxes"></button>
<figcaption><a href="{e(T.format(doc, n))}" target="_blank" rel="noopener">Open p. {n} in Transkribus</a></figcaption></figure></div>
<fieldset><legend>Is the layout right?</legend>
<label class="opt"><input type="radio" name="{i}-choice" value="fine" data-id="{i}" data-field="choice"><span>Fine as it is</span></label>
<label class="opt"><input type="radio" name="{i}-choice" value="fix" data-id="{i}" data-field="choice"><span>Needs fixing (say what in the note)</span></label></fieldset>
<label class="lbl" for="{i}-note">Note</label>
<textarea id="{i}-note" rows="2" data-id="{i}" data-field="note"></textarea>
</article>''')

legend = "".join(f'<span><i style="background:rgb({c[2]},{c[1]},{c[0]})"></i>{NAMES[k]}</span>' for k, c in COL.items())
t = open(HERE.parent / "scan-check" / "review" / "review_template.html").read()
css = t[t.index("<style>"): t.index("</style>")]
css += """.flags { margin: 0; padding-left: 18px; display: grid; gap: 2px; }
.key { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: var(--muted); margin-top: 10px; }
.key i { display: inline-block; width: 12px; height: 12px; border-radius: 2px; margin-right: 6px; vertical-align: -1px; }
.big img { height: 420px; max-width: 100%; object-fit: contain; }
</style>"""
body = f'''<div class="wrap">
  <h1>{e(TITLE)}</h1>
  <p class="lede">{LEDE}</p>
  <p class="status" id="status">Connecting to saved answers…</p>
  <ul class="sum">{"".join(books)}</ul>
  <div class="key">{legend}<span>Thin lines under the text: detected text lines.</span></div>
  <h2>{"Every page" if ALL else "Pages to look at"}</h2>
  <div class="stack">
{chr(10).join(cards)}
  </div>
</div>
'''
viewer = t[t.index('<div class="viewer"'): t.index("<script>")]
page = f'<title>{e(TITLE)}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n' + t[t.index("<link"): t.index("<style>")] + css + "\n" + body + viewer + t[t.index("<script>"):]
(OUT / "layout-review.html").write_text(page)
print(len(cards), "pages on the review page")
