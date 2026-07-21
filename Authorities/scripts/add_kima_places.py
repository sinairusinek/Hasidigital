#!/usr/bin/env python3
"""
Add new places (sourced from the Kima API) to Authorities2026-01-14.xml.

Usage:  python3 Authorities/scripts/add_kima_places.py
"""

import re
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO        = Path(__file__).parent.parent.parent
AUTH_XML    = REPO / "Authorities" / "Authorities2026-01-14.xml"
GEN_SCRIPT  = REPO / "Authorities" / "scripts" / "generate_matching_db.py"

TEI_NS  = "http://www.tei-c.org/ns/1.0"
XML_NS  = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("",    TEI_NS)
ET.register_namespace("xml", XML_NS)

# ── New places fetched from Kima API ──────────────────────────────────────────
# Format: (kima_id, rom_name, heb_name, lat, lon, wikidata_q, note)
# Kima URL: https://data.geo-kima.org/Places/Details/{id}
# Wikidata URL: https://www.wikidata.org/wiki/{q}
NEW_PLACES = [
    (32,    "New York (N.Y.)",          "ניו יורק (נ.י.)",         40.7,             -74.0,              "Q60",      ""),
    (168,   "Podgorze (Krakow, Poland)", "פודגורזה (קרקוב, פולין)", 50.0416,           20.0177,            "Q2553877", ""),
    (272,   "Tel Aviv-Yafo (Israel)",    "תל אביב-יפו (ישראל)",     32.08,             34.78,              "Q33935",   ""),
    (336,   "Husiatyn (Ukraine)",        "הוסיטין (אוקראינה)",       49.070811307796,   26.19387898412,     "Q1638961", ""),
    (421,   "Frampol (Poland)",          "פרמפול (פולין)",           50.683333333333,   22.666666666667,    "Q985646",  ""),
    (525,   "Bilgoraj (Poland)",         "בילגורי (פולין)",          50.55,             22.733333333333,    "Q319445",  ""),
    (570,   "Bardejov (Slovakia)",       "ברדיוב (סלובקיה)",         49.295,            21.275833333333,    "Q27007",   ""),
    (969,   "Hrubieszow (Poland)",       "הרובישוב (פולין)",         50.8,              23.916666666667,    "Q924103",  ""),
    (1681,  "Laszczow (Poland)",         "לשצ'וב (פולין)",           50.53332,          23.72562,           "Q2167485", ""),
    (14092, "Palatinate (Germany)",      "פאלץ (גרמניה)",            49.5,              8.016669444444,     "Q326359",  "Used as placeholder for unlocated Russia-Poland prints"),
    # Kima 10066 does not exist in Kima DB; replacing with correct IDs:
    (405,   "Kaliningrad (Russia)",      "קלינינגרד / קניגסברג (רוסיה)",  54.716666666, 20.5,             "Q1829",    "Historical name: Königsberg (Prussia). Kima 10066 in TSV was incorrect."),
    (1703,  "Zhovkva (Ukraine)",         "זולקוה (אוקראינה)",        50.066666666667,   23.966666666667,    "Q864836",  "Also known as Żółkiew. Kima 10066 in TSV was incorrect for DBid=3598."),
]

# ── TSV corrections implied by this addition ─────────────────────────────────
TSV_CORRECTIONS = """
TSV corrections needed after adding these places:
  DBid=3651 (Koenigsberg, קניגסברג):   dijest:kimaID  10066 → 405
  DBid=3652 (Koenigsburg, קניגסברג):   dijest:kimaID  10066 → 405
  DBid=3598 (זלקווא / Zhovkva):        dijest:kimaID  10066 → 1703
  Note: DBids 3569,3570,3571,3658 have Kima 14092 (Palatinate) with place 'Russia-Poland' — likely placeholder, review manually.
"""

# ── Helpers ────────────────────────────────────────────────────────────────────

def tei(tag):
    return f"{{{TEI_NS}}}{tag}"

def xml_attr(name):
    return f"{{{XML_NS}}}{name}"

