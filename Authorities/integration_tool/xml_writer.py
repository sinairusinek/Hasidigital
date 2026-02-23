"""
Write enriched records back into the TEI XML tree and serialise.
Only "accepted" MatchResults are written (status=MATCHED or NEW with assigned_id).
"""
import xml.etree.ElementTree as ET
from data_models import PlaceRecord, PersonRecord, BiblRecord, MatchResult
from utils import normalize_id_type

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
T = f"{{{TEI_NS}}}"
X = f"{{{XML_NS}}}"


def _tag(local: str) -> str:
    return f"{T}{local}"


# ── Enrich an existing record ────────────────────────────────────────────────

def _enrich_place_element(elem: ET.Element, csv_rec: PlaceRecord) -> None:
    """Add missing idno / placeName elements to an existing <place> element."""
    existing_idno_types = {
        normalize_id_type(e.get("type", ""))
        for e in elem.findall(_tag("idno"))
    }
    existing_names = {
        e.text.strip() for e in elem.findall(_tag("placeName")) if e.text
    }

    # Add new identifiers
    id_map = {
        "Wikidata": csv_rec.wikidata,
        "Kima": csv_rec.kima,
        "Tsadikim": csv_rec.tsadikim,
        "JewishGen": csv_rec.jewishgen,
    }
    for id_type, val in id_map.items():
        if val and id_type not in existing_idno_types:
            idno_el = ET.SubElement(elem, _tag("idno"))
            idno_el.set("type", id_type)
            idno_el.text = val

    # Add new variant names
    for name in csv_rec.names:
        if name and name not in existing_names:
            pn = ET.SubElement(elem, _tag("placeName"))
            pn.text = name

    # Fill in coordinates if missing
    loc = elem.find(_tag("location"))
    if loc is None and csv_rec.lat is not None and csv_rec.lon is not None:
        loc = ET.SubElement(elem, _tag("location"))
        geo = ET.SubElement(loc, _tag("geo"))
        geo.text = f"{csv_rec.lat},{csv_rec.lon}"


def _enrich_person_element(elem: ET.Element, csv_rec: PersonRecord) -> None:
    """Add missing idno / name elements to an existing <person> element."""
    existing_idno_types = {
        normalize_id_type(e.get("type", ""))
        for e in elem.findall(_tag("idno"))
    }

    id_map = {
        "Wikidata": csv_rec.wikidata,
        "Tsadikim": csv_rec.tsadikim,
        "DiJeStDB": csv_rec.dijestdb,
        "Kima": csv_rec.kima,
        "JewishGen": csv_rec.jewishgen,
    }
    for id_type, val in id_map.items():
        if val and id_type not in existing_idno_types:
            idno_el = ET.SubElement(elem, _tag("idno"))
            idno_el.set("type", id_type)
            idno_el.text = val

    existing_he = {
        e.text.strip()
        for e in elem.findall(_tag("name"))
        if e.get(f"{X}lang") == "he" and e.text
    }
    existing_en = {
        e.text.strip()
        for e in elem.findall(_tag("name"))
        if e.get(f"{X}lang") == "en" and e.text
    }
    for n in csv_rec.names_he:
        if n and n not in existing_he:
            el = ET.SubElement(elem, _tag("name"))
            el.set(f"{X}lang", "he")
            el.text = n
    for n in csv_rec.names_en:
        if n and n not in existing_en:
            el = ET.SubElement(elem, _tag("name"))
            el.set(f"{X}lang", "en")
            el.text = n


# ── Create new elements ───────────────────────────────────────────────────────

def _new_place_element(rec: PlaceRecord, xml_id: str) -> ET.Element:
    elem = ET.Element(_tag("place"))
    elem.set(f"{X}id", xml_id)

    for name in rec.names:
        pn = ET.SubElement(elem, _tag("placeName"))
        pn.text = name

    if rec.lat is not None and rec.lon is not None:
        loc = ET.SubElement(elem, _tag("location"))
        geo = ET.SubElement(loc, _tag("geo"))
        geo.text = f"{rec.lat},{rec.lon}"

    id_map = [
        ("Wikidata", rec.wikidata),
        ("Kima", rec.kima),
        ("Tsadikim", rec.tsadikim),
        ("JewishGen", rec.jewishgen),
    ]
    for id_type, val in id_map:
        if val:
            idno_el = ET.SubElement(elem, _tag("idno"))
            idno_el.set("type", id_type)
            idno_el.text = val

    return elem


