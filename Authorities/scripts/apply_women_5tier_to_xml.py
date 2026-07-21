#!/usr/bin/env python3
"""Write claude_new_5tier values from women-5tier-9editions-full.tsv into the
9 edition XMLs. Replaces existing women:major_character/women:minor_character
on each story's topic span with the 5-tier value.

5-tier mapping (file value -> ana tag):
    no-women           -> (omit; remove existing women:*)
    mention-only       -> women:mention_only
    minor-character    -> women:minor_character
    catalyst-character -> women:catalyst_character
    major-character    -> women:major_character

Stories with a blank 5-tier are left untouched.

Usage:
    python apply_women_5tier_to_xml.py --dry-run
    python apply_women_5tier_to_xml.py --apply
"""
from __future__ import annotations
import argparse
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TSV = REPO / "editions" / "women-5tier-9editions-full.tsv"

EDITION_XML = {
    "Adat-Zadikim": REPO / "editions/online/Adat-Zadikim.xml",
    "Khal-Hasidim": REPO / "editions/online/Khal-Hasidim.xml",
    "Khal-Kdoshim": REPO / "editions/online/Khal-Kdoshim.xml",
    "maase-zadikim": REPO / "editions/online/maase-zadikim.xml",
    "Mifalot-HaZadikim": REPO / "editions/online/Mifalot-HaZadikim.xml",
    "PeerMikdoshim": REPO / "editions/online/PeerMikdoshim.xml",
    "Shivhei-Habesht": REPO / "editions/online/Shivhei-Habesht.xml",
    "Shivhei-Harav": REPO / "editions/online/Shivhei-Harav.xml",
    "Sipurei-Zadikim": REPO / "editions/online/Sipurei-Zadikim.xml",
}

TIER_TO_TAG = {
    "no-women": None,
    "mention-only": "women:mention_only",
    "minor-character": "women:minor_character",
    "catalyst-character": "women:catalyst_character",
    "major-character": "women:major_character",
}


def find_topic_span_for_story(text: str, story_id: str):
    div_re = re.compile(rf'<div[^>]*xml:id="{re.escape(story_id)}"[^>]*>')
    m = div_re.search(text)
    if not m:
        return None
    div_start = m.end()
    nxt = re.search(r'<div[^>]*xml:id="[^"]+"[^>]*>', text[div_start:])
    div_end = div_start + (nxt.start() if nxt else len(text) - div_start)
    chunk = text[div_start:div_end]
    sp = re.search(r'<span\b[^>]*\bana="([^"]*)"[^>]*/?>', chunk)
    if not sp:
        return None
    return (div_start + sp.start(), div_start + sp.end(), sp.group(1))


def rewrite_ana(ana: str, new_women_tag: str | None) -> str:
    parts = [p.strip() for p in ana.split(";") if p.strip()]
    # remove all women:* tags
    parts = [p for p in parts if not p.startswith("women:")]
    if new_women_tag:
        parts.append(new_women_tag)
    # also drop placeholder TBD:Unknown if other content present
    if len(parts) > 1:
        parts = [p for p in parts if p != "TBD:Unknown"]
    return "; ".join(parts) if parts else "TBD:Unknown"


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    rows = list(csv.DictReader(TSV.open(encoding="utf-8"), delimiter="\t"))
    print(f"Read {len(rows)} story rows from {TSV.name}")

    file_texts: dict[Path, str] = {p: p.read_text(encoding="utf-8") for p in set(EDITION_XML.values())}
    per_story_status: dict[str, str] = {}
    tier_counts: dict[str, int] = {}
    no_span = []
    no_div = []
    unknown_edition = []

    for row in rows:
        sid = row["story_id"].strip()
        edition = row["edition"].strip()
        tier = (row.get("claude_new_5tier") or "").strip()
        if not tier:
            per_story_status[sid] = "blank-tier-skipped"
            continue
        if tier not in TIER_TO_TAG:
            per_story_status[sid] = f"unknown-tier:{tier}"
            continue
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        xml_path = EDITION_XML.get(edition)
        if not xml_path:
            unknown_edition.append((sid, edition))
            continue
        text = file_texts[xml_path]
        found = find_topic_span_for_story(text, sid)
        if not found:
            # try with stripped trailing 'B' or similar? just record
            no_div.append((sid, edition))
            continue
        s, e, ana = found
        new_ana = rewrite_ana(ana, TIER_TO_TAG[tier])
        if new_ana == ana:
            per_story_status[sid] = "unchanged"
            continue
        span_text = text[s:e]
        new_span = re.sub(r'ana="[^"]*"', f'ana="{new_ana}"', span_text, count=1)
        file_texts[xml_path] = text[:s] + new_span + text[e:]
        per_story_status[sid] = f"rewrote -> {TIER_TO_TAG[tier] or '(no women tag)'}"

    print("\n=== 5-tier distribution applied ===")
    for k, v in sorted(tier_counts.items()):
        print(f"  {k}: {v}")

    print(f"\n=== Status summary ===")
    by_status: dict[str, int] = {}
    for s in per_story_status.values():
        key = s.split(" -> ")[0]
        by_status[key] = by_status.get(key, 0) + 1
    for k, v in sorted(by_status.items()):
        print(f"  {k}: {v}")
    if no_div:
        print(f"\n  Story not found in XML ({len(no_div)}): {no_div[:10]}{'...' if len(no_div)>10 else ''}")
    if unknown_edition:
        print(f"\n  Unknown edition ({len(unknown_edition)}): {unknown_edition[:5]}")

    if args.dry_run:
        print("\nDry run — no files written.")
        return 0

    for p, text in file_texts.items():
        p.write_text(text, encoding="utf-8")
    print("\nApplied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
