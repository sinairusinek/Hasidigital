#!/usr/bin/env python3
"""Merge Dvarim-Yekarim Old (editorial) + New (structural) editions.

Uses OLD as base (story divs, teiHeader, corrections) and imports
structural info from NEW (fw, headings) via facsimile zone subtypes.

Usage:
  python merge_dvarim.py [--dry-run]
"""

import argparse
import re
import sys
from pathlib import Path
from lxml import etree

# Add parent dir so we can import from annotate_fw
sys.path.insert(0, str(Path(__file__).parent))
from annotate_fw import get_text_content, convert_to_fw, annotate_fw, TEI, NS

EDITIONS_DIR = Path(__file__).resolve().parent.parent.parent / "editions" / "online"
OLD_PATH = EDITIONS_DIR / "Dvarim-YekarimOld.xml"
NEW_PATH = EDITIONS_DIR / "Dvarim-YekarimNew.xml"
OUT_PATH = EDITIONS_DIR / "Dvarim-Yekarim.xml"

# Map Transkribus zone subtypes to our fw types
ZONE_TO_FW = {
    "page-number": "pageNum",
    "running-head": "running-head",
    "catch-word": "catch",
}


def normalize_text(text):
    """Normalize text for matching: strip, collapse whitespace, remove quotes."""
    if not text:
        return ""
    text = text.strip()
    # Normalize various quote chars
    text = text.replace('"', '"').replace('"', '"').replace("'", "'").replace("'", "'")
    text = text.replace("&quot;", '"').replace("&apos;", "'")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text


def build_zone_map(new_tree):
    """Build zone_id → subtype map from NEW file's <facsimile> sections."""
    zone_map = {}
    for zone in new_tree.xpath("//t:zone[@subtype]", namespaces=NS):
        zone_id = zone.get("{http://www.w3.org/XML/1998/namespace}id")
        if zone_id:
            zone_map[zone_id] = zone.get("subtype")
    return zone_map


def build_text_subtype_map(new_tree, zone_map):
    """Map normalized text content → subtype for structural paragraphs in NEW."""
    text_map = {}  # normalized_text → subtype

    for p in new_tree.xpath("//t:p[@facs]", namespaces=NS):
        facs = p.get("facs", "")
        if facs.startswith("#"):
            zone_id = facs[1:]
        else:
            zone_id = facs

        subtype = zone_map.get(zone_id)
        if not subtype:
            continue

        # Get text content (ignoring lb, story tags, etc.)
        text = get_text_content_new(p)
        norm = normalize_text(text)
        if norm:
            text_map[norm] = subtype

    return text_map


def get_text_content_new(elem):
    """Get text content from NEW file element, handling story tags and sic/correction."""
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
        if tag == "lb":
            if child.tail:
                parts.append(child.tail)
        elif tag == "story":
            # Include story tag text
            if child.text:
                parts.append(child.text)
            if child.tail:
                parts.append(child.tail)
        elif tag == "sic":
            # Use correction attribute if present, otherwise tag text
            correction = child.get("correction")
            if correction:
                parts.append(correction)
            elif child.text:
                parts.append(child.text)
            if child.tail:
                parts.append(child.tail)
        else:
            parts.append(etree.tostring(child, method="text", encoding="unicode") or "")
            if child.tail:
                parts.append(child.tail)
    return "".join(parts).strip()


def fix_pb_facs(old_tree):
    """Fix pb facs attributes: Shemen-Hatov_* → Dvarim-Yekarim_*."""
    changes = []
    for pb in old_tree.xpath("//t:pb", namespaces=NS):
        old_facs = pb.get("facs", "")
        if "Shemen-Hatov" in old_facs:
            # Extract page number, handling both _0001 and _00010 patterns
            m = re.search(r"_0*(\d+)\.jpg", old_facs)
            if m:
                page_num = int(m.group(1))
                new_facs = f"Dvarim-Yekarim_{page_num:04d}.jpg"
                changes.append(f"  pb facs: '{old_facs}' → '{new_facs}'")
                pb.set("facs", new_facs)
    return changes