def _new_person_element(rec: PersonRecord, xml_id: str) -> ET.Element:
    elem = ET.Element(_tag("person"))
    elem.set(f"{X}id", xml_id)

    for n in rec.names_he:
        el = ET.SubElement(elem, _tag("name"))
        el.set(f"{X}lang", "he")
        el.text = n
    for n in rec.names_en:
        el = ET.SubElement(elem, _tag("name"))
        el.set(f"{X}lang", "en")
        el.text = n

    if rec.birth:
        b = ET.SubElement(elem, _tag("birth"))
        b.set("when", rec.birth)
        b.text = rec.birth
    if rec.death:
        d = ET.SubElement(elem, _tag("death"))
        d.set("when", rec.death)
        d.text = rec.death

    id_map = [
        ("Wikidata", rec.wikidata),
        ("Tsadikim", rec.tsadikim),
        ("DiJeStDB", rec.dijestdb),
        ("Kima", rec.kima),
        ("JewishGen", rec.jewishgen),
    ]
    for id_type, val in id_map:
        if val:
            idno_el = ET.SubElement(elem, _tag("idno"))
            idno_el.set("type", id_type)
            idno_el.text = val

    return elem


def _new_bibl_element(rec: BiblRecord, xml_id: str) -> ET.Element:
    elem = ET.Element(_tag("bibl"))
    elem.set(f"{X}id", xml_id)
    if rec.title:
        t = ET.SubElement(elem, _tag("title"))
        t.text = rec.title
    return elem


# ── Main writer ───────────────────────────────────────────────────────────────

def apply_results(
    tree: ET.ElementTree,
    results: list[MatchResult],
    entity_type: str,          # "place", "person", "bibl"
) -> None:
    """
    Mutate the tree in-place:
    - MATCHED + accepted → enrich existing element
    - NEW + assigned_id  → append new element to correct list
    """
    root = tree.getroot()

    # Build lookup: xml_id → element
    tag_map = {
        "place": (_tag("listPlace"), _tag("place")),
        "person": (_tag("listPerson"), _tag("person")),
        "bibl": (_tag("listBibl"), _tag("bibl")),
    }
    list_tag, elem_tag = tag_map[entity_type]

    elem_by_id: dict[str, ET.Element] = {}
    target_list: ET.Element | None = None

    for list_el in root.iter(list_tag):
        # For persons, we want the "contents" list for new entries
        if entity_type == "person":
            if list_el.get("type") == "contents" or target_list is None:
                target_list = list_el
        else:
            target_list = list_el
        for child in list_el.findall(elem_tag):
            cid = child.get(f"{X}id")
            if cid:
                elem_by_id[cid] = child

    for result in results:
        if result.resolution == "skip":
            continue

        if result.status == MatchResult.MATCHED and result.resolution in ("accept", ""):
            # Enrich existing
            xml_rec = result.xml_record
            if xml_rec and xml_rec.xml_id and xml_rec.xml_id in elem_by_id:
                elem = elem_by_id[xml_rec.xml_id]
                if entity_type == "place":
                    _enrich_place_element(elem, result.csv_record)
                elif entity_type == "person":
                    _enrich_person_element(elem, result.csv_record)

        elif result.status == MatchResult.NEW and result.assigned_id:
            if target_list is None:
                continue
            if entity_type == "place":
                new_el = _new_place_element(result.csv_record, result.assigned_id)
            elif entity_type == "person":
                new_el = _new_person_element(result.csv_record, result.assigned_id)
            elif entity_type == "bibl":
                new_el = _new_bibl_element(result.csv_record, result.assigned_id)
            else:
                continue
            target_list.append(new_el)


def serialise(tree: ET.ElementTree, path: str) -> None:
    """Write the tree to disk, preserving UTF-8 and the XML declaration."""
    ET.register_namespace("", TEI_NS)
    ET.register_namespace("xml", XML_NS)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def serialise_bytes(tree: ET.ElementTree) -> bytes:
    """Serialise to bytes for Streamlit download_button."""
    import io
    ET.register_namespace("", TEI_NS)
    ET.register_namespace("xml", XML_NS)
    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    return buf.getvalue()
