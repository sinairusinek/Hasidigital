#!/usr/bin/env python3
"""Opus refinement of the PATCHED-definition Sonnet sweep.

For every (story, tag) that Sonnet judged True under the *current* patched
definition (tag_lexicons.definition → tag-definitions-merged.tsv), re-judge
with Opus using the SAME definition text Sonnet saw. Verdicts append to the
LLM cache as model=opus-cli. Resume-safe: an (story, tag) already carrying an
opus-cli row at the current prompt_hash is skipped.

Usage:
  python3 opus_refine_patched.py [--model claude-opus-4-8] [--limit N] [--dry-run]
"""
import argparse, csv, hashlib, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "Authorities" / "integration_tool"))

import tag_data
import tag_lexicons
import tag_audit
from tag_audit import _presence_prompt, _call_claude_cli, _append_llm_cache

CACHE = REPO / "editions" / "tag-audit" / ".cache" / "llm-presence.tsv"


def phash(tag):
    return hashlib.md5(
        _presence_prompt(tag, tag_lexicons.definition(tag)).encode()
    ).hexdigest()[:8]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--limit", type=int, default=0, help="cap calls (smoke test)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    # CLAUDE_CLI_MODEL is bound at tag_audit import time, so override the
    # module global directly (env var alone would be too late).
    os.environ["CLAUDE_CLI_MODEL"] = args.model
    tag_audit.CLAUDE_CLI_MODEL = args.model

    rows = list(csv.DictReader(open(CACHE), delimiter="\t"))
    tags = sorted({r["tag"] for r in rows if r["model"] == "claude-cli"})
    ph = {t: phash(t) for t in tags}

    sonnet_true = {
        (r["story_id"], r["tag"])
        for r in rows
        if r["model"] == "claude-cli"
        and r["tag"] in ph
        and r["prompt_hash"] == ph[r["tag"]]
        and r["applies"] == "True"
        and not r["tag"].startswith("test:")
    }
    # resume: skip those already opus-judged at the CURRENT prompt_hash
    opus_at_hash = {
        (r["story_id"], r["tag"])
        for r in rows
        if r["model"] == "opus-cli" and r.get("prompt_hash") == ph.get(r["tag"])
    }
    need = sorted(sonnet_true - opus_at_hash)
    if args.limit:
        need = need[: args.limit]
    print(f"Sonnet-True (patched): {len(sonnet_true)} | "
          f"already opus@hash: {len(sonnet_true & opus_at_hash)} | "
          f"to judge now: {len(need)} | model={args.model}")
    if args.dry_run or not need:
        return

    stories = tag_data.load_stories("core")
    by_id = {s["story_id"]: s for s in stories}

    agree = disagree = errors = 0
    out_rows = []
    start = time.time()
    for i, (sid, tag) in enumerate(need, 1):
        story = by_id.get(sid)
        if story is None:
            errors += 1
            print(f"[{i}/{len(need)}] SKIP story not in core: {sid}")
            continue
        definition = tag_lexicons.definition(tag)
        prompt = _presence_prompt(tag, definition)
        h = hashlib.md5(prompt.encode()).hexdigest()[:8]
        try:
            applies, conf, reason = _call_claude_cli(prompt, story["text"][:12000])
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            _append_llm_cache({
                "story_id": sid, "tag": tag, "prompt_hash": h, "model": "opus-cli",
                "applies": str(applies), "confidence": conf, "reasoning": reason, "ts": ts,
            })
            verdict = "AGREE" if applies else "DISAGREE"
            agree += applies
            disagree += (not applies)
        except Exception as e:
            errors += 1
            applies, conf, reason = None, "", str(e)[:120]
            verdict = f"ERROR:{type(e).__name__}"
        out_rows.append({
            "story_id": sid, "tag": tag, "opus_applies": str(applies),
            "opus_confidence": conf, "verdict": verdict, "opus_reasoning": reason,
        })
        el = time.time() - start
        rate = i / el if el else 0
        eta = (len(need) - i) / rate if rate else 0
        print(f"[{i}/{len(need)}] {verdict:9s} {tag[:34]:34s} {sid[:24]:24s} "
              f"| {rate:.2f}/s eta={eta/60:.0f}m")

    out = REPO / "editions" / "tag-audit" / "opus-refine-patched-results.tsv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()),
                           delimiter="\t", lineterminator="\n")
        w.writeheader(); w.writerows(out_rows)
    n = agree + disagree
    print(f"\n=== Opus refinement (patched) done ===")
    print(f"AGREE {agree}/{n} = {agree/n*100:.1f}%" if n else "no verdicts")
    print(f"DISAGREE {disagree} | errors {errors}")
    print(f"Results: {out}")


if __name__ == "__main__":
    main()
