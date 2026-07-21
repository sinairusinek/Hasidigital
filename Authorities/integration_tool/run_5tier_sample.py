"""
Run the new 5-tier criteria on a 50-story sample from the previously-tagged
editions: 30 stories that had disagreements + 20 that all three (human, Claude,
Gemini) agreed on. Output a side-by-side comparison.
"""
import csv, os, random, sys
sys.path.insert(0, os.path.dirname(__file__))

from women_data import load_stories
from women_llm import annotate_story, load_criteria

random.seed(42)

OLD_COMPARISON = os.path.join(os.path.dirname(__file__), "..", "..",
                              "editions", "women-annotation-comparison.tsv")
OUT = os.path.join(os.path.dirname(__file__), "..", "..",
                   "editions", "women-5tier-sample.tsv")

# Old binary→5-tier translation for the human gold-standard tags
def old_to_5tier(old: str) -> str:
    return {
        "no-women":   "no-women",
        "minor":      "minor-character",   # under old scheme — coarse
        "major":      "major-character",
        "major+minor":"major-character",
    }.get(old, old)

# 1) Load old comparison
old_rows = []
with open(OLD_COMPARISON, encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        if r["claude"] in ("error", "") or r["gemini"] in ("error", ""):
            continue
        old_rows.append(r)

agreements = [r for r in old_rows if r["human"] == r["claude"] == r["gemini"]]
disagreements = [r for r in old_rows if not (r["human"] == r["claude"] == r["gemini"])]

print(f"Pool: {len(agreements)} agreements, {len(disagreements)} disagreements")

# 2) Stratified sample — try to cover all the disagreement sub-types we saw
disagree_sample = []
buckets = {}
for r in disagreements:
    key = (r["human"], r["claude"], r["gemini"])
    buckets.setdefault(key, []).append(r)
# Pick proportional-ish across buckets, prioritising the largest patterns
sorted_buckets = sorted(buckets.items(), key=lambda x: -len(x[1]))
target_disagree = 30
for key, lst in sorted_buckets:
    if len(disagree_sample) >= target_disagree:
        break
    take = max(1, round(target_disagree * len(lst) / len(disagreements)))
    take = min(take, len(lst), target_disagree - len(disagree_sample))
    disagree_sample.extend(random.sample(lst, take))

agree_sample = random.sample(agreements, 20)
sample = disagree_sample + agree_sample
print(f"Sampled: {len(disagree_sample)} disagreements + {len(agree_sample)} agreements = {len(sample)}")

# 3) Build story lookup by id for full-text access
stories = {s["story_id"]: s for s in load_stories()}
sample_stories = [stories[r["story_id"]] for r in sample if r["story_id"] in stories]
print(f"Story texts loaded: {len(sample_stories)}")

# 4) Run new 5-tier annotation (Claude only, force=True so cache miss)
criteria = load_criteria()
print(f"Criteria loaded ({len(criteria)} chars)")
print("Running Claude (CLI, ~2-3s/story)...\n")

results_by_id = {}
for i, s in enumerate(sample_stories, 1):
    print(f"  {i}/{len(sample_stories)}  {s['story_id']}", end="\r", flush=True)
    r = annotate_story(s, criteria=criteria, force=True, models=(True, False))
    results_by_id[s["story_id"]] = r
print("\nDone.\n")

# 5) Write side-by-side TSV
out_cols = [
    "story_id", "edition",
    "old_human_binary", "old_human_5tier_mapped",
    "old_claude_binary", "old_gemini_binary",
    "new_claude_5tier", "new_collective", "new_confidence",
    "old_was_disagreement", "new_reasoning",
    "story_text",
]
with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=out_cols, delimiter="\t")
    w.writeheader()
    for r in sample:
        sid = r["story_id"]
        if sid not in results_by_id:
            continue
        new = results_by_id[sid]
        story = stories.get(sid, {})
        was_disagree = r["human"] != r["claude"] or r["human"] != r["gemini"]
        w.writerow({
            "story_id": sid,
            "edition": r["edition"],
            "old_human_binary": r["human"],
            "old_human_5tier_mapped": old_to_5tier(r["human"]),
            "old_claude_binary": r["claude"],
            "old_gemini_binary": r["gemini"],
            "new_claude_5tier": new["claude_category"],
            "new_collective": new.get("claude_collective", ""),
            "new_confidence": new.get("claude_confidence", ""),
            "old_was_disagreement": "yes" if was_disagree else "no",
            "new_reasoning": new.get("claude_reasoning", ""),
            "story_text": (story.get("text", "") or "")[:1500],
        })
print(f"Wrote: {OUT}")

# 6) Quick summary
from collections import Counter
print()
print("="*80)
print("NEW 5-TIER DISTRIBUTION ON SAMPLE")
print("="*80)
new_cats = Counter(results_by_id[r["story_id"]]["claude_category"]
                   for r in sample if r["story_id"] in results_by_id)
for cat, n in sorted(new_cats.items(), key=lambda x: -x[1]):
    print(f"  {cat:<22} {n}")

print()
print("CONFIDENCE DISTRIBUTION")
print("-"*40)
confs = Counter(results_by_id[r["story_id"]].get("claude_confidence", "")
                for r in sample if r["story_id"] in results_by_id)
for c, n in sorted(confs.items(), key=lambda x: -x[1]):
    print(f"  {c:<10} {n}")

print()
print("HOW DOES THE NEW TAG RELATE TO THE OLD HUMAN TAG?")
print("-"*60)
print(f"{'old_human':<15}{'new_claude':<22}{'count':>6}")
combos = Counter((r["human"], results_by_id[r["story_id"]]["claude_category"])
                 for r in sample if r["story_id"] in results_by_id)
for (h, c), n in sorted(combos.items(), key=lambda x: -x[1]):
    print(f"  {h:<13}{c:<22}{n:>6}")

print()
print("DISAGREEMENT-CASE FOCUS — does the new 5-tier disambiguate?")
print("-"*60)
for r in sample:
    sid = r["story_id"]
    if sid not in results_by_id:
        continue
    if r["human"] == r["claude"] == r["gemini"]:
        continue  # only show old-disagreement rows
    new = results_by_id[sid]
    print(f"  H={r['human']:<10} C={r['claude']:<10} G={r['gemini']:<10}  →  "
          f"new={new['claude_category']:<20} conf={new.get('claude_confidence',''):<6} "
          f"coll={new.get('claude_collective','')}")
