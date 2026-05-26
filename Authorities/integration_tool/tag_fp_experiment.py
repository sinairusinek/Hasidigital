"""
EXPERIMENT (kept separate from the RA review docs): false-positive detection for
SEMANTIC tags.

The main audit only flags false positives for lexical-strong tags (it needs a
keyword to test against). This experiment instead asks the LLM, for each story
that *already carries* a semantic tag, "does this tag really apply?" — reading the
full story text. Stories the LLM judges 'no' are false-positive candidates (possible
mistags or boundary cases).

Output: editions/tag-audit/experiments/semantic-fp-check.tsv  (NOT part of any PI
review doc). Run when no other Gemini job is active:

    python3 tag_fp_experiment.py                      # default cluster
    python3 tag_fp_experiment.py practice:devekut practice:meditation
"""
import os
import sys
import csv

import tag_data
import tag_lexicons
import tag_audit
from config import PROJECT_DIR

OUT_DIR = os.path.join(PROJECT_DIR, "editions", "tag-audit", "experiments")

# Default: the overlapping "inner-life" semantic cluster (high mutual similarity)
DEFAULT_TAGS = [
    "practice:devekut", "practice:meditation", "practice:healing_of_the_soul",
    "practice:solitude", "practice:asceticism",
]


def run(tags, model="gemini-3"):
    os.environ.setdefault("TAG_AUDIT_MODEL", model)
    stories = tag_data.load_stories("core")
    by_id = {s["story_id"]: s for s in stories}
    cache = tag_audit._load_llm_cache()
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "semantic-fp-check.tsv")
    rows, summary = [], []
    for tag in tags:
        definition = tag_lexicons.definition(tag)
        tagged = [s for s in stories if tag in s["tags"]]
        flagged = 0
        for s in tagged:
            applies, conf, reason = tag_audit._llm_presence(s, tag, definition, cache, model=model)
            if not applies:
                flagged += 1
                rows.append({
                    "tag": tag, "story_id": s["story_id"], "edition": s["edition"],
                    "llm_applies": applies, "confidence": conf, "reasoning": reason,
                    "excerpt": s["text"][:220].replace("\n", " "),
                    "agree?": "", "notes": "",
                })
        summary.append((tag, len(tagged), flagged))
        print(f"{tag:34s} tagged={len(tagged):3d}  flagged-as-FP={flagged}")
    if rows:
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
            w.writeheader(); w.writerows(rows)
        print(f"\nWrote {out}: {len(rows)} false-positive candidates")
    else:
        print("\nNo false-positive candidates flagged.")
    return summary


if __name__ == "__main__":
    tags = sys.argv[1:] or DEFAULT_TAGS
    run(tags)
