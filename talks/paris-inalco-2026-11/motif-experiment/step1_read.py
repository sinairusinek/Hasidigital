"""Step 1: Opus reads each Hebrew story and returns (a) an English summary,
(b) a list of narrative events, (c) a Propp analysis with a fit score.
Resumable: skips stories whose JSON already exists."""
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor

from common import SAMPLE_TSV, STEP1_DIR, call_claude

STEP1_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM = r"""You are a folklorist trained in both Proppian morphology and the Aarne-Thompson-Uther / Thompson Motif-Index tradition, and you read 19th-century Hebrew hagiographic prose fluently.

You will receive one Hasidic story (Hebrew, 19th-century print). Return ONLY a JSON object, no prose before or after, with these keys:

"summary_en": 2-4 sentences in English: what happens.

"events": the story broken into its narrative events, in order (typically 3-10). Each item:
  {"n": 1, "event": "<one English sentence, phrased generically like a motif-index entry would describe it: e.g. 'Holy man foresees danger on a journey and forbids the route'>",
   "detail": "<one English sentence with the story-specific detail: who, where>",
   "quote": "<the Hebrew words (max 12) that carry this event, copied exactly>"}
  Do not include pure framing (chain of transmission, 'I heard from...') as an event, but do note it in "frame".

"frame": the narrator/transmission frame in one English sentence, or "" if none.

"propp": {
  "functions": [ {"symbol": "<Propp symbol, e.g. A, a, B, C, ↑, D, E, F, G, H, I, J, K, ↓, Pr, Rs, o, L, M, N, Q, Ex, T, U, W, β, γ, δ, ε, ζ, η, θ, λ>",
                  "name": "<Propp's name, e.g. Villainy, Lack, Mediation, Departure, First function of the donor, Receipt of magical agent, Struggle, Victory, Liquidation of lack, Return, Difficult task, Solution, Recognition, Punishment, Wedding...>",
                  "event_n": <event number or null>,
                  "strength": "clear" | "forced",
                  "why": "<one sentence>"} ],
  "dramatis_personae": {"hero": "...", "villain": "...", "donor": "...", "helper": "...", "princess_or_sought_person": "...", "dispatcher": "...", "false_hero": "..."}  (use "" for roles nobody fills),
  "move_count": <number of Proppian moves, 0 if none>,
  "fit": <integer 1-5: 5 = a full Proppian wondertale sequence; 3 = a recognisable partial sequence (e.g. lack -> liquidation) carrying the plot; 1 = the story's point lies outside Propp's functions altogether>,
  "fit_reason": "<1-2 sentences: what in the story Propp's scheme captures and what it misses>"
}

"genre_free": your own short genre label for this story (a few words), as a folklorist would file it.

"what_motif_indexes_would_miss": one or two sentences: what is central to this story that a general folk motif index is unlikely to have an entry for.

Be honest: mark Proppian functions "forced" when you are stretching the definition; do not pad. Many Hasidic tales are not wondertales and a low fit is a valid result."""


def run(row):
    out = STEP1_DIR / f"{row['story_id']}.json"
    if out.exists():
        return row["story_id"], "cached"
    user = f"Story {row['story_id']} ({row['edition']}):\n\n{row['text']}"
    res = call_claude(SYSTEM, user)
    res["story_id"] = row["story_id"]
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return row["story_id"], f"{len(res.get('events', []))} events, propp fit {res.get('propp', {}).get('fit')}"


if __name__ == "__main__":
    rows = list(csv.DictReader(open(SAMPLE_TSV), delimiter="\t"))
    if len(sys.argv) > 1:
        rows = rows[: int(sys.argv[1])]
    with ThreadPoolExecutor(3) as ex:
        for sid, msg in ex.map(run, rows):
            print(sid, msg, flush=True)
