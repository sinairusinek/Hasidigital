"""
Standalone script: apply nisba/bio nesting fix to existing _corrected.xml files.

Modifies files IN PLACE (overwrites with fixed version).
Does NOT re-call Gemini — only restores persName+placeName nesting.

Usage:
    python apply_nisba_fix.py                     # all _corrected.xml files
    python apply_nisba_fix.py path/to/file.xml    # specific file(s)
"""
import sys
from pathlib import Path
from lxml import etree

# Add repo root to path so ner_pipeline is importable
sys.path.insert(0, str(Path(__file__).parent))
from ner_pipeline.nisba_fixer import fix_nisba_nesting

INCOMING = Path(__file__).parent / "editions" / "incoming"


def apply_to_file(path: Path):
    """Returns (merge_count, error_message_or_None)."""
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(str(path), parser)
        count = fix_nisba_nesting(tree)
        if count:
            tree.write(str(path), encoding="utf-8", xml_declaration=True)
            print(f"  {count:3d} merges  →  {path.name}")
        else:
            print(f"    0 merges      {path.name}")
        return count, None
    except Exception as e:
        print(f"  ERROR         {path.name}: {e}")
        return 0, str(e)


def main():
    if len(sys.argv) > 1:
        files = [Path(p) for p in sys.argv[1:]]
    else:
        files = sorted(INCOMING.glob("*_corrected.xml"))

    print(f"Applying nisba fixer to {len(files)} file(s)...\n")
    total = 0
    errors = []
    for f in files:
        count, err = apply_to_file(f)
        total += count
        if err:
            errors.append((f.name, err))
    print(f"\nTotal merges across all files: {total}")
    if errors:
        print(f"\n⚠️  {len(errors)} file(s) had errors (skipped):")
        for name, err in errors:
            print(f"   {name}: {err}")


if __name__ == "__main__":
    main()
