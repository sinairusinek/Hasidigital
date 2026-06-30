#!/usr/bin/env python3
"""Build a BLIND human-adjudication anchor to measure Opus's own accuracy.

Opus is the pipeline's gold standard but was never validated against expert
human judgment. This samples 100 cases (50 Opus-confirm, 50 Opus-reject) at
the current patched prompt_hash, spread across categories, and writes:

  human-adjudication-anchor.tsv  — BLIND review sheet (no model verdict shown),
      columns: case_id, story_id, tag, definition, text_excerpt,
      `human_applies (yes/no)`, human_notes. An expert fills the verdict.
  human-adjudication-key.tsv     — the held-back Opus + Sonnet verdicts.

Then score with score_human_anchor.py. Blind + interleaved order so the
reviewer can't infer the model's verdict.

Usage:  python3 build_human_anchor.py [--seed 42] [--per-side 50]
"""
import argparse, csv, hashlib, random, sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "Authorities" / "integration_tool"))
import tag_lexicons, tag_data
from tag_audit import _presence_prompt

AUDIT = REPO / "editions" / "tag-audit"
CACHE = AUDIT / ".cache" / "llm-presence.tsv"


def phash(tag):
    return hashlib.md5(
        _presence_prompt(tag, tag_lexicons.definition(tag)).encode()).hexdigest()[:8]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--per-side", type=int, default=50)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(CACHE), delimiter="\t"))
    tags = sorted({r["tag"] for r in rows if r["model"] in ("claude-cli", "opus-cli")})
    H = {t: phash(t) for t in tags}
    opus, sonnet = {}, {}
    for r in rows:
        if r.get("prompt_hash") != H.get(r["tag"]):
            continue
        k = (r["story_id"], r["tag"])
        if r["model"] == "opus-cli":
            opus[k] = (r["applies"] == "True", r["confidence"], r["reasoning"])
        elif r["model"] == "claude-cli":
            sonnet[k] = r["applies"] == "True"

    confirms = [k for k, v in opus.items() if v[0]]
    rejects = [k for k, v in opus.items() if not v[0]]
    rng = random.Random(args.seed)

    def spread(keys, n):
        bycat = {}
        for k in keys:
            bycat.setdefault(k[1].split(":")[0], []).append(k)
        for v in bycat.values():
            rng.shuffle(v)
        out, cats = [], sorted(bycat)
        while len(out) < n and any(bycat.values()):
            for c in cats:
                if bycat[c]:
                    out.append(bycat[c].pop())
                if len(out) >= n:
                    break
        return out

    sample = [("confirm", k) for k in spread(confirms, args.per_side)] + \
             [("reject", k) for k in spread(rejects, args.per_side)]
    rng.shuffle(sample)

    stories = {s["story_id"]: s for s in tag_data.load_stories("core")}

    def excerpt(sid, n=1500):
        t = stories.get(sid, {}).get("text", "")
        return (t[:n] + " …") if len(t) > n else t

    blind, key = [], []
    for i, (_, (sid, tag)) in enumerate(sample, 1):
        cid = f"ADJ-{i:03d}"
        blind.append({"case_id": cid, "story_id": sid, "tag": tag,
                      "definition": tag_lexicons.definition(tag),
                      "text_excerpt": excerpt(sid),
                      "human_applies (yes/no)": "", "human_notes": ""})
        a, c, reason = opus[(sid, tag)]
        key.append({"case_id": cid, "story_id": sid, "tag": tag,
                    "opus_applies": a, "opus_confidence": c,
                    "sonnet_applies": sonnet.get((sid, tag), ""),
                    "opus_reasoning": reason})

    def write(path, data, cols):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", lineterminator="\n")
            w.writeheader(); w.writerows(data)

    write(AUDIT / "human-adjudication-anchor.tsv", blind,
          ["case_id", "story_id", "tag", "definition", "text_excerpt",
           "human_applies (yes/no)", "human_notes"])
    write(AUDIT / "human-adjudication-key.tsv", key,
          ["case_id", "story_id", "tag", "opus_applies", "opus_confidence",
           "sonnet_applies", "opus_reasoning"])
    print(f"Wrote {len(sample)} blind cases "
          f"({args.per_side} confirm / {args.per_side} reject).")
    print("category spread:", dict(Counter(k[1].split(':')[0] for _, k in sample)))


if __name__ == "__main__":
    main()
