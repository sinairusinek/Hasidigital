#!/usr/bin/env python3
"""
Pre-NER validation for TEI XML editions.

Checks image names (pb facs), story xml:ids, and story heads
before running the NER pipeline. Auto-fixes naming issues
(missing underscore in xml:ids/storyHeads). Reports remaining
issues and optionally blocks on critical errors.

Usage:
    python Authorities/scripts/validate_pre_ner.py editions/online/Dvarim-Yekarim.xml
    python Authorities/scripts/validate_pre_ner.py editions/online/   # all files
    python Authorities/scripts/validate_pre_ner.py editions/online/ --dry-run
"""

import argparse
import re
import sys
from pathlib import Path
from lxml import etree

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"t": TEI_NS}


def validate_pb_facs(tree, filename):
    """Check pb facs attributes for consistency and naming pattern."""
    issues = []
    warnings = []
    pbs = tree.xpath("//t:pb", namespaces=NS)

    if not pbs:
        issues.append("No <pb> elements found")
        return issues, warnings

    facs_values = []
    for pb in pbs:
        facs = pb.get("facs")
        if not facs:
            issues.append(f"<pb> missing facs attribute (near line {pb.sourceline})")
            continue
        facs_values.append(facs)

    if not facs_values:
        return issues, warnings

    # Extract edition name prefixes
    prefixes = set()
    for facs in facs_values:
        m = re.match(r"^(.+?)_+\d+\.jpg$", facs)
        if m:
            prefixes.add(m.group(1))
        else:
            warnings.append(f"Unusual facs format: '{facs}'")

    if len(prefixes) > 1:
        issues.append(f"Inconsistent facs prefixes: {prefixes}")
    elif len(prefixes) == 1:
        # Check for double underscores
        for facs in facs_values:
            if "__" in facs:
                warnings.append(f"Double underscore in facs: '{facs}'")
                break
        # Check digit padding consistency
        digit_lengths = set()
        for facs in facs_values:
            m = re.search(r"_+(\d+)\.jpg$", facs)
            if m:
                digit_lengths.add(len(m.group(1)))
        if len(digit_lengths) > 1:
            warnings.append(f"Inconsistent digit padding in facs: {digit_lengths} digit lengths")

    return issues, warnings


def fix_facs_padding(tree, dry_run=False):
    """Normalize pb facs to single underscore + 4-digit zero-padded number.

    E.g. 'Name__00010.jpg' → 'Name_0010.jpg'
         'Name_000100.jpg' → 'Name_0100.jpg'

    Returns count of fixes applied.
    """
    fixed = 0
    for pb in tree.xpath("//t:pb", namespaces=NS):
        facs = pb.get("facs", "")
        m = re.match(r"^(.+?)_+0*(\d+)\.jpg$", facs)
        if not m:
            continue
        prefix = m.group(1)
        page_num = int(m.group(2))
        new_facs = f"{prefix}_{page_num:04d}.jpg"
        if new_facs != facs:
            if not dry_run:
                pb.set("facs", new_facs)
            fixed += 1
    return fixed


def fix_story_id_underscores(tree, dry_run=False):
    """Fix story xml:ids and storyHead text missing underscore before number.

    E.g. 'Dvarim-Yekarim0002' → 'Dvarim-Yekarim_0002'

    Returns count of fixes applied.
    """
    divs = tree.xpath("//t:div[@type='story']", namespaces=NS)
    fixed = 0

    for div in divs:
        xid = div.get(f"{{{XML_NS}}}id", "")
        # Match: prefix (letters/hyphens) directly followed by digits (no underscore)
        m = re.match(r"^(.+?)(\d{2,})$", xid)
        if m and not m.group(1).endswith("_"):
            new_id = m.group(1) + "_" + m.group(2)
            if not dry_run:
                div.set(f"{{{XML_NS}}}id", new_id)
            fixed += 1

            # Also fix storyHead text if it matches the old id
            for head in div.xpath("t:head[@type='storyHead']", namespaces=NS):
                if head.text and head.text.strip() == xid:
                    if not dry_run:
                        head.text = new_id

    return fixed


def validate_story_divs(tree, filename):
    """Check story divs for xml:id and head elements."""
    issues = []
    warnings = []
    divs = tree.xpath("//t:div[@type='story']", namespaces=NS)

    if not divs:
        warnings.append("No <div type='story'> elements found")
        return issues, warnings

    missing_id = []
    missing_head = []

    for i, div in enumerate(divs):
        xml_id = div.get(f"{{{XML_NS}}}id")
        heads = div.xpath("t:head", namespaces=NS)

        if not xml_id:
            first_text = "".join(div.itertext())[:60].strip()
            missing_id.append(f"Story #{i+1} ('{first_text}...')")

        if not heads:
            first_text = "".join(div.itertext())[:60].strip()
            missing_head.append(f"Story #{i+1} ('{first_text}...')")

    if missing_id:
        issues.append(f"{len(missing_id)} story div(s) missing xml:id:")
        for m in missing_id:
            issues.append(f"  - {m}")

    if missing_head:
        issues.append(f"{len(missing_head)} story div(s) missing <head>:")
        for m in missing_head:
            issues.append(f"  - {m}")

    # Check xml:id sequential pattern
    ids = []
    for div in divs:
        xml_id = div.get(f"{{{XML_NS}}}id")
        if xml_id:
            ids.append(xml_id)

    if ids:
        id_prefixes = set()
        for xid in ids:
            m = re.match(r"^(.+?)(\d+)$", xid)
            if m:
                id_prefixes.add(m.group(1))
            else:
                warnings.append(f"Non-standard xml:id format: '{xid}'")
        if len(id_prefixes) > 1:
            warnings.append(f"Multiple xml:id prefixes: {id_prefixes}")

    return issues, warnings


