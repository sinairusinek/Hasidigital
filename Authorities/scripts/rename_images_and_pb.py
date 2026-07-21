#!/usr/bin/env python3
"""
rename_images_and_pb.py
~~~~~~~~~~~~~~~~~~~~~~~~
Rename Transkribus-exported images to the project's canonical format
and update the XML facsimile references to match.

Transkribus naming → canonical naming:
  0007_p007.jpg              →  {Slug}_0007.jpg
  0005_0005_FL96809659.jpg   →  {Slug}_0005.jpg
  0036_default (1).jpg       →  {Slug}_0036.jpg

The leading 4-digit page number is PRESERVED (not renumbered by
position) so that intentionally-dropped pages leave correct gaps.

XML changes made:
  - <graphic url='0007_p007.jpg'>  →  <graphic url='{Slug}_0007.jpg'>
  - <pb facs='#facs_7'/>           →  <pb facs='{Slug}_0007.jpg'/>
  - All <facsimile> blocks removed  (now redundant)

Prerequisite: Step 00 (Metadata Registration) must be complete —
the edition must have an entry in editions/edition-metadata.json with
identifiers.Transkribus set to the DiJeSt folder ID.

Usage:
    python Authorities/scripts/rename_images_and_pb.py <dijest_id>
    python Authorities/scripts/rename_images_and_pb.py <dijest_id> --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from lxml import etree

# ── Repo paths ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
INCOMING_DIR = REPO_ROOT / "editions" / "incoming"
METADATA_FILE = REPO_ROOT / "editions" / "edition-metadata.json"

TEI_NS = "http://www.tei-c.org/ns/1.0"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_metadata() -> list[dict]:
    with open(METADATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("editions", [])


def find_entry(metadata: list[dict], dijest_id: str) -> dict | None:
    """Find the metadata entry whose Transkribus identifier matches dijest_id."""
    for entry in metadata:
        trp_id = entry.get("identifiers", {}).get("Transkribus", "")
        if str(trp_id) == str(dijest_id):
            return entry
    return None


def extract_page_number(filename: str) -> str | None:
    """Extract the leading numeric digits and zero-pad to 4 digits."""
    m = re.match(r"^(\d+)", filename)
    if not m:
        return None
    return f"{int(m.group(1)):04d}"


def find_image_folder(edition_folder: Path) -> Path | None:
    """
    Find the subfolder inside the DiJeSt folder that contains the
    exported .jpg images.  It is the first subdirectory (non-nested)
    that contains .jpg files and whose name does NOT look like a bare
    DiJeSt numeric ID (those are merged sub-documents, not the main export).
    """
    for subdir in sorted(edition_folder.iterdir()):
        if not subdir.is_dir():
            continue
        # Skip numeric-only subdirs (those are merged source documents)
        if subdir.name.isdigit():
            continue
        jpgs = list(subdir.glob("*.jpg"))
        if jpgs:
            return subdir
    return None


def find_main_xml(edition_folder: Path, image_folder: Path) -> Path | None:
    """
    The main Transkribus XML is the .xml file whose stem equals the
    image folder name, located as a sibling of the image folder inside
    the DiJeSt folder.
    """
    candidate = edition_folder / (image_folder.name + ".xml")
    if candidate.exists():
        return candidate
    # Fallback: any .xml at the edition_folder root that isn't mets/metadata
    for p in edition_folder.glob("*.xml"):
        if p.name not in ("mets.xml", "metadata.xml"):
            return p
    return None


# ── Core logic ────────────────────────────────────────────────────────────────

def build_rename_map(image_folder: Path, slug: str) -> dict[str, str]:
    """
    Returns {old_filename: new_filename} for every .jpg in image_folder.
    Files whose names don't start with digits are warned about but skipped.
    """
    rename_map: dict[str, str] = {}
    skipped: list[str] = []

    for img in sorted(image_folder.glob("*.jpg")):
        page = extract_page_number(img.name)
        if page is None:
            skipped.append(img.name)
            continue
        new_name = f"{slug}_{page}.jpg"
        rename_map[img.name] = new_name

    if skipped:
        print(f"  ⚠  Could not extract page number from {len(skipped)} file(s) — skipped:")
        for s in skipped:
            print(f"       {s}")

    return rename_map


def build_rename_map_from_xml(xml_path: Path, slug: str) -> dict[str, str]:
    """
    Build {old_filename: new_filename} by reading <graphic url> values from
    the XML itself.  Used in --xml-only mode when images are already renamed
    on disk but the XML still has original Transkribus filenames.
    """
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(str(xml_path), parser)
    root = tree.getroot()
    rename_map: dict[str, str] = {}
    skipped: list[str] = []
    for graphic in root.iter(f"{{{TEI_NS}}}graphic"):
        old_url = graphic.get("url", "")
        old_name = Path(old_url).name
        if not old_name.endswith(".jpg"):
            continue
        page = extract_page_number(old_name)
        if page is None:
            skipped.append(old_name)
            continue
        new_name = f"{slug}_{page}.jpg"
        if old_name != new_name:
            rename_map[old_name] = new_name
    if skipped:
        print(f"  ⚠  Could not extract page number from {len(skipped)} graphic url(s) — skipped:")
        for s in skipped:
            print(f"       {s}")
    return rename_map


def update_xml(xml_path: Path, rename_map: dict[str, str], slug: str, dry_run: bool) -> int:
    """
    Parse the Transkribus XML, update graphic urls, flatten pb facs
    references, remove facsimile blocks.  Returns count of pb elements
    updated.
    """
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(str(xml_path), parser)
    root = tree.getroot()

    # Namespace-aware element search helper
    def find_all(tag):
        return root.iter(f"{{{TEI_NS}}}{tag}")

    # 1. Build facs_id → new_filename mapping from <facsimile> blocks
    facs_to_new: dict[str, str] = {}
    for facsimile in list(find_all("facsimile")):
        facs_id = facsimile.get("{http://www.w3.org/XML/1998/namespace}id") or facsimile.get("xml:id")
        if facs_id is None:
            continue
        graphic = facsimile.find(f".//{{{TEI_NS}}}graphic")
        if graphic is None:
            continue
        old_url = graphic.get("url", "")
        old_name = Path(old_url).name
        new_name = rename_map.get(old_name)
        if new_name:
            facs_to_new[facs_id] = new_name
            if not dry_run:
                graphic.set("url", new_name)
            else:
                print(f"  XML  graphic url: {old_name!r} → {new_name!r}")

    # 2. Update <pb facs='#facs_N'/> → <pb facs='Slug_NNNN.jpg'/>
    pb_count = 0
    for pb in find_all("pb"):
        facs_attr = pb.get("facs", "")
        if not facs_attr.startswith("#"):
            continue
        facs_id = facs_attr[1:]  # strip leading '#'
        new_name = facs_to_new.get(facs_id)
        if new_name:
            if not dry_run:
                pb.set("facs", new_name)
            else:
                print(f"  XML  pb facs: {facs_attr!r} → {new_name!r}")
            pb_count += 1
        else:
            print(f"  ⚠  pb references {facs_attr!r} but no mapping found — left unchanged")

    # 3. Remove <facsimile> blocks that are pure image references (no zone children).
    #    Facsimile elements that contain <zone> elements carry structural annotation
    #    (heading/catch-word/running-head subtypes) needed for TEI preprocessing —
    #    these must be preserved.
    if not dry_run:
        for facsimile in list(find_all("facsimile")):
            has_zones = facsimile.find(f".//{{{TEI_NS}}}zone") is not None
            if has_zones:
                continue  # keep — structural annotation data
            parent = facsimile.getparent()
            if parent is not None:
                parent.remove(facsimile)

    if not dry_run:
        tree.write(
            str(xml_path),
            encoding="UTF-8",
            xml_declaration=True,
            pretty_print=False,
        )

    return pb_count


def run(dijest_id: str, dry_run: bool, xml_only: bool = False) -> None:
    label = "[DRY RUN] " if dry_run else ""
    print(f"\n{label}rename_images_and_pb  —  DiJeSt ID: {dijest_id}")
    print("=" * 60)

    # ── 1. Load metadata ──────────────────────────────────────────
    metadata = load_metadata()
    entry = find_entry(metadata, dijest_id)
    if entry is None:
        print(
            f"\n✗  No entry found in edition-metadata.json with "
            f"identifiers.Transkribus == {dijest_id!r}\n"
            f"   Complete Step 00 (Metadata Registration) for this edition first."
        )
        sys.exit(1)

    proposed_slug = Path(entry["xml_filename"]).stem
    print(f"\nMetadata entry found: {entry.get('title_en', '?')!r}")
    print(f"Proposed slug: {proposed_slug!r}  (from xml_filename in edition-metadata.json)")

    # ── 2. Prompt for slug confirmation ───────────────────────────
    user_input = input("Press Enter to accept, or type a new slug: ").strip()
    slug = user_input if user_input else proposed_slug
    print(f"Using slug: {slug!r}")

    # ── 3. Locate image folder and XML ───────────────────────────
    edition_folder = INCOMING_DIR / dijest_id
    if not edition_folder.is_dir():
        print(f"\n✗  Folder not found: {edition_folder}")
        sys.exit(1)

    image_folder = find_image_folder(edition_folder)
    if image_folder is None:
        print(f"\n✗  No image subfolder found inside {edition_folder}")
        sys.exit(1)

    xml_path = find_main_xml(edition_folder, image_folder)
    if xml_path is None:
        print(f"\n✗  No main XML found for image folder {image_folder.name!r}")
        sys.exit(1)

    print(f"\nImage folder: {image_folder.relative_to(REPO_ROOT)}")
    print(f"XML file:     {xml_path.relative_to(REPO_ROOT)}")

    # ── 4. Build rename map ───────────────────────────────────────
    if xml_only:
        # Images are already renamed on disk; build the map from the XML's
        # existing <graphic url> values (original Transkribus names) so the
        # XML update can convert them to canonical names.
        rename_map = build_rename_map_from_xml(xml_path, slug)
        if not rename_map:
            print("\n✗  No renameable graphic urls found in XML.")
            sys.exit(1)
        print(f"\n--xml-only: {len(rename_map)} URL mappings derived from XML.")
        print("  Skipping image file renaming.")
    else:
        rename_map = build_rename_map(image_folder, slug)
        if not rename_map:
            print("\n✗  No .jpg files found in image folder.")
            sys.exit(1)

        print(f"\n{len(rename_map)} images to rename:")
        for old, new in sorted(rename_map.items()):
            print(f"  {old}  →  {new}")

        # ── 5. Confirm before proceeding (live run only) ──────────────
        if not dry_run:
            confirm = input("\nProceed with renaming? [y/N] ").strip().lower()
            if confirm != "y":
                print("Aborted.")
                sys.exit(0)

        # ── 6. Rename image files ─────────────────────────────────────
        print(f"\n{'[DRY RUN] ' if dry_run else ''}Renaming images...")
        for old_name, new_name in sorted(rename_map.items()):
            old_path = image_folder / old_name
            new_path = image_folder / new_name
            if not dry_run:
                old_path.rename(new_path)
            # (already printed in map above)

        print(f"  {'Would rename' if dry_run else 'Renamed'} {len(rename_map)} files.")

    # ── 7. Update XML ─────────────────────────────────────────────
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Updating XML: {xml_path.name}")
    pb_count = update_xml(xml_path, rename_map, slug, dry_run)
    print(f"  {'Would update' if dry_run else 'Updated'} {pb_count} <pb> element(s).")
    if not dry_run and not xml_only:
        print(f"  Removed image-only <facsimile> blocks (zone data preserved).")

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Done ✓")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Rename Transkribus-exported images and update XML pb/facs references."
    )
    parser.add_argument(
        "dijest_id",
        help="DiJeSt/Transkribus folder ID (e.g. 6452887)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without making any changes.",
    )
    parser.add_argument(
        "--xml-only",
        action="store_true",
        help=(
            "Update XML references only — skip image file renaming. "
            "Use this when images are already renamed on disk (e.g. after "
            "re-exporting a fresh XML from Transkribus to recover lost zone data)."
        ),
    )
    args = parser.parse_args()
    run(args.dijest_id, args.dry_run, args.xml_only)


if __name__ == "__main__":
    main()
