#!/usr/bin/env python3
"""
Annotate currency terms in TEI XML edition files.

Finds unannotated currency terms (זהובים, רובל, טאלער, etc.) and wraps them
in ``<name type="currency">TERM</name>``.

Usage::

    python3 Authorities/scripts/annotate_currencies.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent
_AUTH_DIR = _SCRIPT_DIR.parent
_TOOL_DIR = _AUTH_DIR / "integration_tool"
sys.path.insert(0, str(_TOOL_DIR))

from config import EDITIONS_INCOMING  # noqa: E402

# ── Currency terms ───────────────────────────────────────────────────────────
# Each entry: (label, [variant1, variant2, ...])
# Sorted longest-first within each group to avoid partial matches.

CURRENCY_TERMS: list[tuple[str, list[str]]] = [
    # Gold coins / florins
    ("זהובים/זהוב", ["זהובים", "זהוב"]),
    # "Red ones" = gold coins
    ("אדומים", ["אדומים"]),
    # Dinar
    ("דינר", ["דינרים", "דינרי", "דינר"]),
    # Ruble
    ("רובל", ["רובעל", "רובל"]),
    # Prutah (small coin)
    ("פרוטה", ["פרוטות", "פרוטה"]),
    # Thaler
    ("טאלער", ["טאלער", "טהלר"]),
    # Pitak (Russian copper coin)
    ("פיטאק", ["פיטאקס", "פיטאק"]),
    # Zuz (ancient Jewish coin) — ONLY plural/Aramaic forms;
    # standalone "זוז" is almost always the verb "to move" (לזוז)
    ("זוז", ["זוזים", "זוזי", "זוזא"]),
    # Kopek
    ("קאפיקע", ["קאפיקעס", "קאפיקע"]),
    # Ducat
    ("דוקאט", ["דוקאטען", "דוקאטי", "דוקאט"]),
    # Groschen
    ("גרוש", ["גרו״ש", 'גרו"ש', "גרושל", "גרוש", "גראשן"]),
    # Rhenish guilder (already annotated in some files, but catch any missed)
    ("ריינש", ["ריינישע", "ריינש"]),
]

# Hebrew prefix particles that may precede a currency term
_HEB_PREFIXES = "בלמהוכד"

# ── Tag detection ────────────────────────────────────────────────────────────

# Matches any opening XML tag (to detect if we're inside one)
_INSIDE_TAG_RE = re.compile(r"<[^/][^>]*$")

# Tags whose content should NOT be annotated
_SKIP_TAGS = [
    "persName", "placeName", "name", "head", "fw", "idno",
]

def _build_skip_spans(text: str) -> list[tuple[int, int]]:
    """Return (start, end) spans of content inside tags we should skip."""
    spans = []
    for tag in _SKIP_TAGS:
        # Match <tag ...>...</tag> (non-greedy, handles attributes)
        pattern = re.compile(
            rf"<{tag}(?:\s[^>]*)?>.*?</{tag}>", re.DOTALL
        )
        for m in pattern.finditer(text):
            spans.append((m.start(), m.end()))
    # Also skip anything inside < ... > (tag attributes)
    for m in re.finditer(r"<[^>]+>", text):
        spans.append((m.start(), m.end()))
    return sorted(spans)


def _in_skip_span(pos: int, end: int, spans: list[tuple[int, int]]) -> bool:
    """Check if position range [pos, end) overlaps any skip span."""
    for s_start, s_end in spans:
        if s_start > end:
            break  # spans are sorted, no more overlaps possible
        if pos < s_end and end > s_start:
            return True
    return False


# ── Main annotation logic ────────────────────────────────────────────────────

def annotate_file(filepath: Path, dry_run: bool) -> list[str]:
    """Annotate currency terms in a single file. Returns list of change descriptions."""
    text = filepath.read_text(encoding="utf-8")
    changes: list[str] = []

    for label, variants in CURRENCY_TERMS:
        # Build alternation pattern for this currency group
        alt = "|".join(re.escape(v) for v in variants)
        # Match: optional Hebrew prefix + currency term
        # The prefix must be preceded by whitespace, > (end of tag), or start of line
        # The term must be followed by whitespace, < (start of tag), punctuation, or end of line
        pattern = re.compile(
            rf"(?<=[\s>])([{_HEB_PREFIXES}]?)({alt})(?=[\s<\u05be,.;:!?\-\)]|$)",
            re.MULTILINE,
        )

        # Rebuild skip spans each time (since text changes between currency groups)
        skip_spans = _build_skip_spans(text)

        # Collect matches in reverse order so replacements don't shift offsets
        matches = list(pattern.finditer(text))
        for m in reversed(matches):
            prefix = m.group(1)
            term = m.group(2)
            term_start = m.start(2)
            term_end = m.end(2)

            # Skip if inside a tag we shouldn't annotate in
            if _in_skip_span(term_start, term_end, skip_spans):
                continue

            # Build replacement
            replacement = f'<name type="currency">{term}</name>'
            if prefix:
                replacement = prefix + replacement

            full_start = m.start()
            full_end = m.end()

            # Get context for reporting
            line_start = text.rfind("\n", 0, full_start) + 1
            line_end = text.find("\n", full_end)
            if line_end == -1:
                line_end = len(text)
            line_num = text[:full_start].count("\n") + 1
            context = text[line_start:line_end].strip()[:120]

            changes.append(
                f"  Line {line_num}: {term} ({label}) → <name type=\"currency\">{term}</name>"
                f"\n    Context: {context}"
            )

            text = text[:full_start] + replacement + text[full_end:]

    if changes and not dry_run:
        filepath.write_text(text, encoding="utf-8")

    return changes


def main():
    parser = argparse.ArgumentParser(description="Annotate currency terms in edition files")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    args = parser.parse_args()

    edition_dir = Path(EDITIONS_INCOMING)
    files = sorted(
        list(edition_dir.glob("*_corrected.xml"))
        + list(edition_dir.glob("*_gemini.xml"))
    )

    total_changes = 0
    files_modified = 0

    for filepath in files:
        changes = annotate_file(filepath, args.dry_run)
        if changes:
            files_modified += 1
            total_changes += len(changes)
            prefix = "[dry-run] " if args.dry_run else ""
            print(f"\n{prefix}{filepath.name}: {len(changes)} annotation(s)")
            for c in changes:
                print(c)

    print(f"\n{'═' * 60}")
    print(f"Total: {total_changes} currency term(s) annotated in {files_modified} file(s)")
    if args.dry_run:
        print("(dry run — no changes written)")


if __name__ == "__main__":
    main()
