"""Choose the layout test set: runs of consecutive finished pages, preferring two-column, footnote and
large-initial pages. Writes test-set.tsv.

Run from the scratch folder used by ../scan-check/calibration (it needs fulldoc/ and the scratch
`fr_profile.tsv`, the per-page profile of FR-313993 against FINAL for every finished page).
"""
import csv, json, random, sys
from pathlib import Path

HERE = Path(__file__).parent
random.seed(20261111)
RUN = 5  # consecutive pages per run, so the catch-word and page-number checks have neighbours

# set A: pages with a Field Recognition 313993 version and a FINAL version (regions and lines)
QUOTA_A = {"9568035": 30, "9194455": 25, "9194535": 20, "7125297": 20, "9194696": 20, "9194435": 15,
           "9194695": 15, "9568095": 14, "6705107": 10, "9561376": 10, "6577969": 10, "7627111": 10, "9194635": 10}
# set B: Lemberg 1864-66, FINAL lines only (no region tags); set C: Lemberg 1879, FINAL tagged by older models
QUOTA_B = {"1467961": 10, "1469156": 10, "1778986": 10, "1469471": 10}
QUOTA_C = {"5758447": 15}
# set D: מסעות הים, no FINAL; unscored stress test for large initial words
QUOTA_D = {"20149799": 10}

prof = {(r["docId"], int(r["page"])): r for r in csv.DictReader(open("fr_profile.tsv"), delimiter="\t")}
def score(doc, n):
    r = prof.get((doc, n))
    if not r: return 0
    return 2 * int(r["two_column"]) + 2 * (int(r["footnote"]) > 0) + 2 * (int(r["big_lines"]) > 0) + (int(r["heading"]) > 0)

def finished_pages(doc):
    out = []
    for p in json.loads(Path(f"fulldoc/{doc}.json").read_text())["pageList"]["pages"]:
        ts = sorted(p["tsList"]["transcripts"], key=lambda t: t["timestamp"])
        if ts[-1]["status"] in ("FINAL", "DONE"): out.append(p["pageNr"])
    return out

def pick(doc, quota, pages):
    """Non-overlapping runs of RUN consecutive pages: best-scoring first, then random, until the quota is filled."""
    pages = sorted(pages); have = set(pages)
    if len(pages) <= quota: return pages
    starts = [n for n in pages if all(n + i in have for i in range(RUN))]
    random.shuffle(starts)
    starts.sort(key=lambda n: -sum(score(doc, n + i) for i in range(RUN)))
    chosen = set()
    for n in starts:
        if len(chosen) >= quota: break
        run = set(range(n, n + RUN))
        if not run & chosen and not {n - 1, n + RUN} & chosen: chosen |= run
    return sorted(chosen)[:quota]

rows = []
for s, quotas in (("A", QUOTA_A), ("B", QUOTA_B), ("C", QUOTA_C)):
    for doc, q in quotas.items():
        pages = [n for (d, n) in prof if d == doc] if s == "A" else finished_pages(doc)
        for n in pick(doc, q, pages):
            r = prof.get((doc, n), {})
            rows.append(dict(set=s, docId=doc, pageNr=n, two_column=r.get("two_column", ""), footnote=r.get("footnote", ""),
                             big_lines=r.get("big_lines", ""), heading=r.get("heading", "")))
for doc, q in QUOTA_D.items():
    n0 = 20  # past the front matter
    rows += [dict(set="D", docId=doc, pageNr=n, two_column="", footnote="", big_lines="", heading="") for n in range(n0, n0 + q)]

w = csv.DictWriter(open(HERE / "test-set.tsv", "w"), rows[0].keys(), delimiter="\t"); w.writeheader(); w.writerows(rows)
print(len(rows), "pages")
