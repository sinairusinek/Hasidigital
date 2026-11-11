import csv, json, re, collections
from pathlib import Path
MAP = "/Users/sinairusinek/Documents/GitHub/Hasidigital/editions/transkribus-collection-map.tsv"
rows = {r["docId"]: r for r in csv.DictReader(open(MAP, encoding="utf-8"), delimiter="\t")}
out = open("current_model_pages.tsv", "w")
out.write("docId\twork_nu\twork\tpageNr\tfinal\tfr313993\tfr_edited\tla51962\tla_edited\thtr52805\thtr_edited\n")
tot = collections.Counter(); per_doc = collections.defaultdict(collections.Counter); other_tools = collections.Counter()
for f in Path("fulldoc").glob("*.json"):
    d = json.loads(f.read_text()); doc = f.stem; r = rows.get(doc, {})
    for p in d["pageList"]["pages"]:
        ts = sorted(p["tsList"]["transcripts"], key=lambda t: t["timestamp"])
        final = ts[-1]["status"] in ("FINAL", "DONE")
        def idx(pat):
            ii = [i for i, t in enumerate(ts) if re.search(pat, t.get("toolName") or "")]
            return ii[-1] if ii else None
        for t in ts:
            tn = t.get("toolName") or ""
            if tn and not tn.startswith("App") and not re.search(r"313993|51962|52805", tn): other_tools[re.sub(r"\d{4,}", lambda m: m.group(0), tn)[:70]] += 1
        res = {}
        for k, pat in (("fr", r"Field Recognition.*313993"), ("la", r"LA.*51962"), ("htr", r"52805")):
            i = idx(pat)
            res[k] = i is not None
            # a later version not produced by a tool = human edit
            res[k + "_ed"] = i is not None and any(not (t.get("toolName") or "") or (t.get("toolName") or "").startswith("App") for t in ts[i+1:])
        out.write("\t".join(map(str, [doc, r.get("work_nu",""), r.get("work",""), p["pageNr"], int(final),
              int(res["fr"]), int(res["fr_ed"]), int(res["la"]), int(res["la_ed"]), int(res["htr"]), int(res["htr_ed"])])) + "\n")
        tot["pages"] += 1; tot["final"] += final
        for k in ("fr", "la", "htr"):
            if res[k] and final: tot[k + "+final"] += 1; per_doc[doc][k] += 1
        if res["fr"] and res["la"] and res["htr"] and final: tot["all3+final"] += 1; per_doc[doc]["all3"] += 1
print(dict(tot))
print("docs with all3+final pages:", sum(1 for c in per_doc.values() if c["all3"]))
print("docs with fr+final:", sum(1 for c in per_doc.values() if c["fr"]), " htr+final:", sum(1 for c in per_doc.values() if c["htr"]))
for doc, c in sorted(per_doc.items(), key=lambda x: -x[1]["htr"]):
    print(doc, rows.get(doc, {}).get("work", "")[:25], dict(c))
print("\nother tools (top):"); [print(n, t) for t, n in other_tools.most_common(15)]
