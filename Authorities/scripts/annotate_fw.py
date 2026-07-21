#!/usr/bin/env python3
"""Annotate forme work (<fw>) elements in TEI XML editions.

Detects page numbers, running heads, and catch words around <pb> breaks
and converts the enclosing <p> elements to <fw> with appropriate @type.

Rules:
  - pageNum:      first <p> after <pb> whose text is 1-3 digits
  - running-head: next 1-3 <p> after <pb>/pageNum whose text is 1-2 words
  - catch:        last <p> before <pb> whose text is a single word (no spaces)

Usage:
  python annotate_fw.py EDITION.xml [--dry-run]
"""

import argparse
import re
from pathlib import Path
from lxml import etree

TEI = "http://www.tei-c.org/ns/1.0"
NS = {"t": TEI}

# Entity tags to strip (unwrap) inside <fw> elements
ENTITY_TAGS = {
    f"{{{TEI}}}persName",
    f"{{{TEI}}}placeName",
    f"{{{TEI}}}name",
}


def get_text_content(elem):
    """Return the concatenated text content of an element, ignoring <lb/> tags."""
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        if child.tag == f"{{{TEI}}}lb":
            # skip <lb/> but include its tail
            if child.tail:
                parts.append(child.tail)
        else:
            # include all text from child subtree
            parts.append(etree.tostring(child, method="text", encoding="unicode") or "")
            if child.tail:
                parts.append(child.tail)
    return "".join(parts).strip()


def unwrap_entity_tags(elem):
    """Remove entity markup tags inside elem, preserving their text content."""
    for entity in list(elem.iter()):
        if entity.tag in ENTITY_TAGS:
            parent = entity.getparent()
            # Merge entity's text into preceding context
            prev = entity.getprevious()
            if prev is not None:
                prev.tail = (prev.tail or "") + (entity.text or "")
            else:
                parent.text = (parent.text or "") + (entity.text or "")
            # Move children of entity to parent
            idx = list(parent).index(entity)
            for i, child in enumerate(list(entity)):
                parent.insert(idx + i, child)
            # Attach entity's tail to the last moved child or preceding text
            if len(list(entity)) == 0:
                # no children were moved
                if prev is not None:
                    prev.tail = (prev.tail or "") + (entity.tail or "")
                elif idx > 0:
                    list(parent)[idx - 1].tail = (list(parent)[idx - 1].tail or "") + (entity.tail or "")
                else:
                    parent.text = (parent.text or "") + (entity.tail or "")
            else:
                last_moved = parent[idx + len(list(entity)) - 1]
                last_moved.tail = (last_moved.tail or "") + (entity.tail or "")
            parent.remove(entity)


def convert_to_fw(elem, fw_type):
    """Convert a <p> element to <fw type='...'>."""
    elem.tag = f"{{{TEI}}}fw"
    elem.set("type", fw_type)
    unwrap_entity_tags(elem)


def next_element_sibling(elem):
    """Return the next sibling that is an Element (skip text nodes)."""
    sib = elem.getnext()
    return sib


def prev_element_sibling(elem):
    """Return the previous sibling that is an Element."""
    sib = elem.getprevious()
    return sib


def annotate_fw(tree, dry_run=False):
    """Find <pb> elements and annotate surrounding <p> as <fw>.

    Returns dict with counts of each fw type added.
    """
    counts = {"pageNum": 0, "running-head": 0, "catch": 0}
    changes = []  # for dry-run reporting

    pbs = tree.xpath("//t:pb", namespaces=NS)

    for pb in pbs:
        facs = pb.get("facs", "?")

        # --- Catch word: last <p> before this <pb> ---
        prev = prev_element_sibling(pb)
        if prev is not None and prev.tag == f"{{{TEI}}}p":
            text = get_text_content(prev)
            # Must be a single word (no spaces) and NOT digits-only
            # (digit-only text before <pb> is likely a misplaced page number)
            if text and " " not in text and not re.match(r"^\d+$", text):
                changes.append(f"  catch: '{text}' (before {facs})")
                counts["catch"] += 1
                if not dry_run:
                    convert_to_fw(prev, "catch")

        # --- Page number & running heads after <pb> ---
        # Order-independent: scan up to 4 short <p> siblings after <pb>,
        # classify each as pageNum (digits) or running-head (1-2 words).
        candidates = []
        nxt = next_element_sibling(pb)
        for _ in range(4):
            if nxt is None or nxt.tag != f"{{{TEI}}}p":
                break
            text = get_text_content(nxt)
            if not text:
                break
            words = text.split()
            if re.match(r"^\d{1,3}$", text):
                candidates.append((nxt, text, "pageNum"))
            elif len(words) in (1, 2):
                candidates.append((nxt, text, "running-head"))
            else:
                break  # hit real content
            nxt = next_element_sibling(nxt)

        for elem, text, fw_type in candidates:
            changes.append(f"  {fw_type}: '{text}' (after {facs})")
            counts[fw_type] += 1
            if not dry_run:
                convert_to_fw(elem, fw_type)

    return counts, changes


def main():
    parser = argparse.ArgumentParser(description="Annotate <fw> elements in TEI XML.")
    parser.add_argument("xml_file", type=Path, help="Path to TEI XML edition")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without modifying the file")
    args = parser.parse_args()

    xml_path = args.xml_file
    if not xml_path.exists():
        print(f"Error: {xml_path} not found")
        return 1

    xml_parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(str(xml_path), xml_parser)

    counts, changes = annotate_fw(tree, dry_run=args.dry_run)

    if args.dry_run:
        print(f"Dry run for {xml_path.name}:")
        for c in changes:
            print(c)
    else:
        # Write back
        tree.write(str(xml_path), encoding="utf-8", xml_declaration=True)
        print(f"Updated {xml_path.name}")

    total = sum(counts.values())
    print(f"\nSummary: {total} <fw> annotations"
          f" ({counts['pageNum']} pageNum,"
          f" {counts['running-head']} running-head,"
          f" {counts['catch']} catch)")
    return 0


if __name__ == "__main__":
    exit(main())
