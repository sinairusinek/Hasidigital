"""Step 4: align OUR tags with the motif picks and the Propp functions, per story.
For each of our tags: which events express it, which picked motifs correspond, and
the relation (same / ours_finer / motif_finer / no_counterpart). For each picked
motif: which of our tags (if any) correspond. Run after step 3."""
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor

from common import OUT, REPO, SAMPLE_TSV, STEP1_DIR, STEP3_DIR, call_claude

STEP4_DIR = OUT / "step4"
STEP4_DIR.mkdir(parents=True, exist_ok=True)
META = {m["id"]: m for m in json.loads((OUT / "motif_meta.json").read_text())}
DEFS = {r["tag"]: r["definition"] for r in
        csv.DictReader(open(REPO / "editions/tag-audit/tag-definitions.tsv"), delimiter="\t")}

SYSTEM = r"""You compare two annotation schemes applied to the same Hasidic story:
(1) the project's own topic tags (with their definitions), and
(2) folk-motif codes from Thompson's and Noy's motif indexes, attached to the story's events.
You also see the story's events and its Propp functions.

Return ONLY a JSON object:
{"tags": [ {"tag": "<tag exactly as given>",
            "events": [<event numbers expressing it>],   // [] if it is a whole-story/background tag
            "motifs": ["<motif codes from the list that correspond>"],
            "propp": ["<Propp symbols that correspond>"],
            "relation": "same" | "ours_broader" | "motif_broader" | "no_counterpart",
            "why": "<short>"} ],
 "motifs": [ {"code": "<code>", "tags": ["<our tags that correspond>"]} ],   // [] tags = no counterpart in our scheme
 "note": "<1-2 sentences: what each scheme sees that the other does not, in this story>"}

relation: "same" = tag and motif(s) describe the same thing at a similar level; "ours_broader"/"motif_broader" = one subsumes the other; "no_counterpart" = no picked motif corresponds (say in 'why' whether the tag is about theme/setting/social world rather than narrative action). Include EVERY tag given and EVERY motif given."""


def run(row):
    sid = row["story_id"]
    out = STEP4_DIR / f"{sid}.json"
    if out.exists():
        return sid, "cached"
    d1 = json.loads((STEP1_DIR / f"{sid}.json").read_text())
    d3 = json.loads((STEP3_DIR / f"{sid}.json").read_text())
    tags = [t for t in row["our_tags"].split(";") if t]
    codes = []
    L = [f"Story {sid}:\n{row['text']}\n", "EVENTS:"]
    picks = {e["n"]: e["picks"] for e in d3["events"]}
    for e in d1["events"]:
        L.append(f"{e['n']}. {e['event']} [{e.get('detail', '')}]")
        for p in picks.get(e["n"], []):
            codes.append(p["code"])
            L.append(f"    motif {p['code']} ({p['grade']}): {META[p['code']]['title']}")
    L.append("\nPROPP FUNCTIONS: " + "; ".join(
        f"{f['symbol']} {f['name']} (event {f['event_n']}, {f['strength']})" for f in d1["propp"]["functions"]))
    L.append("\nOUR TAGS:")
    for t in tags:
        L.append(f"- {t}: {DEFS.get(t, '(no definition)')}")
    res = call_claude(SYSTEM, "\n".join(L))
    res["story_id"] = sid
    full = {t.split(":", 1)[-1]: t for t in tags}
    for t in res.get("tags", []):
        t["tag"] = t.get("tag") if t.get("tag") in tags else full.get(str(t.get("tag")).split(":", 1)[-1], "")
    res["tags"] = [t for t in res.get("tags", []) if t["tag"]]
    res["motifs"] = [m for m in res.get("motifs", []) if m.get("code") in codes]
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    rel = [t["relation"] for t in res["tags"]]
    return sid, f"{len(tags)} tags: " + ", ".join(f"{k} {rel.count(k)}" for k in
                                                  ("same", "ours_broader", "motif_broader", "no_counterpart"))


if __name__ == "__main__":
    rows = [r for r in csv.DictReader(open(SAMPLE_TSV), delimiter="\t")
            if (STEP3_DIR / f"{r['story_id']}.json").exists()]
    if len(sys.argv) > 1:
        rows = rows[: int(sys.argv[1])]
    with ThreadPoolExecutor(3) as ex:
        for sid, msg in ex.map(run, rows):
            print(sid, msg, flush=True)
