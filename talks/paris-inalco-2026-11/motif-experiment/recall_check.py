"""Recall check: were the step-3 'none' events uncovered because the indexes lack a
motif, or because the e5-base top-25 shortlist missed it?
For every 'none' event: new shortlist = top-60 from multilingual-e5-LARGE (event and
event+detail queries) + top-40 from e5-base, minus the 25 already shown. Opus then
judges only these NEW candidates, with the same grading rules as step 3.
Output: private/motif-experiment/recall/<story>.json and a line in results-summary.md."""
import csv
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from common import HERE, OUT, SAMPLE_TSV, STEP1_DIR, STEP2_JSON, STEP3_DIR, call_claude
from step2_shortlist import embed
from step3_pick import SYSTEM

RDIR = OUT / "recall"
RDIR.mkdir(exist_ok=True)
EMB_L = OUT / "motif_emb_e5large.npy"
META = json.loads((OUT / "motif_meta.json").read_text())
SHORT = json.loads(STEP2_JSON.read_text())


def none_events():
    out = {}
    for f in sorted(STEP3_DIR.glob("*.json")):
        d3 = json.loads(f.read_text())
        ns = [e["n"] for e in d3["events"] if e.get("coverage") == "none"]
        if ns:
            out[d3["story_id"]] = ns
    return out


def shortlists(todo):
    from sentence_transformers import SentenceTransformer
    large = SentenceTransformer("intfloat/multilingual-e5-large", device="cpu")
    if EMB_L.exists():
        ML = np.load(EMB_L)
    else:
        ML = embed([m["title"] for m in META], large, "passage: ", bs=64)
        np.save(EMB_L, ML)
    MB = np.load(OUT / "motif_emb_e5base.npy")
    base = SentenceTransformer("intfloat/multilingual-e5-base", device="cpu")
    res = {}
    for sid, ns in todo.items():
        evs = {e["n"]: e for e in json.loads((STEP1_DIR / f"{sid}.json").read_text())["events"]}
        shown = {sl["n"]: {c["idx"] for c in sl["candidates"]} for sl in SHORT[sid]}
        res[sid] = {}
        for n in ns:
            e = evs[n]
            qs = [e["event"], e["event"] + " " + e.get("detail", "")]
            sL = (embed(qs, large, "query: ") @ ML.T).max(0)
            sB = (embed(qs, base, "query: ") @ MB.T).max(0)
            cand = list(dict.fromkeys([int(i) for i in np.argsort(-sL)[:60]] + [int(i) for i in np.argsort(-sB)[:40]]))
            res[sid][n] = [i for i in cand if i not in shown[n]]
    return res


def judge(args):
    sid, cands, text = args
    out = RDIR / f"{sid}.json"
    if out.exists():
        return sid, "cached"
    d1 = json.loads((STEP1_DIR / f"{sid}.json").read_text())
    evs = {e["n"]: e for e in d1["events"]}
    L = [f"Story {sid}:\n{text}\n",
         "Only the events below are to be judged; the other events of the story are not listed.",
         "EVENTS AND CANDIDATES:"]
    for n, idxs in cands.items():
        e = evs[int(n)]
        L.append(f"\nEvent {n}: {e['event']}  [{e.get('detail', '')}]")
        idxs = idxs[:]
        random.Random(int(n)).shuffle(idxs)
        for i in idxs:
            L.append(f"  - {META[i]['id']}: {META[i]['title']}")
    res = call_claude(SYSTEM, "\n".join(L))
    valid = {META[i]["id"] for idxs in cands.values() for i in idxs}
    for ev in res.get("events", []):
        ev["picks"] = [p for p in ev.get("picks", []) if p.get("code") in valid]
        if not ev["picks"]:
            ev["coverage"] = "none"
    res["story_id"] = sid
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    cov = [e.get("coverage") for e in res.get("events", [])]
    return sid, f"{len(cands)} none-events -> exact {cov.count('exact')} / broader {cov.count('broader')} / still none {cov.count('none')}"


if __name__ == "__main__":
    todo = none_events()
    print(sum(map(len, todo.values())), "none events in", len(todo), "stories", flush=True)
    cache = OUT / "recall_shortlists.json"
    if cache.exists():
        sls = json.loads(cache.read_text())
    else:
        sls = shortlists(todo)
        cache.write_text(json.dumps(sls))
    if "--embed-only" in sys.argv:
        sys.exit()
    texts = {r["story_id"]: r["text"] for r in csv.DictReader(open(SAMPLE_TSV), delimiter="\t")}
    with ThreadPoolExecutor(3) as ex:
        for sid, msg in ex.map(judge, [(s, c, texts[s]) for s, c in sls.items()]):
            print(sid, msg, flush=True)
