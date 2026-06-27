#!/usr/bin/env python3
"""Propagate Opus-confirmed True verdicts to near-duplicate stories.

For each (story_a, tag) where Opus said applies=True, find every near-duplicate
story_b in story-duplicates.tsv and emit (story_b, tag) as a "propagated"
verdict — but only if the duplicate isn't already tagged with that tag in the
XML (avoid no-op duplicates).

Writes editions/tag-audit/llm-confirmed-verdicts.tsv with columns:
  story_id, tag, source (direct|propagated), source_story,
  opus_confidence, opus_reasoning.
"""
import csv, re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
AUDIT = REPO / "editions" / "tag-audit"

# 1. Load Opus True verdicts (direct = the story Opus actually evaluated)
opus_true = {}  # (sid, tag) -> (confidence, reasoning)
with open(AUDIT / ".cache" / "llm-presence.tsv") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        if r["model"] == "opus-cli" and r["applies"] == "True":
            opus_true[(r["story_id"], r["tag"])] = (r["confidence"], r["reasoning"])
print(f"Opus True verdicts (direct): {len(opus_true)}")

# 2. Load story duplicates as adjacency list
adj = defaultdict(set)
with open(AUDIT / "story-duplicates.tsv") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        a, b = r["story_a"], r["story_b"]
        adj[a].add(b); adj[b].add(a)
print(f"Stories with at least one near-duplicate: {len(adj)}")

# 3. Load existing RA-tagged (story, tag) pairs from XML so we skip no-ops
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
        if not tagm: continue
        for t in [t.strip() for t in tagm.group(1).split(";") if t.strip()]:
            ra_pairs.add((sid, t))
print(f"RA-tagged pairs already in XML: {len(ra_pairs)}")

# 4. Build the unified verdict set: direct + propagated
verdicts = {}  # (sid, tag) -> dict with source info
for (sid, tag), (conf, reason) in opus_true.items():
    if (sid, tag) in ra_pairs:
        # already tagged in XML — no need to re-add
        continue
    verdicts[(sid, tag)] = {
        "story_id": sid, "tag": tag,
        "source": "direct", "source_story": sid,
        "opus_confidence": conf, "opus_reasoning": reason,
    }

direct_count = len(verdicts)
print(f"Direct verdicts (not yet in XML): {direct_count}")

# Propagate
propagated_count = 0
for (src_sid, tag), (conf, reason) in opus_true.items():
    for dup_sid in adj.get(src_sid, ()):
        k = (dup_sid, tag)
        if k in ra_pairs:        # already tagged — skip
            continue
        if k in verdicts:        # direct verdict wins over propagated
            continue
        verdicts[k] = {
            "story_id": dup_sid, "tag": tag,
            "source": "propagated", "source_story": src_sid,
            "opus_confidence": conf, "opus_reasoning": reason,
        }
        propagated_count += 1

print(f"Propagated verdicts (new): {propagated_count}")
print(f"Total verdicts to write: {len(verdicts)}")

# 5. Write TSV
out = AUDIT / "llm-confirmed-verdicts.tsv"
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["story_id","tag","source","source_story","opus_confidence","opus_reasoning"], delimiter="\t", lineterminator="\n")
    w.writeheader()
    for v in sorted(verdicts.values(), key=lambda x: (x["tag"], x["story_id"])):
        w.writerow(v)
print(f"Saved to {out}")

# 6. Quick per-category report
from collections import Counter
print()
print(f'{"category":25s} {"direct":>7} {"propagated":>11} {"total":>7}')
print("-" * 55)
by_cat = defaultdict(lambda: [0, 0])
for v in verdicts.values():
    cat = v["tag"].split(":")[0]
    if v["source"] == "direct": by_cat[cat][0] += 1
    else: by_cat[cat][1] += 1
for cat, (d, p) in sorted(by_cat.items(), key=lambda x: -sum(x[1])):
    print(f"{cat:25s} {d:>7} {p:>11} {d+p:>7}")
