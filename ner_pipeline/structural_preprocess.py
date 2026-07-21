"""
Structural preprocessing of TEI XML files.

Converts facsimile zone metadata into proper TEI structure:
  - catch-word / page-number / running-head zones → <fw>
  - heading zones → <div type="story"> wrappers with <head>
Also strips facsimile elements and facs/n attributes from the output.
"""

from lxml import etree
from .config import TEI_NS, NAMESPACES, TEI_XMLID


def needs_structural_preprocessing(tree):
    """Return True if the XML tree has facsimile zones that need restructuring."""
    zones = tree.xpath("//tei:facsimile//tei:zone", namespaces=NAMESPACES)
    return len(zones) > 0


def restructure_facsimile_zones(tree):
    """
    Restructure paragraphs based on facsimile zone subtypes.

    - catch-word / page-number / running-head → <fw type="...">
    - heading → wraps heading + following paragraphs into <div type="story">

    Modifies the tree in-place and returns it.
    """
    # Build zone lookup from facsimile
    objects = []
    for zone in tree.xpath("//tei:facsimile//tei:zone", namespaces=NAMESPACES):
        objects.append({
            "subtype": zone.get("subtype"),
            "xml:id": zone.attrib.get(TEI_XMLID),
        })

    div_counter = 1

    for p in tree.xpath("//tei:text//tei:p", namespaces=NAMESPACES):
        facs_id = p.attrib.get("facs")
        if not facs_id:
            continue
        facs_id = facs_id.lstrip("#")
        matching = next((o for o in objects if o["xml:id"] == facs_id), None)
        if not matching:
            continue

        subtype = matching["subtype"]

        # Convert catch-word / page-number / running-head to <fw>
        if subtype in ("catch-word", "page-number", "running-head"):
            p.tag = f"{{{TEI_NS}}}fw"
            p.set("type", subtype)
            continue

        if subtype != "heading":
            continue

        # Wrap heading + following paragraphs into <div type="story">
        parent = p.getparent()
        index = parent.index(p)

        head = etree.Element(f"{{{TEI_NS}}}head", attrib=p.attrib)
        head[:] = p[:]
        head.text = p.text
        head.tail = p.tail

        div = etree.Element(f"{{{TEI_NS}}}div")
        div.set("type", "story")
        div.set(TEI_XMLID, f"Structured_{div_counter:04d}")
        div_counter += 1
        div.append(head)

        parent.remove(p)

        # Collect following siblings until the next heading
        while index < len(parent):
            sibling = parent[index]
            if sibling.tag == f"{{{TEI_NS}}}p":
                next_facs = sibling.attrib.get("facs", "").lstrip("#")
                next_obj = next(
                    (o for o in objects if o["xml:id"] == next_facs), None
                )
                if next_obj and next_obj["subtype"] == "heading":
                    break
            parent.remove(sibling)
            div.append(sibling)

        parent.insert(index, div)

    return tree


def remove_facsimile_and_attrs(tree):
    """
    Remove <facsimile> elements and facs/n attributes from text elements.
    Modifies the tree in-place and returns it.
    """
    for facsimile in tree.xpath("//tei:facsimile", namespaces=NAMESPACES):
        facsimile.getparent().remove(facsimile)

    for el in tree.xpath(
        "//tei:text//tei:p | //tei:text//tei:head | //tei:text//tei:lb",
        namespaces=NAMESPACES,
    ):
        for attr in ("facs", "n"):
            if attr in el.attrib:
                del el.attrib[attr]

    return tree
