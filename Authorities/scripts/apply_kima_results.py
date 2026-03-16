#!/usr/bin/env python3
"""
apply_kima_results.py

Read Kimatch output (editions/unmatched-kima-results.csv), detect ambiguity,
and fill in `action` / `suggested_id` columns in unmatched-places-report.tsv.

Modes
-----
  --mode auto     (default) Auto-fill unambiguous, high-confidence matches.
  --mode confirm  Prompt for confirmation on EVERY match, even exact ones.

Usage
-----
  python3 Authorities/scripts/apply_kima_results.py
  python3 Authorities/scripts/apply_kima_results.py --mode confirm
  python3 Authorities/scripts/apply_kima_results.py --threshold 0.9 --no-kima-db
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

# ── default paths ─────────────────────────────────────────────────────────────
HERE      = Path(__file__).parent
REPO_ROOT = HERE.parent.parent
MATCHING_DB   = HERE.parent / "authorities-matching-db.json"
DEFAULT_TSV     = REPO_ROOT / "editions" / "unmatched-places-report.tsv"
DEFAULT_RESULTS = REPO_ROOT / "editions" / "unmatched-kima-results.csv"
KIMATCH_ROOT  = Path.home() / "Documents" / "GitHub" / "Kimatch"
DEFAULT_PLACES   = KIMATCH_ROOT / "20250126KimaPlacesCSVx.csv"
DEFAULT_VARIANTS = KIMATCH_ROOT / "Kima-Variants-20250929.tsv"

FUZZY_THRESHOLD     = 0.85  # minimum fuzzy confidence for auto-accept
KIMA_URL_PREFIX     = "https://data.geo-kima.org/Places/Details/"

# Names that are NOT geographic places in this corpus (collective/ethnic nouns)
SKIP_NAMES = {"ישראל"}
KIMA_COLS = [
    "_match_status", "_match_method", "_confidence", "_kima_id",
    "_kima_name_rom", "_kima_name_heb", "_distance_km", "_candidates",
]


# ── utilities ──────────────────────────────────────────────────────────────────

def kima_url_to_id(url: str) -> int | None:
    """Extract numeric Kima ID from 'https://data.geo-kima.org/Places/Details/102'."""
    m = re.search(r"/(\d+)$", url or "")
    return int(m.group(1)) if m else None


def build_kima_to_hloc(db_path: Path) -> dict[int, str]:
    """Return {kima_numeric_id: 'H-LOC_xxx'} from the authority matching DB."""
    with open(db_path, encoding="utf-8") as f:
        db = json.load(f)
    result: dict[int, str] = {}
    for p in db["places"]:
        hloc = p["id"]
        kima_url = p.get("identifiers", {}).get("Kima", "")
        kid = kima_url_to_id(kima_url)
        if kid is not None:
            result[kid] = hloc
    return result


def read_tsv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        content = f.read()
    return list(csv.DictReader(io.StringIO(content), delimiter="\t"))


def write_tsv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=fieldnames, delimiter="\t", quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        writer.writerows(rows)


def candidate_ids(row: dict) -> list[int]:
    """Extract all candidate kima IDs from a result row (kima_id + candidates)."""
    ids: list[int] = []
    for raw in [row.get("_kima_id", ""), *(row.get("_candidates", "").split("|"))]:
        raw = (raw or "").strip()
        if raw:
            try:
                ids.append(int(raw))
            except ValueError:
                pass
    # deduplicate preserving order
    seen: set[int] = set()
    deduped: list[int] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            deduped.append(i)
    return deduped


def best_kima_id(row: dict) -> int | None:
    ids = candidate_ids(row)
    return ids[0] if ids else None


def format_suggested_id(ids: list[int]) -> str:
    return "|".join(f"kima:{i}" for i in ids)


# ── ambiguity detection ────────────────────────────────────────────────────────

def is_ambiguous(row: dict, kima_db) -> bool:
    """
    A match is ambiguous if:
    - name_exact AND the name resolves to >1 Kima place (checked via KimaDB)
    - fuzzy AND there are ≥2 candidates (can't break the tie without coords)
    """
    status = row["_match_status"]

    if status == "name_exact":
        if kima_db is None:
            return False  # can't check without DB
        hits = kima_db.search_by_name(row["name"])
        return len(hits) > 1

    if status == "fuzzy":
        cands = [c for c in row.get("_candidates", "").split("|") if c.strip()]
        return len(cands) >= 2

    return False


# ── decision logic ─────────────────────────────────────────────────────────────

def determine_action(
    row: dict, kima_to_hloc: dict[int, str], threshold: float, kima_db
) -> tuple[str, str]:
    """
    Returns (action, suggested_id).

    action values:
      'map_to:H-LOC_xxx'  — links to existing authority entry
      'new'               — should create a new authority entry with this Kima ID
      'ambiguous'         — multiple plausible matches; needs human decision
      ''                  — low-confidence or no match; needs manual review
    """
    # Skip names that are not geographic places
    if row["name"] in SKIP_NAMES:
        return "skip", ""

    status = row["_match_status"]
    confidence = float(row.get("_confidence") or 0)

    if status == "no_match":
        return "", ""

    # Ambiguity check takes priority over confidence
    if is_ambiguous(row, kima_db):
        if status == "name_exact" and kima_db is not None:
            # Use all DB hits (not just Kimatch winner) for full picture
            hits = kima_db.search_by_name(row["name"])
            all_ids = [h.kima_id for h in hits]
        else:
            all_ids = candidate_ids(row)
        return "ambiguous", format_suggested_id(all_ids)

    high_conf = status == "name_exact" or (status == "fuzzy" and confidence >= threshold)
    if not high_conf:
        return "", ""  # not confident enough — leave for manual review

    kid = best_kima_id(row)
    if kid is None:
        return "", ""

    if kid in kima_to_hloc:
        return f"map_to:{kima_to_hloc[kid]}", f"kima:{kid}"
    else:
        return "new", f"kima:{kid}"


# ── confirm mode ───────────────────────────────────────────────────────────────

def confirm_row(row: dict, proposed_action: str, proposed_id: str) -> tuple[str, str]:
    """
    Print match info and prompt the user to accept, reject, or supply an action.
    Raises StopIteration when the user wants to stop early.
    """
    name       = row["name"]
    status     = row["_match_status"]
    conf       = row.get("_confidence", "")
    kima_rom   = row.get("_kima_name_rom", "")
    kima_heb   = row.get("_kima_name_heb", "")
    cands      = candidate_ids(row)
    cand_str   = " | ".join(f"kima:{c}" for c in cands) if cands else "(none)"

    print(f"\n{'─' * 62}")
    print(f"  Name:       {name}   ({row.get('occurrences', '?')} occurrences)")
    print(f"  Status:     {status}   confidence={conf}")
    print(f"  Candidates: {cand_str}")
    if kima_rom or kima_heb:
        print(f"  Best match: {kima_rom}  {kima_heb}")
    print(f"  → Proposed: {proposed_action or '(manual review)'}")
    if proposed_id:
        print(f"  → ID:       {proposed_id}")

    while True:
        ans = input(
            "  [y] accept  [n] skip  [s] stop  [action] custom > "
        ).strip()
        al = ans.lower()
        if al in ("y", "yes", ""):
            return proposed_action, proposed_id
        elif al in ("n", "no"):
            return "", ""
        elif al in ("s", "stop"):
            raise StopIteration
        elif (
            al.startswith("map_to:")
            or al in ("new", "skip", "ambiguous")
        ):
            return al, proposed_id
        else:
            print("    Enter y / n / s  or a custom action like 'map_to:H-LOC_xxx'")


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Apply Kimatch results to unmatched-places-report.tsv"
    )
    ap.add_argument(
        "--results", type=Path, default=DEFAULT_RESULTS,
        help="Kimatch enriched CSV (default: editions/unmatched-kima-results.csv)",
    )
    ap.add_argument(
        "--tsv", type=Path, default=DEFAULT_TSV,
        help="TSV to update (default: editions/unmatched-places-report.tsv)",
    )
    ap.add_argument(
        "--mode", choices=["auto", "confirm"], default="auto",
        help="auto=fill high-confidence matches silently; confirm=prompt for every match",
    )
    ap.add_argument(
        "--threshold", type=float, default=FUZZY_THRESHOLD,
        help=f"Fuzzy confidence threshold for auto-accept (default {FUZZY_THRESHOLD})",
    )
    ap.add_argument(
        "--places", type=Path, default=DEFAULT_PLACES,
        help="Kima Places CSV — needed for exact-match ambiguity detection",
    )
    ap.add_argument(
        "--variants", type=Path, default=DEFAULT_VARIANTS,
        help="Kima Variants TSV — needed for exact-match ambiguity detection",
    )
    ap.add_argument(
        "--no-kima-db", action="store_true",
        help="Skip KimaDB load (disables exact-match ambiguity detection)",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Print decisions without writing the TSV",
    )
    args = ap.parse_args()

    # ── load authority matching DB ────────────────────────────────────────────
    print("Loading authority matching DB…")
    kima_to_hloc = build_kima_to_hloc(MATCHING_DB)
    print(f"  {len(kima_to_hloc)} places already have Kima IDs in authority")

    # ── optionally load KimaDB for exact-match ambiguity detection ────────────
    kima_db = None
    if not args.no_kima_db and args.places.exists() and args.variants.exists():
        print("Loading KimaDB for ambiguity detection…")
        sys.path.insert(0, str(KIMATCH_ROOT))
        from kimatch.data.loader import KimaDB  # type: ignore[import]
        kima_db = KimaDB.load(str(args.places), str(args.variants))
        print(f"  {kima_db.place_count:,} places, {kima_db.variant_count:,} variants")
    else:
        print("  KimaDB not loaded — exact-match ambiguity detection disabled")

    # ── read Kimatch results ──────────────────────────────────────────────────
    print(f"\nReading Kimatch results: {args.results}")
    with open(args.results, encoding="utf-8") as f:
        results_by_name: dict[str, dict] = {r["name"]: r for r in csv.DictReader(f)}
    print(f"  {len(results_by_name)} rows")

    # ── read TSV ──────────────────────────────────────────────────────────────
    print(f"Reading TSV: {args.tsv}")
    tsv_rows = read_tsv(args.tsv)
    fieldnames = list(tsv_rows[0].keys()) if tsv_rows else []
    print(f"  {len(tsv_rows)} rows\n")

    # ── process ───────────────────────────────────────────────────────────────
    stats: Counter = Counter()

    try:
        for tsv_row in tsv_rows:
            name = tsv_row["name"]

            # Skip rows that already have an action
            if tsv_row.get("action", "").strip():
                stats["already_set"] += 1
                continue

            result = results_by_name.get(name)
            if result is None:
                stats["no_result"] += 1
                continue

            status = result["_match_status"]
            action, suggested_id = determine_action(
                result, kima_to_hloc, args.threshold, kima_db
            )

            # ── confirm mode: prompt for every non-no_match row ───────────────
            if args.mode == "confirm" and status != "no_match":
                try:
                    action, suggested_id = confirm_row(result, action, suggested_id)
                    stats["confirmed" if action else "rejected"] += 1
                except StopIteration:
                    print("\nStopping early — remaining rows left unset.")
                    break
            else:
                # Auto mode: tally
                if action.startswith("map_to:"):
                    stats["auto_mapped"] += 1
                elif action == "new":
                    stats["auto_new"] += 1
                elif action == "ambiguous":
                    stats["ambiguous"] += 1
                elif status == "no_match":
                    stats["no_match"] += 1
                else:
                    stats["low_conf"] += 1

            tsv_row["action"] = action
            tsv_row["suggested_id"] = suggested_id

    except KeyboardInterrupt:
        print("\nInterrupted.")

    # ── write ─────────────────────────────────────────────────────────────────
    if args.dry_run:
        print("\n[dry-run] No files written.")
    else:
        write_tsv(args.tsv, tsv_rows, fieldnames)
        print(f"\nUpdated TSV written → {args.tsv}")

    print("\nSummary:")
    total_match = stats["auto_mapped"] + stats["auto_new"] + stats["ambiguous"] + stats.get("confirmed", 0)
    for label, count in [
        ("already had action",         stats["already_set"]),
        ("auto-mapped to existing H-LOC", stats["auto_mapped"]),
        ("auto-marked as new (kima ID)", stats["auto_new"]),
        ("ambiguous — needs human review", stats["ambiguous"]),
        ("low confidence — needs review",  stats["low_conf"]),
        ("no match",                      stats["no_match"]),
        ("confirmed (confirm mode)",       stats.get("confirmed", 0)),
        ("rejected (confirm mode)",        stats.get("rejected", 0)),
    ]:
        if count:
            print(f"  {label}: {count}")
    print(f"  ─────────────────────────────────────────")
    print(f"  Total decisions made: {total_match}")


if __name__ == "__main__":
    main()
