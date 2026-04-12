#!/usr/bin/env python3
"""
story_structure.py  —  Pipeline Step 02b: Story Structure
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Translates the RA's Transkribus story-tagging into a TEI XML draft with
proper <div type="story"> / <front> / <back> structure, ready for human
review and editing.

RA tagging conventions:
  <story n="N">first words</story>            story opener, numbered
  <story>first words</story>                  story opener, unnumbered
  <story rend="non story">first</story>       non-story unit (paratext candidate)
  <story n="non story">first</story>          typo: n= instead of rend=
  <story rend="story continued" n="N">        continuation of previous story
  <story rend="students">…</story>            students list → non-story, ana="students-list"
  <story rend="letter">…</story>              letter → non-story, ana="letter"
  <story rend="dvar torah">…</story>          dvar-torah → non-story, ana="dvar-torah"
  <story rend="marginal" n="N">…</story>      marginal note (flagged for review)
  No <story> tags at all                      use heading-based divs from step 02

The script writes the proposed structure directly to the XML. You then
open the file in your editor, review, and adjust as needed.

Output attributes on produced divs:
  <div type="story" xml:id="Structured_NNNN" n="M">   M = RA's story number
  <div type="non-story" ana="letter">                  known subtype
  <div type="story" ana="FLAGGED: reason">             needs review
  Numbering flags added to ana when sequence has gaps or restarts.

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

# Known rend values that mark non-story units with specific content types.
# Maps rend value → ana subtype label to put on the resulting <div>.
KNOWN_NON_STORY_SUBTYPES: dict[str, str] = {
    "students":  "students-list",
    "letter":    "letter",
    "dvar torah": "dvar-torah",
}


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


def _unwrap_body_container(body) -> None:
    """
    Transkribus TEI exports often place all body content inside a single
    unnamed <div> child of <body>.  Hoist that wrapper's children directly
    into <body> so the rest of the script can treat <body> as the flat
    container.
    """
    children = list(body)
    if len(children) == 1 and children[0].tag == tei("div") and not children[0].get("type"):
        wrapper = children[0]
        idx = 0
        for child in list(wrapper):
            wrapper.remove(child)
            body.insert(idx, child)
            idx += 1
        body.remove(wrapper)


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


def classify_story_tag(el) -> tuple[str, str | None, str | None]:
    """
    Classify a <story> element.
    Returns (type, flag_reason, subtype) where:
      type        one of: 'story', 'non-story', 'continuation', 'unclear'
      flag_reason None for clean cases; a string to add to the XML ana attribute
      subtype     None for plain story/non-story; a label for known content types
                  (e.g. 'letter', 'dvar-torah', 'students-list')
    """
    n_val    = el.get("n",    "").strip()
    rend_val = el.get("rend", "").strip()

    # Standard non-story
    if rend_val == "non story":
        return "non-story", None, None

    # Known typo: n="non story" instead of rend="non story"
    if n_val == "non story":
        return "non-story", 'n="non story" — typo for rend="non story"', None

    # Known non-story subtypes (students, letter, dvar torah, …)
    if rend_val in KNOWN_NON_STORY_SUBTYPES:
        return "non-story", None, KNOWN_NON_STORY_SUBTYPES[rend_val]

    # Story continuation — merge into previous unit
    if "story continued" in rend_val.lower():
        return "continuation", None, None

    # Marginal note — ambiguous when combined with a numeric n
    if rend_val == "marginal":
        flag = (
            f'rend="marginal" with n="{n_val}" — marginal note has story number; '
            f"classify manually as story or non-story"
            if n_val.isdigit()
            else f'rend="marginal" — marginal note; classify manually'
        )
        return "unclear", flag, None

    # Standard story: numeric n, no rend
    if n_val.isdigit() and not rend_val:
        return "story", None, None

    # Numeric n with an unexpected rend — treat as story but flag
    if n_val.isdigit() and rend_val:
        return "story", f'n="{n_val}" with rend="{rend_val}" — review annotation', None

    # Unknown non-empty rend value
    if rend_val:
        return "unclear", f'rend="{rend_val}" — unknown value; classify as story or non-story', None

    # No meaningful attributes at all — still treat as story opener
    if not n_val and not rend_val:
        return "story", None, None

    return "unclear", f"unrecognized attributes: {dict(el.attrib)}", None


def _check_story_numbering(units: list[dict]) -> None:
    """
    Walk story units in order and flag numbering anomalies.
    Adds / appends to unit['flag'] for:
      - gap:     expected N but got M > N
      - restart: n reset to a lower value (likely a new chapter, but flag anyway)
    Modifies units in-place.
    """
    last_n: int | None = None
    for u in units:
        if u["type"] != "story":
            continue
        n = u.get("story_n")
        if n is None:
            last_n = None   # unnumbered story resets sequence tracking
            continue

        if last_n is None:
            # First numbered story — nothing to compare yet
            last_n = n
            continue

        expected = last_n + 1
        if n == expected:
            last_n = n
        elif n < last_n:
            # Numbering went backwards — likely a new chapter
            note = f"numbering restarts at n={n} (was {last_n}) — new chapter?"
            u["flag"] = f"{u['flag']}; {note}" if u.get("flag") else note
            last_n = n
        else:
            # Gap in numbering
            note = f"numbering gap: expected n={expected}, got n={n}"
            u["flag"] = f"{u['flag']}; {note}" if u.get("flag") else note
            last_n = n


def detect_units_from_story_tags(root) -> list[dict]:
    """
    Build story units from <story> inline tags.
    Returns list of dicts:
      {type, paragraphs, heading_text, flag, subtype, story_n}
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
            unit_type, flag, subtype = classify_story_tag(sc)
            head_el = p.find(tei("head"))
            heading_text = inner_text(head_el) if head_el is not None else ""

            # Extract RA story number (numeric n attribute)
            raw_n = sc.get("n", "").strip()
            story_n = int(raw_n) if raw_n.isdigit() else None

            if unit_type == "continuation" and (current is not None or units):
                # Merge into the currently-open unit if one exists, otherwise the
                # last completed unit.  Using current is critical: when a story
                # opener and its continuation are in adjacent paragraphs, current
                # holds the opener's unit but it has not yet been appended to units.
                target = current if current is not None else units[-1]
                target["paragraphs"].append(p)
                # Flag n-value mismatches between continuation and parent unit
                if story_n is not None and target.get("story_n") != story_n:
                    cont_note = (
                        f'continuation tag has n="{story_n}" but parent unit has '
                        f'n="{target.get("story_n")}" — verify'
                    )
                    target["flag"] = (
                        f"{target['flag']}; {cont_note}"
                        if target.get("flag") else cont_note
                    )
            else:
                if current is not None:
                    units.append(current)
                current = {
                    "type":         unit_type,
                    "heading_text": heading_text,
                    "paragraphs":   [p],
                    "flag":         flag,
                    "subtype":      subtype,
                    "story_n":      story_n,
                }

    if current is not None:
        units.append(current)

    if pre_story:
        units.insert(0, {
            "type":         "front-matter",
            "heading_text": "",
            "paragraphs":   pre_story,
            "flag":         None,
            "subtype":      None,
            "story_n":      None,
        })

    _check_story_numbering(units)

    return units


