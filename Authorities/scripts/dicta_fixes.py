#!/usr/bin/env python3
"""
Track A: Deterministic fixes for known DictaBERT NER errors.

Applies rule-based corrections to TEI XML edition files — no LLM involved.
Each fix is a separate function that can be run independently or all together.

Usage:
    python -m Authorities.scripts.dicta_fixes editions/online/Buzina_Denehora.xml
    python -m Authorities.scripts.dicta_fixes editions/online/          # all files
    python -m Authorities.scripts.dicta_fixes editions/online/ --dry-run
"""

import argparse
import logging
import re
import sys
from copy import deepcopy
from pathlib import Path

from lxml import etree

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI_NS}
TEI = f"{{{TEI_NS}}}"

logger = logging.getLogger(__name__)

# ── Utility helpers ───────────────────────────────────────────────────────────

def _text_content(el):
    """Full text content of element including children."""
    return "".join(el.itertext()).strip()


def _unwrap_element(el):
    """Remove an element but keep its text and children in the parent."""
    parent = el.getparent()
    if parent is None:
        return
    idx = list(parent).index(el)

    # Merge el.text into preceding sibling's tail or parent's text
    if el.text:
        if idx > 0:
            prev = parent[idx - 1]
            prev.tail = (prev.tail or "") + el.text
        else:
            parent.text = (parent.text or "") + el.text

    # Move children into parent at the same position
    for i, child in enumerate(el):
        parent.insert(idx + i, child)

    # Merge el.tail into the last moved child's tail or preceding text
    if el.tail:
        if len(el) > 0:
            last_child = el[-1]  # but it's been moved — use parent[idx + len(el) - 1]
            moved_last = parent[idx + len(list(el)) - 1]
            moved_last.tail = (moved_last.tail or "") + el.tail
        elif idx > 0:
            prev = parent[idx - 1]
            prev.tail = (prev.tail or "") + el.tail
        else:
            parent.text = (parent.text or "") + el.tail

    parent.remove(el)


def _remove_element_keep_text(el):
    """Remove element, merging its text content into surrounding text."""
    parent = el.getparent()
    if parent is None:
        return
    idx = list(parent).index(el)
    full_text = _text_content(el)
    combined = (full_text or "") + (el.tail or "")

    if idx > 0:
        prev = parent[idx - 1]
        prev.tail = (prev.tail or "") + combined
    else:
        parent.text = (parent.text or "") + combined

    # Remove any children first (they become plain text)
    for child in list(el):
        el.remove(child)
    parent.remove(el)


# ── Fix 1: Remove empty self-closing NER tags ────────────────────────────────

def fix_empty_self_closing_tags(tree):
    """
    Remove empty self-closing NER tags (<persName/>, <orgName/>, <placeName/>)
    that DictaBERT inserts inside abbreviations.

    These appear before abbreviation marks (״/׳) and split the surrounding
    tag's text. After removal, the text flows naturally.
    """
    count = 0
    ner_local = ["persName", "orgName", "placeName"]

    for local_name in ner_local:
        for el in tree.xpath(f"//tei:{local_name}", namespaces=NS):
            # Empty = no text, no children
            has_text = (el.text or "").strip()
            has_children = len(el) > 0
            if not has_text and not has_children:
                parent = el.getparent()
                if parent is None:
                    continue
                idx = list(parent).index(el)
                # Merge tail into preceding sibling's tail or parent text
                if el.tail:
                    if idx > 0:
                        prev = parent[idx - 1]
                        prev.tail = (prev.tail or "") + el.tail
                    else:
                        parent.text = (parent.text or "") + el.tail
                parent.remove(el)
                count += 1

    return count


# ── Fix 2: Flatten nested same-type tags ──────────────────────────────────────

def fix_nested_same_type(tree):
    """
    Flatten nested same-type NER tags (persName inside persName, etc.).

    Strategy: keep the inner element (which usually has ref/attributes),
    merge any attributes from the outer element that the inner lacks,
    then unwrap the outer.
    """
    count = 0
    ner_local = ["persName", "placeName", "orgName"]

    for local_name in ner_local:
        # Find outer elements that contain a direct or indirect same-type child
        xpath = f"//tei:{local_name}[.//tei:{local_name}]"
        outers = tree.xpath(xpath, namespaces=NS)

        for outer in outers:
            # Find all inner same-type descendants
            inners = outer.xpath(f".//tei:{local_name}", namespaces=NS)
            if not inners:
                continue

            # Merge outer's attributes into inner (inner wins on conflict)
            for inner in inners:
                for attr_name, attr_val in outer.attrib.items():
                    if attr_name not in inner.attrib:
                        inner.set(attr_name, attr_val)

            # Unwrap the outer element
            _unwrap_element(outer)
            count += 1

    return count


