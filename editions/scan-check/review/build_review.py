import csv, html, json, pickle, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, "/Users/sinairusinek/Documents/GitHub/Hasidigital/editions/scan-check")
import scan_checks as sc
R = "/Users/sinairusinek/Documents/GitHub/Hasidigital/editions/scan-check/"
T = "https://app.transkribus.org/collection/49371/doc/{}/edit?pageNr={}"
flags = {(r["docId"], int(r["page"])): r["flags"].split() for r in csv.DictReader(open(R + "scan-pages.tsv"), delimiter="\t")}
books = {r["docId"]: r for r in csv.DictReader(open(R + "scan-books.tsv"), delimiter="\t")}
by = defaultdict(list)
for r in [x for f in sorted(Path("img").glob("*/_measurements.pkl")) for x in pickle.loads(f.read_bytes())]:
    r["flags"] = flags[(r["docId"], r["page"])]; by[r["docId"]].append(r)
issues = list(csv.DictReader(open(R + "scan-issues.tsv"), delimiter="\t"))
issue_docs = {i["docId"] for i in issues}
review = {r["docId"]: r["note"] for r in csv.DictReader(open(R + "scan-review.tsv"), delimiter="\t") if r["docId"].isdigit()}
e = html.escape
from PIL import Image
IMG_OUT = Path("../review/img"); IMG_OUT.mkdir(parents=True, exist_ok=True)
USED = []

def img(d, page, cls="thumb", label=None):
    """Downscaled copy published beside the page (the frame blocks Transkribus image URLs)."""
    name = f"{d}_{int(page):04d}.jpg"
    out = IMG_OUT / name
    if not out.exists():
        im = Image.open(f"img/{d}/{int(page):04d}.jpg").convert("RGB")
        im.thumbnail((1100, 1100))
        im.save(out, quality=72, optimize=True)
    USED.append(name)
    cap = label or f"p. {page}"
    return (f'<figure class="{cls}"><button type="button" class="zoom" data-src="img/{name}" data-link="{e(T.format(d, page))}" '
            f'data-cap="{e(cap)}" aria-label="Enlarge image page {page}"><img loading="lazy" src="img/{name}" alt="Image page {page}"></button>'
            f'<figcaption><a href="{e(T.format(d, page))}" target="_blank" rel="noopener">{e(cap)}</a></figcaption></figure>')

SHOW = {"S1": [107, 108, 113, 118, 123, 124], "S3": [32, 33, 34], "S4": [40, 150, 200]}
ASK = ("S1", "S3", "S4")   # only what needs Sinai's eye

DECIDED = {"S1": "Repeated pages: decided. Both copies go through OCR, the readings are compared, and the repeats are deleted before annotation."}
OPTIONS = {
 "S4": ["Look for a better scan first", "Process this scan as it is", "Something else (see note)"],
 "S3": ["Look for another copy of the page", "Accept the gap and mark it in the edition", "Something else (see note)"],
}
EXTRA = {"S1": ("Is אור הנפלאות a separate work bound into this scan?", ["Yes, a separate work", "No, part of אהל הרבי", "Not sure"])}

def links(i):
    out = [f'<a href="{e(u)}" target="_blank" rel="noopener">Image page {u.split("pageNr=")[1]}</a>' for u in i["pages"].split()]
    out.append(f'<a href="{e(i["source_link"])}" target="_blank" rel="noopener">{e(i["source"])}</a>')
    return " · ".join(out)

