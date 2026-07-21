#!/usr/bin/env python3
"""Merge an edited TEI edition (OLD) with a Transkribus re-export (NEW).

Uses OLD as base (story divs, teiHeader, corrections, NER) and imports
structural info from NEW (fw, headings) via facsimile zone subtypes.

Usage:
  python merge_structural.py <EditionName> [--dry-run]

Example:
  python merge_structural.py MaasiyotUmaamarimYekarim --dry-run
  python merge_structural.py Shemen-Hatov

Expects files:
  editions/online/<EditionName>.xml      (OLD, edited)
  editions/online/<EditionName>New.xml   (NEW, Transkribus export)

Output:
  editions/online/<EditionName>.xml      (merged, overwrites OLD)
  editions/online/<EditionName>Old.xml   (backup of original OLD)
"""

import argparse
import re
import shutil
import sys
from pathlib import Path
from lxml import etree

sys.path.insert(0, str(Path(__file__).parent))
from annotate_fw import get_text_content, convert_to_fw, annotate_fw, TEI, NS

EDITIONS_DIR = Path(__file__).resolve().parent.parent.parent / "editions" / "online"

ZONE_TO_FW = {
    "page-number": "pageNum",
    "running-head": "running-head",
    "catch-word": "catch",
}


def normalize_text(text):
    """Normalize text for matching: strip, collapse whitespace, normalize quotes."""
    if not text:
        return ""
    text = text.strip()
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('\u2018', "'").replace('\u2019', "'")
    text = text.replace("&quot;", '"').replace("&apos;", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def build_zone_map(new_tree):
    """Build zone_id -> subtype map from NEW file's <facsimile> sections."""
    zone_map = {}
    for zone in new_tree.xpath("//t:zone[@subtype]", namespaces=NS):
        zone_id = zone.get("{http://www.w3.org/XML/1998/namespace}id")
        if zone_id:
            zone_map[zone_id] = zone.get("subtype")
    return zone_map


def build_text_subtype_map(new_tree, zone_map):
    """Map normalized text content -> subtype for structural paragraphs in NEW."""
    text_map = {}

    for p in new_tree.xpath("//t:p[@facs]", namespaces=NS):
        facs = p.get("facs", "")
        zone_id = facs[1:] if facs.startswith("#") else facs
        subtype = zone_map.get(zone_id)
        if not subtype:
            continue

        text = get_text_content_new(p)
        norm = normalize_text(text)
        if norm:
            text_map[norm] = subtype

    return text_map


def get_text_content_new(elem):
    """Get text content from NEW file element, handling story/sic tags."""
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
        if tag == "lb":
            if child.tail:
                parts.append(child.tail)
        elif tag == "story":
            if child.text:
                parts.append(child.text)
            if child.tail:
                parts.append(child.tail)
        elif tag == "sic":
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


def annotate_structural(old_tree, text_map, dry_run=False):
    """Annotate fw and heading elements in OLD tree using text_map from NEW."""
    changes = []
    counts = {"pageNum": 0, "running-head": 0, "catch": 0, "heading": 0}
    HEAD_TAG = f"{{{TEI}}}head"

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
            changes.append(f"  fw {fw_type}: '{norm[:70]}'")
            counts[fw_type] += 1
            if not dry_run:
                convert_to_fw(p, fw_type)
        elif subtype == "heading":
            if p.tag == HEAD_TAG:
                continue
            changes.append(f"  heading: '{norm[:70]}'")
            counts["heading"] += 1
            if not dry_run:
                p.tag = HEAD_TAG

    return counts, changes


def main():
    parser = argparse.ArgumentParser(
        description="Merge edited TEI edition with Transkribus structural export.")
    parser.add_argument("edition", help="Edition name (e.g. MaasiyotUmaamarimYekarim)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without modifying files")
    args = parser.parse_args()

    old_path = EDITIONS_DIR / f"{args.edition}.xml"
    new_path = EDITIONS_DIR / f"{args.edition}New.xml"
    backup_path = EDITIONS_DIR / f"{args.edition}Old.xml"

    if not old_path.exists():
        print(f"Error: {old_path} not found")
        return 1
    if not new_path.exists():
        print(f"Error: {new_path} not found")
        return 1

    xml_parser = etree.XMLParser(remove_blank_text=False)
    old_tree = etree.parse(str(old_path), xml_parser)
    new_tree = etree.parse(str(new_path), xml_parser)

    # Step 1: Build zone map from NEW
    zone_map = build_zone_map(new_tree)
    text_map = build_text_subtype_map(new_tree, zone_map)
    print(f"{args.edition}: {len(zone_map)} zones, {len(text_map)} text-subtype entries")

    # Show structural entries only (skip main-text, paragraph)
    structural = {k: v for k, v in text_map.items()
                  if v in ZONE_TO_FW or v == "heading"}
    for norm_text, subtype in sorted(structural.items(), key=lambda x: x[1]):
        print(f"  [{subtype}] {norm_text[:70]}")

    # Step 2: Annotate structural elements using zone-subtype map
    counts, struct_changes = annotate_structural(old_tree, text_map, dry_run=args.dry_run)
    print(f"\nZone-based: {counts['pageNum']} pageNum, {counts['running-head']} running-head,"
          f" {counts['catch']} catch, {counts['heading']} heading")
    for c in struct_changes:
        print(c)

    # Step 3: Heuristic fallback
    heur_counts, heur_changes = annotate_fw(old_tree, dry_run=args.dry_run)
    if heur_changes:
        print(f"\nHeuristic fallback: {heur_counts['pageNum']} pageNum,"
              f" {heur_counts['running-head']} running-head,"
              f" {heur_counts['catch']} catch")
        for c in heur_changes:
            print(c)

    total = sum(counts.values()) + sum(heur_counts.values())
    print(f"\nTotal: {total} annotations")

    if not args.dry_run:
        # Backup old file if not already backed up
        if not backup_path.exists():
            shutil.copy2(old_path, backup_path)
            print(f"Backed up {old_path.name} → {backup_path.name}")
        old_tree.write(str(old_path), encoding="utf-8", xml_declaration=True)
        print(f"Written to {old_path}")
    else:
        print("\nDry run — no files written")

    return 0


if __name__ == "__main__":
    exit(main())
