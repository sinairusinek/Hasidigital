#!/usr/bin/env python3
"""
story_structure.py  —  Pipeline Step 02b: Story Structure
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Translates the RA's Transkribus story-tagging into proper TEI
<div type="story"> / <front> / <back> structure.

Two modes:

  Draft (default):
    Reads the post-step-02 XML, analyses story signals, and writes a
    TSV review file for human confirmation.

    <story>first words</story>           → story opener (RA's positive tag)
    <story rend="non story">first</story>→ non-story unit (paratext candidate)
    No <story> tags at all               → use heading-based divs from step 02

  Apply (--apply):
    Reads the confirmed TSV (with decision column filled in) and rewrites
    the XML with the correct <div type="story">, <front>, <back> structure.

Usage:
    python Authorities/scripts/story_structure.py <dijest_id>
    python Authorities/scripts/story_structure.py <dijest_id> --dry-run
    python Authorities/scripts/story_structure.py <dijest_id> --apply
"""

from __future__ import annotations

import argparse
import csv
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

DRAFT_TSV_NAME = "story-structure-draft.tsv"

DECISION_OPTIONS = ("confirm", "front", "back", "skip")


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


def iter_body_children(root) -> Iterator:
    """Yield direct children of the first <body> element."""
    body = root.find(f".//{tei('body')}")
    if body is None:
        return
    yield from list(body)


def get_facs_page(el) -> str | None:
    """Return the facs page filename from a <pb> sibling preceding el."""
    parent = el.getparent()
    if parent is None:
        return None
    idx = list(parent).index(el)
    for i in range(idx, -1, -1):
        sib = parent[i]
        if sib.tag == tei("pb"):
            facs = sib.get("facs", "")
            m = re.search(r"_(\d{4})\.jpg$", facs)
            return m.group(1) if m else facs
    return None


def inner_text(el) -> str:
    """Return concatenated text content of element (strips tags)."""
    return "".join(el.itertext()).strip()


def first_words(el, n: int = 8) -> str:
    text = inner_text(el)
    words = text.split()
    snippet = " ".join(words[:n])
    if len(words) > n:
        snippet += "…"
    return snippet


# ── Detection: story-tag mode ─────────────────────────────────────────────────

def has_story_tags(root) -> bool:
    return bool(root.findall(f".//{tei('story')}"))


def detect_units_from_story_tags(root) -> list[dict]:
    """
    Walk all <p> elements inside <body> in document order.
    Each <p> containing a <story> (with or without rend) is a unit opener.
    Paragraphs before the first <story> tag are front-matter candidates.
    Paragraphs after the last <story> tag are back-matter candidates.
    Returns a list of unit dicts.
    """
    body = root.find(f".//{tei('body')}")
    if body is None:
        return []

    # Flatten body: unpack any existing <div type="story"> from heading-based
    # step-02 processing back to flat paragraphs before we re-analyse.
    _unpack_story_divs(body)

    # Gather all <p> elements (flat, in order) from body
    paragraphs = list(body.iter(tei("p")))

    # Identify which paragraphs contain story/non-story openers
    # A paragraph "opens" a unit if it directly contains a <story> child.
    def story_child(p):
        return p.find(tei("story"))

    units: list[dict] = []
    current_unit: dict | None = None
    first_story_seen = False

    # Collect pre-story paragraphs (front-matter candidates)
    pre_story: list = []

    for p in paragraphs:
        sc = story_child(p)
        if sc is None:
            if not first_story_seen:
                pre_story.append(p)
            elif current_unit is not None:
                current_unit["paragraphs"].append(p)
            else:
                # between units — attach to previous or treat as back matter
                if units:
                    units[-1]["paragraphs"].append(p)
        else:
            first_story_seen = True
            # Close current unit
            if current_unit is not None:
                units.append(current_unit)
            rend = sc.get("rend", "")
            proposed = "non-story" if rend == "non story" else "story"
            # heading text: the <story> element's text, or the first <head> sibling
            head_el = p.find(tei("head"))
            heading_text = inner_text(head_el) if head_el is not None else ""
            current_unit = {
                "proposed_type": proposed,
                "heading_text": heading_text,
                "opener_p": p,
                "paragraphs": [p],
                "page_start": get_facs_page(p) or "",
            }

    if current_unit is not None:
        units.append(current_unit)

    # Prepend front-matter unit if any pre-story paragraphs exist
    if pre_story:
        units.insert(0, {
            "proposed_type": "front-matter",
            "heading_text": "",
            "opener_p": pre_story[0],
            "paragraphs": pre_story,
            "page_start": get_facs_page(pre_story[0]) or "",
        })

    return units


