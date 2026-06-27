#!/usr/bin/env python3
"""Draw Venn diagrams illustrating the relationships between
- RA (human annotator) tags in the corpus
- Sonnet's verdicts (where it was queried)
- Opus's verdicts (where it was queried)

Saves three PNGs to editions/tag-audit/venns/.
"""
import csv, os
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib_venn import venn2, venn3

REPO = Path(__file__).resolve().parents[3]
AUDIT = REPO / "editions" / "tag-audit"
OUT = AUDIT / "venns"
OUT.mkdir(exist_ok=True)
# (no change here — this file already writes to venns/)


# --- Load cache ---
cache_rows = list(csv.DictReader(open(AUDIT / ".cache" / "llm-presence.tsv"), delimiter="\t"))

# RA-tagged (story, tag) pairs from XML
import re
ra_pairs = set()
for xml in sorted((REPO / "editions" / "online").glob("*.xml")):
    txt = xml.read_text()
    for m in re.finditer(r'<div[^>]*type="story"[^>]*xml:id="([^"]+)"|<div[^>]*xml:id="([^"]+)"[^>]*type="story"', txt):
        sid = m.group(1) or m.group(2)
        start = m.end()
        next_div = re.search(r'<div[^>]*type="story"', txt[start:])
        end = start + next_div.start() if next_div else len(txt)
        chunk = txt[start:end]
        tagm = re.search(r'<span\s+[^>]*ana="([^"]+)"[^>]*>תיוגים\*?</span>', chunk)
        if not tagm:
            continue
        for t in [t.strip() for t in tagm.group(1).split(";") if t.strip()]:
            ra_pairs.add((sid, t))

# Sonnet True pairs (claude-cli)
sonnet_true = {(r["story_id"], r["tag"]) for r in cache_rows if r["model"] == "claude-cli" and r["applies"] == "True"}
sonnet_false = {(r["story_id"], r["tag"]) for r in cache_rows if r["model"] == "claude-cli" and r["applies"] == "False"}
sonnet_queried = sonnet_true | sonnet_false

# Opus True pairs (opus-cli)
opus_true = {(r["story_id"], r["tag"]) for r in cache_rows if r["model"] == "opus-cli" and r["applies"] == "True"}
opus_false = {(r["story_id"], r["tag"]) for r in cache_rows if r["model"] == "opus-cli" and r["applies"] == "False"}
opus_queried = opus_true | opus_false

# Gemini True/False (the old practice pilot)
gem_true = {(r["story_id"], r["tag"]) for r in cache_rows if r["model"] == "gemini-3" and r["applies"] == "True"}
gem_false = {(r["story_id"], r["tag"]) for r in cache_rows if r["model"] == "gemini-3" and r["applies"] == "False"}

print(f"RA-tagged pairs:           {len(ra_pairs):>6}")
print(f"Sonnet True (claude-cli):  {len(sonnet_true):>6}")
print(f"Sonnet False:              {len(sonnet_false):>6}")
print(f"Opus True (opus-cli):      {len(opus_true):>6}")
print(f"Opus False:                {len(opus_false):>6}")
print(f"Gemini-3 True:             {len(gem_true):>6}")
print(f"Gemini-3 False:            {len(gem_false):>6}")
print()


# --- Diagram 1: Within the 100-sample (Sonnet → Opus refinement) ---
fig, ax = plt.subplots(figsize=(8, 6))
# In the sample: all 100 are Sonnet True. Of those, 59 Opus True, 41 Opus False.
# That's a subset relation — but we can still show Sonnet (100) vs Opus (59) as a Venn.
v = venn2(subsets=(100 - 59, 0, 59), set_labels=("Sonnet says\nTag applies\n(100 random\nSonnet-True\ncandidates)", "Opus also says\nTag applies\n(59)"), ax=ax)
ax.set_title("Diagram 1 — Opus refinement of Sonnet's missed positives\n(random sample of 100 Sonnet-True candidates, with definitions)", fontsize=11)
ax.text(0, -0.6, "41 cases: Sonnet over-tagged — Opus disagrees\n59 cases: both agree the tag fits\nExtrapolating to all 1,456 Sonnet Trues:\n~860 confirmed, ~596 likely false positives", fontsize=9, ha="center")
plt.tight_layout()
plt.savefig(OUT / "1_sonnet_vs_opus_sample.png", dpi=140, bbox_inches="tight")
plt.close()
print(f"Saved {OUT / '1_sonnet_vs_opus_sample.png'}")


