"""
Insert NER entities as inline TEI tags into an XML tree via standoffconverter.
Also extract existing annotations for correction-only workflows.
"""

from lxml import etree
from .config import TAGS_DICT, TEI_NS, NAMESPACES

# Reverse mapping: TEI tag → NER label (for extraction)
_TAG_TO_LABEL = {
    "persName": "PER",
    "placeName": "GPE",
    "orgName": "ORG",
    "date": "TIMEX",
}



def _remove_overlapping_entities(entities):
    """
    Remove overlapping entities, keeping the longer span.

    Processes in document order. When two entities overlap (one contains
    the other, or they share a start/end boundary), the shorter one is
    dropped. For equal-length overlapping spans, the earlier one wins.
    Entities with identical (start, end) are deduplicated first.

    Returns a new list with no overlapping spans.
    """
    if not entities:
        return entities

    # Deduplicate exact-same-span entities (same start+end regardless of label/text)
    # This prevents add_span() from being called twice with the same derived ID.
    seen_spans = {}
    deduped = []
    for ent in entities:
        key = (ent["start"], ent["end"])
        if key not in seen_spans:
            seen_spans[key] = True
            deduped.append(ent)

    # Sort by start, then by length descending (longest first)
    sorted_ents = sorted(deduped, key=lambda e: (e["start"], -(e["end"] - e["start"])))

    kept = []
    for ent in sorted_ents:
        s, e = ent["start"], ent["end"]
        # Check against all already-kept entities
        overlap = False
        for k in kept:
            ks, ke = k["start"], k["end"]
            # Any overlap: ranges intersect
            if s < ke and e > ks:
                overlap = True
                break
        if not overlap:
            kept.append(ent)

    # Restore document order (by start)
    kept.sort(key=lambda e: (e["start"], e["end"]))
    return kept


def insert_annotations(so, view, entities):
    """
    Insert entity annotations into the standoff object as inline XML elements.

    For each entity, maps character offsets (relative to the plain text view)
    to standoff table positions and adds the corresponding TEI tag.

    Overlapping entities are removed before insertion (keeping the longer span)
    to avoid standoffconverter producing invalid spanTo/anchor pairs.

    Falls back to ``so.add_span()`` with a unique ID when overlapping annotations
    prevent inline insertion despite the pre-filter (shouldn't normally happen).

    Args:
        so: Standoff object.
        view: View object (from standoffconverter).
        entities: List of dicts with keys: text, start, end, label.

    Returns:
        The modified Standoff object.
    """
    import logging
    logger = logging.getLogger(__name__)

    clean_entities = _remove_overlapping_entities(entities)
    removed = len(entities) - len(clean_entities)
    if removed:
        logger.warning("Removed %d overlapping entity span(s) before insertion.", removed)

    skipped = []
    used_span_ids = set()  # guard against duplicate anchor xml:ids

    for entity in clean_entities:
        label = entity["label"]
        if label not in TAGS_DICT:
            skipped.append((label, entity["text"]))
            continue

        tag_info = TAGS_DICT[label]

        so_start = view.get_table_pos(entity["start"])
        so_end = view.get_table_pos(entity["end"])

        attrib = dict(tag_info["attr"])  # copy to avoid mutation
        if entity.get("ref"):
            attrib["ref"] = entity["ref"]

        annotation = {
            "begin": so_start,
            "end": so_end,
            "tag": tag_info["tag"],
            "depth": None,
            "attrib": attrib,
        }

        try:
            so.add_inline(**annotation)
        except ValueError:
            # Overlapping annotation despite pre-filter — use span with unique ID
            span_id = f"ner_{entity['start']}_{entity['end']}"
            if span_id in used_span_ids:
                # Two entities mapped to the same standoff position; skip the duplicate
                # to prevent duplicate <anchor xml:id="..."/> in the output.
                logger.warning(
                    "Skipping duplicate span ID %s (entity %r) — would produce invalid XML.",
                    span_id, entity["text"],
                )
                continue
            used_span_ids.add(span_id)
            so.add_span(**{**annotation, "id_": span_id})

    return so