# Heading text patterns that signal end-of-book colophon → back-matter
_COLOPHON_PATTERNS = re.compile(
    r"^(תם|תם ונשלם|סוף|נשלם|סוף הספר|תם הספר|ברוך שגמרנו|חזק)",
    re.UNICODE,
)


def _is_colophon_heading(heading_text: str) -> bool:
    return bool(_COLOPHON_PATTERNS.match(heading_text.strip()))


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
                    "flag": None,
                    "subtype": None,
                    "story_n": None,
                })
                loose_pre = []
            head_el = child.find(tei("head"))
            heading_text = inner_text(head_el) if head_el is not None else ""
            # Colophon headings → back-matter instead of story
            if _is_colophon_heading(heading_text):
                units.append({
                    "type":         "back-matter",
                    "heading_text": heading_text,
                    "paragraphs":   list(child),
                    "flag":         None,
                    "subtype":      None,
                    "story_n":      None,
                })
            else:
                units.append({
                    "type":         "story",
                    "heading_text": heading_text,
                    "paragraphs":   list(child),
                    "flag":         None,
                    "subtype":      None,
                    "story_n":      None,
                })
        elif child.tag == tei("p"):
            if not story_seen:
                loose_pre.append(child)
            else:
                if units and units[-1]["type"] == "back-matter":
                    units[-1]["paragraphs"].append(child)
                else:
                    units.append({
                        "type":         "back-matter",
                        "heading_text": "",
                        "paragraphs":   [child],
                        "flag":         None,
                        "subtype":      None,
                        "story_n":      None,
                    })

    # Warn if very few story divs were produced — likely sparse heading tagging
    story_count = sum(1 for u in units if u["type"] == "story")
    if story_count <= 2 and units:
        for u in units:
            if u["type"] == "story" and not u.get("flag"):
                u["flag"] = (
                    f"only {story_count} story div(s) detected — heading zones may be "
                    "sparsely tagged; consider manual story boundary annotation"
                )

    return units


# ── Build XML structure ───────────────────────────────────────────────────────

def _build_ana(subtype: str | None, flag: str | None) -> str | None:
    """Compose the ana attribute value from subtype and/or flag."""
    parts = []
    if subtype:
        parts.append(subtype)
    if flag:
        parts.append(f"FLAGGED: {flag}")
    return " ".join(parts) if parts else None