def build_place_element(hloc_id, kima_id, rom_name, heb_name, lat, lon, wikidata_q, note=""):
    place = ET.Element(tei("place"), {xml_attr("id"): hloc_id})

    # Primary Latin placeName
    pn_rom = ET.SubElement(place, tei("placeName"))
    pn_rom.text = rom_name

    # Coordinates
    if lat is not None and lon is not None:
        loc = ET.SubElement(place, tei("location"))
        geo = ET.SubElement(loc, tei("geo"))
        geo.text = f"{lat},{lon}"

    # Kima identifier
    idno_kima = ET.SubElement(place, tei("idno"))
    idno_kima.set("type", "Kima")
    idno_kima.text = f"https://data.geo-kima.org/Places/Details/{kima_id}"

    # Wikidata identifier
    if wikidata_q:
        idno_wd = ET.SubElement(place, tei("idno"))
        idno_wd.set("type", "Wikidata")
        idno_wd.text = f"https://www.wikidata.org/wiki/{wikidata_q.strip()}"

    # Hebrew placeName
    if heb_name:
        pn_heb = ET.SubElement(place, tei("placeName"))
        pn_heb.set(xml_attr("lang"), "he")
        pn_heb.text = heb_name

    # Note (if any)
    if note:
        n = ET.SubElement(place, tei("note"))
        n.text = note

    return place


def indent_element(elem, level=0, indent="                                    "):
    """Add pretty-print indentation matching the existing file style."""
    pad = "\n" + indent * (level + 1)
    end = "\n" + indent * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = pad
        for child in elem:
            indent_element(child, level + 1, indent)
            if not child.tail or not child.tail.strip():
                child.tail = pad
        if not child.tail or not child.tail.strip():
            child.tail = end
    else:
        if not elem.text:
            elem.text = ""


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    # Parse with namespace preservation
    ET.register_namespace("", TEI_NS)
    tree = ET.parse(AUTH_XML)
    root = tree.getroot()
    ns = {"tei": TEI_NS}

    # Find listPlace
    listplace = root.find(".//tei:listPlace", ns)
    if listplace is None:
        raise RuntimeError("No <listPlace> found in authority file")

    # Current max H-LOC number
    existing = [
        int(p.get(xml_attr("id")).split("_")[1])
        for p in listplace.findall("tei:place", ns)
        if p.get(xml_attr("id"), "").startswith("H-LOC_")
    ]
    next_num = max(existing) + 1

    # Check which Kima IDs already exist (to avoid duplicates)
    existing_kima = set()
    for p in listplace.findall("tei:place", ns):
        for idno in p.findall("tei:idno", ns):
            if idno.get("type") == "Kima" and idno.text:
                m = re.search(r'/(\d+)$', idno.text)
                if m:
                    existing_kima.add(int(m.group(1)))

    added = []
    skipped = []

    for (kima_id, rom_name, heb_name, lat, lon, wd_q, note) in NEW_PLACES:
        if kima_id in existing_kima:
            skipped.append((kima_id, rom_name))
            continue

        hloc_id = f"H-LOC_{next_num}"
        place_el = build_place_element(hloc_id, kima_id, rom_name, heb_name, lat, lon, wd_q, note)

        # Preserve whitespace: copy tail from previous last child
        last = list(listplace)[-1]
        prev_tail = last.tail or ""
        place_el.tail = prev_tail
        # Give new element the same indentation as others
        if not place_el.text:
            place_el.text = "\n" + " " * 36

        listplace.append(place_el)
        added.append((hloc_id, kima_id, rom_name))
        next_num += 1

    # Write back
    tree.write(AUTH_XML, encoding="unicode", xml_declaration=False)

    # Report
    print(f"Added {len(added)} new places to {AUTH_XML.name}:")
    for hloc, kid, name in added:
        print(f"  {hloc}  Kima {kid:6}  {name}")
    if skipped:
        print(f"\nSkipped (already present): {skipped}")

    print(TSV_CORRECTIONS)

    # Regenerate matching DB
    print("Regenerating matching DB...")
    result = subprocess.run(["python3", str(GEN_SCRIPT)], capture_output=True, text=True)
    if result.returncode == 0:
        print("Matching DB regenerated successfully.")
    else:
        print(f"ERROR regenerating matching DB:\n{result.stderr}")


if __name__ == "__main__":
    main()