def _unpack_story_divs(body) -> None:
    """
    Move children of any <div type="story"> back to the body as flat siblings,
    then remove the now-empty div. Preserves document order.
    """
    for div in list(body.findall(tei("div"))):
        if div.get("type") != "story":
            continue
        idx = list(body).index(div)
        for i, child in enumerate(list(div)):
            div.remove(child)
            body.insert(idx + i, child)
        body.remove(div)


# ── Detection: heading mode (no story tags) ───────────────────────────────────

def detect_units_from_headings(root) -> list[dict]:
    """
    Use existing <div type="story"> elements created by structural_preprocess.py.
    Paragraphs outside any story div are paratext candidates.
    """
    body = root.find(f".//{tei('body')}")
    if body is None:
        return []

    units: list[dict] = []
    loose_pre: list = []
    story_seen = False

    for child in list(body):
        if child.tag == tei("div") and child.get("type") == "story":
            story_seen = True
            # Pre-story loose paragraphs → front matter
            if loose_pre:
                units.insert(0, {
                    "proposed_type": "front-matter",
                    "heading_text": "",
                    "opener_p": loose_pre[0],
                    "paragraphs": loose_pre,
                    "page_start": get_facs_page(loose_pre[0]) or "",
                })
                loose_pre = []

            head_el = child.find(tei("head"))
            heading_text = inner_text(head_el) if head_el is not None else ""
            paragraphs = list(child)
            page = get_facs_page(paragraphs[0]) if paragraphs else ""
            units.append({
                "proposed_type": "story",
                "heading_text": heading_text,
                "opener_p": paragraphs[0] if paragraphs else child,
                "paragraphs": paragraphs,
                "page_start": page,
            })
        elif child.tag == tei("p"):
            if not story_seen:
                loose_pre.append(child)
            else:
                # Post-story loose paragraph → back matter
                if units and units[-1]["proposed_type"] == "back-matter":
                    units[-1]["paragraphs"].append(child)
                else:
                    units.append({
                        "proposed_type": "back-matter",
                        "heading_text": "",
                        "opener_p": child,
                        "paragraphs": [child],
                        "page_start": get_facs_page(child) or "",
                    })

    return units


# ── Draft TSV ─────────────────────────────────────────────────────────────────

def units_to_tsv_rows(units: list[dict]) -> list[dict]:
    rows = []
    for i, u in enumerate(units, 1):
        opener = u["opener_p"]
        rows.append({
            "unit_num": i,
            "proposed_type": u["proposed_type"],
            "heading_text": u["heading_text"][:60],
            "first_words": first_words(opener),
            "page_start": u["page_start"],
            "decision": "",
            "notes": "",
        })
    return rows


TSV_FIELDS = ["unit_num", "proposed_type", "heading_text", "first_words",
              "page_start", "decision", "notes"]


def write_draft_tsv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TSV_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def read_draft_tsv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


# ── Report ────────────────────────────────────────────────────────────────────

def print_report(slug: str, mode: str, units: list[dict]) -> None:
    story_count = sum(1 for u in units if u["proposed_type"] == "story")
    non_story = sum(1 for u in units if u["proposed_type"] == "non-story")
    front = sum(1 for u in units if u["proposed_type"] == "front-matter")
    back = sum(1 for u in units if u["proposed_type"] == "back-matter")
    unclear = sum(1 for u in units if u["proposed_type"] == "unclear")

    print(f"\n{'='*60}")
    print(f"  Story Structure Draft  —  {slug}")
    print(f"  Signal: {mode}")
    print(f"{'='*60}")
    print(f"  Stories:       {story_count}")
    print(f"  Non-story:     {non_story}")
    print(f"  Front-matter:  {front}")
    print(f"  Back-matter:   {back}")
    print(f"  Unclear:       {unclear}")
    print(f"  Total units:   {len(units)}")
    print()
    print(f"  {'#':<4}  {'TYPE':<13}  {'PAGE':<6}  FIRST WORDS")
    print(f"  {'-'*4}  {'-'*13}  {'-'*6}  {'-'*40}")
    for i, u in enumerate(units, 1):
        fw = first_words(u["opener_p"])
        print(f"  {i:<4}  {u['proposed_type']:<13}  {u['page_start']:<6}  {fw}")
    print()


# ── Apply decisions ───────────────────────────────────────────────────────────

