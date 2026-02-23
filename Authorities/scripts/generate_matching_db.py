#!/usr/bin/env python3
"""
Generate matching database and display XML from authority XML.

This script:
1. Parses the TEI authority XML file
2. Scans all edition files for place/person name occurrences
3. Generates:
   - authorities-matching-db.json (comprehensive matching DB with occurrence tracking)
   - Authorities.xml (minimal display XML for TEI-Publisher)

Usage:
    python generate_matching_db.py [--authority-xml PATH] [--output-dir DIR]
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
import sys
from typing import Dict, List, Tuple, Optional

# TEI namespace
TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

# Register namespaces
ET.register_namespace('', TEI_NS)
ET.register_namespace('xml', XML_NS)


def get_default_paths():
    """Get default paths for authority file and outputs."""
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent.parent
    auth_dir = project_dir / "Authorities"
    editions_dir = project_dir / "editions"

    authority_xml = auth_dir / "Authorities2026-01-14.xml"
    output_dir = auth_dir

    return authority_xml, editions_dir, output_dir


def parse_place_element(elem) -> Dict:
    """Parse a <place> element into a dict."""
    xml_id = elem.get(f"{{{XML_NS}}}id") or elem.get("id")

    # Collect all placeName elements
    names_he = []
    names_en = []
    primary_name_en = None
    primary_name_he = None

    for pn in elem.findall(f"{{{TEI_NS}}}placeName"):
        lang = pn.get(f"{{{XML_NS}}}lang", "")
        ptype = pn.get("type", "")
        name_text = (pn.text or "").strip()

        if not name_text:
            continue

        if ptype == "primary_en" or (lang == "en" and not primary_name_en):
            primary_name_en = name_text
        elif ptype == "primary_he" or (lang == "he" and not primary_name_he):
            primary_name_he = name_text

        if lang == "he":
            if name_text not in names_he:
                names_he.append(name_text)
        elif lang == "en":
            if name_text not in names_en:
                names_en.append(name_text)
        else:
            # Default to English if no lang specified
            if name_text not in names_en:
                names_en.append(name_text)

    # Fallback: use first name found
    if not primary_name_en and names_en:
        primary_name_en = names_en[0]
    if not primary_name_he and names_he:
        primary_name_he = names_he[0]

    # Get coordinates
    coordinates = None
    geo_elem = elem.find(f"{{{TEI_NS}}}location/{{{TEI_NS}}}geo")
    if geo_elem is not None and geo_elem.text:
        try:
            lat, lon = geo_elem.text.strip().split(",")
            coordinates = [float(lat), float(lon)]
        except (ValueError, IndexError):
            pass

    # Collect identifiers
    identifiers = {}
    for idno in elem.findall(f"{{{TEI_NS}}}idno"):
        idno_type = idno.get("type", "unknown")
        idno_text = (idno.text or "").strip()
        if idno_text:
            identifiers[idno_type] = idno_text

    # Get notes/description
    notes = ""
    desc_elem = elem.find(f"{{{TEI_NS}}}desc")
    if desc_elem is not None:
        notes = (desc_elem.text or "").strip()

    return {
        "id": xml_id,
        "primary_name_he": primary_name_he or "(to be updated)",
        "primary_name_en": primary_name_en or "Unknown",
        "names_he": names_he,
        "names_en": names_en,
        "coordinates": coordinates,
        "identifiers": identifiers,
        "notes": notes,
        "status": "identified" if coordinates else "unidentified",
    }


def parse_person_element(elem) -> Dict:
    """Parse a <person> element into a dict."""
    xml_id = elem.get(f"{{{XML_NS}}}id") or elem.get("id")

    # Collect all name elements
    names_he = []
    names_en = []
    primary_name_en = None
    primary_name_he = None

    for name in elem.findall(f"{{{TEI_NS}}}name"):
        lang = name.get(f"{{{XML_NS}}}lang", "")
        name_text = (name.text or "").strip()

        if not name_text:
            continue

        if lang == "he":
            if name_text not in names_he:
                names_he.append(name_text)
            if not primary_name_he:
                primary_name_he = name_text
        else:  # English or no lang
            if name_text not in names_en:
                names_en.append(name_text)
            if not primary_name_en:
                primary_name_en = name_text

    # Collect identifiers
    identifiers = {}
    for idno in elem.findall(f"{{{TEI_NS}}}idno"):
        idno_type = idno.get("type", "unknown")
        idno_text = (idno.text or "").strip()
        if idno_text:
            identifiers[idno_type] = idno_text

    return {
        "id": xml_id,
        "primary_name_he": primary_name_he or "(to be updated)",
        "primary_name_en": primary_name_en or "Unknown",
        "names_he": names_he,
        "names_en": names_en,
        "identifiers": identifiers,
    }


def parse_authority_xml(xml_path: Path) -> Tuple[List[Dict], List[Dict]]:
    """Parse authority XML and extract places and persons."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    places = []
    persons = []

    # Parse places
    for place_elem in root.findall(f".//{{{TEI_NS}}}listPlace/{{{TEI_NS}}}place"):
        places.append(parse_place_element(place_elem))

    # Parse persons (both paratextual and contents)
    for person_elem in root.findall(f".//{{{TEI_NS}}}listPerson/{{{TEI_NS}}}person"):
        persons.append(parse_person_element(person_elem))

    return places, persons


