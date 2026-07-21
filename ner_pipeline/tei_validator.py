"""
Lightweight TEI XML validation checks.

Runs after pipeline save to catch common structural problems early.
Returns a list of warning strings (empty = all checks passed).
"""

import logging
from pathlib import Path
from lxml import etree

from .config import TEI_NS

logger = logging.getLogger(__name__)

_NS = {"tei": TEI_NS}

# Required order of children inside <fileDesc>
_FILEDESC_ORDER = ["titleStmt", "editionStmt", "extent", "publicationStmt",
                   "seriesStmt", "notesStmt", "sourceDesc"]


def validate_tei(tree_or_path):
    """
    Run structural validation checks on a TEI XML tree or file.

    Args:
        tree_or_path: An lxml ElementTree, or a path to an XML file.

    Returns:
        List of warning strings. Empty list means all checks passed.
    """
    if isinstance(tree_or_path, (str, Path)):
        try:
            tree = etree.parse(str(tree_or_path))
        except etree.XMLSyntaxError as e:
            return [f"XML not well-formed: {e}"]
    else:
        tree = tree_or_path

    warnings = []
    warnings.extend(_check_filedesc_order(tree))
    warnings.extend(_check_no_imprint_in_bibl(tree))
    warnings.extend(_check_no_nested_ner_tags(tree))
    warnings.extend(_check_no_empty_ner_tags(tree))

    return warnings


def _check_filedesc_order(tree):
    """Check that fileDesc children appear in the TEI-required order."""
    warnings = []
    for filedesc in tree.xpath("//tei:fileDesc", namespaces=_NS):
        children = [
            etree.QName(child).localname
            for child in filedesc
            if isinstance(child.tag, str)
        ]
        # Filter to only elements that are in our order list
        ordered_children = [c for c in children if c in _FILEDESC_ORDER]
        expected = sorted(ordered_children, key=lambda c: _FILEDESC_ORDER.index(c))
        if ordered_children != expected:
            warnings.append(
                f"fileDesc child order invalid: got {ordered_children}, "
                f"expected {expected}"
            )
    return warnings


def _check_no_imprint_in_bibl(tree):
    """Check that <imprint> does not appear directly inside <bibl>."""
    warnings = []
    for imprint in tree.xpath("//tei:bibl/tei:imprint", namespaces=_NS):
        parent = imprint.getparent()
        bibl_type = parent.get("type", "")
        warnings.append(
            f"<imprint> inside <bibl type=\"{bibl_type}\"> is invalid TEI "
            f"(only allowed inside <monogr>)"
        )
    return warnings


def _check_no_nested_ner_tags(tree):
    """Check for nested NER annotation tags (e.g. persName inside persName)."""
    warnings = []
    ner_tags = ["persName", "placeName", "orgName"]
    for tag in ner_tags:
        xpath = f"//tei:text//tei:{tag}//tei:{tag}"
        nested = tree.xpath(xpath, namespaces=_NS)
        if nested:
            warnings.append(
                f"Found {len(nested)} nested <{tag}> element(s) in <text>"
            )
    return warnings


def _check_no_empty_ner_tags(tree):
    """Check for NER tags with no text content."""
    warnings = []
    ner_tags = ["persName", "placeName", "orgName", "date"]
    for tag in ner_tags:
        for el in tree.xpath(f"//tei:text//tei:{tag}", namespaces=_NS):
            text = "".join(el.itertext()).strip()
            if not text:
                line = el.sourceline or "?"
                warnings.append(
                    f"Empty <{tag}> at line {line}"
                )
    return warnings


def validate_and_log(tree_or_path, label=""):
    """
    Run validate_tei and log any warnings.

    Args:
        tree_or_path: An lxml ElementTree or file path.
        label: Optional label for log messages (e.g. filename).

    Returns:
        List of warning strings.
    """
    warnings = validate_tei(tree_or_path)
    prefix = f"{label}: " if label else ""
    if warnings:
        for w in warnings:
            logger.warning("%sValidation: %s", prefix, w)
    else:
        logger.debug("%sValidation passed", prefix)
    return warnings
