#!/usr/bin/env python3
"""
add_story_spans.py
~~~~~~~~~~~~~~~~~~
Add <span ana="TBD:Unknown"/> immediately after every <head type="storyHead"> in
all canonical *.xml files in editions/online/ (excludes *_corrected.xml and *.bak).

Rules applied per story <div>:
    • No <span ana=...> after the head               → insert <span ana="TBD:Unknown"/>
    • <span ana=""> or <span ana=""/> present        → update to <span ana="TBD:Unknown"/>
    • <span ana="TBD"/> already present              → normalize to <span ana="TBD:Unknown"/>
    • Placeholder + real topic span both present     → remove placeholder, keep real topics
    • <span ana="TBD:Unknown"/> already present      → leave unchanged
    • <span ana="some-real-tag..."/> present         → leave unchanged (preserve topics)

The "TBD:Unknown" marker is a placeholder; replace with real thematic tags later.

Usage:
    python Authorities/scripts/add_story_spans.py               # all canonical files
    python Authorities/scripts/add_story_spans.py --dry-run     # preview counts
    python Authorities/scripts/add_story_spans.py --file Kokhvei-Or.xml
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
_REPO     = Path(__file__).resolve().parent.parent.parent   # Hasidigital/
_INCOMING = _REPO / "editions" / "online"
_DEFAULT_TOPIC_PLACEHOLDER = "TBD:Unknown"


# ── Core transformation ────────────────────────────────────────────────────────

def _process_content(content: str) -> tuple[str, int, int]:
    """
    Apply span additions/updates to an XML file's text content.

    Returns:
        (new_content, n_inserted, n_updated)
    """
    inserted = 0
    updated  = 0

    # ── Step 0: Remove placeholder if a real topic span already follows the storyHead
    def _remove_redundant_placeholder(m: re.Match) -> str:
        nonlocal updated
        updated += 1
        return m.group(1)

    content = re.sub(
        r'(<head type="storyHead">[^<]*</head>)'
        r'\s*<span\s+ana=(?:"TBD:Unknown"|\'TBD:Unknown\'|"TBD"|\'TBD\')\s*/>'
        r'(?=\s*(?:<lb\s*/>\s*)*<span\s+ana=(?!"TBD:Unknown"|\'TBD:Unknown\'|"TBD"|\'TBD\'|""|\'\'))',
        _remove_redundant_placeholder,
        content,
    )

    # ── Step 1: Normalize legacy exact placeholder <span ana="TBD"...>
    def _normalize_legacy_tbd(m: re.Match) -> str:
        nonlocal updated
        updated += 1
        return f'{m.group(1)}{m.group(2)}{_DEFAULT_TOPIC_PLACEHOLDER}{m.group(2)}'

    content = re.sub(
        r'(<span\b[^>]*\bana=)(["\'])TBD\2',
        _normalize_legacy_tbd,
        content,
    )

    # ── Step 2: Update <span ana=""> / <span ana=""/> → placeholder
    # Matches immediately after a storyHead closing tag.
    def _upgrade_empty(m: re.Match) -> str:
        nonlocal updated
        updated += 1
        return m.group(1) + f'<span ana="{_DEFAULT_TOPIC_PLACEHOLDER}"/>'

    content = re.sub(
        r'(<head type="storyHead">[^<]*</head>)'   # head (plain-text content)
        r'\s*<span\s+ana=""\s*/>',               # followed by empty self-closing span
        _upgrade_empty,
        content,
    )
    content = re.sub(
        r'(<head type="storyHead">[^<]*</head>)'
        r'\s*<span\s+ana=""\s*>',                # followed by empty open span
        _upgrade_empty,
        content,
    )

    # ── Step 3: Insert placeholder where no span exists at all
    def _insert_span(m: re.Match) -> str:
        nonlocal inserted
        inserted += 1
        return m.group(0) + f'<span ana="{_DEFAULT_TOPIC_PLACEHOLDER}"/>'

    content = re.sub(
        r'<head type="storyHead">[^<]*</head>'
        r'(?!\s*(?:<lb\s*/>\s*)*<span\s+ana=)',     # no existing topic span after optional lb/whitespace
        _insert_span,
        content,
    )

    return content, inserted, updated


def process_file(xml_file: Path, dry_run: bool = False) -> tuple[int, int]:
    """Process one file. Returns (n_inserted, n_updated)."""
    with open(xml_file, encoding="utf-8") as fh:
        original = fh.read()

    new_content, inserted, updated = _process_content(original)

    if (inserted or updated) and not dry_run:
        with open(xml_file, "w", encoding="utf-8") as fh:
            fh.write(new_content)

    return inserted, updated


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing files.")
    parser.add_argument("--file", metavar="NAME",
                        help="Process a single file (basename or full path).")
    args = parser.parse_args()

    # Resolve target files
    if args.file:
        p = Path(args.file)
        if not p.is_absolute():
            p = _INCOMING / p
        if not p.exists():
            print(f"ERROR: '{p}' not found.", file=sys.stderr)
            sys.exit(1)
        targets = [p]
    else:
        targets = sorted(
            p for p in _INCOMING.glob("*.xml")
            if not p.name.endswith("_corrected.xml") and not p.suffix == ".bak"
        )

    if not targets:
        print("No *_corrected.xml files found.")
        return

    mode = "[DRY RUN] " if args.dry_run else ""
    print(f"{mode}Processing {len(targets)} file(s)...\n")

    total_inserted = 0
    total_updated  = 0

    for xml_file in targets:
        inserted, updated = process_file(xml_file, dry_run=args.dry_run)
        total_inserted += inserted
        total_updated  += updated
        if inserted or updated:
            parts = []
            if inserted:
                parts.append(f"{inserted} inserted")
            if updated:
                parts.append(f"{updated} updated/cleaned")
            print(f"  {xml_file.name}: {', '.join(parts)}")
        else:
            print(f"  {xml_file.name}: no changes needed")

    print()
    print("=" * 60)
    if args.dry_run:
        print(f"DRY RUN — would insert {total_inserted} span(s), update/clean {total_updated} span(s).")
    else:
        print(
            f"Done. Inserted {total_inserted} span(s), "
            f"updated/cleaned {total_updated} span(s)."
        )


if __name__ == "__main__":
    main()
