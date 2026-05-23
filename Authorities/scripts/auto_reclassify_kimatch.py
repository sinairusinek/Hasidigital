#!/usr/bin/env python3
"""
auto_reclassify_kimatch.py — shrink the manual review burden the way zibn-shtern's
auto_reclassify does. Reads the full match output and partitions every unlinked
toponym into mechanical buckets, so a human only touches the genuine remainder.

Partitions (written under editions/kimatch/auto_reclassify/)
  grade_a       grade-A auto-links → handled by spotcheck_grade_a.py (skipped here)
  auto_linked   confident single-candidate fuzzy (conf ≥ THRESHOLD) + collapsed
                sibling spellings of a confident match, passing safety guards
  rejected      obvious non-places (curated stoplist) → appended to reject_stoplist.tsv
  quick_confirm acronym-pattern tokens (X״Y) — real ones exist (א״י), so a human glances
  parked        single-occurrence no_match with no candidate (long-tail noise)
  manual        the real decisions → the Kimatch app "Hasidigital Review" queue

Safety guards (same as the grade-A spot-check): a candidate in an implausible
region for the corpus, or a very short Hebrew homograph, never auto-links.

Variant collapse: if one spelling auto-links to a Kima place, sibling spellings
whose single candidate is that same place inherit the link (one place, many forms).

Run (from the Kimatch venv — needs KimaDB to resolve candidate names):
    /Users/.../Kimatch/.venv/bin/python Authorities/scripts/auto_reclassify_kimatch.py
"""
from __future__ import annotations

import csv
import os
import re

FUZZY_AUTOLINK_THRESHOLD = 0.9

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
KDIR = os.path.join(PROJECT, "editions", "kimatch")
MATCHED = os.path.join(KDIR, "matched.tsv")              # CSV
OUT = os.path.join(KDIR, "auto_reclassify")
STOPLIST = os.path.join(KDIR, "reject_stoplist.tsv")
MANUAL_OUT = os.path.join(KDIR, "manual_review.tsv")

# ── safety: implausible regions + homographs (kept in sync with spotcheck_grade_a) ──
IMPLAUSIBLE_REGIONS = [
    "uruguay", "ethiopia", "wis.", "wisconsin", "n.m.", "new mexico", "iraq",
    "iran", "brazil", "mexico", "argentina", "india", "indonesia", "u.s.",
    "(usa", "united states", "australia", "china", "japan", "philippines",
    "nigeria", "syria", "(tex", "texas", "ohio", "pa.)", "pennsylvania",
]
KNOWN_HOMOGRAPHS = {"גליל", "יהודה", "ירדן", "חרן", "מדינה", "כפר", "עיר",
                    "מבוא", "באר", "גן",
                    # concept / personal-name words that equal a place name — in
                    # this corpus they usually mean the concept/person, not the town
                    "ישראל", "ציון", "אמן", "גולה", "מערב", "מזרח"}
# High-confidence non-places (NER false positives that aren't toponyms at all).
NONPLACE_STOPLIST = {"עכו״ם", "פרעה", "גן עדן", "גן העדן", "גיהנם", "אבד",
                     "פרדס", "שמים", "עולם", "תורה", "משיח", "פרה"}

_HEB = re.compile(r"[א-ת]")
_ACRONYM = re.compile(r"[א-ת]״[א-ת]")   # gershayim acronym anywhere


def heb_len(s: str) -> int:
    return len(_HEB.findall(s or ""))


def implausible(kima_rom: str) -> bool:
    low = (kima_rom or "").lower()
    return any(tok in low for tok in IMPLAUSIBLE_REGIONS)


