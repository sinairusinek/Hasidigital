"""
Run women annotation on all 9 pre-annotated editions.
Produces a three-way comparison: human (XML) vs Claude vs Gemini.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from women_data import load_stories
from women_llm import annotate_batch, load_criteria, criteria_hash

# Map XML-derived categories to the LLM schema for comparison
def normalize_human(cat: str) -> str:
    if cat == "no":
        return "no-women"
    if cat in ("major", "minor", "major+minor"):
        return cat
    return cat

def agreement_label(human, claude, gemini):
    all_same = human == claude == gemini
    if all_same:
        return "all-agree"
    if claude == gemini and claude != human:
        return "models-agree/human-differs"
    if human == claude and human != gemini:
        return "human=claude/gemini-differs"
    if human == gemini and human != claude:
        return "human=gemini/claude-differs"
    return "all-differ"

def main():
    print("Loading stories from XML editions...")
    all_stories = load_stories()
    annotated_editions = sorted({s["edition"] for s in all_stories if s["category"] != "no"})
    stories_9 = [s for s in all_stories if s["edition"] in annotated_editions]

    print(f"Found {len(annotated_editions)} annotated editions, {len(stories_9)} stories total.")
    print("Editions:", ", ".join(annotated_editions))
    print()

    criteria = load_criteria()
    chash = criteria_hash(criteria)
    print(f"Criteria hash: {chash}")
    print("Running Claude + Gemini annotation (cached where possible)...")
    print()

    # Gemini already cached; force-rerun Claude (CLI) only
    results = annotate_batch(
        stories_9,
        criteria=criteria,
        force=False,
        models=(True, False),   # Claude=True, Gemini=False (use cache)
        progress_callback=lambda i, t: print(f"  {i}/{t}", end="\r"),
    )
    print()

    # Build comparison rows
    story_map = {s["story_id"]: s for s in stories_9}
    rows = []
    for r in results:
        story = story_map.get(r["story_id"], {})
        human = normalize_human(story.get("category", "?"))
        claude = r.get("claude_category", "?")
        gemini = r.get("gemini_category", "?")
        label = agreement_label(human, claude, gemini)
        rows.append({
            "story_id": r["story_id"],
            "edition": r.get("edition", story.get("edition", "")),
            "human": human,
            "claude": claude,
            "gemini": gemini,
            "agreement": label,
            "claude_reasoning": r.get("claude_reasoning", ""),
            "gemini_reasoning": r.get("gemini_reasoning", ""),
        })

    # ── Summary ──────────────────────────────────────────────────────────────
    from collections import Counter
    label_counts = Counter(r["agreement"] for r in rows)
    total = len(rows)

    print("=" * 60)
    print("THREE-WAY AGREEMENT SUMMARY")
    print("=" * 60)
    for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
        print(f"  {label:<40} {count:>4}  ({count/total*100:.1f}%)")
    print(f"  {'TOTAL':<40} {total:>4}")
    print()

    # Per-edition breakdown
    print("PER-EDITION BREAKDOWN")
    print("-" * 60)
    from itertools import groupby
    rows_by_ed = {}
    for r in rows:
        rows_by_ed.setdefault(r["edition"], []).append(r)
    for edition in sorted(rows_by_ed):
        ed_rows = rows_by_ed[edition]
        ed_labels = Counter(r["agreement"] for r in ed_rows)
        agree = ed_labels.get("all-agree", 0)
        total_ed = len(ed_rows)
        print(f"  {edition:<35} {agree}/{total_ed} all-agree  "
              f"({agree/total_ed*100:.0f}%)")
    print()

    # Human category distribution
    print("HUMAN ANNOTATION DISTRIBUTION")
    print("-" * 60)
    human_counts = Counter(r["human"] for r in rows)
    for cat, count in sorted(human_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:<20} {count:>4}  ({count/total*100:.1f}%)")
    print()

    # Disagreement detail
    disagreements = [r for r in rows if r["agreement"] != "all-agree"]
    print(f"DISAGREEMENTS ({len(disagreements)} stories)")
    print("-" * 60)
    print(f"{'story_id':<40} {'human':<12} {'claude':<12} {'gemini':<12} {'label'}")
    print("-" * 100)
    for r in sorted(disagreements, key=lambda x: (x["edition"], x["story_id"])):
        print(f"{r['story_id']:<40} {r['human']:<12} {r['claude']:<12} {r['gemini']:<12} {r['agreement']}")
    print()

    # Save TSV
    import csv
    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "editions", "women-annotation-comparison.tsv")
    out_path = os.path.normpath(out_path)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Full results saved to: {out_path}")

if __name__ == "__main__":
    main()
