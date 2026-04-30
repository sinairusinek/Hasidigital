"""
Scan editions/online/*.xml for annotation quality issues and write a TSV report.

Issue types detected:
  fused_entity   — Hebrew entity text with no whitespace, >6 chars, containing a
                   known honorific mid-string or matching two names run together
  short_fragment — entity text of ≤2 chars (persName, placeName, orgName)
  punct_only     — entity text containing only punctuation / geresh / gershayim
  xmlid_leak     — entity text that looks like an xml:id (contains "_00" pattern)

Output: editions/online/annotation-quality-report.tsv
"""

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

from lxml import etree

REPO_ROOT = Path(__file__).resolve().parents[2]
ONLINE_DIR = REPO_ROOT / "editions" / "online"
REPORT_PATH = ONLINE_DIR / "annotation-quality-report.tsv"

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ENTITY_TAGS = {"persName", "placeName", "orgName"}

# Mid-string honorifics that signal a fused entity
_HONORIFIC_RE = re.compile(r"(?:ר׳|הרב|רבי|מהר|מורנו|ה״ה|כ״ק|ר\")", )

# Pure-punctuation / whitespace check
_PUNCT_ONLY_RE = re.compile(r"^[\s׳״\"\'.,:;!?()–—\-/\\|]+$")

# xml:id leak: entity text contains an id-looking fragment (e.g. Hatov_00015, Yekarim_0006)
_XMLID_LEAK_RE = re.compile(r"_0[0-9]")

# Hebrew letter range for length counting
_HEB_RE = re.compile(r"[א-ת]")

FIELDNAMES = ["file", "story_id", "tag", "text", "issue_type", "line_number", "context"]


def _get_story_id(el):
    """Walk up the tree to find the nearest enclosing story div xml:id."""
    node = el
    while node is not None:
        if node.get("type") == "story":
            return node.get(f"{{{XML_NS}}}id", "")
        node = node.getparent()
    return ""


def _context(el, width=80):
    """Return ±width chars of plain text around this element."""
    parent = el.getparent()
    if parent is None:
        return ""
    full = "".join(parent.itertext())
    entity_text = "".join(el.itertext())
    idx = full.find(entity_text)
    if idx < 0:
        return full[:width * 2]
    start = max(0, idx - width)
    end = min(len(full), idx + len(entity_text) + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(full) else ""
    return prefix + full[start:end].replace("\n", " ") + suffix


def _check_entity(el, tag_local, tree_bytes):
    """Return a list of issue dicts for one entity element (may be empty)."""
    text = "".join(el.itertext()).strip()
    if not text:
        return []

    issues = []

    # ------------------------------------------------------------------
    # 1. short_fragment
    if tag_local in ENTITY_TAGS and len(text) <= 2:
        issues.append("short_fragment")

    # ------------------------------------------------------------------
    # 2. punct_only
    if _PUNCT_ONLY_RE.match(text):
        issues.append("punct_only")

    # ------------------------------------------------------------------
    # 3. xmlid_leak
    if _XMLID_LEAK_RE.search(text):
        issues.append("xmlid_leak")

    # ------------------------------------------------------------------
    # 4. fused_entity — only for persName / placeName
    # Use re.search(r'\s', text) to catch names split across lines (newlines, tabs)
    if tag_local in ("persName", "placeName") and not re.search(r"\s", text):
        heb_len = len(_HEB_RE.findall(text))
        if heb_len > 6:
            # Signal A: honorific mid-string (not at position 0, and followed by more Hebrew chars)
            m = _HONORIFIC_RE.search(text)
            if m and m.start() > 0 and m.end() < len(text) and _HEB_RE.search(text[m.end():]):
                issues.append("fused_entity")
            # Signal B: xml:id leak already caught above; skip double-report

    return issues


def scan_file(xml_path: Path):
    """Scan one XML file and return a list of row dicts."""
    rows = []

    try:
        tree = etree.parse(str(xml_path))
    except etree.XMLSyntaxError as exc:
        print(f"  XML parse error in {xml_path.name}: {exc}", file=sys.stderr)
        return rows

    # Build a line-number lookup: element → line in source
    # lxml stores sourceline on each element
    filename = xml_path.name

    for tag_local in ("persName", "placeName", "orgName", "name"):
        for el in tree.iter(f"{{{TEI_NS}}}{tag_local}"):
            # For <name> only check type=work/misc/event (skip bare <name>)
            if tag_local == "name":
                name_type = el.get("type", "")
                if name_type not in ("work", "book", "misc", "event"):
                    continue

            issues = _check_entity(el, tag_local, b"")
            if not issues:
                continue

            text = "".join(el.itertext()).strip()
            story_id = _get_story_id(el)
            line_no = el.sourceline or 0
            ctx = _context(el)

            for issue in issues:
                rows.append({
                    "file": filename,
                    "story_id": story_id,
                    "tag": tag_local,
                    "text": text,
                    "issue_type": issue,
                    "line_number": line_no,
                    "context": ctx,
                })

    return rows


def main():
    xml_files = sorted(ONLINE_DIR.glob("*.xml"))
    if not xml_files:
        print(f"No XML files found in {ONLINE_DIR}", file=sys.stderr)
        sys.exit(1)

    all_rows = []
    for xf in xml_files:
        print(f"Scanning {xf.name}…")
        rows = scan_file(xf)
        all_rows.extend(rows)

    # Write TSV
    with open(REPORT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, delimiter="\t")
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nWrote {len(all_rows)} issues to {REPORT_PATH.relative_to(REPO_ROOT)}")

    # Summary
    by_issue = defaultdict(lambda: defaultdict(int))
    for row in all_rows:
        by_issue[row["issue_type"]][row["file"]] += 1

    issue_totals = {issue: sum(counts.values()) for issue, counts in by_issue.items()}

    print("\n── Summary by issue type ──────────────────────────────")
    for issue, total in sorted(issue_totals.items(), key=lambda x: -x[1]):
        print(f"  {issue:<20} {total:>4} total")
        for fname, cnt in sorted(by_issue[issue].items(), key=lambda x: -x[1]):
            print(f"    {fname:<45} {cnt:>4}")

    print(f"\nTotal flagged annotations: {len(all_rows)}")


if __name__ == "__main__":
    main()