def extract_existing_entities(tree):
    """
    Extract existing NER annotations from a TEI XML tree.

    Walks the <text> body and finds all persName, placeName, orgName, date,
    and name elements. Computes character offsets by building a plain-text
    view of the document.

    Returns:
        list of dicts: {text, start, end, label, ref} where ref is the
        authority link (e.g. '#H-LOC_151') or None.
    """
    ns = {"tei": TEI_NS}
    text_el = tree.find(f".//{{{TEI_NS}}}text")
    if text_el is None:
        return []

    # Build a plain-text representation by walking the tree in order,
    # tracking character positions as we go.
    entities = []
    plain_parts = []
    char_pos = 0

    def _walk(el, inside_entity=None):
        nonlocal char_pos

        # Check if this element IS an entity
        entity_info = None
        local_name = etree.QName(el.tag).localname if isinstance(el.tag, str) else None

        if local_name in _TAG_TO_LABEL:
            label = _TAG_TO_LABEL[local_name]
            ref = el.get("ref")
            entity_info = {"label": label, "ref": ref, "start": char_pos}
        elif local_name == "name":
            name_type = el.get("type", "")
            if name_type in ("work", "book"):
                entity_info = {"label": "WOA", "ref": el.get("ref"), "start": char_pos}
            elif name_type in ("misc", "event"):
                entity_info = {"label": "MISC", "ref": el.get("ref"), "start": char_pos}

        current = entity_info or inside_entity

        # Process text content
        if el.text:
            text = el.text
            plain_parts.append(text)
            char_pos += len(text)

        # Process children
        for child in el:
            _walk(child, inside_entity=current if entity_info else inside_entity)
            # Process tail text (text after the child element)
            if child.tail:
                plain_parts.append(child.tail)
                char_pos += len(child.tail)

        # Close entity
        if entity_info is not None:
            entity_text = "".join(plain_parts[_find_parts_start(plain_parts, entity_info["start"], char_pos):])
            # Actually, compute text from start to current pos
            full_plain = "".join(plain_parts)
            entity_text = full_plain[entity_info["start"]:char_pos]
            entity_text_stripped = entity_text.strip()
            if entity_text_stripped:
                # Adjust for leading whitespace
                offset = len(entity_text) - len(entity_text.lstrip())
                entities.append({
                    "text": entity_text_stripped,
                    "start": entity_info["start"] + offset,
                    "end": entity_info["start"] + offset + len(entity_text_stripped),
                    "label": entity_info["label"],
                    "ref": entity_info.get("ref"),
                })

    def _find_parts_start(parts, target_pos, current_pos):
        """Helper — not actually needed, we use full_plain slicing."""
        return 0

    # Walk from <text> element
    _walk(text_el)

    return entities


def extract_existing_entities_simple(tree):
    """
    Simpler extraction: get entity text and labels from XML,
    then locate them in the plain text by string matching.

    This avoids the complexity of tracking character positions during tree walk.
    Returns list of dicts: {text, start, end, label, ref}.
    """
    from .text_extraction import create_standoff_view

    # Get plain text via standoffconverter
    so, view, plain_text = create_standoff_view(tree)

    ns = {"tei": TEI_NS}
    text_el = tree.find(f".//{{{TEI_NS}}}text")
    if text_el is None:
        return [], plain_text

    # Collect all annotation elements with their text
    raw_entities = []
    for tag_name, label in _TAG_TO_LABEL.items():
        for el in text_el.iter(f"{{{TEI_NS}}}{tag_name}"):
            text = "".join(el.itertext()).strip()
            ref = el.get("ref")
            if text:
                raw_entities.append({"text": text, "label": label, "ref": ref})

    # Also handle <name type="work|book|misc|event">
    for el in text_el.iter(f"{{{TEI_NS}}}name"):
        name_type = el.get("type", "")
        text = "".join(el.itertext()).strip()
        ref = el.get("ref")
        if not text:
            continue
        if name_type in ("work", "book"):
            raw_entities.append({"text": text, "label": "WOA", "ref": ref})
        elif name_type in ("misc", "event"):
            raw_entities.append({"text": text, "label": "MISC", "ref": ref})

    # Locate each entity in the plain text by sequential string matching
    entities = []
    search_from = 0
    # Sort by document order — find each occurrence sequentially
    for raw in raw_entities:
        # Normalize whitespace for matching
        normalized = " ".join(raw["text"].split())
        # Search in plain text from current position
        idx = plain_text.find(normalized, search_from)
        if idx == -1:
            # Try from beginning (entities may not be in perfect order)
            idx = plain_text.find(normalized)
        if idx == -1:
            # Try with original whitespace
            idx = plain_text.find(raw["text"], search_from)
        if idx >= 0:
            entities.append({
                "text": normalized,
                "start": idx,
                "end": idx + len(normalized),
                "label": raw["label"],
                "ref": raw.get("ref"),
            })
            search_from = idx + len(normalized)

    return entities, plain_text