def annotate_structural(old_tree, text_map, dry_run=False):
    """Annotate fw and heading elements in OLD tree using text_map from NEW."""
    changes = []
    counts = {"pageNum": 0, "running-head": 0, "catch": 0, "heading": 0}

    P_TAG = f"{{{TEI}}}p"
    HEAD_TAG = f"{{{TEI}}}head"

    # Collect all <p> elements that might be structural
    for p in list(old_tree.xpath("//t:p", namespaces=NS)):
        text = get_text_content(p)
        norm = normalize_text(text)
        if not norm:
            continue

        subtype = text_map.get(norm)
        if not subtype:
            continue

        if subtype in ZONE_TO_FW:
            fw_type = ZONE_TO_FW[subtype]
            changes.append(f"  fw {fw_type}: '{text}'")
            counts[fw_type] += 1
            if not dry_run:
                convert_to_fw(p, fw_type)
        elif subtype == "heading":
            # Check if parent is already a <head> or if this <p> should become one
            parent = p.getparent()
            if p.tag == HEAD_TAG:
                continue  # already a head
            changes.append(f"  heading: '{text}'")
            counts["heading"] += 1
            if not dry_run:
                p.tag = HEAD_TAG

    return counts, changes


def main():
    parser = argparse.ArgumentParser(description="Merge Dvarim-Yekarim editions.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing output")
    args = parser.parse_args()

    if not OLD_PATH.exists():
        print(f"Error: {OLD_PATH} not found")
        return 1
    if not NEW_PATH.exists():
        print(f"Error: {NEW_PATH} not found")
        return 1

    xml_parser = etree.XMLParser(remove_blank_text=False)
    old_tree = etree.parse(str(OLD_PATH), xml_parser)
    new_tree = etree.parse(str(NEW_PATH), xml_parser)

    # Step 1: Build zone map from NEW
    zone_map = build_zone_map(new_tree)
    print(f"Zone map: {len(zone_map)} zones")

    text_map = build_text_subtype_map(new_tree, zone_map)
    print(f"Text-subtype map: {len(text_map)} entries")
    for norm_text, subtype in sorted(text_map.items(), key=lambda x: x[1]):
        print(f"  [{subtype}] {norm_text[:60]}")

    # Step 2: Fix pb facs
    pb_changes = fix_pb_facs(old_tree)
    print(f"\nPB facs fixes: {len(pb_changes)}")
    for c in pb_changes:
        print(c)

    # Step 3 & 4: Annotate structural elements using zone-subtype map
    counts, struct_changes = annotate_structural(old_tree, text_map, dry_run=args.dry_run)
    print(f"\nZone-based annotations:")
    for c in struct_changes:
        print(c)

    print(f"\n  Zone totals: {counts['pageNum']} pageNum,"
          f" {counts['running-head']} running-head,"
          f" {counts['catch']} catch,"
          f" {counts['heading']} heading")

    # Step 5: Heuristic fallback for remaining fw (catches page numbers & catch words
    # that weren't in the zone map because Transkribus didn't create <p> elements for them)
    heur_counts, heur_changes = annotate_fw(old_tree, dry_run=args.dry_run)
    if heur_changes:
        print(f"\nHeuristic fw annotations (fallback):")
        for c in heur_changes:
            print(c)
        print(f"\n  Heuristic totals: {heur_counts['pageNum']} pageNum,"
              f" {heur_counts['running-head']} running-head,"
              f" {heur_counts['catch']} catch")

    total = (sum(counts.values()) + sum(heur_counts.values()))
    print(f"\nTotal annotations: {total}")

    if not args.dry_run:
        old_tree.write(str(OUT_PATH), encoding="utf-8", xml_declaration=True)
        print(f"\nWritten to {OUT_PATH}")
    else:
        print(f"\nDry run — no files written")

    return 0


if __name__ == "__main__":
    exit(main())
