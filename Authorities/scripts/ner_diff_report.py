"""
ner_diff_report.py
~~~~~~~~~~~~~~~~~~
Compare *_corrected.xml files against their raw counterparts in
editions/online/ and produce a TSV report listing every entity tag
that was added or removed between the two versions.

Useful for reviewing Gemini-corrected files before accepting them, and
for confirming that a rebuild (via rebuild_corrected.py) matches
expectations.

Output columns (tab-separated):
    file        – edition stem (no _corrected suffix or .xml)
    tag_type    – persName / placeName / orgName / date / name
    action      – added | removed
    text        – text content of the tag
    ref         – ref attribute value, or empty
    context     – ±40-character window around the tag in the raw plain text

Usage:
    python Authorities/scripts/ner_diff_report.py
    python Authorities/scripts/ner_diff_report.py --output report.tsv
    python Authorities/scripts/ner_diff_report.py --file Buzina_Denehora20251129
    python Authorities/scripts/ner_diff_report.py --summary    # entity counts only
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

try:
    from lxml import etree
    _PARSER = "lxml"
except ImportError:
    import xml.etree.ElementTree as etree  # type: ignore
    _PARSER = "stdlib"

# ── Paths ─────────────────────────────────────────────────────────────────────
_REPO     = Path(__file__).resolve().parent.parent.parent   # Hasidigital/
_INCOMING = _REPO / "editions" / "online"

# TEI entity tag names we care about
_ENTITY_TAGS = {"persName", "placeName", "orgName", "date", "name"}

# Context window (chars) around each entity occurrence
_CTX = 40


# ── XML helpers ───────────────────────────────────────────────────────────────

def _iter_entity_tags(xml_path: Path) -> list[dict]:
    """
    Extract every entity tag from *xml_path*.

    Returns a list of dicts: {tag_type, text, ref, position (int)}
    The position is a simple enumeration index (order in document), used
    for presence comparison — not a character offset.
    """
    if _PARSER == "lxml":
        tree = etree.parse(str(xml_path))
        root = tree.getroot()
        ns_map = {"tei": "http://www.tei-c.org/ns/1.0"}

        entries = []
        for el in root.iter():
            local = etree.QName(el.tag).localname if isinstance(el.tag, str) else ""
            if local in _ENTITY_TAGS:
                text = "".join(el.itertext()).strip()
                ref  = el.get("ref", "")
                entries.append({"tag_type": local, "text": text, "ref": ref})
        return entries

    else:
        # stdlib ElementTree fallback — strip namespace prefix manually
        tree = etree.parse(str(xml_path))
        root = tree.getroot()
        _RE_TAG = re.compile(r'\{[^}]*\}(.+)')

        entries = []
        for el in root.iter():
            m = _RE_TAG.match(el.tag or "")
            local = m.group(1) if m else el.tag
            if local in _ENTITY_TAGS:
                text = "".join(el.itertext()).strip()
                ref  = el.get("ref", "")
                entries.append({"tag_type": local, "text": text, "ref": ref})
        return entries


def _plain_text(xml_path: Path) -> str:
    """Extract plain text from *xml_path* (no tags)."""
    if _PARSER == "lxml":
        tree = etree.parse(str(xml_path))
        return "".join(tree.getroot().itertext())
    else:
        tree = etree.parse(str(xml_path))
        return "".join(tree.getroot().itertext())


def _context_snippet(plain: str, entity_text: str, window: int = _CTX) -> str:
    """Return the first occurrence of *entity_text* in *plain* with ±window context."""
    idx = plain.find(entity_text)
    if idx < 0:
        return ""
    start = max(0, idx - window)
    end   = min(len(plain), idx + len(entity_text) + window)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(plain) else ""
    return prefix + plain[start:end].replace("\n", " ").replace("\t", " ") + suffix


# ── Diff logic ────────────────────────────────────────────────────────────────

def _make_key(entry: dict) -> tuple:
    """Canonical comparison key: (tag_type, normalized_text, ref)."""
    return (entry["tag_type"], entry["text"].strip(), entry["ref"])


def diff_files(raw_path: Path, corrected_path: Path) -> list[dict]:
    """
    Compare entity tags between *raw_path* and *corrected_path*.

    Returns a list of row dicts suitable for CSV output.
    Entries present in raw but absent from corrected → action='removed'.
    Entries present in corrected but absent from raw  → action='added'.
    """
    raw_entries       = _iter_entity_tags(raw_path)
    corrected_entries = _iter_entity_tags(corrected_path)
    raw_plain         = _plain_text(raw_path)

    raw_keys       = {}   # key → count
    corrected_keys = {}

    for e in raw_entries:
        k = _make_key(e)
        raw_keys[k] = raw_keys.get(k, 0) + 1

    for e in corrected_entries:
        k = _make_key(e)
        corrected_keys[k] = corrected_keys.get(k, 0) + 1

    rows = []
    file_stem = raw_path.stem

    # Removed: in raw more times than in corrected (or not in corrected at all)
    for k, raw_count in raw_keys.items():
        corr_count = corrected_keys.get(k, 0)
        delta = raw_count - corr_count
        if delta > 0:
            tag_type, text, ref = k
            ctx = _context_snippet(raw_plain, text)
            for _ in range(delta):
                rows.append({
                    "file":     file_stem,
                    "tag_type": tag_type,
                    "action":   "removed",
                    "text":     text,
                    "ref":      ref,
                    "context":  ctx,
                })

    # Added: in corrected more times than in raw (or not in raw at all)
    for k, corr_count in corrected_keys.items():
        raw_count = raw_keys.get(k, 0)
        delta = corr_count - raw_count
        if delta > 0:
            tag_type, text, ref = k
            ctx = _context_snippet(raw_plain, text)
            for _ in range(delta):
                rows.append({
                    "file":     file_stem,
                    "tag_type": tag_type,
                    "action":   "added",
                    "text":     text,
                    "ref":      ref,
                    "context":  ctx,
                })

    # Sort: removed first, then added; within each group: tag_type, text
    rows.sort(key=lambda r: (r["action"] == "added", r["tag_type"], r["text"]))
    return rows


def _find_raw(corrected_path: Path) -> Path | None:
    """
    Given a *_corrected.xml path, find its raw counterpart in the same dir.

    Strategy:
    1. Strip _corrected / _gemini suffix from stem.
    2. Look for exact match in the same directory.
    """
    stem = corrected_path.stem
    for suffix in ("_corrected", "_gemini"):
        if stem.endswith(suffix):
            raw_stem = stem[: -len(suffix)]
            candidate = corrected_path.parent / f"{raw_stem}.xml"
            if candidate.exists():
                return candidate
    return None


# ── Summary ───────────────────────────────────────────────────────────────────

def _print_summary(all_rows: list[dict], corrected_files: list[Path]) -> None:
    """Print a compact per-file entity count summary."""
    from collections import defaultdict

    # Entity counts per file from the rows collected
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"raw": 0, "corrected": 0, "removed": 0, "added": 0})

    # We need to recount; track per-file tallies from raw XML directly
    for cp in corrected_files:
        raw = _find_raw(cp)
        stem = cp.stem.replace("_corrected", "").replace("_gemini", "")
        if raw:
            counts[stem]["raw"] = len(_iter_entity_tags(raw))
        counts[stem]["corrected"] = len(_iter_entity_tags(cp))

    for row in all_rows:
        file_stem = row["file"]
        counts[file_stem][row["action"]] += 1

    # Print
    header = f"{'File':<50}  {'Raw':>6}  {'Corr':>6}  {'Rmvd':>6}  {'Addd':>6}  {'Loss%':>7}"
    print(header)
    print("-" * len(header))
    for stem in sorted(counts):
        c = counts[stem]
        raw_n   = c["raw"]
        corr_n  = c["corrected"]
        removed = c["removed"]
        added   = c["added"]
        loss_pct = (removed / raw_n * 100) if raw_n else 0.0
        flag = "  ⚠" if loss_pct > 30 else ""
        print(
            f"{stem:<50}  {raw_n:>6}  {corr_n:>6}  {removed:>6}  {added:>6}  {loss_pct:>6.1f}%{flag}"
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Diff NER tags between raw and *_corrected.xml editions."
    )
    ap.add_argument(
        "--output", "-o", metavar="FILE",
        help="Write TSV to FILE instead of stdout.",
    )
    ap.add_argument(
        "--file", metavar="STEM",
        help="Diff only this file (raw stem without date or suffix, partial match ok).",
    )
    ap.add_argument(
        "--summary", action="store_true",
        help="Print a one-line-per-file entity count summary, no per-tag rows.",
    )
    ap.add_argument(
        "--removed-only", action="store_true",
        help="Only include 'removed' rows in the output.",
    )
    ap.add_argument(
        "--added-only", action="store_true",
        help="Only include 'added' rows in the output.",
    )
    args = ap.parse_args()

    if not _INCOMING.is_dir():
        print(f"ERROR: incoming dir not found: {_INCOMING}", file=sys.stderr)
        sys.exit(1)

    corrected_files = sorted(
        list(_INCOMING.glob("*_corrected.xml"))
        + list(_INCOMING.glob("*_gemini.xml"))
    )

    if args.file:
        corrected_files = [f for f in corrected_files if args.file in f.stem]
        if not corrected_files:
            print(f"No _corrected/_gemini file matching '{args.file}' found.", file=sys.stderr)
            sys.exit(1)

    all_rows: list[dict] = []
    skipped: list[str] = []

    for cp in corrected_files:
        raw = _find_raw(cp)
        if raw is None:
            skipped.append(cp.name)
            continue
        rows = diff_files(raw, cp)
        all_rows.extend(rows)

    if skipped:
        print(f"Skipped (no raw counterpart): {', '.join(skipped)}", file=sys.stderr)

    # Filter by action if requested
    if args.removed_only:
        all_rows = [r for r in all_rows if r["action"] == "removed"]
    elif args.added_only:
        all_rows = [r for r in all_rows if r["action"] == "added"]

    # Summary mode
    if args.summary:
        _print_summary(all_rows, corrected_files)
        return

    # TSV output
    fieldnames = ["file", "tag_type", "action", "text", "ref", "context"]
    if args.output:
        out_path = Path(args.output)
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"Written {len(all_rows)} rows to {out_path}")
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(all_rows)


if __name__ == "__main__":
    main()
