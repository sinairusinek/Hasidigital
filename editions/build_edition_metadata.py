#!/usr/bin/env python3
"""
Build the initial edition-metadata.json from:
  1. edition-bibliography-match.tsv (XML ↔ bibliography mapping)
  2. Hasidic-editions-status - hasidic editions.tsv (full bibliography data)
  3. The XML edition files themselves (for existing sourceDesc fields)

This is a one-time bootstrap script. After this, edition-metadata.json
becomes the single source of truth, edited via the Streamlit page.
"""
from __future__ import annotations
import csv
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MATCH_TSV = REPO / "editions" / "edition-bibliography-match.tsv"
BIB_TSV = REPO / "Hasidic-editions-status - hasidic editions.tsv"
INCOMING = REPO / "editions" / "incoming"
OUTPUT = REPO / "editions" / "edition-metadata.json"


def load_match_report() -> list[dict]:
    with open(MATCH_TSV, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def load_bibliography() -> dict[str, list[dict]]:
    """Return dict: DBid → list of TSV rows (some DBids have pipes)."""
    by_dbid = {}
    with open(BIB_TSV, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            dbid = row.get("DBid", "").strip()
            if dbid:
                # Handle pipe-separated DBids
                for d in dbid.split("|"):
                    d = d.strip()
                    if d:
                        by_dbid.setdefault(d, []).append(row)
    return by_dbid


def extract_xml_metadata(xml_path: Path) -> dict:
    """Extract existing metadata from an edition XML's teiHeader."""
    meta = {}
    try:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
        ns = "{http://www.tei-c.org/ns/1.0}"

        # Title from titleStmt
        title_el = root.find(f".//{ns}titleStmt/{ns}title")
        if title_el is not None and title_el.text:
            meta["xml_title"] = title_el.text.strip()

        # sourceDesc/bibl metadata
        bibl = root.find(f".//{ns}sourceDesc/{ns}bibl")
        if bibl is not None:
            # Transkribus ID
            for idno in bibl.findall(f"{ns}idno"):
                id_type = (idno.get("type") or "").strip()
                val = (idno.text or "").strip()
                if id_type and val and val != "NA":
                    meta.setdefault("xml_identifiers", {})[id_type] = val

            # Date
            date_el = bibl.find(f"{ns}date")
            if date_el is not None:
                meta["xml_date_when"] = date_el.get("when", "")
                meta["xml_date_text"] = (date_el.text or "").strip()

            # pubPlace
            place_el = bibl.find(f"{ns}pubPlace")
            if place_el is not None:
                meta["xml_pubplace_ref"] = place_el.get("ref", "")
                meta["xml_pubplace_text"] = (place_el.text or "").strip()

        # Also check for richer sourceDesc (Kokhvei-Or style)
        for bibl2 in root.findall(f".//{ns}sourceDesc/{ns}bibl[@type='original']"):
            # Author
            author = bibl2.find(f"{ns}author")
            if author is not None:
                for pn in author.findall(f"{ns}persName"):
                    lang = pn.get(f"{{{ns.strip('{}')}}}lang", pn.get("xml:lang", ""))
                    if not lang:
                        lang = "he" if any('\u0590' <= c <= '\u05FF' for c in (pn.text or "")) else "en"
                    if "he" in lang:
                        meta["xml_author_he"] = (pn.text or "").strip()
                    else:
                        meta["xml_author_en"] = (pn.text or "").strip()

    except ET.ParseError:
        pass
    return meta


def build_edition_entry(match_row: dict, bib_by_dbid: dict) -> dict:
    """Build a single edition metadata entry."""
    xml_filename = match_row["xml_filename"]
    work_number = match_row.get("work_number", "")
    dbid = match_row.get("DBid", "")
    match_notes = match_row.get("notes", "")

    # Look up the bibliography row
    bib_row = None
    if dbid:
        # Try first DBid (may be pipe-separated)
        first_dbid = dbid.split("|")[0].strip().split(".")[0]  # handle "3727.0"
        rows = bib_by_dbid.get(first_dbid, [])
        if rows:
            bib_row = rows[0]

    # Extract from XML
    xml_path = INCOMING / xml_filename
    xml_meta = extract_xml_metadata(xml_path) if xml_path.exists() else {}

    # Build the entry
    entry = {
        "xml_filename": xml_filename,
        "work_number": int(work_number) if work_number and work_number != "0" else None,
        "DBid": dbid or None,
        "title_he": "",
        "title_en": "",
        "date_ce": "",
        "date_he": "",
        "pub_place_ref": "",
        "pub_place_he": "",
        "pub_place_en": "",
        "author_he": "",
        "author_en": "",
        "language": "",
        "identifiers": {},
        "match_method": match_row.get("match_method", ""),
        "match_notes": match_notes,
    }

    # Fill from bibliography TSV
    if bib_row:
        entry["title_he"] = bib_row.get("Final Edition Title for the DB", "").strip().replace('"', '')
        entry["title_en"] = bib_row.get("title-eng-Y", "").strip()
        entry["date_ce"] = bib_row.get("BHB-date", "").strip()
        entry["date_he"] = bib_row.get("BHBHebrewDate", "").strip().replace('"', '')
        entry["language"] = bib_row.get("Language", "").strip() or bib_row.get("dcterms:lanugage", "").strip()
        entry["author_he"] = bib_row.get("Author-heb-Y", "").strip()
        entry["author_en"] = bib_row.get("Author-eng-Y", "").strip()

        # Publication place from TSV
        pub_place = bib_row.get("BHBpublicationDate", "").strip()  # Mislabeled column!
        kitsis_place = bib_row.get("KitsispubPlace", "").strip()
        if pub_place:
            # Parse mixed he/en place names
            parts = [p.strip() for p in pub_place.split(",")]
            for p in parts:
                if any('\u0590' <= c <= '\u05FF' for c in p):
                    if not entry["pub_place_he"]:
                        entry["pub_place_he"] = p
                elif p and not entry["pub_place_en"]:
                    entry["pub_place_en"] = p
        if not entry["pub_place_he"] and kitsis_place:
            entry["pub_place_he"] = kitsis_place

        # Identifiers from TSV
        bhb = bib_row.get("Bibliography of the Hebrew Book", "").strip()
        if bhb:
            entry["identifiers"]["BHB"] = bhb
        alma = bib_row.get("ALMA ID", "").strip()
        if alma:
            entry["identifiers"]["ALMA"] = alma
        kima = bib_row.get("dijest:kimaID", "").strip()
        if kima and kima != "NULL":
            entry["identifiers"]["Kima"] = kima
        kitsis = bib_row.get("KitsisID", "").strip()
        if kitsis:
            entry["identifiers"]["Kitsis"] = kitsis

    # Overlay/fill from XML where TSV is empty
    if not entry["title_he"] and "xml_title" in xml_meta:
        # Try to extract Hebrew part from xml_title
        title = xml_meta["xml_title"]
        he_part = re.search(r'[\u0590-\u05FF][\u0590-\u05FF\s\u0027\u05F3\u05F4״]+', title)
        if he_part:
            entry["title_he"] = he_part.group(0).strip()

    if not entry["date_ce"] and xml_meta.get("xml_date_when"):
        entry["date_ce"] = xml_meta["xml_date_when"]

    if not entry["date_he"] and xml_meta.get("xml_date_text"):
        entry["date_he"] = xml_meta["xml_date_text"]

    if not entry["pub_place_ref"] and xml_meta.get("xml_pubplace_ref"):
        entry["pub_place_ref"] = xml_meta["xml_pubplace_ref"]

    if xml_meta.get("xml_identifiers"):
        for k, v in xml_meta["xml_identifiers"].items():
            if k not in entry["identifiers"]:
                entry["identifiers"][k] = v

    if not entry["author_he"] and xml_meta.get("xml_author_he"):
        entry["author_he"] = xml_meta["xml_author_he"]
    if not entry["author_en"] and xml_meta.get("xml_author_en"):
        entry["author_en"] = xml_meta["xml_author_en"]

    return entry


def main():
    match_rows = load_match_report()
    bib_by_dbid = load_bibliography()

    editions = []
    for row in match_rows:
        entry = build_edition_entry(row, bib_by_dbid)
        editions.append(entry)

    output = {
        "editions": editions,
        "meta": {
            "description": "Single source of truth for edition metadata. Edit here, then sync to XML headers and authorities-matching-db.json.",
            "edition_count": len(editions),
        }
    }

    with open(str(OUTPUT), "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Created {OUTPUT}")
    print(f"  {len(editions)} editions")
    for e in editions:
        status = "OK" if e["work_number"] else "NEEDS WORK#"
        print(f"  {status:15s} {e['xml_filename']:<55s} W-{str(e['work_number'] or '?'):<5s} {e['title_he'] or e['title_en'] or '(no title)'}")


if __name__ == "__main__":
    main()
