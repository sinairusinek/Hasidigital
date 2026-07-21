"""
Run the new 5-tier (+ collective + confidence) annotation on all stories
from the 9 previously-tagged editions, via the Anthropic SDK.

Cache lives at editions/women-llm-results-v2.tsv (separate from the legacy
binary-scheme cache at women-llm-results.tsv, which is left untouched).

Force=False: the 50-story sample we already ran is reused as-is (same
criteria hash); only the remaining ~600 get fresh API calls.
"""
import csv, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))

from women_data import load_stories
from women_llm import annotate_batch, load_criteria, criteria_hash, get_cached_results

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(PROJECT_ROOT, "editions", "women-5tier-9editions-summary.tsv")

# 1) Identify the 9 already-tagged editions and gather their stories
all_stories = load_stories()
annotated_eds = sorted({s["edition"] for s in all_stories if s["category"] != "no-women"})
target_stories = [s for s in all_stories if s["edition"] in annotated_eds]

print(f"Target editions ({len(annotated_eds)}): {', '.join(annotated_eds)}")
print(f"Total stories: {len(target_stories)}")

criteria = load_criteria()
chash = criteria_hash(criteria)
print(f"Criteria hash: {chash}\n")

# 2) Run (cached calls are free; new ones go through SDK)
print("Running Claude annotation (SDK)...")
results = annotate_batch(
    target_stories,
    criteria=criteria,
    force=False,
    models=(True, False),  # Claude only
    progress_callback=lambda i, t: print(f"  {i}/{t}", end="\r", flush=True),
)
print()

# 3) Build per-story comparison row: old human (binary) vs new Claude (5-tier)
def old_to_5tier(old_human: str) -> str:
    return {"no-women":"no-women", "minor":"minor-character",
            "major":"major-character", "major+minor":"major-character"}.get(old_human, old_human)

# Need the OLD human binary tag from the legacy comparison TSV
old_path = os.path.join(PROJECT_ROOT, "editions", "women-annotation-comparison.tsv")
old_by_id = {}
with open(old_path, encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        old_by_id[r["story_id"]] = r

rows_out = []
for s, r in zip(target_stories, results):
    sid = s["story_id"]
    old = old_by_id.get(sid, {})
    rows_out.append({
        "story_id": sid,
        "edition": s["edition"],
        "old_human_binary":     old.get("human", ""),
        "old_claude_binary":    old.get("claude", ""),
        "old_gemini_binary":    old.get("gemini", ""),
        "new_claude_5tier":     r.get("claude_category", ""),
        "new_collective":       r.get("claude_collective", ""),
        "new_confidence":       r.get("claude_confidence", ""),
        "new_reasoning":        r.get("claude_reasoning", ""),
    })

with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()), delimiter="\t")
    w.writeheader()
    w.writerows(rows_out)
print(f"Wrote: {OUT}\n")

# 4) Headline summary
total = len(rows_out)
non_error = [r for r in rows_out if r["new_claude_5tier"] not in ("error", "")]
print("="*72)
print(f"NEW 5-TIER DISTRIBUTION  ({len(non_error)} non-error, of {total})")
print("="*72)
cats = Counter(r["new_claude_5tier"] for r in non_error)
for cat in ["no-women","mention-only","minor-character","catalyst-character","major-character"]:
    n = cats.get(cat, 0)
    print(f"  {cat:<22} {n:>5}  ({n/len(non_error)*100:>5.1f}%)")

print()
print("CONFIDENCE")
print("-"*40)
confs = Counter(r["new_confidence"] for r in non_error)
for c in ["high","medium","low"]:
    n = confs.get(c, 0)
    print(f"  {c:<10} {n:>5}  ({n/len(non_error)*100:>5.1f}%)")

print()
print(f"COLLECTIVE-WOMEN flag set: "
      f"{sum(1 for r in non_error if r['new_collective']=='True')}/{len(non_error)}")

print()
print("OLD HUMAN (binary) → NEW CLAUDE (5-tier)")
print("-"*60)
combos = Counter((r["old_human_binary"], r["new_claude_5tier"]) for r in non_error)
for (h, c), n in sorted(combos.items(), key=lambda x: -x[1]):
    print(f"  {h:<13} → {c:<22} {n:>4}")

print()
print("PER-EDITION 5-TIER COUNTS")
print("-"*72)
print(f"{'edition':<26}{'no-w':>6}{'ment':>6}{'minor':>6}{'cata':>6}{'major':>6}{'low':>6}")
for ed in annotated_eds:
    ed_rows = [r for r in non_error if r["edition"] == ed]
    c = Counter(r["new_claude_5tier"] for r in ed_rows)
    low = sum(1 for r in ed_rows if r["new_confidence"]=="low")
    print(f"  {ed:<24}{c.get('no-women',0):>6}{c.get('mention-only',0):>6}"
          f"{c.get('minor-character',0):>6}{c.get('catalyst-character',0):>6}"
          f"{c.get('major-character',0):>6}{low:>6}")
