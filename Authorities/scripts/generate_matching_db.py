#!/usr/bin/env python3
"""
Generate (or regenerate) authorities-matching-db.json from Authorities2026-01-14.xml.

Run directly:
    python3 Authorities/scripts/generate_matching_db.py

Also called automatically by the Streamlit integration tool after commits.
"""

import datetime
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO        = Path(__file__).parent.parent.parent
AUTH_XML    = REPO / "Authorities" / "Authorities2026-01-14.xml"
MATCH_DB    = REPO / "Authorities" / "authorities-matching-db.json"
DISPLAY_XML = REPO / "Authorities" / "Authorities.xml"

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
T = f"{{{TEI_NS}}}"
X = f"{{{XML_NS}}}"


# ── Language detection ─────────────────────────────────────────────────────────

def detect_lang(text: str) -> str:
    """Return 'he' if text contains Hebrew characters, else 'en'."""
    return "he" if any('\u0590' <= c <= '\u05FF' for c in text) else "en"


# ── Place parsing ──────────────────────────────────────────────────────────────

def _parse_places(root: ET.Element) -> list[dict]:
    records = []
    for list_place in root.iter(f"{T}listPlace"):
        for place in list_place.findall(f"{T}place"):
            xml_id = place.get(f"{X}id")
            if not xml_id:
                continue

            # Collect all placeName texts, split by language
            names_he, names_en = [], []
            for pn in place.findall(f"{T}placeName"):
                text = (pn.text or "").strip()
                if not text:
                    continue
                if detect_lang(text) == "he":
                    names_he.append(text)
                else:
                    names_en.append(text)

            # Coordinates
            coords = None
            loc = place.find(f"{T}location")
            if loc is not None:
                geo = loc.find(f"{T}geo")
                if geo is not None and geo.text:
                    parts = geo.text.strip().split(",")
                    if len(parts) == 2:
                        try:
                            coords = [float(parts[0]), float(parts[1])]
                        except ValueError:
                            pass

            # Identifiers
            identifiers = {}
            for idno in place.findall(f"{T}idno"):
                id_type = (idno.get("type") or "").strip()
                val = (idno.text or "").strip()
                if id_type and val:
                    # Normalise multi-URL Tsadikim entries (pipe-separated)
                    identifiers[id_type] = val

            records.append({
                "id":              xml_id,
                "primary_name_he": names_he[0] if names_he else "(to be updated)",
                "primary_name_en": names_en[0] if names_en else "(to be updated)",
                "names_he":        names_he,
                "names_en":        names_en,
                "coordinates":     coords,
                "identifiers":     identifiers,
                "notes":           "",
            })
    return records


# ── Person parsing ─────────────────────────────────────────────────────────────

def _parse_persons(root: ET.Element) -> list[dict]:
    records = []
    for list_person in root.iter(f"{T}listPerson"):
        for person in list_person.findall(f"{T}person"):
            xml_id = person.get(f"{X}id")
            if not xml_id:
                continue

            names_he, names_en = [], []

            # <persName> elements (may have xml:lang or not)
            for pn in person.findall(f"{T}persName"):
                lang = pn.get(f"{X}lang", "")
                text = "".join(pn.itertext()).strip()
                if not text:
                    continue
                if lang == "he" or (not lang and detect_lang(text) == "he"):
                    names_he.append(text)
                else:
                    names_en.append(text)

            # <name> elements (used in some entries)
            for nm in person.findall(f"{T}name"):
                lang = nm.get(f"{X}lang", "")
                text = (nm.text or "").strip()
                if not text:
                    continue
                if lang == "he" or (not lang and detect_lang(text) == "he"):
                    names_he.append(text)
                else:
                    names_en.append(text)

            # Identifiers
            identifiers = {}
            for idno in person.findall(f"{T}idno"):
                id_type = (idno.get("type") or "").strip()
                val = (idno.text or "").strip()
                if id_type and val:
                    identifiers[id_type] = val

            records.append({
                "id":              xml_id,
                "primary_name_he": names_he[0] if names_he else "(to be updated)",
                "primary_name_en": names_en[0] if names_en else "(to be updated)",
                "names_he":        names_he,
                "names_en":        names_en,
                "identifiers":     identifiers,
            })
    return records


# ── Duplicate URI detection ────────────────────────────────────────────────────

def _find_duplicate_uris(places: list[dict]) -> list[str]:
    """Return list of warning strings for places sharing external URIs."""
    from collections import defaultdict
    uri_to_ids = defaultdict(list)
    for p in places:
        for uri in p["identifiers"].values():
            for u in uri.split("|"):
                u = u.strip()
                if u:
                    uri_to_ids[u].append(p["id"])
    return [
        f"URI shared by {ids}: {uri}"
        for uri, ids in uri_to_ids.items()
        if len(ids) > 1
    ]


# ── Main ───────────────────────────────────────────────────────────────────────

def generate(auth_xml_path=AUTH_XML, out_path=MATCH_DB, verbose=True):
    ET.register_namespace("", TEI_NS)
    ET.register_namespace("xml", XML_NS)
    tree = ET.parse(str(auth_xml_path))
    root = tree.getroot()

    places  = _parse_places(root)
    persons = _parse_persons(root)

    db = {
        "places":  places,
        "persons": persons,
        "meta": {
            "generated":    datetime.datetime.now().isoformat(),
            "source":       str(auth_xml_path),
            "place_count":  len(places),
            "person_count": len(persons),
        },
    }

    with open(str(out_path), "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    if verbose:
        print(f"Generated {out_path}")
        print(f"  {len(places)} places, {len(persons)} persons")
        dupes = _find_duplicate_uris(places)
        if dupes:
            print(f"  ⚠ {len(dupes)} duplicate URI warning(s):")
            for d in dupes:
                print(f"    {d}")
        else:
            print("  No duplicate URI warnings.")

    return db


if __name__ == "__main__":
    generate()