cards = []
for i in [i for i in issues if i["id"] in ASK]:
    opts = "".join(f'<label class="opt"><input type="radio" name="{i["id"]}-choice" value="{e(o)}" data-id="{i["id"]}" data-field="choice"><span>{e(o)}</span></label>' for o in OPTIONS.get(i["id"], []))
    ask = f'<fieldset><legend>What should we do?</legend>{opts}</fieldset>' if opts else f'<p class="decided">{e(DECIDED[i["id"]])}</p>'
    gallery = '<div class="gallery">' + "".join(img(i["docId"], p, "big") for p in SHOW[i["id"]]) + "</div>"
    report = (f'<label><input type="checkbox" id="{i["id"]}-reported" data-id="{i["id"]}" data-field="reported"> Reported to {e(i["report_to"])}</label>'
              if i["report_to"] == "NLI" else "")
    fixed = (f'<label><input type="checkbox" id="{i["id"]}-fixed" data-id="{i["id"]}" data-field="fixed"> Fixed in Transkribus</label>'
             if i["id"] == "S3" else "")
    extra = ""
    if i["id"] in EXTRA:
        q, os_ = EXTRA[i["id"]]
        extra = f'<fieldset><legend>{e(q)}</legend>' + "".join(f'<label class="opt"><input type="radio" name="{i["id"]}-extra" value="{e(o)}" data-id="{i["id"]}" data-field="extra"><span>{e(o)}</span></label>' for o in os_) + "</fieldset>"
    cards.append(f'''<article class="issue" id="{i["id"]}">
<header><span class="tag check">{i["id"]}</span><h3><span dir="rtl" lang="he">{e(i["work"])}</span> <span class="meta">work {i["work_nu"]} · doc {i["docId"]}</span></h3><span class="saved" data-saved="{i["id"]}"></span></header>
<p>{e(i["issue"])}</p>
<p class="links">{links(i)}</p>
{gallery}
{ask}{extra}
<label class="lbl" for="{i["id"]}-note">Note (what you saw, what you changed)</label>
<textarea id="{i["id"]}-note" rows="3" data-id="{i["id"]}" data-field="note"></textarea>
<div class="checks">{fixed}{report}</div>
</article>''')

from collections import Counter
crop, deskew, clean = [], [], []
for d in sorted(by, key=lambda d: float(books[d]["work_nu"] or 0)):
    v = " ".join(t for t, _ in sc.verdict(by[d]))
    name = f'<span dir="rtl" lang="he">{e(books[d]["work"])}</span> ({books[d]["work_nu"]})'
    if "crop" in v: crop.append(name)
    if "deskew" in v: deskew.append(name)
    if not v: clean.append(name)
OLD = {"6270967", "15561748", "6705191", "6705189"}
old = [f'<span dir="rtl" lang="he">{e(books[d]["work"])}</span> ({books[d]["work_nu"]})' for d in OLD if d in books]
summary = (f'<ul class="sum"><li><b>Cropping</b> ({len(crop)} books): photos that also show the neighbouring page, the copy stand or tape. {", ".join(crop)}.</li>'
           f'<li><b>Deskewing</b> ({len(deskew)} books): {", ".join(deskew)}.</li>'
           f'<li><b>Pages I looked at and found harmless</b>: covers, endpapers and library labels the measures took for damaged text; a stain on one page of <span dir="rtl" lang="he">אילנא דחיי</span> (91) that leaves the words readable.</li>'
           f'<li><b>Repeated pages</b> in <span dir="rtl" lang="he">מעשה נחמיה</span> (137): kept through OCR, as you decided.</li>'
           f'<li><b>The four books uploaded in 2025</b>, now checked too ({", ".join(old)}): clean scans; their difficulty is layout (two columns, footnotes), which the layout test covers.</li>'
           f'<li><b>No findings</b>: {len(clean)} of {len(by)} books.</li></ul>')
rows = []
page = open("review_template.html").read()
page = page.replace("%%ISSUES%%", "\n".join(cards)).replace("%%SUMMARY%%", summary).replace("%%NBOOKS%%", str(len(by)))
open("../review/scan-review.html", "w").write(page)
print(len(cards), len(rows), len(clean), "images", len(set(USED)))
import json as _j; open("../review/files.json", "w").write(_j.dumps({f"img/{n}": f"img/{n}" for n in sorted(set(USED))}))