# --- Diagram 2: RA vs LLM where they BOTH evaluated the same pair ---
# Combine all LLM verdicts (any model) per pair, take the most authoritative (opus > claude-cli > gemini-3).
# Then look at pairs where the LLM verdict exists AND the pair is RA-tagged.
def best_verdict(sid_tag):
    for model in ("opus-cli", "claude-cli", "gemini-3"):
        for r in cache_rows:
            if (r["story_id"], r["tag"]) == sid_tag and r["model"] == model:
                return r["applies"] == "True", model
    return None, None

# Build per-pair best verdict
best = {}
priority = {"opus-cli": 3, "claude-cli": 2, "gemini-3": 1}
for r in cache_rows:
    k = (r["story_id"], r["tag"])
    p = priority.get(r["model"], 0)
    if k not in best or best[k][1] < p:
        best[k] = (r["applies"] == "True", p)

# Pairs that are both RA-tagged AND have an LLM verdict
ra_and_llm = {k for k in ra_pairs if k in best}
ra_llm_agree = {k for k in ra_and_llm if best[k][0]}      # both yes
ra_llm_disagree = {k for k in ra_and_llm if not best[k][0]}  # RA yes, LLM no
print(f"RA-tagged pairs probed by any LLM: {len(ra_and_llm)}")
print(f"  Of which LLM also said True (agree):  {len(ra_llm_agree)}")
print(f"  Of which LLM said False (disagree):   {len(ra_llm_disagree)}")

fig, ax = plt.subplots(figsize=(8, 6))
v = venn2(subsets=(len(ra_llm_disagree), 0, len(ra_llm_agree)), set_labels=(f"RA tagged\n({len(ra_and_llm)} pairs\nprobed by LLM)", "LLM agrees\nthe tag applies"), ax=ax)
ax.set_title("Diagram 2 — Where RA and LLMs both evaluated the same (story, tag)\n(coverage is sparse: most RA tags were never re-checked)", fontsize=11)
ax.text(0, -0.6, f"{len(ra_llm_agree)} agreements   |   {len(ra_llm_disagree)} disagreements (RA-True, LLM-False)\nMostly from the May Gemini practice pilot + Opus hand-review", fontsize=9, ha="center")
plt.tight_layout()
plt.savefig(OUT / "2_ra_vs_llm_overlap.png", dpi=140, bbox_inches="tight")
plt.close()
print(f"Saved {OUT / '2_ra_vs_llm_overlap.png'}")


# --- Diagram 3: Three-circle conceptual Venn ---
# Show all (story, tag) judgments in a unified way:
# - RA-tagged set (4890 pairs)
# - LLM-True set (Sonnet True + Opus True + Gemini True, union)
# - Where LLM also evaluated RA-tagged (the small intersection)
llm_true_any = sonnet_true | opus_true | gem_true
ra_only = ra_pairs - llm_true_any
llm_only = llm_true_any - ra_pairs
both = ra_pairs & llm_true_any
print(f"\nRA only (LLM didn't confirm / didn't probe): {len(ra_only)}")
print(f"LLM-True only (RA didn't tag): {len(llm_only)}")
print(f"Both RA-tagged AND LLM confirmed: {len(both)}")

fig, ax = plt.subplots(figsize=(10, 7))
v = venn2(subsets=(len(ra_only), len(llm_only), len(both)),
          set_labels=(f"RA-tagged\n({len(ra_pairs)} pairs)", f"LLM said True\nsomewhere\n({len(llm_true_any)} pairs)"), ax=ax)
ax.set_title("Diagram 3 — Full corpus view: RA tags vs LLM positive verdicts\n(union of Sonnet, Opus, Gemini True verdicts)", fontsize=11)
ax.text(0, -0.7,
        "LEFT lobe: RA tags the LLM never confirmed (~5,000) — mostly because the LLM was never asked.\n"
        "RIGHT lobe: LLM 'missed positives' the RA hadn't tagged (~1,500) — candidates from the audit funnel.\n"
        "MIDDLE: tiny — the audit pipeline never probed already-tagged stories systematically.",
        fontsize=9, ha="center")
plt.tight_layout()
plt.savefig(OUT / "3_ra_vs_llm_full_corpus.png", dpi=140, bbox_inches="tight")
plt.close()
print(f"Saved {OUT / '3_ra_vs_llm_full_corpus.png'}")

print(f"\nAll diagrams in {OUT}")