def apply_decisions(root, units: list[dict], rows: list[dict]) -> None:
    """
    Rewrite the body using decisions from the TSV.
    units[i] corresponds to rows[i].
    """
    body = root.find(f".//{tei('body')}")
    if body is None:
        raise ValueError("No <body> element found")

    # If story tags drove analysis, body is already flat (unpacked).
    # If heading mode, unpack the divs first so we start from a flat state.
    _unpack_story_divs(body)

    # Build a lookup: paragraph element → unit index
    p_to_unit: dict = {}
    for i, u in enumerate(units):
        for p in u["paragraphs"]:
            p_to_unit[id(p)] = i

    # Build final element groups per decision
    front_groups: list[list] = []
    body_groups: list[tuple[str, list]] = []  # (decision, paragraphs)
    back_groups: list[list] = []

    for i, (u, row) in enumerate(zip(units, rows)):
        decision = row["decision"].strip().lower() or row["proposed_type"]
        # Normalise decision
        if decision in ("confirm", "story"):
            decision = "confirm"
        elif decision in ("front", "front-matter"):
            decision = "front"
        elif decision in ("back", "back-matter"):
            decision = "back"
        elif decision in ("skip",):
            decision = "skip"
        elif decision in ("non-story", "non story"):
            decision = "skip"
        else:
            decision = "confirm"  # fallback

        paras = u["paragraphs"]

        if decision == "front":
            front_groups.append(paras)
        elif decision == "back":
            back_groups.append(paras)
        elif decision == "skip":
            pass  # drop entirely
        else:  # confirm → story
            body_groups.append((u["heading_text"], paras))

    # Clear body
    for child in list(body):
        body.remove(child)

    # Build <front> if needed
    text_el = root.find(f".//{tei('text')}")
    if text_el is None:
        raise ValueError("No <text> element found")

    if front_groups:
        front_el = etree.SubElement(text_el, tei("front"))
        text_el.remove(front_el)
        text_el.insert(list(text_el).index(body), front_el)
        for paras in front_groups:
            div = etree.SubElement(front_el, tei("div"))
            div.set("type", "front-matter")
            for p in paras:
                div.append(p)

    # Build story divs in body
    div_counter = 1
    for heading_text, paras in body_groups:
        div = etree.SubElement(body, tei("div"))
        div.set("type", "story")
        div.set(TEI_XMLID, f"Structured_{div_counter:04d}")
        div_counter += 1
        # If the first paragraph has a heading, convert it
        if paras and heading_text:
            head = etree.SubElement(div, tei("head"))
            head.set("type", "orig")
            head.text = heading_text
        for p in paras:
            div.append(p)

    # Build <back> if needed
    if back_groups:
        back_el = etree.SubElement(text_el, tei("back"))
        for paras in back_groups:
            div = etree.SubElement(back_el, tei("div"))
            div.set("type", "back-matter")
            for p in paras:
                div.append(p)

    # Strip <story> inline tags (replace each with its text content inlined)
    _strip_story_tags(root)


def _strip_story_tags(root) -> None:
    """Remove all <story> elements, promoting their text content in-place."""
    for story_el in list(root.iter(tei("story"))):
        parent = story_el.getparent()
        if parent is None:
            continue
        idx = list(parent).index(story_el)
        # Prepend story text to parent or preceding sibling tail
        story_text = (story_el.text or "") + (story_el.tail or "")
        if idx == 0:
            parent.text = (parent.text or "") + story_text
        else:
            prev = parent[idx - 1]
            prev.tail = (prev.tail or "") + story_text
        parent.remove(story_el)


# ── Main ──────────────────────────────────────────────────────────────────────

