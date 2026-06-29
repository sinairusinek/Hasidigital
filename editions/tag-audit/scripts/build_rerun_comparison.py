"""Build editions/tag-audit/rerun-comparison.tsv from the LLM cache.

For every category that has at least two distinct claude-cli prompt_hashes
per tag, compare the OLD Sonnet sweep (earlier rows) vs the NEW patched-
definition re-run (later rows). One row per category.

Usage:  python3 scripts/build_rerun_comparison.py
"""
import csv
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, ".cache", "llm-presence.tsv")
OUT = os.path.join(ROOT, "rerun-comparison.tsv")

COLS = ["category", "old_n", "old_true", "old_true_pct",
        "new_n", "new_true", "new_true_pct",
        "overlap_pairs", "overlap_T_to_F", "overlap_F_to_T",
        "true_pct_delta", "notes"]


def load_claude_cli_rows():
    rows = []
    with open(CACHE, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["model"] != "claude-cli":
                continue
            rows.append(r)
    rows.sort(key=lambda r: r["ts"])
    return rows


def split_old_new(rows):
    """For a category's rows: rows with the OLDEST prompt_hash per tag are
    'old'; rows with any newer prompt_hash for that same tag are 'new'."""
    first_hash_for_tag = {}
    for r in rows:
        first_hash_for_tag.setdefault(r["tag"], r["prompt_hash"])
    old, new = [], []
    for r in rows:
        if r["prompt_hash"] == first_hash_for_tag[r["tag"]]:
            old.append(r)
        else:
            new.append(r)
    return old, new


def category_stats(cat, rows):
    old, new = split_old_new(rows)
    if not new:
        return None
    n_o, n_n = len(old), len(new)
    t_o = sum(1 for r in old if r["applies"] == "True")
    t_n = sum(1 for r in new if r["applies"] == "True")
    pct_o = (t_o / n_o * 100) if n_o else 0
    pct_n = (t_n / n_n * 100) if n_n else 0
    # Overlap
    old_by = {(r["story_id"], r["tag"]): r["applies"] for r in old}
    new_by = {(r["story_id"], r["tag"]): r["applies"] for r in new}
    both = set(old_by) & set(new_by)
    tf = ft = 0
    for st in both:
        ov = old_by[st] == "True"
        nv = new_by[st] == "True"
        if ov and not nv:
            tf += 1
        elif nv and not ov:
            ft += 1
    return {
        "category": cat,
        "old_n": n_o, "old_true": t_o, "old_true_pct": f"{pct_o:.0f}%",
        "new_n": n_n, "new_true": t_n, "new_true_pct": f"{pct_n:.0f}%",
        "overlap_pairs": len(both),
        "overlap_T_to_F": tf, "overlap_F_to_T": ft,
        "true_pct_delta": f"{pct_n - pct_o:+.0f}pp",
        "notes": "",
    }


def main():
    rows = load_claude_cli_rows()
    by_cat = defaultdict(list)
    for r in rows:
        cat = r["tag"].split(":")[0]
        if cat in ("test", "kabbalah"):
            continue  # kabbalah used the curated DEFINITIONS dict; no re-run
        by_cat[cat].append(r)
    out_rows = []
    for cat in sorted(by_cat):
        s = category_stats(cat, by_cat[cat])
        if s is not None:
            out_rows.append(s)
    if not out_rows:
        print("No re-run rows detected yet.")
        return
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter="\t")
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    # Pretty-print
    print(f"Wrote {OUT}")
    print()
    widths = {c: max(len(c), max(len(str(r[c])) for r in out_rows)) for c in COLS}
    print("  ".join(c.ljust(widths[c]) for c in COLS))
    for r in out_rows:
        print("  ".join(str(r[c]).ljust(widths[c]) for c in COLS))


if __name__ == "__main__":
    main()
