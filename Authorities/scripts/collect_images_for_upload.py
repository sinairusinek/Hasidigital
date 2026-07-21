#!/usr/bin/env python3
"""
collect_images_for_upload.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Collect all canonically-named images from editions/incoming/ into a single
staging folder ready for bulk upload to the server.

Only images matching the canonical pattern {Slug}_NNNN.jpg are collected;
inner merged-subfolder images (still in Transkribus naming) are skipped.

Usage:
    python Authorities/scripts/collect_images_for_upload.py
    python Authorities/scripts/collect_images_for_upload.py --out editions/incoming/for-upload
    python Authorities/scripts/collect_images_for_upload.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INCOMING_DIR = REPO_ROOT / "editions" / "incoming"
DEFAULT_OUT = INCOMING_DIR / "for-upload"

CANONICAL_PATTERN = re.compile(r"^.+_\d{4}\.jpg$")


def collect(out_dir: Path, dry_run: bool) -> None:
    images = sorted(
        p for p in INCOMING_DIR.rglob("*.jpg")
        if CANONICAL_PATTERN.match(p.name)
        and p.parent != out_dir  # don't re-copy from staging folder itself
    )

    if not images:
        print("No canonically-named images found.")
        return

    # Count per edition slug
    by_slug: dict[str, list[Path]] = {}
    for img in images:
        slug = img.name.rsplit("_", 1)[0]
        by_slug.setdefault(slug, []).append(img)

    print(f"{'[DRY RUN] ' if dry_run else ''}Collecting {len(images)} images from {len(by_slug)} edition(s) → {out_dir.relative_to(REPO_ROOT)}\n")
    for slug, imgs in sorted(by_slug.items()):
        print(f"  {slug}: {len(imgs)}")

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        for img in images:
            shutil.copy2(img, out_dir / img.name)
        print(f"\nDone. {len(images)} files copied to {out_dir.relative_to(REPO_ROOT)}")
    else:
        print(f"\n[DRY RUN] Would copy {len(images)} files.")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Collect canonically-named images into a staging folder for upload."
    )
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="Output staging folder (default: editions/incoming/for-upload)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    collect(Path(args.out), args.dry_run)


if __name__ == "__main__":
    main()
