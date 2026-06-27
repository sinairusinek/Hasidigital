#!/usr/bin/env python3
"""Run Opus CLI on a sample of Sonnet verdicts to compute agreement rate.

Reads editions/tag-audit/opus-quality-sample.tsv (or another --sample file),
calls Opus 4.7 via claude CLI for each (story_id, tag) using the same
adjudication prompt as the audit pipeline, and writes verdicts back to the
LLM cache plus an agreement summary.

Usage:
  python3 opus_check.py [--sample <path>]
"""
import argparse, csv, hashlib, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "Authorities" / "integration_tool"))

import tag_data
from tag_audit import _presence_prompt, _call_claude_cli, _append_llm_cache

# Force Opus
os.environ["CLAUDE_CLI_MODEL"] = "claude-opus-4-7"

DEFAULT_SAMPLE = REPO / "editions" / "tag-audit" / "opus-quality-sample.tsv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default=str(DEFAULT_SAMPLE))
    args = ap.parse_args()

    sample_rows = list(csv.DictReader(open(args.sample), delimiter="\t"))
    print(f"Sample: {len(sample_rows)} rows")

    # Load stories + tag definitions
    stories = tag_data.load_stories("core")
    story_by_id = {s["story_id"]: s for s in stories}

    # Tag definitions from the Drive sheet (refined_definition or draft_definition)
    tag_defs = {}
    defs_path = REPO / "editions" / "tag-audit" / "tag-definitions.tsv"
    if defs_path.exists():
        for r in csv.DictReader(open(defs_path), delimiter="\t"):
            tag_defs[r["tag"]] = r["definition"]
    print(f"Loaded {len(tag_defs)} tag definitions")

    results = []
    agree = disagree = errors = 0
    start = time.time()

    for i, row in enumerate(sample_rows, 1):
        sid = row["story_id"]; tag = row["tag"]
        if sid not in story_by_id:
            print(f"[{i}/{len(sample_rows)}] SKIP — story not in core: {sid}")
            errors += 1
            continue
        story = story_by_id[sid]
        # Prefer Drive-sheet definition; fall back to generic if missing.
        definition = tag_defs.get(tag, "")
        if not definition:
            sub = tag.split(":", 1)[-1].replace("_", " ")
            definition = f"The story depicts or substantially discusses {sub}."
        prompt = _presence_prompt(tag, definition)
        phash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        try:
            applies, conf, reason = _call_claude_cli(prompt, story["text"][:12000])
            # Cache it
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            _append_llm_cache({
                "story_id": sid, "tag": tag, "prompt_hash": phash, "model": "opus-cli",
                "applies": str(applies), "confidence": conf, "reasoning": reason, "ts": ts,
            })
            if applies:
                agree += 1; verdict = "AGREE"
            else:
                disagree += 1; verdict = "DISAGREE"
        except Exception as e:
            errors += 1; verdict = f"ERROR: {type(e).__name__}"
            applies, conf, reason = None, "", str(e)[:120]
        results.append({
            "story_id": sid, "tag": tag,
            "sonnet_applies": "True", "sonnet_confidence": row.get("sonnet_confidence", ""),
            "opus_applies": str(applies) if applies is not None else "",
            "opus_confidence": conf, "opus_reasoning": reason, "verdict": verdict,
        })
        elapsed = time.time() - start
        rate = i / elapsed if elapsed else 0
        eta = (len(sample_rows) - i) / rate if rate else 0
        print(f"[{i}/{len(sample_rows)}] {verdict:8s} {tag[:35]:35s} {sid[:25]:25s} | rate={rate:.2f}/s eta={eta:.0f}s")

    out = REPO / "editions" / "tag-audit" / "opus-quality-results.tsv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()), delimiter="\t", lineterminator="\n")
        w.writeheader(); w.writerows(results)

    n = agree + disagree
    print(f"\n=== Opus quality sample done ===")
    print(f"Agreement: {agree}/{n} = {agree/n*100:.1f}%" if n else "no verdicts")
    print(f"Disagreements (Opus says False on Sonnet True): {disagree}")
    print(f"Errors: {errors}")
    print(f"Results: {out}")


if __name__ == "__main__":
    main()
