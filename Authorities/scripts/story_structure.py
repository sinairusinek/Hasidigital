#!/usr/bin/env python3
"""
story_structure.py  —  Pipeline Step 02b: Story Structure
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Translates the RA's Transkribus story-tagging into a TEI XML draft with
proper <div type="story"> / <front> / <back> structure, ready for human
review and editing.

RA tagging conventions:
  <story>first words</story>             story opener  (positive)
  <story rend="non story">first</story>  non-story unit (paratext candidate)
  No <story> tags at all                 use heading-based divs from step 02

The script writes the proposed structure directly to the XML. You then
open the file in your editor, review, and adjust as needed.

Usage:
    python Authorities/scripts/story_structure.py <dijest_id>
    python Authorities/scripts/story_structure.py <dijest_id> --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterator

from lxml import etree

# ── Repo paths ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
INCOMING_DIR = REPO_ROOT / "editions" / "incoming"
METADATA_FILE = REPO_ROOT / "editions" / "edition-metadata.json"

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
TEI_XMLID = f"{{{XML_NS}}}id"


# ── Metadata helpers ──────────────────────────────────────────────────────────

def load_metadata() -> list[dict]:
    with open(METADATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("editions", [])


def find_entry(metadata: list[dict], dijest_id: str) -> dict | None:
    for entry in metadata:
        if str(entry.get("identifiers", {}).get("Transkribus", "")) == str(dijest_id):
            return entry
    return None


def find_main_xml(edition_folder: Path) -> Path | None:
    for p in edition_folder.glob("*.xml"):
        if p.name not in ("mets.xml", "metadata.xml"):
            return p
    return None


# ── XML helpers ───────────────────────────────────────────────────────────────

def tei(tag: str) -> str:
    return f"{{{TEI_NS}}}{tag}"


def inner_text(el) -> str:
    return "".join(el.itertext()).strip()


def first_words(el, n: int = 8) -> str:
    text = inner_text(el)
    words = text.split()
    snippet = " ".join(words[:n])
    if len(words) > n:
        snippet += "…"
    return snippet


def get_pb_facs(el) -> str | None:
    """Return the facs attribute of the nearest preceding <pb> sibling."""
    parent = el.getparent()
    if parent is None:
        return None
    siblings = list(parent)
    idx = siblings.index(el)
    for i in range(idx, -1, -1):
        if siblings[i].tag == tei("pb"):
            return siblings[i].get("facs", "")
    return None


# ── Detection ─────────────────────────────────────────────────────────────────

def has_story_tags(root) -> bool:
    return bool(root.findall(f".//{tei('story')}"))


def _unpack_story_divs(body) -> None:
    """Move children of <div type="story"> back to body as flat siblings."""
    for div in list(body.findall(tei("div"))):
        if div.get("type") != "story":
            continue
        idx = list(body).index(div)
        for i, child in enumerate(list(div)):
            div.remove(child)
            body.insert(idx + i, child)
        body.remove(div)


def detect_units_from_story_tags(root) -> list[dict]:
    """
    Build story units from <story> inline tags.
    Returns list of dicts: {type, paragraphs, heading_text}
    """
    body = root.find(f".//{tei('body')}")
    if body is None:
        return []

    # Unpack any heading-based divs so we work on a flat paragraph list
    _unpack_story_divs(body)

    paragraphs = list(body.iter(tei("p")))

    units: list[dict] = []
    current: dict | None = None
    pre_story: list = []
    first_story_seen = False

    for p in paragraphs:
        sc = p.find(tei("story"))
        if sc is None:
            if not first_story_seen:
                pre_story.append(p)
            elif current is not None:
                current["paragraphs"].append(p)
            elif units:
                units[-1]["paragraphs"].append(p)
        else:
            first_story_seen = True
            if current is not None:
                units.append(current)
            rend = sc.get("rend", "")
            is_non_story = rend == "non story"
            head_el = p.find(tei("head"))
            current = {
                "type": "non-story" if is_non_story else "story",
                "heading_text": inner_text(head_el) if head_el is not None else "",
                "paragraphs": [p],
            }

    if current is not None:
        units.append(current)

    if pre_story:
        units.insert(0, {
            "type": "front-matter",
            "heading_text": "",
            "paragraphs": pre_story,
        })

    return units


def detect_units_from_headings(root) -> list[dict]:
    """Use existing <div type="story"> elements from step-02 heading processing."""
    body = root.find(f".//{tei('body')}")
    if body is None:
        return []

    units: list[dict] = []
    loose_pre: list = []
    story_seen = False

    for child in list(body):
        if child.tag == tei("div") and child.get("type") == "story":
            story_seen = True
            if loose_pre:
                units.insert(0, {
                    "type": "front-matter",
                    "heading_text": "",
                    "paragraphs": loose_pre,
                })
                loose_pre = []
            head_el = child.find(tei("head"))
            units.append({
                "type": "story",
                "heading_text": inner_text(head_el) if head_el is not None else "",
                "paragraphs": list(child),
            })
        elif child.tag == tei("p"):
            if not story_seen:
                loose_pre.append(child)
            else:
                if units and units[-1]["type"] == "back-matter":
                    units[-1]["paragraphs"].append(child)
                else:
                    units.append({
                        "type": "back-matter",
                        "heading_text": "",
                        "paragraphs": [child],
                    })

    return units


# ── Build XML structure ───────────────────────────────────────────────────────

def build_structure(root, units: list[dict]) -> None:
    """
    Rewrite <body> (and optionally add <front>/<back>) using detected units.
    Non-story units are placed in <!-- non-story --> commented divs so they
    are visible for review but excluded from story counting.
    Strips <story> inline tags after restructuring.
    """
    body = root.find(f".//{tei('body')}")
    text_el = root.find(f".//{tei('text')}")
    if body is None or text_el is None:
        raise ValueError("No <body> or <text> element found")

    # Ensure body is flat before rebuilding
    _unpack_story_divs(body)
    for child in list(body):
        body.remove(child)

    front_units = [u for u in units if u["type"] == "front-matter"]
    back_units  = [u for u in units if u["type"] == "back-matter"]
    story_units = [u for u in units if u["type"] == "story"]
    non_story   = [u for u in units if u["type"] == "non-story"]

    # ── <front> ───────────────────────────────────────────────────────────────
    if front_units:
        front_el = etree.Element(tei("front"))
        text_el.insert(list(text_el).index(body), front_el)
        for u in front_units:
            div = etree.SubElement(front_el, tei("div"))
            div.set("type", "front-matter")
            for p in u["paragraphs"]:
                div.append(p)

    # ── <body>: story divs + non-story marked divs ────────────────────────────
    # Interleave stories and non-story units in document order
    # (preserve original paragraph order across all units)
    all_body_units = [u for u in units if u["type"] in ("story", "non-story")]
    div_counter = 1
    for u in all_body_units:
        if u["type"] == "story":
            div = etree.SubElement(body, tei("div"))
            div.set("type", "story")
            div.set(TEI_XMLID, f"Structured_{div_counter:04d}")
            div_counter += 1
            if u["heading_text"]:
                head = etree.SubElement(div, tei("head"))
                head.set("type", "orig")
                head.text = u["heading_text"]
            for p in u["paragraphs"]:
                div.append(p)
        else:
            # Non-story: wrap in a div with type="non-story" for easy review
            div = etree.SubElement(body, tei("div"))
            div.set("type", "non-story")
            for p in u["paragraphs"]:
                div.append(p)

    # ── <back> ────────────────────────────────────────────────────────────────
    if back_units:
        back_el = etree.SubElement(text_el, tei("back"))
        for u in back_units:
            div = etree.SubElement(back_el, tei("div"))
            div.set("type", "back-matter")
            for p in u["paragraphs"]:
                div.append(p)

    # ── Strip <story> inline tags ─────────────────────────────────────────────
    _strip_story_tags(root)


def _strip_story_tags(root) -> None:
    """Remove all <story> elements, inlining their text content."""
    for story_el in list(root.iter(tei("story"))):
        parent = story_el.getparent()
        if parent is None:
            continue
        idx = list(parent).index(story_el)
        text = (story_el.text or "") + (story_el.tail or "")
        if idx == 0:
            parent.text = (parent.text or "") + text
        else:
            prev = parent[idx - 1]
            prev.tail = (prev.tail or "") + text
        parent.remove(story_el)


# ── Report ────────────────────────────────────────────────────────────────────

def print_report(slug: str, mode: str, units: list[dict]) -> None:
    counts = {}
    for u in units:
        counts[u["type"]] = counts.get(u["type"], 0) + 1

    print(f"\n{'='*60}")
    print(f"  Story Structure  —  {slug}")
    print(f"  Signal: {mode}")
    print(f"{'='*60}")
    for k, v in sorted(counts.items()):
        print(f"  {k+':':<16} {v}")
    print(f"  {'total:':<16} {len(units)}")
    print()
    print(f"  {'#':<4}  {'TYPE':<13}  FIRST WORDS")
    print(f"  {'-'*4}  {'-'*13}  {'-'*45}")
    for i, u in enumerate(units, 1):
        fw = first_words(u["paragraphs"][0]) if u["paragraphs"] else "(empty)"
        print(f"  {i:<4}  {u['type']:<13}  {fw}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def run(dijest_id: str, dry_run: bool) -> None:
    metadata = load_metadata()
    entry = find_entry(metadata, dijest_id)
    if entry is None:
        print(f"\n✗  No metadata entry found for Transkribus ID {dijest_id!r}")
        sys.exit(1)

    slug = Path(entry["xml_filename"]).stem
    edition_folder = INCOMING_DIR / dijest_id
    xml_path = find_main_xml(edition_folder)
    if xml_path is None:
        print(f"\n✗  No main XML found in {edition_folder}")
        sys.exit(1)

    print(f"\nStep 02b — Story Structure  [{slug}  /  DiJeSt: {dijest_id}]")
    print(f"XML: {xml_path.relative_to(REPO_ROOT)}")

    parser = etree.XMLParser(remove_blank_text=False, recover=True)
    tree = etree.parse(str(xml_path), parser)
    root = tree.getroot()

    if has_story_tags(root):
        units = detect_units_from_story_tags(root)
        mode = "story tags (RA tagging)"
    else:
        zones_remaining = root.findall(f".//{tei('zone')}")
        story_divs = root.findall(f".//{tei('div')}[@type='story']")
        if zones_remaining and not story_divs:
            print(f"\n✗  No <story> tags found and facsimile zones are still present.")
            print(f"   Step 02 (TEI conversion) must run before Step 02b.")
            sys.exit(1)
        units = detect_units_from_headings(root)
        mode = "heading zones (from step 02)"

    print_report(slug, mode, units)

    if dry_run:
        print("[DRY RUN] XML not modified.")
        return

    build_structure(root, units)

    tree.write(str(xml_path), encoding="UTF-8",
               xml_declaration=True, pretty_print=True)

    story_count = len(root.findall(f".//{tei('div')}[@type='story']"))
    non_story_count = len(root.findall(f".//{tei('div')}[@type='non-story']"))
    has_front = root.find(f".//{tei('front')}") is not None
    has_back = root.find(f".//{tei('back')}") is not None
    remaining = root.findall(f".//{tei('story')}")

    print(f"✓  XML written: {xml_path.name}")
    print(f"   Story divs:       {story_count}")
    print(f"   Non-story divs:   {non_story_count}  (type=\"non-story\", review and remove or reclassify)")
    print(f"   <front> element:  {'yes' if has_front else 'no'}")
    print(f"   <back> element:   {'yes' if has_back else 'no'}")
    if remaining:
        print(f"   ⚠  {len(remaining)} <story> tag(s) still in XML — check for parse errors")
    print(f"\nOpen {xml_path.name} in your editor to review and adjust the structure.")


def main():
    parser = argparse.ArgumentParser(
        description="Step 02b: Build story structure draft in TEI XML for review."
    )
    parser.add_argument("dijest_id", help="DiJeSt/Transkribus folder ID")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print report only, do not modify XML.")
    args = parser.parse_args()
    run(args.dijest_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
