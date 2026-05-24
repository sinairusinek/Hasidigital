#!/usr/bin/env python3
"""
build_kima_review_queue.py — emit the Hasidigital review queue for the **Kimatch
app** (same structure as the Zylbercweig / E-GERET review pages: candidate cards,
KimaDB-backed details, GitHub-synced decisions).

Reads  editions/kimatch/matched.tsv  (the match output, CSV)
Writes the rows that need a human into the Kimatch repo so the app — including
its Streamlit Cloud deployment — can serve them:

    <Kimatch repo>/data/hasidigital/kima_review.tsv

Queue = everything that is NOT a grade-A auto-link (those go through
spotcheck_grade_a.py instead). i.e. name_ambiguous + fuzzy + no_match + B_review.

Run:
    python3 Authorities/scripts/build_kima_review_queue.py
"""
from __future__ import annotations

import csv
import os
import re
from collections import Counter

_HEB_RE = re.compile(r"[א-ת]")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
KDIR = os.path.join(PROJECT, "editions", "kimatch")
# Prefer the auto-reclassified manual-only set (the real review burden); fall back
# to the full match output if auto_reclassify hasn't been run yet.
_MANUAL = os.path.join(KDIR, "manual_review.tsv")
_FULL = os.path.join(KDIR, "matched.tsv")
MATCHED = _MANUAL if os.path.exists(_MANUAL) else _FULL
USING_MANUAL = MATCHED == _MANUAL

KIMATCH_REPO = os.path.join(os.path.expanduser("~"), "Documents", "GitHub", "Kimatch")
OUT_DIR = os.path.join(KIMATCH_REPO, "data", "hasidigital")
OUT_TSV = os.path.join(OUT_DIR, "kima_review.tsv")

# match_status → review-filter bucket the app groups by
STATUS_MAP = {
    "name_ambiguous": "ambiguous",
    "fuzzy":          "fuzzy",
    "name_exact":     "fuzzy",     # single-candidate exact → "suggested, confirm"
    "no_match":       "no_match",
}

FIELDS = ["local_id", "kind", "name", "name_rom", "wikidata_qid", "match_status",
          "confidence", "occurrences", "editions", "contexts", "candidates", "mentions"]

_MENTIONS_JSON = os.path.join(KDIR, "mentions.json")


def main():
    import json
    if not os.path.isdir(KIMATCH_REPO):
        raise SystemExit(f"Kimatch repo not found at {KIMATCH_REPO}")
    os.makedirs(OUT_DIR, exist_ok=True)

    mentions_by_id = {}
    if os.path.exists(_MENTIONS_JSON):
        with open(_MENTIONS_JSON, encoding="utf-8") as f:
            mentions_by_id = json.load(f)

    with open(MATCHED, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))   # comma-delimited

    n = 0
    by_bucket = {}
    with open(OUT_TSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t")
        w.writeheader()
        for r in sorted(rows, key=lambda x: -int(x.get("occurrences") or 0)):
            # When falling back to the full match output, still drop grade-A
            # (handled by the spot-check loop). The manual set is already filtered.
            if not USING_MANUAL and r.get("_grade") == "A_autolink":
                continue
            bucket = STATUS_MAP.get(r.get("_match_status", ""), "no_match")
            contexts = (r.get("context", "") or "").replace(" ⟦SEP⟧ ", "|")
            local_id = r.get("local_id", "")
            ments = mentions_by_id.get(local_id, [])
            # Display name: prefer the Hebrew form the reviewer sees in the text.
            # Authority places can have a romanized primary (e.g. "Volia") while the
            # corpus surface form is Hebrew (נישחיז) — show the Hebrew.
            name_heb = (r.get("name_heb") or "").strip()
            if not name_heb:
                heb = Counter(m.get("text", "") for m in ments
                              if _HEB_RE.search(m.get("text", "") or ""))
                name_heb = heb.most_common(1)[0][0] if heb else ""
            display_name = name_heb or (r.get("name_rom") or "").strip() or local_id
            w.writerow({
                "local_id": local_id,
                "kind": r.get("kind", ""),
                "name": display_name,
                "name_rom": r.get("name_rom", ""),
                "wikidata_qid": r.get("wikidata_qid", ""),
                "match_status": bucket,
                "confidence": r.get("_confidence", ""),
                "occurrences": r.get("occurrences", ""),
                # page.py splits the editions list on "," — normalise from "; "
                "editions": (r.get("editions", "") or "").replace("; ", ", "),
                "contexts": contexts,
                "candidates": r.get("_candidates", ""),
                "mentions": json.dumps(mentions_by_id.get(r.get("local_id", ""), []),
                                       ensure_ascii=False),
            })
            n += 1
            by_bucket[bucket] = by_bucket.get(bucket, 0) + 1

    print(f"Wrote {n} review rows → {OUT_TSV}")
    print(f"  buckets: {by_bucket}")
    print("Commit data/hasidigital/kima_review.tsv in the Kimatch repo to deploy on Cloud.")


if __name__ == "__main__":
    main()
