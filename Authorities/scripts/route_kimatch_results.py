#!/usr/bin/env python3
"""
route_kimatch_results.py — split the Kimatch match output into review queues by
the zibn-shtern routing test: *can the reviewer decide from the row alone?*

  YES  → OpenRefine TSV   (bulk candidate-pick / spelling / no-match residue)
  NO   → Streamlit feed   (context-dependent disambiguation: ambiguous spelling,
                           wrong-city risk, multi-candidate fuzzy — needs the
                           attestation text + map the Kima Review page shows)

Also emits an auto-confirmed table (grade A) that seeds donations later.

Inputs   editions/kimatch/matched.tsv            (kimatch match output, CSV)
Outputs  editions/kimatch/openrefine_review_queue.tsv
         editions/kimatch/kima_review_queue.csv  (results, Kima-Review schema)
         editions/kimatch/kima_review_report.tsv (decisions, Kima-Review schema)
         editions/kimatch/auto_confirmed.tsv     (grade-A, donation-ready)
         editions/kimatch/routing_summary.md

Run:
    python3 Authorities/scripts/route_kimatch_results.py
"""
from __future__ import annotations

import csv
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
KDIR = os.path.join(PROJECT, "editions", "kimatch")

MATCHED = os.path.join(KDIR, "matched.tsv")          # CSV despite extension
OPENREFINE = os.path.join(KDIR, "openrefine_review_queue.tsv")
SL_QUEUE = os.path.join(KDIR, "kima_review_queue.csv")
SL_REPORT = os.path.join(KDIR, "kima_review_report.tsv")
AUTO = os.path.join(KDIR, "auto_confirmed.tsv")
SUMMARY = os.path.join(KDIR, "routing_summary.md")

KIMA_URL = "https://data.geo-kima.org/Places/Details/"


def candidates(row) -> list[str]:
    return [c for c in (row.get("_candidates", "") or "").split("|") if c.strip()]


def needs_context(row) -> bool:
    """Streamlit route: the decision needs the surrounding text / map / siblings."""
    status = row.get("_match_status", "")
    flags = row.get("_flags", "") or ""
    if status == "name_ambiguous":
        return True
    if "phonetic_mismatch" in flags:
        return True
    if status == "fuzzy" and len(candidates(row)) > 1:
        return True
    return False


def display_name(row) -> str:
    return (row.get("name_heb") or row.get("name_rom") or row.get("local_id") or "").strip()


