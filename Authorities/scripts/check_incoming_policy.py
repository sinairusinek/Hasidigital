#!/usr/bin/env python3
"""
check_incoming_policy.py
~~~~~~~~~~~~~~~~~~~~~~~~
Validate edition-management policy for editions/online/*.xml.

Policy:
1) No incoming filename may contain `_corrected`.
2) No incoming filename may end with a trailing date token.
3) TEI header must include:
   - fileDesc/editionStmt/edition/@n  (semantic version)
   - revisionDesc/change/@when        (last change date)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET


TEI_NS = "http://www.tei-c.org/ns/1.0"
NS = {"tei": TEI_NS}

BAD_CORRECTED = re.compile(r"_corrected\.xml$", re.IGNORECASE)
BAD_TRAILING_DATE = re.compile(r"(?:[-_]?(?:\d{8}|\d{4}-\d{1,2}-\d{1,2}))\.xml$", re.IGNORECASE)


def _validate_header(xml_file: Path) -> list[str]:
    problems: list[str] = []

    try:
        tree = ET.parse(str(xml_file))
    except Exception as exc:
        return [f"{xml_file.name}: XML parse error: {exc}"]

    root = tree.getroot()
    tei_header = root.find("tei:teiHeader", NS)
    if tei_header is None:
        return [f"{xml_file.name}: missing teiHeader"]

    edition = tei_header.find(".//tei:fileDesc/tei:editionStmt/tei:edition", NS)
    if edition is None or not (edition.get("n") or "").strip():
        problems.append(f"{xml_file.name}: missing editionStmt/edition/@n (version)")

    change = tei_header.find(".//tei:revisionDesc/tei:change", NS)
    if change is None or not (change.get("when") or "").strip():
        problems.append(f"{xml_file.name}: missing revisionDesc/change/@when (last change date)")

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent,
        help="Hasidigital repo root (defaults to auto-detected).",
    )
    args = ap.parse_args()

    repo = args.repo_root.resolve()
    incoming = repo / "editions" / "online"
    if not incoming.is_dir():
        print(f"ERROR: incoming dir not found: {incoming}", file=sys.stderr)
        return 1

    all_errors: list[str] = []

    for xml_file in sorted(incoming.glob("*.xml")):
        name = xml_file.name

        if BAD_CORRECTED.search(name):
            all_errors.append(f"{name}: filename contains _corrected")
        if BAD_TRAILING_DATE.search(name):
            all_errors.append(f"{name}: filename ends with trailing date")

        all_errors.extend(_validate_header(xml_file))

    if all_errors:
        print("FAILED: incoming policy violations detected")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print("OK: incoming policy checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
