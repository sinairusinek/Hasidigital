"""How well do the flags pick out the pages the RA had to fix?  python score_qa.py SUFFIX
Uses baseline-pages.tsv (region_fix: real / stray only / none)."""
import csv, sys, collections
from pathlib import Path

HERE = Path(__file__).parent
suffix = sys.argv[1] if len(sys.argv) > 1 else "fr"
base = {(r["docId"], r["pageNr"]): r for r in csv.DictReader(open(HERE / "baseline-pages.tsv"), delimiter="\t")}
qa = [r for r in csv.DictReader(open(HERE / f"qa-{suffix}.tsv"), delimiter="\t") if base.get((r["docId"], r["pageNr"]), {}).get("region_fix")]
fixed = lambda r: base[(r["docId"], r["pageNr"])]["region_fix"] == "real"
tp = sum(bool(r["flags"]) and fixed(r) for r in qa); fn = sum(not r["flags"] and fixed(r) for r in qa)
fp = sum(bool(r["flags"]) and not fixed(r) for r in qa); tn = sum(not r["flags"] and not fixed(r) for r in qa)
print(f"{len(qa)} pages; RA fixed {tp+fn}. Flagged {tp+fp} ({(tp+fp)/len(qa):.0%}).")
print(f"  caught {tp}/{tp+fn} fixed pages ({tp/max(1,tp+fn):.0%}); missed {fn}; flagged but fine {fp}/{fp+tn}")
print("per book: flagged / pages, caught / fixed")
for d in dict.fromkeys(r["docId"] for r in qa):
    xs = [r for r in qa if r["docId"] == d]
    print(f"  {d}: {sum(bool(r['flags']) for r in xs)}/{len(xs)}, {sum(bool(r['flags']) and fixed(r) for r in xs)}/{sum(fixed(r) for r in xs)}")
c = collections.Counter(f.split(" (")[0].lstrip("0123456789 ") for r in qa for f in r["flags"].split("; ") if f)
print("flags:", c.most_common())
miss = [r for r in qa if not r["flags"] and fixed(r)]
print("missed, with what the RA did:")
for r in miss[:40]:
    b = base[(r["docId"], r["pageNr"])]
    print(f"  {r['docId']} p{r['pageNr']}: relabel {b['relabelled']} split/merge {b['deleted_split']} added {b['added']} | cleanups: {r['cleanups']}")
