"""Step 2: MOMFER-style retrieval. Embed every motif title (Thompson's revised TMI
+ Noy's motifs that have no Thompson counterpart) with multilingual-e5-base and, for
every step-1 event, keep the top-K nearest motifs as a shortlist for step 3.

Each motif carries: origin (tmi / noy_only), jewish (Neuman flag or Noy match),
n_cultures (Mas"a attestations), used later in the report but NOT shown to the picker."""
import csv
import json
import re
import sys

import numpy as np

from common import MOTIFS, OUT, STEP1_DIR, STEP2_JSON

csv.field_size_limit(sys.maxsize)
K = 25
EMB = OUT / "motif_emb_e5base.npy"
META = OUT / "motif_meta.json"


def clean(t):
    t = re.sub(r"\((?:Cf|cf)\.[^)]*\)", "", t)
    return " ".join(t.split()).strip(" .")


def load_motifs():
    rows = list(csv.DictReader(open(MOTIFS / "jewish_motifs_unified.tsv"), delimiter="\t"))
    jew = {r["motif"] for r in rows if r["source"] == "tmi"}
    cultures = {}
    for r in csv.DictReader(open(MOTIFS / "thompson_masa_attestations.tsv"), delimiter="\t"):
        cultures[r["motif"]] = len([c for c in r["cultures"].split(";") if c.strip()]) if r["cultures"] else 0
    meta = []
    for r in csv.DictReader(open(MOTIFS / "tmi_with_noy.tsv"), delimiter="\t"):
        m = r["motif"]
        if re.fullmatch(r"[A-Z]", m) or not r["title"].strip():
            continue
        meta.append({"id": m, "origin": "tmi", "title": clean(r["title"]),
                     "jewish": int(m in jew), "n_cultures": cultures.get(m)})
    seen = set()
    for r in rows:
        src, m = r["source"], r["motif"]
        if src != "tmi" and (m, r["title"]) not in seen:
            seen.add((m, r["title"]))
            meta.append({"id": "Noy " + m + ("" if sum(1 for x in seen if x[0] == m) == 1 else f"#{sum(1 for x in seen if x[0] == m)}"), "origin": src, "title": clean(r["title"]),
                         "jewish": 1, "n_cultures": None})
    return meta


def embed(texts, model, prefix, bs=128):
    out = []
    for i in range(0, len(texts), bs):
        out.append(model.encode([prefix + t for t in texts[i:i + bs]], normalize_embeddings=True,
                                batch_size=bs, show_progress_bar=False))
        if i % (bs * 40) == 0:
            print(f"  {i}/{len(texts)}", flush=True)
    return np.vstack(out).astype(np.float32)


def main():
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("intfloat/multilingual-e5-base", device="cpu")
    if EMB.exists() and META.exists():
        meta = json.loads(META.read_text())
        M = np.load(EMB)
    else:
        meta = load_motifs()
        print(len(meta), "motifs;", sum(m["origin"] != "tmi" for m in meta), "Noy-only/uncertain")
        M = embed([m["title"] for m in meta], model, "passage: ")
        np.save(EMB, M)
        META.write_text(json.dumps(meta, ensure_ascii=False))
    shortlists = {}
    for f in sorted(STEP1_DIR.glob("*.json")):
        d = json.loads(f.read_text())
        evs = d.get("events", [])
        if not evs:
            continue
        q1 = embed([e["event"] for e in evs], model, "query: ")
        q2 = embed([e["event"] + " " + e.get("detail", "") for e in evs], model, "query: ")
        S = np.maximum(q1 @ M.T, q2 @ M.T)
        sl = []
        for e, row in zip(evs, S):
            top = np.argsort(-row)[:K]
            sl.append({"n": e["n"], "event": e["event"],
                       "candidates": [{"idx": int(i), "sim": round(float(row[i]), 3)} for i in top]})
        shortlists[d["story_id"]] = sl
    STEP2_JSON.write_text(json.dumps(shortlists, ensure_ascii=False))
    print(len(shortlists), "stories shortlisted ->", STEP2_JSON)


if __name__ == "__main__":
    main()
