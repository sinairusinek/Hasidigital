#!/usr/bin/env python3
"""
Sync edition-metadata.json → two targets:
  1. Each edition XML's <teiHeader>/<sourceDesc>  (updates in place)
  2. authorities-matching-db.json  (adds/updates "editions" key)

Run directly:
    python3 Authorities/scripts/sync_edition_metadata.py

Also called by the Streamlit integration tool after metadata edits.
"""
from __future__ import annotations
import datetime
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
EDITION_META = REPO / "editions" / "edition-metadata.json"
INCOMING = REPO / "editions" / "online"
MATCH_DB = REPO / "Authorities" / "authorities-matching-db.json"

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
T = f"{{{TEI_NS}}}"
X = f"{{{XML_NS}}}"


def load_edition_metadata() -> list[dict]:
    with open(EDITION_META, encoding="utf-8") as f:
        return json.load(f)["editions"]


# ── Target 1: Update XML sourceDesc ─────────────────────────────────────────

def _build_source_desc(entry: dict) -> ET.Element:
    """Build a <sourceDesc> element from an edition metadata entry."""
    sd = ET.SubElement(ET.Element("dummy"), f"{T}sourceDesc")

    bibl = ET.SubElement(sd, f"{T}bibl", attrib={"type": "original"})

    # Title
    if entry.get("title_he"):
        t_he = ET.SubElement(bibl, f"{T}title", attrib={
            "type": "main", f"{X}lang": "he"
        })
        t_he.text = entry["title_he"]
    if entry.get("title_en"):
        t_en = ET.SubElement(bibl, f"{T}title", attrib={
            "type": "main", f"{X}lang": "en"
        })
        t_en.text = entry["title_en"]

    # Author
    if entry.get("author_he") or entry.get("author_en"):
        author = ET.SubElement(bibl, f"{T}author")
        if entry.get("author_he"):
            pn = ET.SubElement(author, f"{T}persName", attrib={f"{X}lang": "he"})
            pn.text = entry["author_he"]
        if entry.get("author_en"):
            pn = ET.SubElement(author, f"{T}persName", attrib={f"{X}lang": "en"})
            pn.text = entry["author_en"]

    # Imprint (pubPlace + date)
    imprint = ET.SubElement(bibl, f"{T}imprint")
    if entry.get("pub_place_he"):
        attrib = {}
        if entry.get("pub_place_ref"):
            attrib["ref"] = entry["pub_place_ref"]
        attrib[f"{X}lang"] = "he"
        pp = ET.SubElement(imprint, f"{T}pubPlace", attrib=attrib)
        pp.text = entry["pub_place_he"]
    if entry.get("pub_place_en"):
        attrib = {}
        if entry.get("pub_place_ref"):
            attrib["ref"] = entry["pub_place_ref"]
        attrib[f"{X}lang"] = "en"
        pp = ET.SubElement(imprint, f"{T}pubPlace", attrib=attrib)
        pp.text = entry["pub_place_en"]
    if entry.get("date_ce"):
        d = ET.SubElement(imprint, f"{T}date", attrib={"when": entry["date_ce"]})
        d.text = entry.get("date_he") or entry["date_ce"]

    # Language
    if entry.get("language"):
        tl = ET.SubElement(bibl, f"{T}textLang", attrib={"mainLang": entry["language"]})

    # Identifiers
    for id_type, val in entry.get("identifiers", {}).items():
        if val:
            idno = ET.SubElement(bibl, f"{T}idno", attrib={"type": id_type})
            idno.text = str(val)

    # DBid
    if entry.get("DBid"):
        idno = ET.SubElement(bibl, f"{T}idno", attrib={"type": "DBid"})
        idno.text = str(entry["DBid"])

    # Work number
    if entry.get("work_number"):
        idno = ET.SubElement(bibl, f"{T}idno", attrib={"type": "work"})
        idno.text = str(entry["work_number"])

    return sd