def build_structure(root, units: list[dict]) -> None:
    """
    Rewrite <body> (and optionally add <front>/<back>) using detected units.
    Strips <story> inline tags after restructuring.

    Div attributes produced:
      type="story"      xml:id="Structured_NNNN"  [n="M" if RA numbered it]
                        [ana="FLAGGED: …" if flagged]
      type="non-story"  [ana="subtype"]  [ana="subtype FLAGGED: …"]
      type="unclear"    ana="FLAGGED: …"
      type="front-matter" / type="back-matter"
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

    # ── <front> ───────────────────────────────────────────────────────────────
    if front_units:
        front_el = etree.Element(tei("front"))
        text_el.insert(list(text_el).index(body), front_el)
        for u in front_units:
            div = etree.SubElement(front_el, tei("div"))
            div.set("type", "front-matter")
            for p in u["paragraphs"]:
                div.append(p)

    # ── <body>: story + non-story + unclear divs in document order ────────────
    body_unit_types = ("story", "non-story", "unclear")
    all_body_units = [u for u in units if u["type"] in body_unit_types]
    div_counter = 1
    for u in all_body_units:
        div = etree.SubElement(body, tei("div"))
        div.set("type", u["type"])

        if u["type"] == "story":
            div.set(TEI_XMLID, f"Structured_{div_counter:04d}")
            div_counter += 1
            # Preserve RA's story number if available
            if u.get("story_n") is not None:
                div.set("n", str(u["story_n"]))

        ana = _build_ana(u.get("subtype"), u.get("flag"))
        if ana:
            div.set("ana", ana)

        if u["heading_text"]:
            head = etree.SubElement(div, tei("head"))
            head.set("type", "orig")
            head.text = u["heading_text"]

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
    counts: dict[str, int] = {}
    for u in units:
        counts[u["type"]] = counts.get(u["type"], 0) + 1
    flagged = [u for u in units if u.get("flag")]

    print(f"\n{'='*60}")
    print(f"  Story Structure  —  {slug}")
    print(f"  Signal: {mode}")
    print(f"{'='*60}")
    for k, v in sorted(counts.items()):
        print(f"  {k+':':<16} {v}")
    print(f"  {'total:':<16} {len(units)}")
    if flagged:
        print(f"  {'⚠ flagged:':<16} {len(flagged)}")
    print()
    print(f"  {'#':<4}  {'TYPE':<13}  {'N':<4}  FIRST WORDS")
    print(f"  {'-'*4}  {'-'*13}  {'-'*4}  {'-'*45}")
    for i, u in enumerate(units, 1):
        fw = first_words(u["paragraphs"][0]) if u["paragraphs"] else "(empty)"
        n_label = str(u.get("story_n")) if u.get("story_n") is not None else ""
        flag_marker = "  ⚠" if u.get("flag") else ""
        sub_marker = f"  [{u['subtype']}]" if u.get("subtype") else ""
        print(f"  {i:<4}  {u['type']:<13}  {n_label:<4}  {fw}{sub_marker}{flag_marker}")
    if flagged:
        print()
        print("  ⚠  Flagged units — review the ana=\"FLAGGED:...\" attribute in the XML:")
        for i, u in enumerate(units, 1):
            if u.get("flag"):
                fw = first_words(u["paragraphs"][0]) if u["paragraphs"] else "(empty)"
                n_label = f" n={u['story_n']}" if u.get("story_n") is not None else ""
                print(f"     #{i}{n_label}  [{u['type']}]  {fw}")
                print(f"          {u['flag']}")
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
            # No RA story tags and step 02 hasn't run yet.
            # Auto-apply structural preprocessing: heading zones → <div type="story">
            print("  No <story> tags found; applying structural preprocessing (step 02)…")
            sys.path.insert(0, str(REPO_ROOT))
            from ner_pipeline.structural_preprocess import (
                restructure_facsimile_zones,
                remove_facsimile_and_attrs,
            )
            restructure_facsimile_zones(tree)
            remove_facsimile_and_attrs(tree)
            # Hoist wrapper <div> children directly into <body> if present
            _body = root.find(f".//{tei('body')}")
            if _body is not None:
                _unwrap_body_container(_body)
            mode = "heading zones (step 02 preprocessing applied inline)"
        else:
            mode = "heading zones (step 02 already applied)"
        units = detect_units_from_headings(root)

    print_report(slug, mode, units)

    if dry_run:
        print("[DRY RUN] XML not modified.")
        return

    build_structure(root, units)

    tree.write(str(xml_path), encoding="UTF-8",
               xml_declaration=True, pretty_print=True)

    story_count     = len(root.findall(f".//{tei('div')}[@type='story']"))
    non_story_count = len(root.findall(f".//{tei('div')}[@type='non-story']"))
    unclear_count   = len(root.findall(f".//{tei('div')}[@type='unclear']"))
    flagged_divs    = [
        el for el in root.iter()
        if (el.get("ana") or "").startswith("FLAGGED") or "FLAGGED:" in (el.get("ana") or "")
    ]
    has_front = root.find(f".//{tei('front')}") is not None
    has_back  = root.find(f".//{tei('back')}")  is not None
    remaining = root.findall(f".//{tei('story')}")

    print(f"✓  XML written: {xml_path.name}")
    print(f"   Story divs:       {story_count}")
    print(f"   Non-story divs:   {non_story_count}")
    if unclear_count:
        print(f"   Unclear divs:     {unclear_count}  ⚠ needs classification")
    if flagged_divs:
        print(f"   Flagged divs:     {len(flagged_divs)}  ⚠ search ana=\"FLAGGED\" in the XML")
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
