#!/usr/bin/env python3
"""
normalize_edition.py — standard post-NER cleanup for an editions directory, the
step the online editions received but the freshly-NER'd incoming editions did not.
Bundles the deterministic, safe fixes so a new edition can be normalized in one run
before it enters the toponym/person pipelines and before publication.

Steps (in order):
  1. ישראל / א"י fix      — fix_yisrael_tags.fix_file: unwrap false <placeName>ישראל</placeName>,
                            add ref to א"י (so step 2 won't touch the now-linked א"י).
  2. unwrap bad NER tags  — remove persName/placeName/orgName annotations whose text is
                            empty, punctuation-only, ≤2 chars, or an xml:id leak — KEEPING
                            the inner text in the running prose. Tags carrying a `ref`
                            (already linked/curated) are never touched.

These are the classes flagged by scan_annotation_quality.py; in this corpus they are
always NER false positives (single letters, gershayim, honorific fragments like זצ/״ק,
punctuation, leaked ids), never real entities.

Usage:
    python3 Authorities/scripts/normalize_edition.py --dir editions/incoming/ready [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fix_yisrael_tags  # noqa: E402  (reuse the ישראל/א"י fixer)

ENTITY_RE = re.compile(r'<(persName|placeName|orgName)((?:\s[^>]*?)?)>([^<]*)</\1>')
_PUNCT_ONLY_RE = re.compile(r'^[\s׳״"\'.,:;!?()\[\]–—\-/\\|]*$')
_XMLID_LEAK_RE = re.compile(r'_0[0-9]')


def _is_bad(inner: str) -> bool:
    s = inner.strip()
    if _PUNCT_ONLY_RE.match(inner):       # empty or punctuation/gershayim only
        return True
    if len(s) <= 2:                       # ≤2 chars — never a real entity here
        return True
    if _XMLID_LEAK_RE.search(inner):      # leaked xml:id fragment in text
        return True
    return False


def unwrap_bad_annotations(path: Path, dry_run: bool = False) -> int:
    text = path.read_text(encoding="utf-8")
    n = 0

    def repl(m: re.Match) -> str:
        nonlocal n
        attrs, inner = m.group(2), m.group(3)
        if "ref=" in attrs:               # linked/curated — leave it alone
            return m.group(0)
        if _is_bad(inner):
            n += 1
            return inner                  # unwrap: keep the text, drop the tag
        return m.group(0)

    new = ENTITY_RE.sub(repl, text)
    if n and not dry_run:
        path.write_text(new, encoding="utf-8")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, help="Editions directory to normalize")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = sorted(Path(args.dir).glob("*.xml"))
    if not files:
        print(f"No XML files in {args.dir}", file=sys.stderr)
        sys.exit(1)

    tot_y = tot_a = tot_u = 0
    for path in files:
        n_y, n_a = fix_yisrael_tags.fix_file(path, dry_run=args.dry_run)
        n_u = unwrap_bad_annotations(path, dry_run=args.dry_run)
        if n_y or n_a or n_u:
            parts = []
            if n_y: parts.append(f"{n_y} ישראל")
            if n_a: parts.append(f"{n_a} א\"י linked")
            if n_u: parts.append(f"{n_u} bad tags unwrapped")
            print(f"  {path.name}: {', '.join(parts)}")
        tot_y += n_y; tot_a += n_a; tot_u += n_u

    prefix = "[dry-run] " if args.dry_run else ""
    print(f"\n{prefix}Totals across {len(files)} files: "
          f"{tot_y} ישראל removed, {tot_a} א\"י linked, {tot_u} bad tags unwrapped")


if __name__ == "__main__":
    main()