def sync_xml_headers(editions: list[dict], verbose: bool = True) -> int:
    """Update each edition XML's sourceDesc. Returns count of files updated."""
    ET.register_namespace("", TEI_NS)
    ET.register_namespace("xml", XML_NS)

    updated = 0
    for entry in editions:
        xml_path = INCOMING / entry["xml_filename"]
        if not xml_path.exists():
            if verbose:
                print(f"  SKIP {entry['xml_filename']} (file not found)")
            continue

        tree = ET.parse(str(xml_path))
        root = tree.getroot()

        # Find fileDesc
        file_desc = root.find(f".//{T}fileDesc")
        if file_desc is None:
            if verbose:
                print(f"  SKIP {entry['xml_filename']} (no fileDesc)")
            continue

        # Find or create sourceDesc
        source_desc = file_desc.find(f"{T}sourceDesc")
        if source_desc is None:
            source_desc = ET.SubElement(file_desc, f"{T}sourceDesc")
            # Position after publicationStmt
            pub_stmt = file_desc.find(f"{T}publicationStmt")
            if pub_stmt is not None:
                idx = list(file_desc).index(pub_stmt) + 1
                file_desc.remove(source_desc)
                file_desc.insert(idx, source_desc)

        # Remove only bibl[@type='original'] (or untyped bibl); preserve others
        for old_bibl in list(source_desc):
            btype = old_bibl.get("type", "")
            if btype in ("original", "") or old_bibl.tag != f"{T}bibl":
                source_desc.remove(old_bibl)

        # Build new bibl[@type='original'] and append to sourceDesc
        new_sd = _build_source_desc(entry)
        new_bibl = new_sd.find(f"{T}bibl")
        if new_bibl is not None:
            source_desc.append(new_bibl)

        # Also update the titleStmt/title to be canonical
        title_stmt = file_desc.find(f"{T}titleStmt")
        if title_stmt is not None:
            title_el = title_stmt.find(f"{T}title")
            if title_el is not None:
                canonical = ""
                if entry.get("title_en") and entry.get("title_he"):
                    canonical = f"{entry['title_en']} {entry.get('date_ce', '')} {entry['title_he']}".strip()
                elif entry.get("title_he"):
                    canonical = entry["title_he"]
                elif entry.get("title_en"):
                    canonical = entry["title_en"]
                if canonical:
                    title_el.text = canonical

        # Add revisionDesc entry
        revision = root.find(f".//{T}revisionDesc")
        if revision is None:
            tei_header = root.find(f"{T}teiHeader")
            if tei_header is not None:
                revision = ET.SubElement(tei_header, f"{T}revisionDesc")
        if revision is not None:
            change = ET.SubElement(revision, f"{T}change", attrib={
                "when": datetime.date.today().isoformat()
            })
            change.text = "sourceDesc synced from edition-metadata.json"

        tree.write(str(xml_path), encoding="unicode", xml_declaration=True)
        updated += 1
        if verbose:
            print(f"  OK   {entry['xml_filename']}")

    return updated


# ── Target 2: Update authorities-matching-db.json ───────────────────────────

def sync_matching_db(editions: list[dict], verbose: bool = True):
    """Add/update 'editions' section in authorities-matching-db.json."""
    if not MATCH_DB.exists():
        if verbose:
            print(f"  SKIP matching DB (not found at {MATCH_DB})")
        return

    with open(MATCH_DB, encoding="utf-8") as f:
        db = json.load(f)

    # Build edition records for the matching DB
    edition_records = []
    for entry in editions:
        rec = {
            "xml_filename": entry["xml_filename"],
            "work_number": entry.get("work_number"),
            "DBid": entry.get("DBid"),
            "title_he": entry.get("title_he", ""),
            "title_en": entry.get("title_en", ""),
            "date": entry.get("date_ce", ""),
            "language": entry.get("language", ""),
            "pub_place_ref": entry.get("pub_place_ref", ""),
            "identifiers": entry.get("identifiers", {}),
        }
        edition_records.append(rec)

    db["editions"] = edition_records
    db["meta"]["edition_count"] = len(edition_records)
    db["meta"]["editions_synced"] = datetime.datetime.now().isoformat()

    with open(MATCH_DB, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    if verbose:
        print(f"  Updated matching DB with {len(edition_records)} editions")


# ── Main ────────────────────────────────────────────────────────────────────

def sync(verbose: bool = True):
    """Run the full sync: JSON → XML headers + matching DB."""
    editions = load_edition_metadata()

    if verbose:
        print(f"Syncing {len(editions)} editions from {EDITION_META}")
        print()
        print("1. Updating XML sourceDesc:")

    n = sync_xml_headers(editions, verbose=verbose)

    if verbose:
        print(f"\n   {n}/{len(editions)} XML files updated")
        print()
        print("2. Updating matching DB:")

    sync_matching_db(editions, verbose=verbose)

    if verbose:
        print("\nDone.")

    return n


if __name__ == "__main__":
    sync()
