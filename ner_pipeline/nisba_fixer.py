"""
Post-processor that restores nisba/bio nesting in TEI XML.

After Gemini correction + annotation insertion, person-name + place-of-origin
patterns are flattened into adjacent siblings:

    <persName>יצחק</persName> מ<placeName>לובלין</placeName>

This module merges them back into the proper nested TEI structure:

    <persName>יצחק מ<placeName ana="bio">לובלין</placeName></persName>
"""

import logging
import re
from lxml import etree

from .config import TEI_NS

logger = logging.getLogger(__name__)

# Hebrew particles that connect a person name to their place of origin.
# Matches the full tail text between </persName> and <placeName>.
_PARTICLE_RE = re.compile(
    r"^\s*"
    r"("
    r'מק"ק\s*'       # מקהילת קודש (from holy community of)
    r"|מק[׳']\s*"    # מק' abbreviated
    r"|מ"             # מ = from
    r"|ד"             # ד = of (Aramaic)
    r"|ה"             # ה = the (adjectival / nisba)
    r")"
    r"\s*$"
)

# Line/page/column break local names — may appear in the gap between persName and placeName
_BREAK_LOCALNAMES = {"lb", "pb", "cb"}


def _localname(el):
    """Return the local name of an element, or None for non-element nodes."""
    tag = el.tag
    if not isinstance(tag, str):
        return None
    return etree.QName(tag).localname


def fix_nisba_nesting(tree: etree._ElementTree) -> int:
    """Scan TEI XML tree and merge persName + particle + placeName siblings
    into nested ``<persName>...<placeName ana="bio">...</placeName></persName>``.

    Works on the tree **in-place**.  Returns the number of merges performed.
    Safe to call multiple times (idempotent).

    Handles both TEI-namespaced and non-namespaced elements (the latter arise
    when standoffconverter inserts annotations without the namespace prefix).
    Also handles ``<lb/>``, ``<pb/>``, and ``<cb/>`` break elements that may
    appear between the persName and placeName.
    """
    root = tree if isinstance(tree, etree._Element) else tree.getroot()
    # Accept both namespaced and non-namespaced <text> elements
    text_el = root.find(f".//{{{TEI_NS}}}text")
    if text_el is None:
        text_el = root.find(".//text")
    if text_el is None:
        return 0

    candidates = _find_merge_candidates(text_el)
    merge_count = 0

    for pers_el, lb_els, place_el, gap_text in candidates:
        _merge_persname_placename(pers_el, lb_els, place_el, gap_text)
        merge_count += 1
        pers_text = "".join(pers_el.itertext()).strip()
        logger.info("Merged nisba: %s", pers_text)

    if merge_count:
        logger.info("Total nisba merges: %d", merge_count)
    return merge_count


# ── internals ────────────────────────────────────────────────────────────────

def _find_merge_candidates(text_el):
    """Return list of ``(persName, lb_elements, placeName, gap_text)`` to merge.

    Uses local-name matching so that both TEI-namespaced and non-namespaced
    elements (produced by standoffconverter) are handled.  Also walks back
    past ``<lb/>``, ``<pb/>``, and ``<cb/>`` break elements that may sit
    between the persName and placeName.
    """
    candidates = []
    for place_el in list(text_el.iter()):
        if _localname(place_el) != "placeName":
            continue

        # Skip if already nested inside a persName (idempotency).
        if _is_inside_persname(place_el):
            continue

        # Walk back through preceding siblings, skipping break elements.
        prev = place_el.getprevious()
        lb_elements = []
        while prev is not None and _localname(prev) in _BREAK_LOCALNAMES:
            lb_elements.insert(0, prev)  # maintain document order
            prev = prev.getprevious()

        if prev is None or _localname(prev) != "persName":
            continue

        # Build the full gap text: persName.tail + lb/pb/cb tails.
        gap_text = (prev.tail or "") + "".join(lb.tail or "" for lb in lb_elements)
        if _PARTICLE_RE.match(gap_text):
            candidates.append((prev, lb_elements, place_el, gap_text))

    return candidates


def _is_inside_persname(el):
    """Check whether *el* has a ``<persName>`` ancestor (any namespace)."""
    ancestor = el.getparent()
    while ancestor is not None:
        if _localname(ancestor) == "persName":
            return True
        ancestor = ancestor.getparent()
    return False


def _merge_persname_placename(pers_el, lb_els, place_el, gap_text):
    """Move *place_el* inside *pers_el*, transferring gap text.

    Handles optional ``lb_els`` — break elements in the gap that are removed
    from the parent during the merge (their text contribution is already
    included in *gap_text*).

    Before (lxml model)::

        <p>...<persName>Name</persName> מ<lb/><placeName ref="X">Place</placeName> rest...</p>
        pers_el.tail  = " מ"       (first part of gap_text)
        lb.tail       = ""         (second part of gap_text)
        place_el.tail = " rest..."

    After::

        <p>...<persName>Name מ<placeName ref="X" ana="bio">Place</placeName></persName> rest...</p>
        pers_el.text  = "Name מ"   (gap appended inside)
        pers_el.tail  = " rest..."
        place_el.tail = None
    """
    parent = place_el.getparent()

    # 1. Remember what comes after the placeName.
    after_text = place_el.tail or ""

    # 2. Remove intervening break elements and the placeName from the parent.
    for lb in lb_els:
        parent.remove(lb)
    parent.remove(place_el)

    # 3. Append the combined gap text inside persName.
    children = list(pers_el)
    if children:
        last = children[-1]
        last.tail = (last.tail or "") + gap_text
    else:
        pers_el.text = (pers_el.text or "") + gap_text

    # 4. Append placeName as a child of persName.
    pers_el.append(place_el)
    place_el.tail = None

    # 5. Transfer the after-text to persName's tail.
    pers_el.tail = after_text

    # 6. Add ana="bio" if not already set.
    if place_el.get("ana") is None:
        place_el.set("ana", "bio")
