#!/usr/bin/env python3
"""
migrate_incoming_editions.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
One-time migration utility for edition management policy.

Goals:
1) Move uncorrected/raw XMLs out of editions/online/ into archive.
2) Rename corrected files to canonical names (remove _corrected + trailing date).
3) Update TEI header metadata in the remaining incoming files:
   - bump edition version in <edition n="...">
   - append <change when="YYYY-MM-DD"> in <revisionDesc>

By default the script is dry-run (no writes). Use --apply to execute.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import xml.etree.ElementTree as ET


TEI_NS = "http://www.tei-c.org/ns/1.0"
NS = {"tei": TEI_NS}
ET.register_namespace("", TEI_NS)

_DERIVED_SUFFIXES = re.compile(r"_(corrected|gemini|flawed)$", re.IGNORECASE)
_TRAILING_DATE = re.compile(r"(?:[-_]?(?:\d{8}|\d{4}-\d{1,2}-\d{1,2}))$")
_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


@dataclass
class Plan:
    move_raw: list[tuple[Path, Path]]
    rename_corrected: list[tuple[Path, Path]]
    touch_headers: list[Path]


def _is_raw(xml_path: Path) -> bool:
    return xml_path.suffix.lower() == ".xml" and not _DERIVED_SUFFIXES.search(xml_path.stem)


def _canonical_stem(stem: str) -> str:
    stem = re.sub(r"_corrected$", "", stem)
    stem = re.sub(r"_gemini$", "", stem)
    stem = _TRAILING_DATE.sub("", stem)
    return stem.rstrip("-_")


def _bump_patch(version: str | None) -> str:
    if not version:
        return "1.0.0"
    m = _VERSION.match(version.strip())
    if not m:
        return "1.0.0"
    major, minor, patch = map(int, m.groups())
    return f"{major}.{minor}.{patch + 1}"


def _qname(local: str) -> str:
    return f"{{{TEI_NS}}}{local}"


def _ensure_child(parent: ET.Element, local: str) -> ET.Element:
    node = parent.find(f"tei:{local}", NS)
    if node is None:
        node = ET.SubElement(parent, _qname(local))
    return node


def _update_header(xml_path: Path, note: str, dry_run: bool) -> None:
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    tei_header = root.find("tei:teiHeader", NS)
    if tei_header is None:
        tei_header = ET.SubElement(root, _qname("teiHeader"))

    file_desc = _ensure_child(tei_header, "fileDesc")
    edition_stmt = _ensure_child(file_desc, "editionStmt")
    edition = edition_stmt.find("tei:edition", NS)
    if edition is None:
        edition = ET.SubElement(edition_stmt, _qname("edition"))
        edition.text = "Working edition"

    old_v = edition.get("n")
    new_v = _bump_patch(old_v)
    edition.set("n", new_v)

    revision_desc = tei_header.find("tei:revisionDesc", NS)
    if revision_desc is None:
        revision_desc = ET.SubElement(tei_header, _qname("revisionDesc"))

    change = ET.SubElement(revision_desc, _qname("change"))
    change.set("when", str(date.today()))
    change.text = f"{note}; version {old_v or 'none'} -> {new_v}"

    if not dry_run:
        tree.write(str(xml_path), encoding="utf-8", xml_declaration=True)


def _build_plan(incoming_dir: Path, archive_dir: Path) -> Plan:
    raws: dict[str, Path] = {}
    corrected_by_key: dict[str, list[Path]] = {}

    for xml_file in sorted(incoming_dir.glob("*.xml")):
        if xml_file.stem.endswith("_corrected"):
            key = _canonical_stem(xml_file.stem)
            corrected_by_key.setdefault(key, []).append(xml_file)
        elif _is_raw(xml_file):
            key = _canonical_stem(xml_file.stem)
            raws[key] = xml_file

    conflicts = {k: v for k, v in corrected_by_key.items() if len(v) > 1}
    if conflicts:
        lines = []
        for key, files in sorted(conflicts.items()):
            lines.append(f"{key}: {[f.name for f in files]}")
        raise RuntimeError("Conflicting corrected filenames:\n" + "\n".join(lines))

    move_raw: list[tuple[Path, Path]] = []
    rename_corrected: list[tuple[Path, Path]] = []
    touch_headers: list[Path] = []

    for key, corrected_list in sorted(corrected_by_key.items()):
        corrected = corrected_list[0]
        target = incoming_dir / f"{key}.xml"

        raw = raws.get(key)
        if raw is not None:
            move_raw.append((raw, archive_dir / raw.name))

        if corrected.resolve() != target.resolve():
            if target.exists():
                # Allowed only if this target is exactly the matching raw file,
                # which will be moved to archive in the same migration run.
                if raw is None or target.resolve() != raw.resolve():
                    raise RuntimeError(
                        f"Cannot rename {corrected.name} -> {target.name}: target exists"
                    )
            rename_corrected.append((corrected, target))
            touch_headers.append(target)
        else:
            touch_headers.append(corrected)

    return Plan(move_raw=move_raw, rename_corrected=rename_corrected, touch_headers=touch_headers)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent,
        help="Hasidigital repo root (defaults to auto-detected).",
    )
    ap.add_argument("--apply", action="store_true", help="Execute planned changes.")
    args = ap.parse_args()

    repo = args.repo_root.resolve()
    incoming = repo / "editions" / "online"
    archive_uncorrected = repo / "editions" / "archived-editions" / "uncorrected"

    if not incoming.is_dir():
        print(f"ERROR: incoming dir not found: {incoming}", file=sys.stderr)
        return 1

    try:
        plan = _build_plan(incoming, archive_uncorrected)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"{mode}: edition migration plan")
    print(f"  Raw files to archive: {len(plan.move_raw)}")
    print(f"  Corrected files to rename: {len(plan.rename_corrected)}")
    print(f"  Incoming files for header update: {len(plan.touch_headers)}")

    if not args.apply:
        for src, dst in plan.rename_corrected[:10]:
            print(f"    rename: {src.name} -> {dst.name}")
        if len(plan.rename_corrected) > 10:
            print(f"    ... ({len(plan.rename_corrected)-10} more rename operations)")
        print("No changes written. Re-run with --apply to execute.")
        return 0

    archive_uncorrected.mkdir(parents=True, exist_ok=True)

    for src, dst in plan.move_raw:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        print(f"moved raw: {src.name} -> {dst}")

    for src, dst in plan.rename_corrected:
        src.rename(dst)
        print(f"renamed: {src.name} -> {dst.name}")

    note = "Edition management migration (canonical filename + archived uncorrected source)"
    for xml_path in plan.touch_headers:
        _update_header(xml_path, note=note, dry_run=False)
        print(f"header updated: {xml_path.name}")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