def validate_file(xml_path, auto_fix=False, dry_run=False):
    """Run all validations on a single XML file.

    If auto_fix is True, apply safe fixes (underscore in xml:ids)
    and write the file back (unless dry_run).
    """
    try:
        tree = etree.parse(str(xml_path))
    except etree.XMLSyntaxError as e:
        return {"errors": [f"XML parse error: {e}"], "warnings": [], "fixes": []}

    fixes = []

    # ── Auto-fixes ──────────────────────────────────────────────────────────
    if auto_fix:
        dirty = False
        tag = "[dry-run] " if dry_run else ""

        # Fix facs padding (double underscores, inconsistent digit count)
        n_facs = fix_facs_padding(tree, dry_run=dry_run)
        if n_facs:
            fixes.append(f"{tag}Fixed {n_facs} pb facs: normalized to single underscore + 4-digit padding")
            dirty = True

        # Fix story xml:ids missing underscore before number
        n_ids = fix_story_id_underscores(tree, dry_run=dry_run)
        if n_ids:
            fixes.append(f"{tag}Fixed {n_ids} story xml:id(s): added underscore before number")
            dirty = True

        if dirty and not dry_run:
            tree.write(str(xml_path), encoding="utf-8", xml_declaration=True)

    # ── Validation checks ──────────────────────────────────────────────────
    all_issues = []
    all_warnings = []

    # A. Image names
    issues, warnings = validate_pb_facs(tree, xml_path.name)
    all_issues.extend(issues)
    all_warnings.extend(warnings)

    # B+C. Story divs (xml:id + heads)
    issues, warnings = validate_story_divs(tree, xml_path.name)
    all_issues.extend(issues)
    all_warnings.extend(warnings)

    # Summary stats
    pbs = tree.xpath("//t:pb", namespaces=NS)
    divs = tree.xpath("//t:div[@type='story']", namespaces=NS)
    with_id = [d for d in divs if d.get(f"{{{XML_NS}}}id")]
    with_head = [d for d in divs if d.xpath("t:head", namespaces=NS)]

    stats = {
        "pb_count": len(pbs),
        "story_count": len(divs),
        "with_id": len(with_id),
        "with_head": len(with_head),
    }

    return {"errors": all_issues, "warnings": all_warnings, "fixes": fixes, "stats": stats}


def main():
    parser = argparse.ArgumentParser(description="Pre-NER validation for TEI XML editions.")
    parser.add_argument("input", help="XML file or directory of XMLs.")
    parser.add_argument("--strict", action="store_true",
                        help="Exit with error code if any issues found.")
    parser.add_argument("--fix", action="store_true",
                        help="Auto-fix safe issues (facs padding, underscore in xml:ids/storyHeads).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what --fix would change without writing files.")
    args = parser.parse_args()

    auto_fix = args.fix or args.dry_run

    p = Path(args.input)
    if p.is_file():
        files = [p]
    elif p.is_dir():
        files = sorted(p.glob("*.xml"))
        # Skip derived files
        files = [f for f in files if not re.search(r"_(corrected|gemini|flawed|Old|New)", f.stem)]
    else:
        print(f"Error: {args.input} not found.", file=sys.stderr)
        return 1

    has_errors = False

    for xml_path in files:
        result = validate_file(xml_path, auto_fix=auto_fix, dry_run=args.dry_run)
        stats = result.get("stats", {})

        print(f"\n{'='*60}")
        print(f"  {xml_path.name}")
        print(f"  {stats.get('pb_count', '?')} pages | "
              f"{stats.get('story_count', '?')} stories | "
              f"{stats.get('with_id', '?')} with xml:id | "
              f"{stats.get('with_head', '?')} with head")
        print(f"{'='*60}")

        if result.get("fixes"):
            print("  FIXES:")
            for f in result["fixes"]:
                print(f"    🔧 {f}")

        if result["errors"]:
            has_errors = True
            print("  ERRORS:")
            for e in result["errors"]:
                print(f"    ✗ {e}")

        if result["warnings"]:
            print("  WARNINGS:")
            for w in result["warnings"]:
                print(f"    ⚠ {w}")

        if not result["errors"] and not result["warnings"] and not result.get("fixes"):
            print("  ✓ All checks passed")

    print()
    if has_errors:
        print("RESULT: Issues found — review before running NER.")
        return 1 if args.strict else 0
    else:
        print("RESULT: All files passed validation.")
        return 0


if __name__ == "__main__":
    exit(main())
