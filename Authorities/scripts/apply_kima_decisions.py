#!/usr/bin/env python3
"""
Apply decisions from the Kima Review TSV to authority XML and edition files.

Reads ``editions/unmatched-places-report.tsv`` and processes three action types:

* **map_to:H-LOC_xxx** – add the Hebrew name as a ``<placeName>`` variant on
  the existing ``<place>`` element in the authority XML.
* **new** – create a brand-new ``<place>`` element with the next available
  ``H-LOC_`` id, seeded with the Kima identifier from ``suggested_id``.
* **skip** – unwrap every ``<placeName>`` tag whose *text* matches the
  decision name (preserving the text), and log the name to
  ``Authorities/skipped_places.json``.

After mutating the authority XML the script:

1. Writes the updated XML back to disk.
2. Regenerates the matching DB by calling ``generate_matching_db.py``.
3. Batch-links unlinked ``<placeName>`` elements in all ``_corrected.xml``
   edition files against the freshly-rebuilt matching DB.
4. Prints a summary and optionally creates a git commit.

Usage::

    python3 Authorities/scripts/apply_kima_decisions.py [--dry-run] [--skip-commit]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# ── Paths (import from config.py) ────────────────────────────────────────────

# Allow imports from the integration_tool directory
_SCRIPT_DIR = Path(__file__).resolve().parent
_AUTH_DIR = _SCRIPT_DIR.parent
_TOOL_DIR = _AUTH_DIR / "integration_tool"
sys.path.insert(0, str(_TOOL_DIR))

from config import (  # noqa: E402
    AUTHORITY_XML_PATH,
    MATCHING_DB_PATH,
    SKIPPED_JSON_PATH,
    GEN_SCRIPT,
    EDITIONS_INCOMING,
    UNMATCHED_TSV,
    TEI_NS,
    XML_NS,
)

T = f"{{{TEI_NS}}}"
X = f"{{{XML_NS}}}"

# Hebrew prefix letters that can be glued to a place name (מ/ב/ל/ו/ה/כ/ש)
_HE_PREFIXES = set("במולהוכש")


# ═════════════════════════════════════════════════════════════════════════════
# Step 1 – Load inputs
# ═════════════════════════════════════════════════════════════════════════════

def load_tsv_decisions(tsv_path: str) -> dict[str, list[dict]]:
    """
    Parse the TSV and return decisions grouped by action type.

    Returns ``{"map_to": [...], "new": [...], "skip": [...]}``.
    Each item carries the original row fields: name, occurrences, editions,
    contexts, suggested_id, action.
    """
    decisions: dict[str, list[dict]] = {"map_to": [], "new": [], "skip": []}
    with open(tsv_path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t", quotechar='"')
        for row in reader:
            action_raw = (row.get("action") or "").strip()
            if not action_raw:
                continue

            name = (row.get("name") or "").strip()
            if not name:
                continue

            rec = {
                "name": name,
                "occurrences": int(row.get("occurrences") or 0),
                "editions": (row.get("editions") or "").strip(),
                "contexts": (row.get("contexts") or "").strip(),
                "suggested_id": (row.get("suggested_id") or "").strip(),
                "action_raw": action_raw,
            }

            if action_raw.startswith("map_to:"):
                rec["target_id"] = action_raw.split(":", 1)[1].strip()
                decisions["map_to"].append(rec)
            elif action_raw == "map_to":
                # map_to without H-LOC target — try to resolve via Kima ID
                rec["target_id"] = None  # will be resolved later
                decisions["map_to"].append(rec)
            elif action_raw == "new":
                decisions["new"].append(rec)
            elif action_raw == "skip":
                decisions["skip"].append(rec)
    return decisions


def _strip_hebrew_prefix(name: str) -> tuple[str, str]:
    """
    If *name* starts with a single Hebrew prefix letter (במולהוכש)
    followed by more Hebrew text, return ``(prefix, bare_name)``.
    Otherwise return ``("", name)``.
    """
    if len(name) >= 2 and name[0] in _HE_PREFIXES:
        # Make sure the rest is Hebrew-ish (first char after prefix)
        if "\u0590" <= name[1] <= "\u05FF":
            return name[0], name[1:]
    return "", name


# ═════════════════════════════════════════════════════════════════════════════
# Step 2 – Process map_to decisions
# ═════════════════════════════════════════════════════════════════════════════

def _find_place_by_id(root: ET.Element, hloc_id: str) -> ET.Element | None:
    """Find a ``<place xml:id="…">`` element by its H-LOC id."""
    for place in root.iter(f"{T}place"):
        if place.get(f"{X}id") == hloc_id:
            return place
    return None


def _existing_place_names(place_elem: ET.Element) -> set[str]:
    """Collect all ``<placeName>`` text values already on *place_elem*."""
    names: set[str] = set()
    for pn in place_elem.findall(f"{T}placeName"):
        t = (pn.text or "").strip()
        if t:
            names.add(t)
    return names


def _add_name_variant(place_elem: ET.Element, name_he: str) -> bool:
    """
    Append ``<placeName>name_he</placeName>`` to *place_elem* if not
    already present.  Returns True if a variant was actually added.
    """
    existing = _existing_place_names(place_elem)
    if name_he in existing:
        return False
    new_pn = ET.SubElement(place_elem, f"{T}placeName")
    new_pn.text = name_he
    return True


def _resolve_map_to_target(root: ET.Element, rec: dict) -> str | None:
    """
    Resolve the target H-LOC id for a map_to decision.

    If ``rec["target_id"]`` is already set (from ``map_to:H-LOC_xxx``),
    return it.  Otherwise look up the Kima id from ``suggested_id`` and
    find the matching ``<place>`` in the authority XML.
    """
    target = rec.get("target_id")
    if target:
        return target

    # Bare map_to — resolve via Kima id
    kima_num = _parse_kima_id(rec.get("suggested_id", ""))
    if not kima_num:
        return None

    kima_url_suffix = f"/Details/{kima_num}"
    for place in root.iter(f"{T}place"):
        for idno in place.findall(f"{T}idno"):
            if idno.text and kima_url_suffix in idno.text:
                return place.get(f"{X}id")
    return None


def process_map_to(root: ET.Element, decisions: list[dict], dry_run: bool) -> int:
    """
    For each map_to decision, add the Hebrew name as a variant on the
    target ``<place>`` element.

    The TSV name is used as-is (no prefix stripping) because the names
    in the TSV already represent the correct bare form as tagged in the
    edition XML.

    Returns the number of variants actually added.
    """
    added = 0
    for rec in decisions:
        target_id = _resolve_map_to_target(root, rec)
        name = rec["name"]

        if not target_id:
            print(f"  ⚠ Could not resolve map_to target for '{name}' "
                  f"(suggested_id={rec.get('suggested_id', '')})")
            continue

        place = _find_place_by_id(root, target_id)
        if place is None:
            print(f"  ⚠ map_to target {target_id} not found for '{name}'")
            continue

        if dry_run:
            existing = _existing_place_names(place)
            if name not in existing:
                print(f"  [dry-run] Would add variant '{name}' → {target_id}")
                added += 1
            else:
                print(f"  '{name}' already on {target_id}")
        else:
            if _add_name_variant(place, name):
                print(f"  ✓ Added variant '{name}' → {target_id}")
                added += 1
            else:
                print(f"  '{name}' already on {target_id}")
    return added


# ═════════════════════════════════════════════════════════════════════════════
# Step 3 – Process new decisions
# ═════════════════════════════════════════════════════════════════════════════

def _highest_hloc_num(root: ET.Element) -> int:
    """Return the highest numeric suffix among existing H-LOC_N ids."""
    best = 0
    for place in root.iter(f"{T}place"):
        xml_id = place.get(f"{X}id") or ""
        m = re.match(r"H-LOC_(\d+)$", xml_id)
        if m:
            best = max(best, int(m.group(1)))
    return best


def _find_list_place(root: ET.Element) -> ET.Element | None:
    """Find the (first) ``<listPlace>`` in the tree."""
    for lp in root.iter(f"{T}listPlace"):
        return lp
    return None


def _parse_kima_id(suggested: str) -> str | None:
    """Extract the numeric Kima id from suggested_id like 'kima:12345'."""
    if not suggested:
        return None
    m = re.match(r"kima:\s*(\d+)", suggested, re.I)
    return m.group(1) if m else None


def _load_kima_lookup() -> dict[str, dict]:
    """
    Load the Kima places CSV and return a lookup ``{kima_id: row_dict}``.

    The CSV is expected at the path resolved by config.KIMA_PLACES_CSV.
    Returns an empty dict if the file is not available.
    """
    from config import KIMA_PLACES_CSV  # noqa: E402
    if not os.path.exists(KIMA_PLACES_CSV):
        return {}
    lookup: dict[str, dict] = {}
    with open(KIMA_PLACES_CSV, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            kid = (row.get("id") or "").strip()
            if kid:
                lookup[kid] = row
    return lookup


def _kima_already_in_authority(root: ET.Element, kima_num: str) -> str | None:
    """
    Return the H-LOC id of an existing place with this Kima number,
    or None if no match.  Used to make ``process_new`` idempotent.
    """
    if not kima_num:
        return None
    suffix = f"/Details/{kima_num}"
    for place in root.iter(f"{T}place"):
        for idno in place.findall(f"{T}idno"):
            if idno.text and suffix in idno.text:
                return place.get(f"{X}id")
    return None


def process_new(root: ET.Element, decisions: list[dict],
                dry_run: bool) -> tuple[int, int]:
    """
    Create new ``<place>`` elements for each 'new' decision.

    Enriches each element with English name, coordinates, and Wikidata
    QID from the Kima gazetteer CSV when available.

    The TSV name is used as-is (no prefix stripping).

    Idempotent: skips decisions whose Kima ID already exists in the
    authority XML.

    Returns ``(n_created, next_free_num)``.
    """
    list_place = _find_list_place(root)
    if list_place is None:
        print("  ✗ <listPlace> not found in authority XML!")
        return 0, 0

    kima_lookup = _load_kima_lookup()
    next_num = _highest_hloc_num(root) + 1
    created = 0

    for rec in decisions:
        name = rec["name"]
        kima_num = _parse_kima_id(rec["suggested_id"])

        # Idempotency: skip if this Kima ID already exists
        existing_id = _kima_already_in_authority(root, kima_num)
        if existing_id:
            print(f"  '{name}' (Kima {kima_num}) already exists as {existing_id}")
            continue

        new_id = f"H-LOC_{next_num}"

        # Look up enrichment data from Kima CSV
        kima_row = kima_lookup.get(kima_num, {}) if kima_num else {}
        en_name = (kima_row.get("primary_rom_full") or "").strip()
        lat = (kima_row.get("lat") or "").strip()
        lon = (kima_row.get("lon") or "").strip()
        wd_qid = (kima_row.get("WikiData_Id") or "").strip()

        if dry_run:
            parts = [f"  [dry-run] Would create {new_id} for '{name}'"]
            if en_name:
                parts.append(f"({en_name})")
            if kima_num:
                parts.append(f"Kima {kima_num}")
            print(" ".join(parts))
        else:
            place_elem = ET.SubElement(list_place, f"{T}place")
            place_elem.set(f"{X}id", new_id)

            # English name first (matches existing convention)
            if en_name:
                pn_en = ET.SubElement(place_elem, f"{T}placeName")
                pn_en.text = en_name

            # Coordinates
            if lat and lon and lat != "NULL" and lon != "NULL":
                loc = ET.SubElement(place_elem, f"{T}location")
                geo = ET.SubElement(loc, f"{T}geo")
                geo.text = f"{lat},{lon}"

            # Kima ID
            if kima_num:
                idno = ET.SubElement(place_elem, f"{T}idno")
                idno.set("type", "Kima")
                idno.text = f"https://data.geo-kima.org/Places/Details/{kima_num}"

            # Wikidata
            if wd_qid:
                idno_wd = ET.SubElement(place_elem, f"{T}idno")
                idno_wd.set("type", "Wikidata")
                idno_wd.text = f"https://www.wikidata.org/wiki/{wd_qid}"

            # Hebrew name last (matches existing convention)
            pn_he = ET.SubElement(place_elem, f"{T}placeName")
            pn_he.text = name

            print(f"  ✓ Created {new_id} for '{name}'"
                  f"{f' ({en_name})' if en_name else ''}"
                  f"{f' Kima {kima_num}' if kima_num else ''}")

        next_num += 1
        created += 1

    return created, next_num


# ═════════════════════════════════════════════════════════════════════════════
# Step 4 – Write updated authority XML
# ═════════════════════════════════════════════════════════════════════════════

def write_authority_xml(tree: ET.ElementTree, dry_run: bool) -> None:
    """Serialize the modified authority tree back to disk."""
    if dry_run:
        print(f"\n  [dry-run] Would write {AUTHORITY_XML_PATH}")
        return

    ET.register_namespace("", TEI_NS)
    ET.register_namespace("xml", XML_NS)
    tree.write(AUTHORITY_XML_PATH, encoding="unicode", xml_declaration=True)
    print(f"\n  ✓ Written {AUTHORITY_XML_PATH}")


# ═════════════════════════════════════════════════════════════════════════════
# Step 5 – Regenerate matching DB
# ═════════════════════════════════════════════════════════════════════════════

def regenerate_matching_db(dry_run: bool) -> None:
    if dry_run:
        print(f"  [dry-run] Would run {GEN_SCRIPT}")
        return

    print(f"\n  Running {Path(GEN_SCRIPT).name} …")
    subprocess.check_call([sys.executable, GEN_SCRIPT])


# ═════════════════════════════════════════════════════════════════════════════
# Step 6 – Batch-link unlinked <placeName> in editions
# ═════════════════════════════════════════════════════════════════════════════

def _build_variant_index(db_path: str) -> dict[str, str]:
    """
    Build a mapping ``{name_variant: H-LOC_id}`` from the matching DB JSON.
    """
    with open(db_path, encoding="utf-8") as fh:
        db = json.load(fh)

    idx: dict[str, str] = {}
    for place in db.get("places", []):
        pid = place["id"]
        for n in place.get("names_he", []):
            if n and n not in idx:
                idx[n] = pid
        for n in place.get("names_en", []):
            if n and n not in idx:
                idx[n] = pid
    return idx


def _build_parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    """Return a child→parent mapping for the tree."""
    return {child: parent for parent in root.iter() for child in parent}


def batch_link_edition(edition_path: str, variant_index: dict[str, str],
                       dry_run: bool) -> int:
    """
    Scan *edition_path* for ``<placeName>`` elements without a ``ref``
    attribute and try to match their text (with optional prefix stripping)
    against the *variant_index*.

    Returns number of newly linked elements.
    """
    tree = ET.parse(edition_path)
    root = tree.getroot()
    linked = 0

    for pn in root.findall(f".//{T}placeName"):
        if pn.get("ref"):
            continue  # already linked
        text = (pn.text or "").strip()
        if not text:
            continue

        # Try exact match first
        match_id = variant_index.get(text)

        # Try prefix-stripped match
        if not match_id:
            _pfx, bare = _strip_hebrew_prefix(text)
            if _pfx:
                match_id = variant_index.get(bare)

        if match_id:
            if dry_run:
                linked += 1
            else:
                # If the match was via prefix stripping, fix the annotation:
                # move the prefix letter outside the tag
                _pfx, bare = _strip_hebrew_prefix(text)
                if _pfx and variant_index.get(bare) == match_id:
                    # We need to restructure: <placeName>מXXX</placeName>
                    # becomes: מ<placeName ref="…">XXX</placeName>
                    # To do this we set text to bare and prepend prefix as
                    # the tail of the preceding sibling or the text of parent.
                    parent_map = _build_parent_map(root)
                    parent = parent_map.get(pn)
                    if parent is not None:
                        # Find position of pn among parent's children
                        children = list(parent)
                        idx = children.index(pn)
                        if idx == 0:
                            # First child — prefix goes into parent.text
                            parent.text = (parent.text or "") + _pfx
                        else:
                            # Prefix goes into preceding sibling's tail
                            prev = children[idx - 1]
                            prev.tail = (prev.tail or "") + _pfx
                        pn.text = bare

                pn.set("ref", f"#{match_id}")
                linked += 1

    if not dry_run and linked > 0:
        ET.register_namespace("", TEI_NS)
        ET.register_namespace("xml", XML_NS)
        tree.write(edition_path, encoding="unicode", xml_declaration=True)

    return linked


def batch_link_all_editions(dry_run: bool) -> int:
    """
    Run batch-linking on every ``_corrected.xml`` file in ``editions/incoming/``.
    Returns total number of newly linked elements across all editions.
    """
    variant_index = _build_variant_index(MATCHING_DB_PATH)
    total = 0
    edition_dir = Path(EDITIONS_INCOMING)

    for xml_file in sorted(
        list(edition_dir.glob("*_corrected.xml"))
        + list(edition_dir.glob("*_gemini.xml"))
    ):
        n = batch_link_edition(str(xml_file), variant_index, dry_run)
        if n > 0:
            tag = "[dry-run] " if dry_run else ""
            print(f"  {tag}Linked {n} placeName(s) in {xml_file.name}")
            total += n
    return total


# ═════════════════════════════════════════════════════════════════════════════
# Step 7 – Process skip decisions (unwrap + log)
# ═════════════════════════════════════════════════════════════════════════════

def _load_skipped_json(path: str) -> list[dict]:
    """Load existing skipped_places.json or return empty list."""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return []


def _save_skipped_json(path: str, data: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _unwrap_placename_in_edition(edition_path: str, name: str,
                                 dry_run: bool) -> int:
    """
    In *edition_path*, find every ``<placeName>`` whose text equals *name*
    (exact match) and unwrap it — i.e. replace the element with its bare
    text content, preserving surrounding text flow.

    Also handles prefixed variants: if a tag contains ``מXXX`` we also
    check if the bare ``XXX`` equals *name*.

    Returns the number of unwrapped occurrences.
    """
    tree = ET.parse(edition_path)
    root = tree.getroot()
    parent_map = _build_parent_map(root)
    count = 0

    for pn in root.findall(f".//{T}placeName"):
        text = (pn.text or "").strip()
        if not text:
            continue

        # Match the exact name, or the name with a prefix
        match = False
        if text == name:
            match = True
        else:
            _pfx, bare = _strip_hebrew_prefix(text)
            if _pfx and bare == name:
                match = True

        if not match:
            continue
        if pn.get("ref"):
            continue  # already linked to something — don't unwrap

        parent = parent_map.get(pn)
        if parent is None:
            continue

        # Unwrap: merge pn.text (with any prefix) + pn.tail into
        # the surrounding text flow.
        full_text = (pn.text or "") + (pn.tail or "")
        children = list(parent)
        idx = children.index(pn)

        if idx == 0:
            parent.text = (parent.text or "") + full_text
        else:
            prev = children[idx - 1]
            prev.tail = (prev.tail or "") + full_text

        parent.remove(pn)
        count += 1

    if not dry_run and count > 0:
        ET.register_namespace("", TEI_NS)
        ET.register_namespace("xml", XML_NS)
        tree.write(edition_path, encoding="unicode", xml_declaration=True)

    return count


def process_skip(decisions: list[dict], dry_run: bool) -> int:
    """
    For each 'skip' decision:
    1. Unwrap ``<placeName>`` tags across all editions.
    2. Log to ``skipped_places.json``.

    Returns total number of unwrapped tags.
    """
    edition_dir = Path(EDITIONS_INCOMING)
    skipped_log = _load_skipped_json(SKIPPED_JSON_PATH) if not dry_run else []
    existing_names = {s["name"] for s in skipped_log}
    total_unwrapped = 0

    for rec in decisions:
        name = rec["name"]

        # Unwrap in all corrected editions mentioned for this name
        edition_files = [
            e.strip() for e in rec["editions"].split(";") if e.strip()
        ]
        # Fall back to all corrected editions if none specified
        if not edition_files:
            edition_files = [f.name for f in edition_dir.glob("*_corrected.xml")]

        name_count = 0
        for ed_name in edition_files:
            ed_path = edition_dir / ed_name
            if not ed_path.exists():
                continue
            n = _unwrap_placename_in_edition(str(ed_path), name, dry_run)
            name_count += n

        tag = "[dry-run] " if dry_run else ""
        if name_count:
            print(f"  {tag}Unwrapped {name_count} <placeName> tag(s) for '{name}'")
        else:
            print(f"  {tag}No unlinked <placeName> tags found for '{name}'")

        total_unwrapped += name_count

        # Log to skipped_places.json
        if not dry_run and name not in existing_names:
            skipped_log.append({
                "name": name,
                "editions": rec["editions"],
                "context_snippet": rec["contexts"][:300] if rec["contexts"] else "",
                "source": "apply_kima_decisions",
            })
            existing_names.add(name)

    if not dry_run and skipped_log:
        _save_skipped_json(SKIPPED_JSON_PATH, skipped_log)
        print(f"  ✓ Updated {SKIPPED_JSON_PATH}")

    return total_unwrapped


# ═════════════════════════════════════════════════════════════════════════════
# Step 7b – Ensure <head type="storyHead"> in all corrected editions
# ═════════════════════════════════════════════════════════════════════════════

def ensure_story_heads(dry_run: bool) -> int:
    """
    Ensure every ``<div type="story">`` in corrected editions has a
    ``<head type="storyHead">`` child whose text is the div's ``xml:id``.

    If a story div already has a ``<head type="storyHead">`` child it is
    left untouched.  The new ``<head>`` is inserted as the **first child**
    of the div, before any existing ``<head>``, ``<span>``, or ``<p>``.

    Returns the total number of storyHead elements added.
    """
    edition_dir = Path(EDITIONS_INCOMING)
    total = 0

    for xml_file in sorted(edition_dir.glob("*_corrected.xml")):
        ET.register_namespace("", TEI_NS)
        ET.register_namespace("xml", XML_NS)
        tree = ET.parse(str(xml_file))
        root = tree.getroot()
        added = 0

        for div in root.findall(f".//{T}div"):
            if div.get("type") != "story":
                continue

            xml_id = div.get(f"{X}id")
            if not xml_id:
                continue

            # Check if storyHead already exists
            has_story_head = any(
                h.get("type") == "storyHead"
                for h in div.findall(f"{T}head")
            )
            if has_story_head:
                continue

            # Create and insert as first child
            head = ET.Element(f"{T}head")
            head.set("type", "storyHead")
            head.text = xml_id
            head.tail = "\n"
            div.insert(0, head)
            added += 1

        if added:
            tag = "[dry-run] " if dry_run else ""
            print(f"  {tag}Added {added} storyHead(s) in {xml_file.name}")
            if not dry_run:
                tree.write(str(xml_file), encoding="unicode",
                           xml_declaration=True)
            total += added

    return total


# ═════════════════════════════════════════════════════════════════════════════
# Step 7c – Fix namespace declarations in corrected editions
# ═════════════════════════════════════════════════════════════════════════════

_TEI_URI = "http://www.tei-c.org/ns/1.0"

def fix_edition_namespaces(dry_run: bool) -> int:
    """
    Transform the namespace declarations in every ``*_corrected.xml``
    edition to the TEI-Publisher-required format via string-level
    post-processing (ElementTree cannot produce this format natively).

    Transforms applied:
    - ``<TEI xmlns="…tei-c.org…">``  →  ``<tei:TEI xmlns:tei="…tei-c.org…">``
    - ``<teiHeader>``                →  ``<teiHeader xmlns="…tei-c.org…">``
    - ``<text>`` (top-level only)    →  ``<text xmlns="…tei-c.org…">``
    - ``</TEI>``                     →  ``</tei:TEI>``

    Idempotent: files that already start with ``<tei:TEI`` are skipped.

    **Must be the last step that writes edition XML files**, because any
    subsequent ElementTree write would revert these changes.

    Returns the number of files modified.
    """
    edition_dir = Path(EDITIONS_INCOMING)
    modified = 0

    for xml_file in sorted(edition_dir.glob("*_corrected.xml")):
        with open(str(xml_file), encoding="utf-8") as fh:
            content = fh.read()

        # Idempotency check
        if f"<tei:TEI xmlns:tei=\"{_TEI_URI}\">" in content:
            continue

        original = content

        # 1. Root element: <TEI xmlns="…"> → <tei:TEI xmlns:tei="…">
        content = content.replace(
            f'<TEI xmlns="{_TEI_URI}">',
            f'<tei:TEI xmlns:tei="{_TEI_URI}">',
        )

        # 2. <teiHeader> → <teiHeader xmlns="…"> (only if no xmlns yet)
        content = re.sub(
            r'<teiHeader(?!\s+xmlns)',
            f'<teiHeader xmlns="{_TEI_URI}"',
            content,
            count=1,
        )

        # 3. Top-level <text> → <text xmlns="…">  (first occurrence only)
        content = re.sub(
            r'<text(?=\s*>)',
            f'<text xmlns="{_TEI_URI}"',
            content,
            count=1,
        )

        # 4. Closing </TEI> → </tei:TEI>
        content = content.replace("</TEI>", "</tei:TEI>")

        if content == original:
            continue  # nothing changed (shouldn't happen, but be safe)

        tag = "[dry-run] " if dry_run else ""
        print(f"  {tag}Fixed namespaces in {xml_file.name}")
        if not dry_run:
            with open(str(xml_file), "w", encoding="utf-8") as fh:
                fh.write(content)
        modified += 1

    return modified


# ═════════════════════════════════════════════════════════════════════════════
# Step 8 – Summary & optional git commit
# ═════════════════════════════════════════════════════════════════════════════

def git_commit(message: str) -> None:
    """Stage changed files and create a commit."""
    # Stage the key files
    files_to_stage = [
        AUTHORITY_XML_PATH,
        MATCHING_DB_PATH,
        SKIPPED_JSON_PATH,
        UNMATCHED_TSV,
    ]
    # Also stage all edition XMLs that may have been modified
    edition_dir = Path(EDITIONS_INCOMING)
    for pattern in ("*_corrected.xml", "*_gemini.xml"):
        for f in edition_dir.glob(pattern):
            files_to_stage.append(str(f))

    existing = [f for f in files_to_stage if os.path.exists(f)]
    subprocess.check_call(["git", "add"] + existing)
    subprocess.check_call(["git", "commit", "-m", message])
    print("\n  ✓ Git commit created.")


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply Kima Review decisions to authority XML and editions.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would happen without modifying any files.",
    )
    parser.add_argument(
        "--skip-commit", action="store_true",
        help="Apply changes but do not create a git commit.",
    )
    args = parser.parse_args()
    dry_run: bool = args.dry_run
    skip_commit: bool = args.skip_commit

    if dry_run:
        print("═══ DRY RUN — no files will be modified ═══\n")

    # ── Step 1: Load ──────────────────────────────────────────────────────
    print("Step 1: Loading TSV decisions …")
    decisions = load_tsv_decisions(UNMATCHED_TSV)
    n_map = len(decisions["map_to"])
    n_new = len(decisions["new"])
    n_skip = len(decisions["skip"])
    print(f"  Found {n_map} map_to, {n_new} new, {n_skip} skip decisions.\n")

    if n_map + n_new + n_skip == 0:
        print("Nothing to do.")
        return

    # ── Load authority XML ────────────────────────────────────────────────
    ET.register_namespace("", TEI_NS)
    ET.register_namespace("xml", XML_NS)
    tree = ET.parse(AUTHORITY_XML_PATH)
    root = tree.getroot()

    # ── Step 2: map_to ────────────────────────────────────────────────────
    if n_map:
        print("Step 2: Processing map_to decisions …")
        variants_added = process_map_to(root, decisions["map_to"], dry_run)
        print(f"  → {variants_added} variant(s) added.\n")
    else:
        print("Step 2: No map_to decisions.\n")

    # ── Step 3: new ───────────────────────────────────────────────────────
    if n_new:
        print("Step 3: Processing new place decisions …")
        places_created, _next = process_new(root, decisions["new"], dry_run)
        print(f"  → {places_created} place(s) created.\n")
    else:
        print("Step 3: No new place decisions.\n")

    # ── Step 4: Write authority XML ───────────────────────────────────────
    print("Step 4: Writing authority XML …")
    write_authority_xml(tree, dry_run)

    # ── Step 5: Regenerate matching DB ────────────────────────────────────
    print("\nStep 5: Regenerating matching DB …")
    regenerate_matching_db(dry_run)

    # ── Step 6: Batch-link editions ───────────────────────────────────────
    print("\nStep 6: Batch-linking editions …")
    linked = batch_link_all_editions(dry_run)
    print(f"  → {linked} placeName(s) linked.\n")

    # ── Step 7: Process skip decisions ────────────────────────────────────
    if n_skip:
        print("Step 7: Processing skip decisions (unwrap + log) …")
        unwrapped = process_skip(decisions["skip"], dry_run)
        print(f"  → {unwrapped} tag(s) unwrapped.\n")
    else:
        print("Step 7: No skip decisions.\n")

    # ── Step 7b: Ensure storyHead ────────────────────────────────────────
    print("Step 7b: Ensuring storyHead in corrected editions …")
    heads_added = ensure_story_heads(dry_run)
    if heads_added:
        print(f"  → {heads_added} storyHead(s) added.\n")
    else:
        print("  → All story divs already have storyHead.\n")

    # ── Step 7c: Fix namespace declarations (MUST be last XML write) ────
    print("Step 7c: Fixing namespace declarations in corrected editions …")
    ns_fixed = fix_edition_namespaces(dry_run)
    if ns_fixed:
        print(f"  → {ns_fixed} file(s) updated.\n")
    else:
        print("  → All corrected editions already have correct namespaces.\n")

    # ── Step 8: Summary ──────────────────────────────────────────────────
    print("═══ Summary ═══")
    print(f"  map_to variants added : {variants_added if n_map else 0}")
    print(f"  new places created    : {places_created if n_new else 0}")
    print(f"  edition links added   : {linked}")
    print(f"  skip tags unwrapped   : {unwrapped if n_skip else 0}")
    print(f"  storyHeads added      : {heads_added}")
    print(f"  namespace fixes       : {ns_fixed}")

    if dry_run:
        print("\n  (dry run — no changes written)")
        return

    if not skip_commit:
        commit_msg = (
            f"Apply Kima decisions: "
            f"{variants_added if n_map else 0} map_to, "
            f"{places_created if n_new else 0} new, "
            f"{unwrapped if n_skip else 0} skip, "
            f"{linked} batch-linked, "
            f"{heads_added} storyHeads, "
            f"{ns_fixed} ns-fixes"
        )
        try:
            git_commit(commit_msg)
        except subprocess.CalledProcessError as exc:
            print(f"\n  ⚠ Git commit failed: {exc}")
    else:
        print("\n  (--skip-commit: no git commit created)")


if __name__ == "__main__":
    main()
