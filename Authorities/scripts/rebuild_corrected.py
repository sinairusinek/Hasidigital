#!/usr/bin/env python3
"""
rebuild_corrected.py
~~~~~~~~~~~~~~~~~~~~
Create fresh *_corrected.xml files from the raw annotated XMLs in
editions/online/, applying all safe post-processing steps WITHOUT
running Gemini correction.

Steps applied (in order):
  1.  Copy raw  →  {stem}_corrected.xml
  2.  Remove <facsimile> element blocks
  3.  Nisba-fix (persName+placeName nesting repair)
  4.  Fix ישראל / א״י placeName tags
  5.  Batch-link unlinked <placeName> to authority refs
  6.  Annotate currency terms
  7.  Add <head type="storyHead"> to every story div
    8.  Add <span ana="TBD:Unknown"/> after every storyHead (topic placeholder)
  9.  Fix TEI namespace declarations  (MUST be the last XML write)

Usage:
    python Authorities/scripts/rebuild_corrected.py
    python Authorities/scripts/rebuild_corrected.py --dry-run
    python Authorities/scripts/rebuild_corrected.py --file Buzina_Denehora20251129.xml
    python Authorities/scripts/rebuild_corrected.py --all   # rebuild even existing _corrected

Safety:
    By default the script skips any raw file that already has a
    _corrected.xml partner.  Pass --all to force-rebuild all files.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
_REPO     = Path(__file__).resolve().parent.parent.parent   # Hasidigital/
_INCOMING = _REPO / "editions" / "online"
_SCRIPTS  = _REPO / "Authorities" / "scripts"
_PYTHON   = sys.executable   # re-use the same interpreter / venv

# ── Helpers ───────────────────────────────────────────────────────────────────
_DERIVED_SUFFIXES = re.compile(r'_(corrected|gemini|flawed)$', re.IGNORECASE)


def _is_raw(p: Path) -> bool:
    """True for *.xml files whose stem does NOT carry a derived suffix."""
    return p.suffix.lower() == ".xml" and not _DERIVED_SUFFIXES.search(p.stem)


def _corrected_path(raw: Path) -> Path:
    return raw.parent / f"{raw.stem}_corrected{raw.suffix}"


def _run(cmd: list[str], dry_run: bool, label: str) -> bool:
    """Run a subprocess command; in dry_run only print it. Returns success."""
    pretty = " ".join(str(c) for c in cmd)
    if dry_run:
        print(f"  [dry-run] {label}: {pretty}")
        return True
    print(f"  {label} …")
    result = subprocess.run(cmd, cwd=str(_REPO))
    if result.returncode != 0:
        print(f"  ⚠  {label} exited with code {result.returncode}", file=sys.stderr)
        return False
    return True


# ── Step implementations ───────────────────────────────────────────────────────

def step_copy(raw_files: list[Path], dry_run: bool) -> list[Path]:
    """
    Phase 1 – Copy raw → _corrected.

    Returns the list of _corrected paths that were actually created
    (or would be created in dry-run mode).
    """
    created: list[Path] = []
    for raw in raw_files:
        dest = _corrected_path(raw)
        if dry_run:
            print(f"  [dry-run] copy  {raw.name}  →  {dest.name}")
            created.append(dest)
        else:
            shutil.copy2(raw, dest)
            print(f"  Copied  {raw.name}  →  {dest.name}")
            created.append(dest)
    return created


def step_remove_facsimiles(corrected_files: list[Path], dry_run: bool) -> None:
    """Phase 2 – Remove <facsimile> element blocks from all corrected files."""
    from lxml import etree
    
    _TEI = "http://www.tei-c.org/ns/1.0"
    total = 0
    
    for f in corrected_files:
        try:
            tree = etree.parse(str(f))
            root = tree.getroot()
            facsimiles = root.findall(f".//{{{_TEI}}}facsimile")
            
            for facs in facsimiles:
                parent = facs.getparent()
                if parent is not None:
                    parent.remove(facs)
            
            if len(facsimiles) > 0:
                if not dry_run:
                    tree.write(str(f), encoding='utf-8', xml_declaration=True)
                    print(f"  {f.name}: removed {len(facsimiles)} <facsimile> element(s)")
                    total += len(facsimiles)
                else:
                    print(f"  [dry-run] {f.name}: would remove {len(facsimiles)} <facsimile> element(s)")
                    total += len(facsimiles)
        except Exception as e:
            print(f"  ⚠  {f.name}: error removing facsimiles - {e}", file=sys.stderr)
    
    if total > 0 or dry_run:
        print(f"  Total: {total} <facsimile> element(s)")


def step_nisba_fix(corrected_files: list[Path], dry_run: bool) -> None:
    """Phase 3 – Nisba-fix each new _corrected file individually."""
    for f in corrected_files:
        _run(
            [_PYTHON, "-m", "ner_pipeline.cli",
             "--input", str(f),
             "--nisba-fix"],
            dry_run,
            label=f"nisba-fix {f.name}",
        )


def step_yisrael_fix(dry_run: bool) -> None:
    """Phase 4 – Fix ישראל / א״י placeName tags across all *.xml in incoming/."""
    args = [_PYTHON, str(_SCRIPTS / "fix_yisrael_tags.py")]
    if dry_run:
        args.append("--dry-run")
    _run(args, dry_run=False, label="fix_yisrael_tags")


def step_batch_link(dry_run: bool) -> None:
    """Phase 5 – Link unlinked <placeName> to authority refs."""
    args = [_PYTHON, str(_SCRIPTS / "batch_link_places.py")]
    if dry_run:
        args.append("--dry-run")
    _run(args, dry_run=False, label="batch_link_places")


def step_currencies(dry_run: bool) -> None:
    """Phase 6 – Annotate currency terms in all *_corrected.xml files."""
    args = [_PYTHON, str(_SCRIPTS / "annotate_currencies.py")]
    if dry_run:
        args.append("--dry-run")
    _run(args, dry_run=False, label="annotate_currencies")


# ── Steps 6 & 7: story heads + namespace fix (inlined, no config.py needed) ──

_TEI_NS  = "http://www.tei-c.org/ns/1.0"
_TEI_URI = _TEI_NS
_T       = f"{{{_TEI_NS}}}"
_X       = "{http://www.w3.org/XML/1998/namespace}"

import xml.etree.ElementTree as ET


def _ensure_story_heads_one(xml_file: Path, dry_run: bool) -> int:
    """Add <head type="storyHead"> to story divs that lack one. Returns count."""
    ET.register_namespace("", _TEI_NS)
    ET.register_namespace("xml", "http://www.w3.org/XML/1998/namespace")
    tree = ET.parse(str(xml_file))
    root = tree.getroot()
    added = 0

    for div in root.findall(f".//{_T}div"):
        if div.get("type") != "story":
            continue
        xml_id = div.get(f"{_X}id")
        if not xml_id:
            continue
        has_head = any(h.get("type") == "storyHead" for h in div.findall(f"{_T}head"))
        if has_head:
            continue

        head = ET.Element(f"{_T}head")
        head.set("type", "storyHead")
        head.text = xml_id
        head.tail = "\n"
        div.insert(0, head)
        added += 1

    if added and not dry_run:
        tree.write(str(xml_file), encoding="unicode", xml_declaration=True)
    return added


def step_story_heads(dry_run: bool) -> None:
    """Phase 6 – Ensure every story div has a storyHead."""
    total = 0
    for xml_file in sorted(_INCOMING.glob("*_corrected.xml")):
        n = _ensure_story_heads_one(xml_file, dry_run)
        if n:
            tag = "[dry-run] " if dry_run else ""
            print(f"  {tag}Added {n} storyHead(s) in {xml_file.name}")
            total += n
    if not total:
        print("  All story divs already have storyHead.")


def step_story_spans(dry_run: bool) -> None:
    """Phase 8 – Add <span ana="TBD:Unknown"/> after every storyHead (topic placeholder)."""
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("add_story_spans", _SCRIPTS / "add_story_spans.py")
    _mod  = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    _process_span_file = _mod.process_file
    total_ins = 0
    total_upd = 0
    for xml_file in sorted(_INCOMING.glob("*_corrected.xml")):
        inserted, updated = _process_span_file(xml_file, dry_run=dry_run)
        total_ins += inserted
        total_upd += updated
        if inserted or updated:
            parts = []
            if inserted:
                parts.append(f"{inserted} inserted")
            if updated:
                parts.append(f"{updated} updated")
            tag = "[dry-run] " if dry_run else ""
            print(f"  {tag}{xml_file.name}: {', '.join(parts)}")
    if not (total_ins or total_upd):
        print("  All story spans already present.")
    else:
        tag = "[dry-run] " if dry_run else ""
        print(f"  {tag}Total: {total_ins} inserted, {total_upd} updated/cleaned")


def step_fix_namespaces(dry_run: bool) -> None:
    """Phase 9 – Fix TEI namespace declarations (MUST be last XML write)."""
    modified = 0
    for xml_file in sorted(_INCOMING.glob("*_corrected.xml")):
        content = xml_file.read_text(encoding="utf-8")
        if f'<tei:TEI xmlns:tei="{_TEI_URI}">' in content:
            continue   # already correct — idempotent skip

        original = content
        content = content.replace(
            f'<TEI xmlns="{_TEI_URI}">',
            f'<tei:TEI xmlns:tei="{_TEI_URI}">',
        )
        content = re.sub(
            r'<teiHeader(?!\s+xmlns)',
            f'<teiHeader xmlns="{_TEI_URI}"',
            content, count=1,
        )
        content = re.sub(
            r'<text(?=\s*>)',
            f'<text xmlns="{_TEI_URI}"',
            content, count=1,
        )
        content = content.replace("</TEI>", "</tei:TEI>")

        if content == original:
            continue
        tag = "[dry-run] " if dry_run else ""
        print(f"  {tag}Fixed namespaces in {xml_file.name}")
        if not dry_run:
            xml_file.write_text(content, encoding="utf-8")
        modified += 1

    if not modified:
        print("  All corrected editions already have correct namespaces.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Rebuild *_corrected.xml files from raw XMLs without Gemini correction."
        )
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Report what would be done without writing any files.",
    )
    ap.add_argument(
        "--file", metavar="RAW_NAME",
        help="Rebuild only for this raw file (basename, e.g. Buzina_Denehora20251129.xml).",
    )
    ap.add_argument(
        "--all", dest="force_all", action="store_true",
        help="Rebuild even files that already have a _corrected counterpart.",
    )
    args = ap.parse_args()

    if not _INCOMING.is_dir():
        print(f"ERROR: incoming dir not found: {_INCOMING}", file=sys.stderr)
        sys.exit(1)

    # ── Collect eligible raw files ────────────────────────────────────────
    all_raw = sorted(p for p in _INCOMING.iterdir() if _is_raw(p))
    if args.file:
        target = Path(args.file).name   # strip any directory prefix
        all_raw = [p for p in all_raw if p.name == target]
        if not all_raw:
            print(f"ERROR: '{target}' not found as a raw XML in {_INCOMING}", file=sys.stderr)
            sys.exit(1)

    if args.force_all:
        to_rebuild = all_raw
    else:
        to_rebuild = [p for p in all_raw if not _corrected_path(p).exists()]

    if not to_rebuild:
        print("No raw XML files need rebuilding (all have _corrected partners).")
        print("Use --all to force a full rebuild.")
        return

    mode = "DRY RUN — " if args.dry_run else ""
    print(f"{mode}Rebuilding {len(to_rebuild)} file(s) from raw XMLs.\n")
    for f in to_rebuild:
        print(f"  {f.name}")
    print()

    dry = args.dry_run

    # ── Phase 1: copy ──────────────────────────────────────────────────────
    print("Phase 1: Copying raw → _corrected …")
    new_corrected = step_copy(to_rebuild, dry)
    print()

    # ── Phase 2: remove facsimiles ─────────────────────────────────────────
    print("Phase 2: Removing <facsimile> elements …")
    step_remove_facsimiles(new_corrected, dry)
    print()

    # ── Phase 3: nisba fix ─────────────────────────────────────────────────
    print("Phase 3: Applying nisba fix …")
    step_nisba_fix(new_corrected, dry)
    print()

    # ── Phase 4: ישראל fix ─────────────────────────────────────────────────
    print("Phase 4: Fixing ישראל / א״י tags …")
    step_yisrael_fix(dry)
    print()

    # ── Phase 5: batch-link places ─────────────────────────────────────────
    print("Phase 5: Batch-linking place names …")
    step_batch_link(dry)
    print()

    # ── Phase 6: currencies ────────────────────────────────────────────────
    print("Phase 6: Annotating currency terms …")
    step_currencies(dry)
    print()

    # ── Phase 7: story heads ───────────────────────────────────────────────
    print("Phase 7: Adding storyHead elements …")
    step_story_heads(dry)
    print()

    # ── Phase 8: story spans ───────────────────────────────────────────────
    print("Phase 8: Adding <span ana=\"TBD:Unknown\"/> topic placeholders …")
    step_story_spans(dry)
    print()

    # ── Phase 9: namespace fix (MUST be last) ──────────────────────────────
    print("Phase 9: Fixing TEI namespace declarations …")
    step_fix_namespaces(dry)
    print()

    # ── Summary ────────────────────────────────────────────────────────────
    print("=" * 60)
    if dry:
        print(f"DRY RUN complete. Would rebuild {len(to_rebuild)} file(s).")
    else:
        print(f"Done. Rebuilt {len(to_rebuild)} file(s).")
        print(
            "\nNext steps:\n"
            "  • Review the new _corrected files with ner_diff_report.py\n"
            "  • Run Gemini correction with --max-removal-pct 40 when ready\n"
            "    python -m ner_pipeline.cli --input editions/online/ --correct\n"
            "          --max-removal-pct 40"
        )


if __name__ == "__main__":
    main()