def f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def main():
    from kimatch.data.loader import KimaDB
    places_csv = os.path.join(os.path.expanduser("~"), "Documents", "GitHub",
                              "Kimatch", "20250126KimaPlacesCSVx.csv")
    variants_tsv = os.path.join(os.path.expanduser("~"), "Documents", "GitHub",
                                "Kimatch", "Kima-Variants-20250929.tsv")
    print("Loading Kima data…")
    db = KimaDB.load(places_csv, variants_tsv)

    def cand_rom(kid: str) -> str:
        p = db.get(int(kid)) if str(kid).isdigit() else None
        return p.primary_rom if p else ""

    with open(MATCHED, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    def cands(r):
        return [c for c in (r.get("_candidates", "") or "").split("|") if c.strip()]

    # ── pass 1: find "trusted" kima_ids (≥1 confident, safe single-candidate row) ──
    trusted: set[str] = set()
    for r in rows:
        if r.get("_grade") == "A_autolink":
            continue
        cs = cands(r)
        if len(cs) != 1:
            continue
        if r.get("_match_status") not in ("fuzzy", "name_exact"):
            continue
        if f(r.get("_confidence")) < FUZZY_AUTOLINK_THRESHOLD:
            continue
        name = (r.get("name_heb") or "").strip()
        if name in KNOWN_HOMOGRAPHS or (name and heb_len(name) <= 3):
            continue
        if implausible(cand_rom(cs[0])):
            continue
        trusted.add(cs[0])

    # ── pass 2: assign partitions ──
    buckets = {k: [] for k in ("grade_a", "auto_linked", "rejected",
                               "quick_confirm", "parked", "manual")}
    for r in rows:
        name = (r.get("name_heb") or "").strip()
        cs = cands(r)
        status = r.get("_match_status", "")

        if r.get("_grade") == "A_autolink":
            buckets["grade_a"].append((r, ""))
            continue
        if name in NONPLACE_STOPLIST:
            buckets["rejected"].append((r, "stoplist non-place"))
            continue
        if name and _ACRONYM.search(name):
            buckets["quick_confirm"].append((r, "acronym pattern"))
            continue
        # auto-link: single trusted candidate (confident itself or a sibling spelling)
        if len(cs) == 1 and cs[0] in trusted:
            buckets["auto_linked"].append((r, cs[0]))
            continue
        if status == "no_match" and not cs and (r.get("occurrences") or "0") == "1":
            buckets["parked"].append((r, "single-occurrence no-match"))
            continue
        buckets["manual"].append((r, ""))

    # ── write partitions ──
    os.makedirs(OUT, exist_ok=True)

    def write(path, recs, extra_cols, rowfn):
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter="\t")
            w.writerow(extra_cols)
            for rec in recs:
                w.writerow(rowfn(rec))

    write(os.path.join(OUT, "auto_linked.tsv"),
          buckets["auto_linked"],
          ["local_id", "name_heb", "name_rom", "kima_id", "kima_name_rom",
           "confidence", "occurrences", "via"],
          lambda rc: [rc[0].get("local_id", ""), rc[0].get("name_heb", ""),
                      rc[0].get("name_rom", ""), rc[1], cand_rom(rc[1]),
                      rc[0].get("_confidence", ""), rc[0].get("occurrences", ""),
                      "auto_reclassify"])

    write(os.path.join(OUT, "quick_confirm.tsv"),
          buckets["quick_confirm"],
          ["local_id", "name_heb", "occurrences", "candidates", "reason",
           "decision", "chosen_kima_id"],
          lambda rc: [rc[0].get("local_id", ""), rc[0].get("name_heb", ""),
                      rc[0].get("occurrences", ""), rc[0].get("_candidates", ""),
                      rc[1], "", ""])

    write(os.path.join(OUT, "rejected.tsv"),
          buckets["rejected"],
          ["local_id", "name_heb", "occurrences", "reason"],
          lambda rc: [rc[0].get("local_id", ""), rc[0].get("name_heb", ""),
                      rc[0].get("occurrences", ""), rc[1]])

    write(os.path.join(OUT, "parked.tsv"),
          buckets["parked"],
          ["local_id", "name_heb", "name_rom", "occurrences", "reason"],
          lambda rc: [rc[0].get("local_id", ""), rc[0].get("name_heb", ""),
                      rc[0].get("name_rom", ""), rc[0].get("occurrences", ""), rc[1]])

    # manual remainder → full match columns (so build_kima_review_queue can consume it)
    manual_rows = [rc[0] for rc in buckets["manual"]]
    with open(MANUAL_OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(manual_rows)

    # append non-places to the reject stoplist (dedup)
    existing = set()
    if os.path.exists(STOPLIST):
        with open(STOPLIST, encoding="utf-8") as fh:
            existing = {r["name"] for r in csv.DictReader(fh, delimiter="\t") if r.get("name")}
    new_rejects = [rc[0].get("name_heb", "").strip() for rc in buckets["rejected"]
                   if rc[0].get("name_heb", "").strip()]
    to_add = [n for n in new_rejects if n not in existing]
    if to_add:
        write_header = not os.path.exists(STOPLIST)
        with open(STOPLIST, "a", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter="\t")
            if write_header:
                w.writerow(["name"])
            for n in to_add:
                w.writerow([n])

    # ── summary ──
    n = {k: len(v) for k, v in buckets.items()}
    total = sum(n.values())
    lines = [
        "# Auto-reclassify summary",
        f"\nTotal toponyms: {total}  ·  fuzzy auto-link threshold: {FUZZY_AUTOLINK_THRESHOLD}",
        f"\n- grade_a (→ spotcheck_grade_a.py): {n['grade_a']}",
        f"- **auto_linked** (confident + collapsed siblings): {n['auto_linked']} "
        f"→ auto_reclassify/auto_linked.tsv  ({len(trusted)} distinct Kima places)",
        f"- rejected (non-place stoplist → reject_stoplist.tsv): {n['rejected']} "
        f"(+{len(to_add)} appended)",
        f"- quick_confirm (acronyms, human glance): {n['quick_confirm']} "
        f"→ auto_reclassify/quick_confirm.tsv",
        f"- parked (single-occurrence no-match): {n['parked']}",
        f"- **manual** (real review → Kimatch app): {n['manual']} → manual_review.tsv",
        f"\nManual burden: {total} → **{n['manual']}** "
        f"({100*n['manual']//total}% of the original).",
    ]
    with open(os.path.join(OUT, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
