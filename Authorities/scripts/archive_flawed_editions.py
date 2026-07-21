"""
archive_flawed_editions.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Move all *_corrected.xml and *_gemini.xml files from editions/online/ to
editions/archived-editions/, appending "_flawed" before the .xml extension.

By default this is a DRY RUN — nothing is moved.
Pass --execute to actually move the files.

Usage:
    python Authorities/scripts/archive_flawed_editions.py
    python Authorities/scripts/archive_flawed_editions.py --execute
"""

import argparse
import shutil
import sys
from pathlib import Path

# Paths relative to the repository root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # Hasidigital/
_INCOMING = _REPO_ROOT / "editions" / "online"
_ARCHIVED = _REPO_ROOT / "editions" / "archived-editions"

# Suffixes that mark a "derived" file (the ones we want to archive)
_FLAWED_SUFFIXES = ("_corrected", "_gemini")


def _is_flawed(p: Path) -> bool:
    """Return True if this XML file is a *_corrected.xml or *_gemini.xml."""
    if p.suffix.lower() != ".xml":
        return False
    stem = p.stem
    return any(stem.endswith(s) for s in _FLAWED_SUFFIXES)


def _dest_name(p: Path) -> str:
    """
    Build the archived filename: insert '_flawed' before '.xml'.

    e.g.  Buzina_Denehora20251129_corrected.xml
       →  Buzina_Denehora20251129_corrected_flawed.xml
    """
    # Avoid double-suffix if the file was somehow already archived
    if p.stem.endswith("_flawed"):
        return p.name
    return f"{p.stem}_flawed{p.suffix}"


def run(execute: bool = False) -> int:
    """
    Scan _INCOMING for flawed files and (if execute=True) move them.

    Returns the number of files processed.
    """
    if not _INCOMING.is_dir():
        print(f"ERROR: incoming dir not found: {_INCOMING}", file=sys.stderr)
        return 0

    flawed = sorted(p for p in _INCOMING.iterdir() if _is_flawed(p))

    if not flawed:
        print("No *_corrected.xml or *_gemini.xml files found in incoming/.")
        return 0

    tag = "[DRY RUN]" if not execute else "[MOVING]"
    print(f"Found {len(flawed)} flawed file(s).  {'' if execute else '(pass --execute to move)'}\n")

    if execute:
        _ARCHIVED.mkdir(parents=True, exist_ok=True)

    moved = 0
    for src in flawed:
        dest_name = _dest_name(src)
        dest = _ARCHIVED / dest_name

        # Check for naming collision
        if dest.exists():
            print(f"  {tag}  SKIP  {src.name}  →  {dest_name}  (destination already exists)")
            continue

        print(f"  {tag}  {src.name}  →  archived-editions/{dest_name}")
        if execute:
            shutil.copy2(src, dest)
            src.unlink()
            moved += 1
        else:
            moved += 1

    print()
    if execute:
        print(f"Done. Moved {moved}/{len(flawed)} file(s) to archived-editions/.")
    else:
        print(f"DRY RUN complete. Would move {moved}/{len(flawed)} file(s).")
        print("Re-run with --execute to apply.")
    return moved


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Archive all *_corrected.xml and *_gemini.xml files from "
            "editions/online/ to editions/archived-editions/ with a _flawed suffix."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually move the files (default is dry-run only).",
    )
    args = parser.parse_args()
    run(execute=args.execute)


if __name__ == "__main__":
    main()