# ── Fix 3: Remove stray punctuation entities ─────────────────────────────────

def fix_stray_punctuation(tree):
    """
    Remove persName/placeName/orgName tags that contain only punctuation
    (geresh ׳, gershayim ״, quotes, single letters that are clearly
    not abbreviation-names).
    """
    count = 0
    # Punctuation-only pattern: only contains geresh, gershayim, quotes, spaces
    punct_only = re.compile(r'^[\s׳״\'\"''""`]+$')

    ner_local = ["persName", "orgName", "placeName"]
    for local_name in ner_local:
        for el in tree.xpath(f"//tei:text//tei:{local_name}", namespaces=NS):
            text = _text_content(el)
            if punct_only.match(text):
                _remove_element_keep_text(el)
                count += 1

    return count


# ── Fix 4: Remove bare honorific tags ─────────────────────────────────────────

def fix_bare_honorifics(tree):
    """
    Remove persName tags that contain only a title/honorific abbreviation
    (מו"ה, מוה, מוהר, etc.) with no actual person name.
    """
    count = 0
    # Known bare honorifics that DictaBERT tags as persName
    bare_titles = {
        'מו"ה', "מו״ה", "מוה", "מוהר", "מו", "מוהרר",
        "הרב", "הרה״ק", 'הרה"ק',
    }

    for el in tree.xpath("//tei:text//tei:persName", namespaces=NS):
        text = _text_content(el)
        if text in bare_titles and len(el) == 0:
            _remove_element_keep_text(el)
            count += 1

    return count


# ── Fix 5: Remove ק״ק false placeName tags ───────────────────────────────────

def fix_kk_placename(tree):
    """
    Remove <placeName> tags where the text is exactly ק״ק / ק"ק
    (קהילת קודש = holy community — a prefix, not a place name).
    """
    count = 0
    kk_forms = {'ק״ק', 'ק"ק'}

    for el in tree.xpath("//tei:text//tei:placeName", namespaces=NS):
        text = _text_content(el)
        if text in kk_forms and len(el) == 0:
            _remove_element_keep_text(el)
            count += 1

    return count


# ── Fix 6: Remove נבג״מ false placeName tags ─────────────────────────────────

def fix_nbgm_placename(tree):
    """
    Remove <placeName> tags where the text is נבג״מ / נבג"מ
    (an honorific abbreviation, not a place).
    """
    count = 0
    nbgm_forms = {'נבג״מ', 'נבג"מ'}

    for el in tree.xpath("//tei:text//tei:placeName", namespaces=NS):
        text = _text_content(el)
        if text in nbgm_forms:
            _remove_element_keep_text(el)
            count += 1

    return count


# ── Fix 7: Fix divine name tags ───────────────────────────────────────────────

def fix_divine_names(tree):
    """
    Fix divine names incorrectly tagged as persName:
    - הקב״ה / הקב"ה → remove persName tag (already inside name[misc] usually)
    - השי״ת / השי"ת → remove persName tag
    - ד׳ / ד' → remove persName tag
    If the divine name is inside a <name type="misc">, just remove the persName.
    If standalone persName, remove the tag entirely.
    """
    count = 0
    divine_patterns = re.compile(
        r'^(ה?קב[״"]ה|ה?שי[״"]ת|בהשי[״"]ת|ד[׳\'])$'
    )

    for el in tree.xpath("//tei:text//tei:persName", namespaces=NS):
        text = _text_content(el)
        if divine_patterns.match(text):
            _remove_element_keep_text(el)
            count += 1

    return count


# ── Fix 8: Remove לפ״ק false placeName tags ──────────────────────────────────

def fix_lpk_placename(tree):
    """
    Remove <placeName> tags where the text is/contains לפ״ק / לפ"ק
    (date-era suffix, not a place).
    """
    count = 0
    lpk_forms = {'לפ״ק', 'לפ"ק', 'פ״ק', 'פ"ק'}

    for el in tree.xpath("//tei:text//tei:placeName", namespaces=NS):
        text = _text_content(el)
        if text in lpk_forms:
            _remove_element_keep_text(el)
            count += 1

    return count