def scan_editions_for_places(editions_dir: Path, places: List[Dict]) -> Dict:
    """
    Scan all edition files for place name occurrences.

    Returns dict: place_id → {file_name → {variant_name → count}}
    """
    occurrences = {}

    # Build a map of all name variants to place IDs
    name_to_places = {}  # name → [(place_id, lang)]
    for place in places:
        place_id = place["id"]
        for name in place["names_he"]:
            if name not in name_to_places:
                name_to_places[name] = []
            name_to_places[name].append((place_id, "he"))
        for name in place["names_en"]:
            if name not in name_to_places:
                name_to_places[name] = []
            name_to_places[name].append((place_id, "en"))

    # Scan editions
    edition_files = sorted(editions_dir.glob("*.xml"))
    for edition_file in edition_files:
        try:
            tree = ET.parse(edition_file)
            root = tree.getroot()

            # Find all placeName elements
            for pn_elem in root.findall(f".//{{{TEI_NS}}}placeName"):
                place_text = (pn_elem.text or "").strip()

                if not place_text:
                    continue

                # Check if this name matches any place variant
                if place_text in name_to_places:
                    for place_id, lang in name_to_places[place_text]:
                        if place_id not in occurrences:
                            occurrences[place_id] = {}

                        file_name = edition_file.name
                        if file_name not in occurrences[place_id]:
                            occurrences[place_id][file_name] = {}

                        # Track which variant (with language tag) was found
                        if place_text not in occurrences[place_id][file_name]:
                            occurrences[place_id][file_name][place_text] = 0
                        occurrences[place_id][file_name][place_text] += 1

        except Exception as e:
            print(f"Warning: Could not parse {edition_file}: {e}", file=sys.stderr)

    return occurrences


def build_matching_db_json(places: List[Dict], persons: List[Dict],
                           occurrences: Dict) -> Dict:
    """Build the matching database JSON structure."""
    # Enhance places with occurrence data
    places_with_occ = []
    for place in places:
        place_copy = place.copy()
        place_id = place["id"]

        if place_id in occurrences:
            place_copy["occurrences"] = occurrences[place_id]
            # Calculate total occurrences across all files and variants
            total = 0
            for file_dict in occurrences[place_id].values():
                # file_dict is {variant_name → count}
                for count in file_dict.values():
                    total += count
            place_copy["total_occurrences"] = total
        else:
            place_copy["occurrences"] = {}
            place_copy["total_occurrences"] = 0

        places_with_occ.append(place_copy)

    return {
        "places": places_with_occ,
        "persons": persons,
        "meta": {
            "generated": datetime.now().isoformat(),
            "source_file": "Authorities2026-01-14.xml",
        }
    }


def generate_display_xml(places: List[Dict], persons: List[Dict], output_path: Path):
    """Generate minimal TEI-Publisher display XML."""
    # Create root TEI element
    tei_root = ET.Element("TEI")
    tei_root.set("xmlns", TEI_NS)

    # Add header
    tei_header = ET.SubElement(tei_root, "teiHeader")
    file_desc = ET.SubElement(tei_header, "fileDesc")
    title_stmt = ET.SubElement(file_desc, "titleStmt")
    title = ET.SubElement(title_stmt, "title")
    title.text = "Hasidic Stories - Authorities Display File"

    pub_stmt = ET.SubElement(file_desc, "publicationStmt")
    pub_p = ET.SubElement(pub_stmt, "p")
    pub_p.text = f"Generated {datetime.now().isoformat()} for TEI-Publisher display"

    source_desc = ET.SubElement(file_desc, "sourceDesc")

    # Add places
    list_place = ET.SubElement(source_desc, "listPlace")
    for place in places:
        place_elem = ET.SubElement(list_place, "place")
        place_elem.set(f"{{{XML_NS}}}id", place["id"])

        # Add primary Hebrew name placeholder
        pn_he = ET.SubElement(place_elem, "placeName")
        pn_he.set(f"{{{XML_NS}}}lang", "he")
        pn_he.set("type", "primary_he")
        pn_he.text = place["primary_name_he"]

        # Add primary English name
        pn_en = ET.SubElement(place_elem, "placeName")
        pn_en.set(f"{{{XML_NS}}}lang", "en")
        pn_en.set("type", "primary_en")
        pn_en.text = place["primary_name_en"]

        # Add coordinates if available
        if place["coordinates"]:
            geo_elem = ET.SubElement(place_elem, "geo")
            geo_elem.text = f"{place['coordinates'][0]},{place['coordinates'][1]}"

    # Add persons
    list_person = ET.SubElement(source_desc, "listPerson")
    for person in persons:
        person_elem = ET.SubElement(list_person, "person")
        person_elem.set(f"{{{XML_NS}}}id", person["id"])

        name_elem = ET.SubElement(person_elem, "name")
        name_elem.text = person["primary_name_en"]

    # Write to file
    tree = ET.ElementTree(tei_root)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def main():
    """Main entry point."""
    authority_xml, editions_dir, output_dir = get_default_paths()

    print(f"Reading authority XML: {authority_xml}")
    places, persons = parse_authority_xml(authority_xml)
    print(f"  Found {len(places)} places, {len(persons)} persons")

    print(f"Scanning editions in: {editions_dir}")
    occurrences = scan_editions_for_places(editions_dir, places)
    print(f"  Found occurrences for {len(occurrences)} places")

    # Build matching database
    print("Building matching database JSON...")
    matching_db = build_matching_db_json(places, persons, occurrences)
    matching_db_path = output_dir / "authorities-matching-db.json"
    with open(matching_db_path, "w", encoding="utf-8") as f:
        json.dump(matching_db, f, ensure_ascii=False, indent=2)
    print(f"  Wrote: {matching_db_path}")

    # Generate display XML
    print("Generating TEI-Publisher display XML...")
    display_xml_path = output_dir / "Authorities.xml"
    generate_display_xml(places, persons, display_xml_path)
    print(f"  Wrote: {display_xml_path}")

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
