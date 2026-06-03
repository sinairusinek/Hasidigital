"""Propagate tag-audit verdicts across near-duplicate stories.

For a category whose suggested-taggings CSV has been reviewed (or even just
auto-confirmed by the audit), this script:

  1. Reads `<cat>-suggested-taggings.csv` (decision = confirm / reject).
  2. Reads `editions/tag-audit/story-duplicates.tsv` (cross-edition twins).
  3. For each verdict on story A, propagates the same decision to every twin B
     above threshold.
  4. Cross-checks the LLM-presence cache (`.cache/llm-presence.tsv`): if B was
     ALREADY adjudicated for the same tag with the OPPOSITE verdict, emit a
     conflict row for PI review rather than auto-propagating.
  5. Writes `editions/tag-audit/<cat>/<cat>-duplicate-propagations.tsv` with
     one row per propagation (action ∈ {auto-confirm, auto-reject, conflict}).

CLI:
    python3 tag_propagate.py <category> [--threshold 0.98]

The PI reviews the conflicts column and accepts the rest before XML write-back.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import tag_lexicons  # noqa: E402
import tag_audit     # noqa: E402

AUDIT_DIR = Path(tag_audit.AUDIT_DIR)
DUPES_PATH = AUDIT_DIR / "story-duplicates.tsv"


def _load_duplicates(threshold: float):
    """Return {story_id: [(twin_id, sim), …]} for pairs above threshold."""
    if not DUPES_PATH.exists():
        sys.exit(f"Missing {DUPES_PATH} — run `tag_duplicates.py build` first.")
    twins: dict[str, list[tuple[str, float]]] = {}
    with open(DUPES_PATH, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            sim = float(r["sim"])
            if sim < threshold:
                continue
            twins.setdefault(r["story_a"], []).append((r["story_b"], sim))
            twins.setdefault(r["story_b"], []).append((r["story_a"], sim))
    return twins


def _load_suggestions(category: str):
    """Yield {tag, story_id, decision, ...} rows from <cat>-suggested-taggings.csv.
    The default `decision` column is pre-set to `confirm` by tag_review; the PI
    only edits rejects."""
    path = AUDIT_DIR / category / f"{category}-suggested-taggings.csv"
    if not path.exists():
        sys.exit(f"Missing {path} — run `tag_review.py {category}` first.")
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            yield r


def _llm_verdict_for(cache, story_id: str, tag: str) -> str | None:
    """Look up the cached LLM verdict for (story, tag) regardless of which model.
    Returns 'confirm' / 'reject' / None."""
    phash = hashlib.md5(tag_audit._presence_prompt(tag, tag_lexicons.definition(tag)).encode()).hexdigest()[:8]
    # Try opus-cli first (hand-judged), then any model that adjudicated it.
    for (sid, t, ph, model), row in cache.items():
        if sid == story_id and t == tag and ph == phash:
            applies = str(row.get("applies", "")).strip().lower() in ("true", "1", "yes")
            return "confirm" if applies else "reject"
    return None


def propagate(category: str, threshold: float = 0.98) -> Path:
    twins = _load_duplicates(threshold)
    cache = tag_audit._load_llm_cache()

    out_rows = []
    counts = {"auto-confirm": 0, "auto-reject": 0, "conflict": 0, "no-twin": 0}

    for sug in _load_suggestions(category):
        decision = (sug.get("decision") or "").strip().lower()
        if decision not in ("confirm", "reject"):
            continue
        tag = sug.get("tag") or sug.get("Tag") or ""
        story_id = sug.get("story_id") or ""
        if not tag or not story_id:
            continue
        for twin_id, sim in twins.get(story_id, []):
            existing = _llm_verdict_for(cache, twin_id, tag)
            if existing is not None and existing != decision:
                action = "conflict"
            else:
                action = f"auto-{decision}"
            counts[action] += 1
            out_rows.append({
                "tag": tag,
                "source_story": story_id,
                "source_decision": decision,
                "twin_story": twin_id,
                "twin_existing_verdict": existing or "",
                "sim": sim,
                "action": action,
            })
        if story_id not in twins:
            counts["no-twin"] += 1

    out_path = AUDIT_DIR / category / f"{category}-duplicate-propagations.tsv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        cols = ["tag", "source_story", "source_decision", "twin_story",
                "twin_existing_verdict", "sim", "action"]
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        w.writeheader()
        w.writerows(sorted(out_rows, key=lambda r: (r["action"] != "conflict",
                                                    r["tag"], r["source_story"])))
    print(f"Wrote {out_path}")
    print(f"  auto-confirm: {counts['auto-confirm']}")
    print(f"  auto-reject:  {counts['auto-reject']}")
    print(f"  conflict:     {counts['conflict']}  (PI must review)")
    print(f"  source stories with no twin: {counts['no-twin']}")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("category")
    ap.add_argument("--threshold", type=float, default=0.98)
    args = ap.parse_args()
    propagate(args.category, threshold=args.threshold)


if __name__ == "__main__":
    main()