def strip_annotations_from_heads(tree):
    """
    Remove any NER entity tags that were incorrectly inserted inside <head>
    elements (e.g. storyHead titles whose id fragments got annotated).

    Modifies tree in-place and returns it.
    """
    tei_ns = TEI_NS
    entity_tags = {
        f"{{{tei_ns}}}persName",
        f"{{{tei_ns}}}placeName",
        f"{{{tei_ns}}}orgName",
        f"{{{tei_ns}}}date",
    }
    for head in tree.iter(f"{{{tei_ns}}}head"):
        for el in list(head.iter()):
            if el.tag in entity_tags:
                _unwrap_element(el)
    return tree


def save_annotated_xml(tree, output_path):
    """Serialize the XML tree to a file."""
    with open(output_path, "wb") as f:
        f.write(
            etree.tostring(tree, pretty_print=True, encoding="utf-8",
                           xml_declaration=True)
        )


def has_existing_annotations(tree):
    """
    Check whether the XML tree already contains NER annotation tags
    (persName, placeName, orgName, date, name) in the <text> body.
    """
    ns = {"tei": "http://www.tei-c.org/ns/1.0"}
    tags = ["persName", "placeName", "orgName", "date", "name"]
    for tag in tags:
        if tree.xpath(f"//tei:text//tei:{tag}", namespaces=ns):
            return True
    return False


def strip_existing_annotations(tree):
    """
    Remove existing NER tags from the XML, preserving their text content.
    This allows re-annotation of already-annotated files.

    Modifies tree in-place and returns it.
    """
    ns = {"tei": "http://www.tei-c.org/ns/1.0"}
    tei_ns = "http://www.tei-c.org/ns/1.0"
    tags_to_strip = [
        f"{{{tei_ns}}}persName",
        f"{{{tei_ns}}}placeName",
        f"{{{tei_ns}}}orgName",
        f"{{{tei_ns}}}date",
    ]
    # Also strip <name type="misc|work|event">
    name_tag = f"{{{tei_ns}}}name"

    # Find all annotation elements within <text>
    text_el = tree.find(f".//{{{tei_ns}}}text")
    if text_el is None:
        return tree

    for tag in tags_to_strip:
        for el in text_el.iter(tag):
            _unwrap_element(el)

    # Handle <name> elements with type attribute
    for el in list(text_el.iter(name_tag)):
        if el.get("type") in ("misc", "work", "event"):
            _unwrap_element(el)

    return tree


def _unwrap_element(el):
    """
    Remove an element but keep its text and children in the parent.
    """
    parent = el.getparent()
    if parent is None:
        return

    idx = list(parent).index(el)

    # Prepend element's text to next sibling's tail or append to previous
    if el.text:
        if idx > 0:
            prev = parent[idx - 1]
            prev.tail = (prev.tail or "") + el.text
        else:
            parent.text = (parent.text or "") + el.text

    # Move children into parent
    for i, child in enumerate(el):
        parent.insert(idx + i, child)

    # Append element's tail to last moved child or adjust parent text
    if el.tail:
        moved_count = len(el)
        if moved_count > 0:
            last_moved = parent[idx + moved_count - 1]
            last_moved.tail = (last_moved.tail or "") + el.tail
        elif idx > 0:
            prev = parent[idx - 1] if moved_count == 0 else parent[idx + moved_count - 1]
            prev.tail = (prev.tail or "") + el.tail
        else:
            parent.text = (parent.text or "") + el.tail

    parent.remove(el)
