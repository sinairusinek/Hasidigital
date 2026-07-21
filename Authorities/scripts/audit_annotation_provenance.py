#!/usr/bin/env python3
"""
Audit annotation provenance across edition XML files.

Goal:
- identify files likely produced by Gemini-only annotation
- classify editions by available variants (raw/corrected/gemini/canonical)
- surface revisionDesc markers (gemini/dicta) for review triage

Usage:
  python Authorities/scripts/audit_annotation_provenance.py
  python Authorities/scripts/audit_annotation_provenance.py --as-tsv editions/annotation-provenance.tsv
  python Authorities/scripts/audit_annotation_provenance.py --include-archived
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from lxml import etree
except Exception:  # pragma: no cover
    import xml.etree.ElementTree as etree  # type: ignore


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INCOMING_DIR = REPO_ROOT / "editions" / "online"
ARCHIVED_DIR = REPO_ROOT / "editions" / "archived-editions"
TEI_NS = "http://www.tei-c.org/ns/1.0"

NER_TAGS = {"persName", "placeName", "orgName", "date", "name"}


@dataclass
class FileAudit:
    path: Path
    edition_key: str
    variant: str  # raw|corrected|gemini|corrected_flawed|gemini_flawed|canonical
    ner_count: int
    has_gemini_marker: bool
    has_dicta_marker: bool
    has_ner_marker: bool


def detect_variant(path: Path) -> tuple[str, str]:
    stem = path.stem
    if stem.endswith("_corrected_flawed"):
        return stem[: -len("_corrected_flawed")], "corrected_flawed"
    if stem.endswith("_gemini_flawed"):
        return stem[: -len("_gemini_flawed")], "gemini_flawed"
    if stem.endswith("_corrected"):
        return stem[: -len("_corrected")], "corrected"
    if stem.endswith("_gemini"):
        return stem[: -len("_gemini")], "gemini"
    return stem, "canonical"


def iter_revision_text(root) -> str:
    parts: list[str] = []

    try:
        changes = root.findall(f".//{{{TEI_NS}}}revisionDesc/{{{TEI_NS}}}change")
        for ch in changes:
            parts.append("".join(ch.itertext()))
    except Exception:
        pass

    return "\n".join(parts).lower()


def count_ner_tags(root) -> int:
    count = 0
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if "}" in el.tag:
            local = el.tag.split("}", 1)[1]
        else:
            local = el.tag
        if local in NER_TAGS:
            count += 1
    return count


def inspect_file(path: Path) -> FileAudit | None:
    try:
        tree = etree.parse(str(path))
        root = tree.getroot()
    except Exception:
        return None

    edition_key, variant = detect_variant(path)
    rev_text = iter_revision_text(root)

    has_gemini_marker = bool(re.search(r"\bgemini\b|google\s*ai", rev_text))
    has_dicta_marker = bool(re.search(r"\bdicta\b|dictabert", rev_text))
    has_ner_marker = bool(re.search(r"\bner\b|annotation", rev_text))

    return FileAudit(
        path=path,
        edition_key=edition_key,
        variant=variant,
        ner_count=count_ner_tags(root),
        has_gemini_marker=has_gemini_marker,
        has_dicta_marker=has_dicta_marker,
        has_ner_marker=has_ner_marker,
    )


def collect_files(include_archived: bool) -> Iterable[Path]:
    if INCOMING_DIR.exists():
        yield from sorted(INCOMING_DIR.glob("*.xml"))
    if include_archived and ARCHIVED_DIR.exists():
        yield from sorted(ARCHIVED_DIR.glob("*.xml"))


def is_likely_gemini_only(audits: list[FileAudit]) -> bool:
    variants = {a.variant for a in audits}
    has_gemini_variant = bool(variants & {"gemini", "gemini_flawed"})
    has_corrected_variant = bool(variants & {"corrected", "corrected_flawed"})

    if has_gemini_variant and not has_corrected_variant:
        return True

    # Canonicalized naming fallback: only canonical file with Gemini marker
    # and no Dicta marker visible in revisionDesc.
    canon = [a for a in audits if a.variant == "canonical"]
    if len(canon) == 1:
        a = canon[0]
        if a.has_gemini_marker and not a.has_dicta_marker:
            return True

    return False


def write_tsv(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "edition",
                "likely_gemini_only",
                "variants",
                "files",
                "ner_counts",
                "has_gemini_variant",
                "has_gemini_marker",
                "has_dicta_marker",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit annotation provenance for editions")
    ap.add_argument(
        "--include-archived",
        action="store_true",
        help="Also scan editions/archived-editions/*.xml",
    )
    ap.add_argument(
        "--as-tsv",
        metavar="FILE",
        help="Write detailed TSV report",
    )
    args = ap.parse_args()

    audits: list[FileAudit] = []
    for p in collect_files(include_archived=args.include_archived):
        rec = inspect_file(p)
        if rec is not None:
            audits.append(rec)

    grouped: dict[str, list[FileAudit]] = {}
    for a in audits:
        grouped.setdefault(a.edition_key, []).append(a)

    rows: list[dict] = []
    gemini_only_editions: list[str] = []
    gemini_variant_editions: list[str] = []

    for edition in sorted(grouped):
        bucket = grouped[edition]
        variants = sorted({a.variant for a in bucket})
        has_gemini_variant = bool({"gemini", "gemini_flawed"} & set(variants))
        likely = is_likely_gemini_only(bucket)

        if has_gemini_variant:
            gemini_variant_editions.append(edition)
        if likely:
            gemini_only_editions.append(edition)

        row = {
            "edition": edition,
            "likely_gemini_only": "yes" if likely else "no",
            "variants": ",".join(variants),
            "files": "; ".join(str(a.path.relative_to(REPO_ROOT)) for a in bucket),
            "ner_counts": "; ".join(f"{a.path.name}:{a.ner_count}" for a in bucket),
            "has_gemini_variant": "yes" if has_gemini_variant else "no",
            "has_gemini_marker": "yes" if any(a.has_gemini_marker for a in bucket) else "no",
            "has_dicta_marker": "yes" if any(a.has_dicta_marker for a in bucket) else "no",
        }
        rows.append(row)

    print(f"Scanned editions: {len(grouped)}")
    print(f"Editions with Gemini-variant files: {len(gemini_variant_editions)}")
    print(f"Likely Gemini-only editions: {len(gemini_only_editions)}")
    for e in gemini_only_editions:
        print(f"  - {e}")

    if args.as_tsv:
        out_path = Path(args.as_tsv)
        if not out_path.is_absolute():
            out_path = REPO_ROOT / out_path
        write_tsv(rows, out_path)
        print(f"Report written: {out_path}")


if __name__ == "__main__":
    main()
