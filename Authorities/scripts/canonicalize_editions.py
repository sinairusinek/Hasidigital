#!/usr/bin/env python3
"""
canonicalize_editions.py
~~~~~~~~~~~~~~~~~~~~~~~~
One-time migration: rename already-processed editions in editions/incoming/ready/
(and ready/check/) to their canonical names from edition-metadata.json, and
replace "Structured_NNNN" xml:id values with "{canonical-slug}_NNNN".

Usage:
    python Authorities/scripts/canonicalize_editions.py [--dry-run]
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
METADATA_FILE = REPO_ROOT / "editions" / "edition-metadata.json"
READY_DIR = REPO_ROOT / "editions" / "incoming" / "ready"
CHECK_DIR = READY_DIR / "check"

TRANSKRIBUS_ID_FIELDS = ("Transkribus", "transkribus_id")


def load_metadata() -> list[dict]:
    with open(METADATA_FILE, encoding="utf-8") as f:
        return json.load(f)["editions"]


def build_dijest_map(metadata: list[dict]) -> dict[str, dict]:
    """Map Transkribus ID → metadata entry."""
    result = {}
    for entry in metadata:
        ids = entry.get("identifiers", {})
        for field in TRANSKRIBUS_ID_FIELDS:
            tid = ids.get(field) or entry.get(field)
            if tid:
                result[str(tid)] = entry
    return result


def slug_for(entry: dict) -> str:
    return Path(entry["xml_filename"]).stem


def migrate_file(xml_path: Path, canonical_name: str, slug: str, dry_run: bool) -> bool:
    """Rename file and replace Structured_ xml:ids. Returns True if changes made."""
    content = xml_path.read_text(encoding="utf-8")

    # Replace all Structured_NNNN occurrences (in xml:id= and in storyHead text)
    new_content = re.sub(r'Structured_(\d{4})', rf'{slug}_\1', content)

    canonical_path = xml_path.parent / canonical_name
    changed_ids = new_content != content
    changed_name = canonical_path != xml_path

    if not changed_ids and not changed_name:
        print(f"  (already canonical) {xml_path.name}")
        return False

    changes = []
    if changed_name:
        changes.append(f"rename → {canonical_name}")
    if changed_ids:
        n = len(re.findall(r'Structured_\d{4}', content))
        changes.append(f"replace {n} xml:id(s)")

    tag = "[dry-run] " if dry_run else ""
    print(f"  {tag}{xml_path.name}: {', '.join(changes)}")

    if not dry_run:
        canonical_path.write_text(new_content, encoding="utf-8")
        if changed_name:
            xml_path.unlink()
    return True


def main():
    ap = argparse.ArgumentParser(description="Canonicalize incoming edition filenames and xml:ids")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    metadata = load_metadata()

    # Build a map from current filename → (canonical_name, slug)
    # using xml_filename as-is (some entries already have the right name)
    canonical_by_name: dict[str, tuple[str, str]] = {}
    for entry in metadata:
        canonical_name = entry["xml_filename"]
        sl = slug_for(entry)
        canonical_by_name[canonical_name] = (canonical_name, sl)

    # Also map by stem (in case current file has different extension casing etc.)
    # Build a more flexible lookup: for each XML in ready/ and check/, find matching entry
    # by trying to match on Transkribus ID embedded in path or by known mapping
    KNOWN = {
        "MaasimTovim-MAIN.xml":                        "Maasim-Tovim.xml",
        "Likutim-Hadashim-Hebrewbooks_org_3671.xml":   "Likutim-Hadashim.xml",
        "Toldot_Haniflaot.xml":                        "Toldot-Haniflaot.xml",
        "Derech-Haemuna-Umaase-Rav.xml":               "Derech-Haemuna.xml",
        "SeferMaimRabim-Hebrewbooks_org_3711_(1).xml": "Maim-Rabim.xml",
        "Sva-Razon-Hebrewbooks_org_39105.xml":         "Seva-Ratzon.xml",
        "SeferPeulatHatzadikim-Hebrewbooks_org_3801.xml": "Peulat-Hatzadikim.xml",
        "עשר_קדושות.xml":                              "Eser-Kedushot.xml",
        "עשר_אורות.xml":                               "Eser-Orot.xml",
        "תפארת_חיים.xml":                              "Tiferet-Hayyim.xml",
    }

    # Build slug lookup from canonical name
    slug_by_canonical: dict[str, str] = {e["xml_filename"]: slug_for(e) for e in metadata}

    dirs = [READY_DIR] + ([CHECK_DIR] if CHECK_DIR.is_dir() else [])
    total = 0
    for d in dirs:
        xml_files = sorted(p for p in d.iterdir() if p.suffix.lower() == ".xml" and p.is_file())
        if not xml_files:
            continue
        print(f"\n{d.relative_to(REPO_ROOT)}/")
        for xml_path in xml_files:
            name = xml_path.name
            # Determine canonical name
            if name in KNOWN:
                canonical_name = KNOWN[name]
            elif name in slug_by_canonical:
                canonical_name = name  # already canonical
            else:
                print(f"  ⚠  {name}: no canonical mapping found — skipping")
                continue
            sl = slug_by_canonical.get(canonical_name)
            if not sl:
                print(f"  ⚠  {canonical_name}: no slug in metadata — skipping")
                continue
            if migrate_file(xml_path, canonical_name, sl, args.dry_run):
                total += 1

    tag = "Would rename/update" if args.dry_run else "Renamed/updated"
    print(f"\n{tag} {total} file(s).")


if __name__ == "__main__":
    main()