# ── Fix 9: Repair abbreviation boundaries ─────────────────────────────────────

def fix_abbreviation_boundaries(tree):
    """
    Fix tags that end with an abbreviation mark (״/׳) but the final letter
    of the abbreviation is orphaned in the tag's tail.

    Example: <name type="misc">שי״</name>ת → <name type="misc">שי״ת</name>
    Also:    <name type="misc">הקב״</name>ה → <name type="misc">הקב״ה</name>

    Only extends by one Hebrew letter from the tail.
    """
    count = 0
    abbrev_marks = {'״', '׳', '"', "'"}
    hebrew_re = re.compile(r'^[\u05D0-\u05EA]')  # starts with Hebrew letter

    tag_names = ["name", "persName", "placeName", "orgName"]
    for local_name in tag_names:
        for el in tree.xpath(f"//tei:text//tei:{local_name}", namespaces=NS):
            # Get the last text node of the element
            # For simple elements: el.text; for elements with children: last child's tail
            if len(el) > 0:
                last_text_holder = el[-1]
                text_attr = "tail"
            else:
                last_text_holder = el
                text_attr = "text"

            inner_text = getattr(last_text_holder, text_attr) or ""
            if not inner_text:
                continue

            # Check: does the element's text end with an abbreviation mark?
            if inner_text.rstrip()[-1:] not in abbrev_marks:
                continue

            # Check: does the tail start with a Hebrew letter?
            tail = el.tail or ""
            if not tail or not hebrew_re.match(tail):
                continue

            # Absorb the first Hebrew letter from the tail into the element
            setattr(last_text_holder, text_attr, inner_text + tail[0])
            el.tail = tail[1:]
            count += 1

    return count


# ── Master function ───────────────────────────────────────────────────────────

ALL_FIXES = [
    ("empty_self_closing", fix_empty_self_closing_tags),
    ("nested_same_type", fix_nested_same_type),
    ("abbreviation_boundaries", fix_abbreviation_boundaries),
    ("stray_punctuation", fix_stray_punctuation),
    ("bare_honorifics", fix_bare_honorifics),
    ("kk_placename", fix_kk_placename),
    ("nbgm_placename", fix_nbgm_placename),
    ("divine_names", fix_divine_names),
    ("lpk_placename", fix_lpk_placename),
]


def apply_all_fixes(tree):
    """
    Apply all deterministic fixes to a parsed XML tree.

    Returns:
        dict mapping fix name → count of changes.
    """
    results = {}
    for name, func in ALL_FIXES:
        count = func(tree)
        results[name] = count
    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Apply deterministic DictaBERT NER fixes to TEI XML files."
    )
    parser.add_argument(
        "input", help="XML file or directory of XMLs."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would change without modifying files."
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show per-fix counts for each file."
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    p = Path(args.input)
    if p.is_file():
        files = [p]
    elif p.is_dir():
        files = sorted(p.glob("*.xml"))
    else:
        print(f"Error: {args.input} not found.", file=sys.stderr)
        sys.exit(1)

    # Skip _corrected files (they're derived from source files)
    files = [f for f in files if "_corrected" not in f.name]

    total_fixes = {}
    files_changed = 0

    for i, xml_path in enumerate(files, 1):
        tree = etree.parse(str(xml_path))

        results = apply_all_fixes(tree)
        total_changes = sum(results.values())

        if total_changes > 0:
            files_changed += 1
            detail = ", ".join(f"{k}={v}" for k, v in results.items() if v > 0)
            print(f"[{i}/{len(files)}] {xml_path.name}: {total_changes} fixes ({detail})")

            if not args.dry_run:
                with open(xml_path, "wb") as f:
                    f.write(etree.tostring(
                        tree, pretty_print=True, encoding="utf-8",
                        xml_declaration=True
                    ))
        else:
            if args.verbose:
                print(f"[{i}/{len(files)}] {xml_path.name}: no changes")

        for k, v in results.items():
            total_fixes[k] = total_fixes.get(k, 0) + v

    print()
    print("=" * 60)
    print(f"{'DRY RUN — ' if args.dry_run else ''}Summary: {files_changed}/{len(files)} files changed")
    for k, v in total_fixes.items():
        if v > 0:
            print(f"  {k}: {v}")
    print(f"  TOTAL: {sum(total_fixes.values())}")


if __name__ == "__main__":
    main()
