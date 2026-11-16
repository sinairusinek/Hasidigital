"""Step 3: Opus judges, for each event of a story, which shortlisted motifs truly
apply (exact / broader) or that none does, and drafts a Thompson-style motif for
the gap. The picker sees the Hebrew story, the events, and the shortlisted motif
ids+titles only: not the Jewish/Noy flags or culture counts (no bias)."""
import csv
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor

from common import SAMPLE_TSV, STEP1_DIR, STEP2_JSON, STEP3_DIR, OUT, call_claude

STEP3_DIR.mkdir(parents=True, exist_ok=True)
META = json.loads((OUT / "motif_meta.json").read_text())
SHORT = json.loads(STEP2_JSON.read_text())

SYSTEM = r"""You are a folklorist expert in Thompson's Motif-Index of Folk-Literature and in Noy's Motif-Index of Talmudic-Midrashic Literature, and you read 19th-century Hebrew.

You get a Hasidic story (Hebrew), its events (English), and for each event a shortlist of candidate motifs found by a search engine. The shortlist is noisy: most candidates will NOT apply. Codes starting with "Noy" come from Noy's index; the others from Thompson's. Treat both alike.

For every event decide which candidate motifs genuinely describe it, as a folklorist indexing this tale would. Grades:
- "exact": the motif states what happens in this event (allowing for the Hasidic setting, e.g. 'saint' / 'holy man' = the tsaddik, 'magician' does not = tsaddik unless the story frames him so).
- "broader": the motif is a correct but more general description (e.g. 'Saint heals sick' for a specific healing by touch).
Do not accept a motif that only shares words or a theme.

Return ONLY a JSON object:
{"events": [
  {"n": 1,
   "picks": [{"code": "<code exactly as given>", "grade": "exact"|"broader", "why": "<short>"}],   // may be []
   "coverage": "exact" | "broader" | "none",   // best grade reached for this event
   "proposed_motif": "<if coverage is not exact: a new motif title in Thompson's style that WOULD index this event, e.g. 'Saint rebukes Angel of Death, who flees'; else ''>",
   "proposed_branch": "<Thompson chapter letter + section where it would belong, e.g. 'V220 Saints' or 'E Dead'; else ''>"}
 ],
 "story_level_note": "<1-2 sentences: how well the two indexes, taken together, capture this story>"}"""


def build_user(row, d):
    lines = [f"Story {row['story_id']}:\n{row['text']}\n", "EVENTS AND CANDIDATES:"]
    for e, sl in zip(d["events"], SHORT[row["story_id"]]):
        lines.append(f"\nEvent {e['n']}: {e['event']}  [{e.get('detail', '')}]")
        cands = sl["candidates"][:]
        random.Random(e["n"]).shuffle(cands)   # hide retrieval rank
        for c in cands:
            m = META[c["idx"]]
            lines.append(f"  - {m['id']}: {m['title']}")
    return "\n".join(lines)


def run(row):
    sid = row["story_id"]
    out = STEP3_DIR / f"{sid}.json"
    if out.exists():
        return sid, "cached"
    d = json.loads((STEP1_DIR / f"{sid}.json").read_text())
    res = call_claude(SYSTEM, build_user(row, d))
    valid = {META[c["idx"]]["id"] for sl in SHORT[sid] for c in sl["candidates"]}
    for ev in res.get("events", []):
        ev["picks"] = [p for p in ev.get("picks", []) if p.get("code") in valid]  # drop hallucinated codes
    res["story_id"] = sid
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    cov = [e.get("coverage") for e in res.get("events", [])]
    return sid, f"exact {cov.count('exact')} / broader {cov.count('broader')} / none {cov.count('none')}"


if __name__ == "__main__":
    rows = [r for r in csv.DictReader(open(SAMPLE_TSV), delimiter="\t") if r["story_id"] in SHORT]
    if len(sys.argv) > 1:
        rows = rows[: int(sys.argv[1])]
    with ThreadPoolExecutor(3) as ex:
        for sid, msg in ex.map(run, rows):
            print(sid, msg, flush=True)
