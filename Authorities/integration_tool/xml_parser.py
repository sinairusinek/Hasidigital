"""
Parse the TEI XML authority file into data model objects.
"""
import xml.etree.ElementTree as ET
from typing import Optional
from data_models import PlaceRecord, PersonRecord, BiblRecord
from utils import normalize_id_type

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

T = f"{{{TEI_NS}}}"
X = f"{{{XML_NS}}}"


def _tag(local: str) -> str:
    return f"{T}{local}"


def parse_xml(path: str) -> tuple[list[PlaceRecord], list[PersonRecord], list[BiblRecord], ET.ElementTree]:
    """
    Parse a TEI authority XML file.
    Returns (places, persons, bibls, tree) where tree is the raw ElementTree
    for later mutation by xml_writer.
    """
    ET.register_namespace("", TEI_NS)
    ET.register_namespace("xml", XML_NS)
    tree = ET.parse(path)
    root = tree.getroot()

    places = _parse_places(root)
    persons = _parse_persons(root)
    bibls = _parse_bibls(root)
    return places, persons, bibls, tree


# ── Places ──────────────────────────────────────────────────────────────────

def _parse_places(root: ET.Element) -> list[PlaceRecord]:
    records = []
    for list_place in root.iter(_tag("listPlace")):
        for place in list_place.findall(_tag("place")):
            rec = PlaceRecord()
            rec.xml_id = place.get(f"{X}id")

            # names
            for pn in place.findall(_tag("placeName")):
                if pn.text and pn.text.strip():
                    rec.names.append(pn.text.strip())

            # coordinates
            loc = place.find(_tag("location"))
            if loc is not None:
                geo = loc.find(_tag("geo"))
                if geo is not None and geo.text:
                    parts = geo.text.strip().split(",")
                    if len(parts) == 2:
                        try:
                            rec.lat = float(parts[0])
                            rec.lon = float(parts[1])
                        except ValueError:
                            pass

            # identifiers
            for idno in place.findall(_tag("idno")):
                id_type = normalize_id_type(idno.get("type", ""))
                val = idno.text.strip() if idno.text else ""
                if id_type == "Wikidata":
                    rec.wikidata = val
                elif id_type == "Kima":
                    rec.kima = val
                elif id_type == "Tsadikim":
                    rec.tsadikim = val
                elif id_type == "JewishGen":
                    rec.jewishgen = val

            records.append(rec)
    return records


# ── Persons ─────────────────────────────────────────────────────────────────

def _parse_persons(root: ET.Element) -> list[PersonRecord]:
    records = []
    for list_person in root.iter(_tag("listPerson")):
        for person in list_person.findall(_tag("person")):
            rec = PersonRecord()
            rec.xml_id = person.get(f"{X}id")

            for name_el in person.findall(_tag("name")):
                lang = name_el.get(f"{X}lang", "")
                val = name_el.text.strip() if name_el.text else ""
                if not val:
                    continue
                if lang == "he":
                    rec.names_he.append(val)
                elif lang == "en":
                    rec.names_en.append(val)
                else:
                    rec.names_en.append(val)

            birth = person.find(_tag("birth"))
            if birth is not None:
                rec.birth = birth.get("when") or (birth.text.strip() if birth.text else None)

            death = person.find(_tag("death"))
            if death is not None:
                rec.death = death.get("when") or (death.text.strip() if death.text else None)

            for idno in person.findall(_tag("idno")):
                id_type = normalize_id_type(idno.get("type", ""))
                val = idno.text.strip() if idno.text else ""
                if id_type == "Wikidata":
                    rec.wikidata = val
                elif id_type == "Tsadikim":
                    rec.tsadikim = val
                elif id_type == "DiJeStDB":
                    rec.dijestdb = val
                elif id_type == "Kima":
                    rec.kima = val
                elif id_type == "JewishGen":
                    rec.jewishgen = val

            records.append(rec)
    return records


# ── Bibls ────────────────────────────────────────────────────────────────────

def _parse_bibls(root: ET.Element) -> list[BiblRecord]:
    records = []
    for list_bibl in root.iter(_tag("listBibl")):
        for bibl in list_bibl.findall(_tag("bibl")):
            rec = BiblRecord()
            rec.xml_id = bibl.get(f"{X}id")
            title_el = bibl.find(_tag("title"))
            if title_el is not None and title_el.text:
                rec.title = title_el.text.strip()
            records.append(rec)
    return records
