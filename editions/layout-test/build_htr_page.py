"""HTR Test results page: score tables from htr_test.py / ink_score.py / line_merge.py, and the sampled lines where
Claude and the RA's FINAL disagree, each with its line image, my verdict, and a "who is right" answer saved to the
artifact's db (collection `answers`, doc `line-<k>`). Prose comes from htr-results/text.json.

    python build_htr_page.py   → htr-results/htr-results.html + img/
"""
import csv, difflib, html, json
from pathlib import Path
import numpy as np, cv2
from htr_test import page_lines, IMG, HERE, DATA
from layout_qa import letters

OUT = HERE / "htr-results"; (OUT / "img").mkdir(parents=True, exist_ok=True)
T = "https://app.transkribus.org/collection/49371/doc/{}/edit?pageNr={}"
e = html.escape
text = json.loads((OUT / "text.json").read_text())


def diff(a, b):
    """Two strings with the words that differ marked."""
    aw, bw = a.split(), b.split(); sm = difflib.SequenceMatcher(None, aw, bw); x, y = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        A, B = " ".join(aw[i1:i2]), " ".join(bw[j1:j2])
        if op == "equal": x.append(e(A)); y.append(e(B))
        else:
            if A: x.append(f"<mark>{e(A)}</mark>")
            if B: y.append(f"<mark>{e(B)}</mark>")
    return " ".join(x), " ".join(y)


def crop(doc, n, i, k):
    l = page_lines(HERE / "xml" / doc / f"{n:04d}.final.xml")[i - 1]
    im = cv2.imread(str(IMG / doc / f"{n:04d}.jpg")); H, W = im.shape[:2]
    h = float(np.median(letters(IMG / doc / f"{n:04d}.jpg", W, H)[:, 2])); bl = l["bl"]
    c = im[int(max(0, bl[:, 1].min() - 1.6 * h)):int(bl[:, 1].max() + 0.6 * h), int(max(0, bl[:, 0].min() - h)):int(min(W, bl[:, 0].max() + h))]
    c = cv2.resize(c, (1400, int(c.shape[0] * 1400 / c.shape[1])), interpolation=cv2.INTER_AREA)
    name = f"line{k:02d}.jpg"; cv2.imwrite(str(OUT / "img" / name), c, [cv2.IMWRITE_JPEG_QUALITY, 82]); return name


def table(rows, cols):
    head = "".join(f"<th>{e(c)}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td>{v}</td>" for v in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


pct = lambda v: f"{100 * float(v):.1f}%"
names = {"read opus": "Claude Opus, on the RA's lines", "read gemini-3.8-flash": "Gemini 3.8 Flash, on the RA's lines",
         "read gemini-2.5-pro": "Gemini 2.5 Pro, on the RA's lines", "combined opus": "Claude Opus, on our layout (one call: text + tags)",
         "combined gemini-3.8-flash": "Gemini 3.8 Flash, on our layout (one call: text + tags)"}
sc = {r["method"]: r for r in csv.DictReader(open(HERE / "htr-scores.tsv"), delimiter="\t")}
read_rows = [[e(names[m]), sc[m]["pages"], pct(sc[m]["cer"]), pct(sc[m]["letters_cer"]), pct(sc[m]["transkribus_cer"]),
              f'{sc[m]["pages_over_5pct"]} / {sc[m]["transkribus_pages_over_5pct"]}'] for m in names if m in sc]

items = []
for k, r in enumerate(csv.DictReader(open(DATA / "htr" / "adjud.tsv"), delimiter="\t"), 1):
    d, n, i = r["docId"], int(r["pageNr"]), int(r["line"]); a, b = diff(r["ref"], r["hyp"]); v = text["verdicts"].get(str(k), "")
    items.append(f'''<article class="issue" id="l{k}"><header><span class="tag check">line {k}</span><h3><span class="meta">doc {d} · p. {n} · line {i}</span></h3>
<a href="{e(T.format(d, n))}" target="_blank" rel="noopener">Open in Transkribus</a><span class="saved" data-saved="line-{k}"></span></header>
<button type="button" class="zoom" data-src="img/{crop(d, n, i, k)}" data-link="{e(T.format(d, n))}" data-cap="Line {k}"><img loading="lazy" src="img/line{k:02d}.jpg" alt="Printed line {k}"></button>
<dl class="read" dir="rtl" lang="he"><dt>RA</dt><dd>{a}</dd><dt>Claude</dt><dd>{b}</dd></dl>
<p class="mine"><b>My reading:</b> {e(v)}</p>
<fieldset><legend>Who is right?</legend><div class="checks">
{"".join(f'<label class="opt"><input type="radio" name="line-{k}-c" value="{val}" data-id="line-{k}" data-field="who"><span>{lab}</span></label>' for val, lab in (("ra", "the RA"), ("claude", "Claude"), ("both", "both wrong"), ("unsure", "can't tell")))}
</div></fieldset></article>''')

t = open(HERE.parent / "scan-check" / "review" / "review_template.html").read()
css = t[t.index("<style>"): t.index("</style>")] + """
.tw { overflow-x: auto; margin-top: 10px; }
table { border-collapse: collapse; font-size: 14px; min-width: 560px; width: 100%; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-weight: 600; color: var(--muted); font-size: 12.5px; }
td:not(:first-child), th:not(:first-child) { font-variant-numeric: tabular-nums; white-space: nowrap; }
.prose p { margin: 10px 0 0; max-width: 70ch; } .prose ul { margin: 8px 0 0; padding-left: 20px; max-width: 70ch; } .prose li { margin: 4px 0; }
.zoom img { width: 100%; height: auto; display: block; }
.read { display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px; margin: 0; font: 18px/1.5 "IBM Plex Sans Hebrew", var(--body); }
.read dt { font: 600 12px var(--mono); color: var(--muted); padding-top: 4px; } .read dd { margin: 0; }
mark { background: color-mix(in srgb, var(--check) 22%, transparent); color: inherit; border-radius: 2px; padding: 0 2px; }
</style>"""
P = lambda key: "".join(f"<p>{x}</p>" for x in text[key])
body = f'''<div class="wrap">
  <h1>HTR Test</h1>
  <div class="prose">{P("lede")}</div>
  <p class="status" id="status">Connecting to saved answers…</p>
  <h2>1. Reading: vision models against the Transkribus model</h2>
  <div class="prose">{P("read_intro")}</div>
  {table(read_rows, ["Method", "Pages", "Characters wrong", "Letters only", "Transkribus, same pages", "Pages over 5% (model / Transkribus)"])}
  <div class="prose">{P("read_after")}</div>
  <h2>2. Who is right when Claude and the RA differ?</h2>
  <div class="prose">{P("adjud_intro")}</div>
  <div class="stack">{"".join(items)}</div>
  <h2>3. Can the reading correct the tags and the lines?</h2>
  <div class="prose">{P("layout")}</div>
  {table(text["layout_rows"], text["layout_cols"])}
  <div class="prose">{P("layout_after")}</div>
  <h2>4. What I would do next</h2>
  <div class="prose">{P("next")}</div>
</div>
'''
viewer = t[t.index('<div class="viewer"'): t.index("<script>")]
(OUT / "htr-results.html").write_text('<title>HTR Test</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
                                      + t[t.index("<link"): t.index("<style>")] + css + "\n" + body + viewer + t[t.index("<script>"):])
print(len(items), "lines;", len(read_rows), "reading rows")
