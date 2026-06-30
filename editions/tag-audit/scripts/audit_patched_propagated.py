#!/usr/bin/env python3
"""Direct Opus audit of the PATCHED propagated adds (L5′ propagation pass).

L8 showed near-duplicate propagation is the main over-tagging source (64% of
propagated old inserts failed direct re-judgment). The 280 propagated tags in
the patched writeback (llm-confirmed-verdicts-patched.tsv, source=propagated)
were never directly judged either — they were copied from Opus-confirmed
sources to near-duplicate stories. This judges each directly with Opus-4.7
under the patched definition; Opus-False ⇒ removal candidate.

Resume-safe (skips pairs already opus@patched-hash); circuit-breaker on a
throttle wall. Verdicts append to the cache as model=opus-cli.

Usage:  python3 audit_patched_propagated.py [--model claude-opus-4-7] [--limit N] [--dry-run]
"""
import argparse, csv, hashlib, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "Authorities" / "integration_tool"))
import tag_data, tag_lexicons, tag_audit
from tag_audit import _presence_prompt, _call_claude_cli, _append_llm_cache

AUDIT = REPO / "editions" / "tag-audit"
CACHE = AUDIT / ".cache" / "llm-presence.tsv"
ADDS = AUDIT / "llm-confirmed-verdicts-patched.tsv"
OUT = AUDIT / "patched-propagated-audit.tsv"


def phash(tag):
    return hashlib.md5(
        _presence_prompt(tag, tag_lexicons.definition(tag)).encode()).hexdigest()[:8]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-opus-4-7")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    os.environ["CLAUDE_CLI_MODEL"] = args.model
    tag_audit.CLAUDE_CLI_MODEL = args.model

    targets = [(r["story_id"], r["tag"]) for r in
               csv.DictReader(open(ADDS), delimiter="\t") if r["source"] == "propagated"]
    H = {t: phash(t) for _, t in targets}
    rows = list(csv.DictReader(open(CACHE), delimiter="\t"))
    done = {(r["story_id"], r["tag"]) for r in rows
            if r["model"] == "opus-cli" and r.get("prompt_hash") == H.get(r["tag"])}
    need = [(s, t) for (s, t) in targets if (s, t) not in done]
    if args.limit:
        need = need[: args.limit]
    print(f"patched propagated adds: {len(targets)} | already opus@hash: "
          f"{len(targets) - len([1 for s,t in targets if (s,t) not in done])} | "
          f"to judge now: {len(need)} | model={args.model}")
    if args.dry_run or not need:
        return

    by_id = {s["story_id"]: s for s in tag_data.load_stories("core")}
    confirm = reject = errors = consec = 0
    out_rows = []
    start = time.time()
    for i, (sid, tag) in enumerate(need, 1):
        story = by_id.get(sid)
        if story is None:
            errors += 1
            print(f"[{i}/{len(need)}] SKIP not in core: {sid}")
            continue
        prompt = _presence_prompt(tag, tag_lexicons.definition(tag))
        h = hashlib.md5(prompt.encode()).hexdigest()[:8]
        try:
            applies, conf, reason = _call_claude_cli(prompt, story["text"][:12000])
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            _append_llm_cache({"story_id": sid, "tag": tag, "prompt_hash": h,
                               "model": "opus-cli", "applies": str(applies),
                               "confidence": conf, "reasoning": reason, "ts": ts})
            verdict = "CONFIRM" if applies else "REJECT"
            confirm += applies; reject += (not applies); consec = 0
        except Exception as e:
            errors += 1; consec += 1
            applies, conf, reason = None, "", str(e)[:120]
            verdict = f"ERROR:{type(e).__name__}"
        if consec >= 12:
            print(f"\n!! {consec} consecutive errors — throttle wall. Stopping at {i}/{len(need)}.")
            break
        out_rows.append({"story_id": sid, "tag": tag, "opus_applies": str(applies),
                         "opus_confidence": conf, "verdict": verdict, "opus_reasoning": reason})
        el = time.time() - start; rate = i / el if el else 0
        print(f"[{i}/{len(need)}] {verdict:8s} {tag[:32]:32s} {sid[:22]:22s} "
              f"| {rate:.2f}/s eta={((len(need)-i)/rate/60) if rate else 0:.0f}m")

    prior = []
    if OUT.exists():
        seen = {(o["story_id"], o["tag"]) for o in out_rows}
        prior = [r for r in csv.DictReader(open(OUT), delimiter="\t")
                 if (r["story_id"], r["tag"]) not in seen]
    allrows = prior + out_rows
    if allrows:
        with open(OUT, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["story_id", "tag", "opus_applies",
                               "opus_confidence", "verdict", "opus_reasoning"],
                               delimiter="\t", lineterminator="\n")
            w.writeheader(); w.writerows(allrows)
    n = confirm + reject
    print(f"\n=== patched propagated audit (batch) ===")
    print(f"CONFIRM {confirm}/{n} = {confirm/n*100:.0f}%" if n else "no verdicts")
    print(f"REJECT {reject} (removal evidence) | errors {errors} | results: {OUT.name}")


if __name__ == "__main__":
    main()
