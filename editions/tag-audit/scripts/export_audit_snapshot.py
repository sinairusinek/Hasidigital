#!/usr/bin/env python3
"""Export a committed snapshot of the audit verdicts for the Tag Audit page.

The authoritative LLM cache (.cache/llm-presence.tsv) is git-ignored, so the
Streamlit-Cloud deployment can't see it. This writes the subset the dashboard
needs — every claude-cli and opus-cli verdict at the CURRENT patched
prompt_hash — to a committed file the page falls back to when the live cache
is absent. Same columns as the cache, so the page logic is unchanged.

Re-run + commit this after each batch of the precision audit to refresh what
Cloud shows.

Usage:  python3 editions/tag-audit/scripts/export_audit_snapshot.py
"""
import csv
import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "Authorities" / "integration_tool"))
import tag_lexicons
from tag_audit import _presence_prompt

AUDIT = REPO / "editions" / "tag-audit"
CACHE = AUDIT / ".cache" / "llm-presence.tsv"
SNAPSHOT = AUDIT / "audit-cache-snapshot.tsv"
COLS = ["story_id", "tag", "prompt_hash", "model", "applies",
        "confidence", "reasoning", "ts"]


def phash(tag):
    return hashlib.md5(
        _presence_prompt(tag, tag_lexicons.definition(tag)).encode()).hexdigest()[:8]


def main():
    if not CACHE.exists():
        sys.exit(f"No cache at {CACHE}")
    rows = list(csv.DictReader(open(CACHE), delimiter="\t"))
    tags = sorted({r["tag"] for r in rows if r["model"] in ("claude-cli", "opus-cli")})
    H = {t: phash(t) for t in tags}

    kept = [r for r in rows
            if r["model"] in ("claude-cli", "opus-cli")
            and r.get("prompt_hash") == H.get(r["tag"])]
    with open(SNAPSHOT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for r in kept:
            w.writerow({c: r.get(c, "") for c in COLS})

    from collections import Counter
    by = Counter((r["model"], r["applies"]) for r in kept)
    print(f"Wrote {len(kept):,} current-hash rows → {SNAPSHOT.name}")
    for (m, a), n in sorted(by.items()):
        print(f"  {m:10s} applies={a:5s} {n:,}")


if __name__ == "__main__":
    main()
