"""Flags against consequential errors (ink-<suffix>.tsv): python score_flags.py SUFFIX"""
import csv, sys, collections
s = sys.argv[1] if len(sys.argv) > 1 else "fr"
ink = {(r["docId"], r["pageNr"]): r for r in csv.DictReader(open(f"ink-{s}.tsv"), delimiter="\t")}
qa = [r for r in csv.DictReader(open(f"qa-{s}.tsv"), delimiter="\t") if (r["docId"], r["pageNr"]) in ink]
err = lambda r: ink[(r["docId"], r["pageNr"])]["error"] == "1"
tp = sum(bool(r["flags"]) and err(r) for r in qa); fn = sum(not r["flags"] and err(r) for r in qa); fp = sum(bool(r["flags"]) and not err(r) for r in qa)
print(f"{s}: {len(qa)} pages, {tp+fn} with an error; flagged {tp+fp} ({(tp+fp)/len(qa):.0%}); caught {tp} ({tp/max(1,tp+fn):.0%}); slipped through {fn}; flagged but fine {fp}")
c = collections.defaultdict(lambda: [0, 0])
for r in qa:
    for f in {f.split(" (")[0].lstrip("0123456789 ") for f in r["flags"].split("; ") if f}: c[f][err(r)] += 1
for f, (a, b) in sorted(c.items(), key=lambda x: -sum(x[1])): print(f"  {f:42} error pages {b:3}  fine pages {a:3}")
for r in qa:
    if err(r) and not r["flags"]: print("  missed", r["docId"], r["pageNr"], ink[(r["docId"], r["pageNr"])]["kinds"])
