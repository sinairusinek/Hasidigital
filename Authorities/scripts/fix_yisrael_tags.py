#!/usr/bin/env python3
"""
fix_yisrael_tags.py

One-shot fix for two issues in edition XML files:

1. Remove false `<placeName>ישראל</placeName>` tags — standalone "ישראל" is a collective
   name for the Jewish people, not a geographic place.  Unwraps the tag, keeping the text.

2. Add missing `ref="#H-LOC_105"` to `<placeName>א"י</placeName>` and `<placeName>א״י</placeName>`
   tags that lack a ref attribute (character mismatch prevented batch linker from matching).

Does NOT touch:
  - `<placeName ref="#H-LOC_105">ארץ ישראל</placeName>` (already correct)
  - `<placeName ref="...">א״י</placeName>` (already linked)

Usage:
    python3 Authorities/scripts/fix_yisrael_tags.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

EDITIONS_DIR = Path(__file__).parent.parent.parent / "editions" / "incoming"

# ── regex patterns ─────────────────────────────────────────────────────────────

# 1. Standalone ישראל inside <placeName> — unwrap (remove tag, keep text)
#    Matches: <placeName>ישראל</placeName>  or  <placeName type="...">ישראל</placeName>
#    Does NOT match: <placeName...>ארץ ישראל</placeName> (content differs)
RE_YISRAEL = re.compile(r'<placeName[^>]*>ישראל</placeName>')

# 2. א"י / א״י inside <placeName> WITHOUT ref attribute — add ref="#H-LOC_105"
#    Matches: <placeName>א"י</placeName>  or  <placeName>א״י</placeName>
#    Does NOT match: <placeName ref="#H-LOC_105">א״י</placeName> (already has ref)
#    The quote char can be ASCII " or Unicode ״ (U+05F4 gershayim)
RE_AY_NO_REF = re.compile(r'<placeName>(א[״"]י)</placeName>')


def fix_file(path: Path, dry_run: bool = False) -> tuple[int, int]:
    """
    Fix one XML file.  Returns (yisrael_removed, ay_linked).
    """
    text = path.read_text(encoding="utf-8")
    original = text

    # 1. Remove standalone ישראל tags
    text, n_yisrael = RE_YISRAEL.subn("ישראל", text)

    # 2. Add ref to א"י tags that lack it
    text, n_ay = RE_AY_NO_REF.subn(
        r'<placeName ref="#H-LOC_105">\1</placeName>', text
    )

    if text != original and not dry_run:
        path.write_text(text, encoding="utf-8")

    return n_yisrael, n_ay


def main() -> None:
    ap = argparse.ArgumentParser(description="Fix ישראל / א״י placeName tags")
    ap.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    args = ap.parse_args()

    xml_files = sorted(EDITIONS_DIR.glob("*.xml"))
    if not xml_files:
        print(f"No XML files found in {EDITIONS_DIR}")
        return

    total_yisrael = 0
    total_ay = 0

    for path in xml_files:
        n_y, n_a = fix_file(path, dry_run=args.dry_run)
        if n_y or n_a:
            parts = []
            if n_y:
                parts.append(f"{n_y} ישראל removed")
            if n_a:
                parts.append(f"{n_a} א\"י linked")
            print(f"  {path.name}: {', '.join(parts)}")
            total_yisrael += n_y
            total_ay += n_a

    prefix = "[dry-run] " if args.dry_run else ""
    print(f"\n{prefix}Total: {total_yisrael} ישראל tags removed, {total_ay} א\"י refs added")
    print(f"  across {len(xml_files)} XML files")


if __name__ == "__main__":
    main()