def run(dijest_id: str, dry_run: bool, apply: bool) -> None:
    # ── Load metadata ──────────────────────────────────────────────────────
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

    draft_tsv_path = edition_folder / DRAFT_TSV_NAME

    print(f"\nStory Structure  —  {slug}  (DiJeSt: {dijest_id})")
    print(f"XML: {xml_path.relative_to(REPO_ROOT)}")

    # ── APPLY mode ─────────────────────────────────────────────────────────
    if apply:
        if not draft_tsv_path.exists():
            print(f"\n✗  Draft TSV not found: {draft_tsv_path.relative_to(REPO_ROOT)}")
            print(f"   Run without --apply first to generate the draft.")
            sys.exit(1)

        rows = read_draft_tsv(draft_tsv_path)
        unfilled = [r for r in rows if not r["decision"].strip()]
        if unfilled:
            print(f"\n⚠  {len(unfilled)} row(s) have no decision filled in.")
            print("   Fill in the 'decision' column before applying.")
            print("   Options: confirm, front, back, skip")
            sys.exit(1)

        parser = etree.XMLParser(remove_blank_text=False, recover=True)
        tree = etree.parse(str(xml_path), parser)
        root = tree.getroot()

        # Re-detect units to get paragraph references (must match TSV order)
        if has_story_tags(root):
            units = detect_units_from_story_tags(root)
            mode = "story tags"
        else:
            units = detect_units_from_headings(root)
            mode = "heading zones"

        if len(units) != len(rows):
            print(f"\n✗  TSV has {len(rows)} rows but detected {len(units)} units.")
            print("   The XML or TSV may have changed since the draft was generated.")
            print("   Re-run without --apply to regenerate.")
            sys.exit(1)

        apply_decisions(root, units, rows)

        if not dry_run:
            tree.write(str(xml_path), encoding="UTF-8",
                       xml_declaration=True, pretty_print=False)
            print(f"\n✓  XML updated: {xml_path.relative_to(REPO_ROOT)}")
            # Count results
            new_stories = root.findall(f".//{tei('div')}[@type='story']")
            front_divs = root.findall(f".//{tei('front')}")
            back_divs = root.findall(f".//{tei('back')}")
            print(f"  Story divs:    {len(new_stories)}")
            print(f"  Front element: {'yes' if front_divs else 'no'}")
            print(f"  Back element:  {'yes' if back_divs else 'no'}")
            remaining_story_tags = root.findall(f".//{tei('story')}")
            print(f"  Remaining <story> tags: {len(remaining_story_tags)}  (should be 0)")
        else:
            print(f"\n[DRY RUN] Would rewrite {xml_path.name} with decisions applied.")
        return

    # ── DRAFT mode ─────────────────────────────────────────────────────────
    parser = etree.XMLParser(remove_blank_text=False, recover=True)
    tree = etree.parse(str(xml_path), parser)
    root = tree.getroot()

    if has_story_tags(root):
        units = detect_units_from_story_tags(root)
        mode = "story tags (RA tagging)"
    else:
        # Check step 02 has run (zones stripped, story divs present)
        zones_remaining = root.findall(f".//{tei('zone')}")
        story_divs = root.findall(f".//{tei('div')}[@type='story']")
        if zones_remaining and not story_divs:
            print(f"\n✗  This edition has no <story> tags and facsimile zones are still present.")
            print(f"   Step 02 (TEI conversion) must run before Step 02b.")
            print(f"   Run the NER pipeline first: python ner_pipeline/pipeline.py {dijest_id}")
            sys.exit(1)
        units = detect_units_from_headings(root)
        mode = "heading zones (structural_preprocess)"

    print_report(slug, mode, units)

    rows = units_to_tsv_rows(units)

    # Pre-fill decisions for unambiguous cases
    for row in rows:
        if row["proposed_type"] in ("front-matter", "back-matter"):
            row["decision"] = row["proposed_type"].replace("-", "")[:5]  # "front" / "back"
        elif row["proposed_type"] == "story":
            row["decision"] = "confirm"
        elif row["proposed_type"] == "non-story":
            row["decision"] = "skip"
        # "unclear" left blank for user

    unclear_count = sum(1 for r in rows if not r["decision"].strip())

    if not dry_run:
        write_draft_tsv(draft_tsv_path, rows)
        print(f"✓  Draft TSV written: {draft_tsv_path.relative_to(REPO_ROOT)}")
        if unclear_count:
            print(f"⚠  {unclear_count} unit(s) need a decision — fill in the TSV before running --apply.")
        else:
            print(f"   All decisions pre-filled. Review the TSV, then run --apply.")
    else:
        print("[DRY RUN] Draft TSV not written.")


def main():
    parser = argparse.ArgumentParser(
        description="Step 02b: Story structure detection and application."
    )
    parser.add_argument("dijest_id", help="DiJeSt/Transkribus folder ID")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print report without writing any files.")
    parser.add_argument("--apply", action="store_true",
                        help="Apply decisions from the draft TSV to the XML.")
    args = parser.parse_args()

    if args.dry_run and args.apply:
        print("✗  --dry-run and --apply are mutually exclusive.")
        sys.exit(1)

    run(args.dijest_id, dry_run=args.dry_run, apply=args.apply)


if __name__ == "__main__":
    main()