def main():
    with open(MATCHED, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))   # comma-delimited

    openrefine, streamlit, auto_conf = [], [], []
    by_route = Counter()
    by_grade = Counter()

    for r in rows:
        grade = r.get("_grade", "")
        by_grade[grade] += 1
        if r.get("_grade") == "A_autolink":
            auto_conf.append(r)
        if needs_context(r):
            streamlit.append(r)
            by_route["streamlit"] += 1
        else:
            openrefine.append(r)
            by_route["openrefine"] += 1

    # ── OpenRefine queue (decide-from-row) ──────────────────────────────────
    or_fields = ["local_id", "kind", "name_heb", "name_rom", "wikidata_qid",
                 "occurrences", "n_editions", "match_status", "grade", "confidence",
                 "sound_match", "flags", "kima_id", "kima_name_rom", "kima_name_heb",
                 "distance_km", "candidates", "kima_url", "context_sample",
                 # reviewer fills these in OpenRefine:
                 "decision", "chosen_kima_id", "reviewer_notes"]
    with open(OPENREFINE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=or_fields, delimiter="\t",
                           extrasaction="ignore")
        w.writeheader()
        for r in sorted(openrefine, key=lambda x: -int(x.get("occurrences") or 0)):
            kid = r.get("_kima_id", "")
            w.writerow({
                "local_id": r.get("local_id", ""),
                "kind": r.get("kind", ""),
                "name_heb": r.get("name_heb", ""),
                "name_rom": r.get("name_rom", ""),
                "wikidata_qid": r.get("wikidata_qid", ""),
                "occurrences": r.get("occurrences", ""),
                "n_editions": r.get("n_editions", ""),
                "match_status": r.get("_match_status", ""),
                "grade": r.get("_grade", ""),
                "confidence": r.get("_confidence", ""),
                "sound_match": r.get("_sound_match", ""),
                "flags": r.get("_flags", ""),
                "kima_id": kid,
                "kima_name_rom": r.get("_kima_name_rom", ""),
                "kima_name_heb": r.get("_kima_name_heb", ""),
                "distance_km": r.get("_distance_km", ""),
                "candidates": r.get("_candidates", ""),
                "kima_url": (KIMA_URL + kid) if kid else "",
                "context_sample": (r.get("context", "") or "")[:300],
                "decision": "", "chosen_kima_id": "", "reviewer_notes": "",
            })

    # ── Streamlit feed (Kima-Review schema) ─────────────────────────────────
    # results CSV (comma) — the page reads these _ columns + name/occurrences.
    sl_results_fields = ["name", "occurrences", "editions", "contexts", "suggested_id",
                         "action", "_match_status", "_match_method", "_confidence",
                         "_kima_id", "_kima_name_rom", "_kima_name_heb",
                         "_distance_km", "_candidates"]
    # decisions TSV — name/occurrences/editions/contexts/suggested_id/action
    sl_report_fields = ["name", "occurrences", "editions", "contexts",
                        "suggested_id", "action"]

    with open(SL_QUEUE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sl_results_fields, extrasaction="ignore")
        w.writeheader()
        for r in sorted(streamlit, key=lambda x: -int(x.get("occurrences") or 0)):
            ctx = (r.get("context", "") or "").replace(" ⟦SEP⟧ ", "\n\n")
            w.writerow({
                "name": display_name(r),
                "occurrences": r.get("occurrences", ""),
                "editions": r.get("editions", ""),
                "contexts": ctx,
                "suggested_id": r.get("_kima_id", ""),
                "action": "",
                "_match_status": r.get("_match_status", ""),
                "_match_method": r.get("_match_method", ""),
                "_confidence": r.get("_confidence", ""),
                "_kima_id": r.get("_kima_id", ""),
                "_kima_name_rom": r.get("_kima_name_rom", ""),
                "_kima_name_heb": r.get("_kima_name_heb", ""),
                "_distance_km": r.get("_distance_km", ""),
                "_candidates": r.get("_candidates", ""),
            })

    with open(SL_REPORT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sl_report_fields, delimiter="\t",
                           quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in sorted(streamlit, key=lambda x: -int(x.get("occurrences") or 0)):
            ctx = (r.get("context", "") or "").replace(" ⟦SEP⟧ ", "\n\n")
            w.writerow({
                "name": display_name(r),
                "occurrences": r.get("occurrences", ""),
                "editions": r.get("editions", ""),
                "contexts": ctx,
                "suggested_id": r.get("_kima_id", ""),
                "action": "",
            })

    # ── auto-confirmed (grade A → donation seed) ─────────────────────────────
    auto_fields = ["local_id", "kind", "name_heb", "name_rom", "wikidata_qid",
                   "occurrences", "match_method", "confidence", "kima_id",
                   "kima_name_rom", "kima_name_heb"]
    with open(AUTO, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=auto_fields, delimiter="\t",
                           extrasaction="ignore")
        w.writeheader()
        for r in sorted(auto_conf, key=lambda x: -int(x.get("occurrences") or 0)):
            w.writerow({
                "local_id": r.get("local_id", ""),
                "kind": r.get("kind", ""),
                "name_heb": r.get("name_heb", ""),
                "name_rom": r.get("name_rom", ""),
                "wikidata_qid": r.get("wikidata_qid", ""),
                "occurrences": r.get("occurrences", ""),
                "match_method": r.get("_match_method", ""),
                "confidence": r.get("_confidence", ""),
                "kima_id": r.get("_kima_id", ""),
                "kima_name_rom": r.get("_kima_name_rom", ""),
                "kima_name_heb": r.get("_kima_name_heb", ""),
            })

    # ── summary ──────────────────────────────────────────────────────────────
    status_counts = Counter(r.get("_match_status", "") for r in rows)
    lines = [
        "# Kimatch routing summary",
        "",
        f"Total unlinked toponyms matched: **{len(rows)}**",
        "",
        "## By grade",
        *(f"- {g}: {by_grade[g]}" for g in ("A_autolink", "B_review", "C_review")),
        "",
        "## By match status",
        *(f"- {s}: {status_counts[s]}" for s in
          ("name_exact", "name_ambiguous", "fuzzy", "no_match")),
        "",
        "## Routing (zibn-shtern decidability test)",
        f"- **OpenRefine** (decide from row alone): {by_route['openrefine']} "
        f"→ `openrefine_review_queue.tsv`",
        f"- **Streamlit Kima Review** (needs context/map): {by_route['streamlit']} "
        f"→ `kima_review_queue.csv` + `kima_review_report.tsv`",
        f"- **Auto-confirmed (grade A, donation seed)**: {len(auto_conf)} "
        f"→ `auto_confirmed.tsv`",
        "",
        "Streamlit route = name_ambiguous, phonetic_mismatch-flagged, or multi-candidate fuzzy.",
    ]
    with open(SUMMARY, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("\n".join(lines))
    print(f"\nWrote:\n  {OPENREFINE}\n  {SL_QUEUE}\n  {SL_REPORT}\n  {AUTO}\n  {SUMMARY}")


if __name__ == "__main__":
    main()
