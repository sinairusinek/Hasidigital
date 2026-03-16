#!/usr/bin/env python3
"""
Batch Place-Name Linker
=======================
Auto-links unlinked <placeName> elements across all corrected/gemini editions
to the authorities matching DB, and produces a TSV report of unmatched names.

Usage:
    python3 Authorities/scripts/batch_link_places.py [--dry-run]

Flags:
    --dry-run   Show what would happen without modifying any files.
"""
import argparse
import csv
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter

# ── Paths (mirror config.py but standalone) ──────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
PROJECT_DIR = os.path.abspath(os.path.join(AUTH_DIR, ".."))
EDITIONS_INCOMING = os.path.join(PROJECT_DIR, "editions", "incoming")
MATCHING_DB_PATH = os.path.join(AUTH_DIR, "authorities-matching-db.json")
REPORT_PATH = os.path.join(PROJECT_DIR, "editions", "unmatched-places-report.tsv")

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

# Names that are NOT geographic places in this corpus (collective/ethnic nouns)
SKIP_NAMES = {"ישראל"}


# ── Helpers (from edition_linker.py, standalone) ─────────────────────────────

def build_variant_index(db):
    """Build lookup: variant_name -> place dict from matching DB."""
    index = {}
    for place in db["places"]:
        for name in place.get("names_he", []) + place.get("names_en", []):
            if name and name not in index:
                index[name] = place
    return index


def detect_lang(text):
    """Detect Hebrew vs Latin text."""
    return "he" if any('\u0590' <= c <= '\u05FF' for c in text) else "en"


def elem_full_text(elem):
    """Full text content of an element including descendants."""
    return "".join(elem.itertext()).strip()


def build_parent_map(root):
    """Child -> parent mapping for the XML tree."""
    return {child: parent for parent in root.iter() for child in parent}


def find_parent_p(elem, parent_map):
    """Find nearest ancestor <p> element."""
    current = elem
    while current is not None:
        current = parent_map.get(current)
        if current is not None and current.tag == f"{{{TEI_NS}}}p":
            return current
    return None


# ── Main logic ───────────────────────────────────────────────────────────────

def process_editions(db, variant_index, dry_run=False):
    """
    Process all corrected/gemini editions.
    Returns (total_refs_added, new_variants_added, unmatched_global)
    where unmatched_global maps name -> {occurrences, editions, contexts}.
    """
    edition_files = sorted([
        f for f in os.listdir(EDITIONS_INCOMING)
        if f.endswith(("_corrected.xml", "_gemini.xml"))
    ])

    if not edition_files:
        print("No corrected/gemini XML files found.")
        return 0, 0, {}

    total_refs = 0
    new_variants = 0
    # Global tracker for unmatched names
    unmatched_global = {}  # name -> {occurrences, editions: set, contexts: list}

    # Pre-build set of known variants for quick new-variant detection
    known_variants = set()
    for place in db["places"]:
        known_variants.update(place.get("names_he", []))
        known_variants.update(place.get("names_en", []))

    print(f"Processing {len(edition_files)} editions...\n")

    for fn in edition_files:
        path = os.path.join(EDITIONS_INCOMING, fn)
        ET.register_namespace('', TEI_NS)
        ET.register_namespace('xml', XML_NS)
        tree = ET.parse(path)
        root = tree.getroot()
        parent_map = build_parent_map(root)

        refs_added = 0
        unlinked_count = 0
        unmatched_count = 0

        for pn_elem in root.findall(f".//{{{TEI_NS}}}placeName"):
            if pn_elem.get("ref"):
                continue  # already linked

            text = (pn_elem.text or "").strip()
            if not text:
                continue
            if text in SKIP_NAMES:
                continue  # not a geographic place

            unlinked_count += 1

            if text in variant_index:
                place = variant_index[text]
                pn_elem.set("ref", f"#{place['id']}")
                refs_added += 1

                # Track new variant for DB update
                if text not in known_variants:
                    lang = detect_lang(text)
                    key = "names_he" if lang == "he" else "names_en"
                    if text not in place.get(key, []):
                        place.setdefault(key, []).append(text)
                        known_variants.add(text)
                        new_variants += 1
            else:
                # Unmatched — collect for report
                unmatched_count += 1
                if text not in unmatched_global:
                    unmatched_global[text] = {
                        "occurrences": 0,
                        "editions": set(),
                        "contexts": [],
                    }
                entry = unmatched_global[text]
                entry["occurrences"] += 1
                entry["editions"].add(fn)
                # Collect up to 2 unique contexts
                if len(entry["contexts"]) < 2:
                    parent_p = find_parent_p(pn_elem, parent_map)
                    if parent_p is not None:
                        ctx = elem_full_text(parent_p)
                        if ctx and ctx not in entry["contexts"]:
                            entry["contexts"].append(ctx)

        if refs_added > 0 and not dry_run:
            tree.write(path, encoding="utf-8", xml_declaration=True)

        total_refs += refs_added
        still_unmatched = unlinked_count - refs_added
        status = "(dry-run) " if dry_run else ""
        print(f"  {status}{fn}: {refs_added} refs added "
              f"({unlinked_count} unlinked, {still_unmatched} still unmatched)")

    return total_refs, new_variants, unmatched_global


def save_matching_db(db):
    """Write updated matching DB back to disk."""
    import datetime
    db["meta"]["generated"] = datetime.datetime.now().isoformat()
    with open(MATCHING_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def write_report(unmatched_global):
    """Write unmatched names report TSV."""
    rows = []
    for name, info in unmatched_global.items():
        rows.append({
            "name": name,
            "occurrences": info["occurrences"],
            "editions": "; ".join(sorted(info["editions"])),
            "contexts": " ||| ".join(info["contexts"]),
            "suggested_id": "",
            "action": "",
        })
    # Sort by frequency descending
    rows.sort(key=lambda r: -r["occurrences"])

    with open(REPORT_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys(), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Batch place-name linker")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without modifying files")
    args = parser.parse_args()

    # Load matching DB
    print(f"Loading matching DB from {MATCHING_DB_PATH}...")
    with open(MATCHING_DB_PATH, "r", encoding="utf-8") as f:
        db = json.load(f)
    print(f"  {len(db['places'])} places, building variant index...")

    variant_index = build_variant_index(db)
    print(f"  {len(variant_index)} unique name variants indexed.\n")

    # Process all editions
    total_refs, new_variants, unmatched_global = process_editions(
        db, variant_index, dry_run=args.dry_run
    )

    print(f"\n{'=' * 60}")
    print(f"Total refs added: {total_refs}")
    print(f"New variants added to matching DB: {new_variants}")
    print(f"Unmatched unique names: {len(unmatched_global)}")

    if not args.dry_run:
        # Save updated matching DB
        if new_variants > 0:
            save_matching_db(db)
            print(f"Matching DB updated: {MATCHING_DB_PATH}")

        # Write unmatched report
        if unmatched_global:
            report_rows = write_report(unmatched_global)
            print(f"Unmatched report: {REPORT_PATH} ({report_rows} rows)")
    else:
        print("\n(Dry run — no files modified)")


if __name__ == "__main__":
    main()
