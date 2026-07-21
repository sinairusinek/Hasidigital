#!/usr/bin/env python3
"""Apply pidyon tag retagging per editions/pidyon-stories-review.md.

Two operations:
1. Global merge: practice:pidyon_monetary_gift -> practice:pidyon_nefesh (in every
   span/@ana in every online + corrected XML, plus in topics TSVs). Dedup repeated
   pidyon_nefesh within the same ana value.
2. Per-story adds: ensure each story in the review has its target tag
   (pidyon_nefesh, pidyon_shvuyim, or pidyon_haben) in the topic span and in the
   topics TSV.

Usage:
    python apply_pidyon_retag.py --dry-run    # show planned changes
    python apply_pidyon_retag.py --apply      # write changes to disk
"""
from __future__ import annotations
import argparse
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# story_id -> tag to ensure-present
PER_STORY_ADDS: list[tuple[str, str]] = [
    # Group A — pidyon_nefesh (newly identified)
    ("Adat-Zadikim_0004", "pidyon_nefesh"),
    ("Adat-Zadikim_0007", "pidyon_nefesh"),
    ("Buzina-DiNehora_009", "pidyon_nefesh"),
    ("Dvarim-Yekarim_0006", "pidyon_nefesh"),
    ("Hitgalut-HaZadikim_00026", "pidyon_nefesh"),
    ("Hitgalut-HaZadikim_00032", "pidyon_nefesh"),
    ("Khal-Hasidim_0024", "pidyon_nefesh"),
    ("Khal-Hasidim_0205", "pidyon_nefesh"),
    ("Sipurei-Zadikim_0007", "pidyon_nefesh"),
    ("Khal-Hasidim_0243", "pidyon_nefesh"),
    ("Maase-Zadikim_0018", "pidyon_nefesh"),
    ("Kokhvei-Or_0026", "pidyon_nefesh"),
    ("Sefer-Moraim-Gdolim_008", "pidyon_nefesh"),
    ("Shlosha-Edrei-Zon_0022", "pidyon_nefesh"),
    ("Shlosha-Edrei-Zon_0026", "pidyon_nefesh"),
    ("Shlosha-Edrei-Zon_0032", "pidyon_nefesh"),
    ("Sipurei-Anshei-Shem_0009", "pidyon_nefesh"),
    ("Sipurei-Anshei-Shem_00016", "pidyon_nefesh"),
    ("Sipurim-Nehmadim_0008", "pidyon_nefesh"),
    # Group B — pidyon_shvuyim
    ("Buzina-DiNehora_003", "pidyon_shvuyim"),
    ("Khal-Hasidim_0075", "pidyon_shvuyim"),
    ("Shivhei-Habesht_0086", "pidyon_shvuyim"),
    ("Khal-Hasidim_0170", "pidyon_shvuyim"),
    ("Maase-Zadikim_0006", "pidyon_shvuyim"),
    ("Maasiot-veSihot-Tsadikim_0018", "pidyon_shvuyim"),
    ("Shemen-Hatov_00052", "pidyon_shvuyim"),
    ("Mifalot-HaZadikim_0022", "pidyon_shvuyim"),
    ("Sipurei-Kdoshim_0015", "pidyon_shvuyim"),
    ("Sipurei-Anshei-Shem_00015", "pidyon_shvuyim"),
    # Group C — pidyon_haben
    ("Maasyiot-Mzadikei-Yesodei-Olam_0003", "pidyon_haben"),
    ("Shivhei-Habesht_0164", "pidyon_haben"),
]

# story_id -> edition prefix; derived from id by stripping the final _NNNN
def edition_prefix(story_id: str) -> str:
    return re.sub(r"_[0-9A-Za-z]+$", "", story_id)


def find_story_xml(story_id: str, xml_files: list[Path]) -> Path | None:
    pat = re.compile(rf'xml:id="{re.escape(story_id)}"')
    for p in xml_files:
        # cheap: scan
        text = p.read_text(encoding="utf-8")
        if pat.search(text):
            return p
    return None


def collect_xml_files() -> list[Path]:
    roots = [REPO / "editions" / "online", REPO / "editions" / "corrected"]
    files: list[Path] = []
    for r in roots:
        if r.exists():
            files.extend(sorted(r.glob("*.xml")))
    return files


# ----------------------- XML ops -----------------------

ANA_ATTR_RE = re.compile(r'ana="([^"]*)"')


def dedup_and_clean_ana(value: str) -> str:
    # split on ';' or whitespace+; – normalize to '; '
    parts = [p.strip() for p in value.split(";")]
    parts = [p for p in parts if p]
    # merge monetary_gift -> nefesh
    parts = ["practice:pidyon_nefesh" if p == "practice:pidyon_monetary_gift" else p for p in parts]
    # dedup preserving order
    seen = set()
    out = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return "; ".join(out)


def global_merge_xml(text: str) -> tuple[str, int]:
    """Replace pidyon_monetary_gift -> pidyon_nefesh in every ana value, dedup."""
    changes = 0

    def repl(m: re.Match) -> str:
        nonlocal changes
        orig = m.group(1)
        if "pidyon_monetary_gift" not in orig:
            return m.group(0)
        cleaned = dedup_and_clean_ana(orig)
        if cleaned != orig:
            changes += 1
        return f'ana="{cleaned}"'

    new = ANA_ATTR_RE.sub(repl, text)
    return new, changes


def find_topic_span_for_story(text: str, story_id: str) -> tuple[int, int, str] | None:
    """Return (span_start, span_end, ana_value) for the topic span inside the story div."""
    # locate the div opening
    div_re = re.compile(rf'<div[^>]*xml:id="{re.escape(story_id)}"[^>]*>')
    m = div_re.search(text)
    if not m:
        return None
    div_start = m.end()
    # find the end: next <div ...xml:id=... at same nesting level, OR </body>
    # heuristic: find the next <div type="story" or <div xml:id= after div_start
    nxt = re.search(r'<div[^>]*xml:id="[^"]+"[^>]*>', text[div_start:])
    div_end = div_start + (nxt.start() if nxt else len(text) - div_start)
    chunk = text[div_start:div_end]
    # find first span with ana=
    sp = re.search(r'<span\b[^>]*\bana="([^"]*)"[^>]*/?>', chunk)
    if not sp:
        return None
    return (div_start + sp.start(), div_start + sp.end(), sp.group(1))


def add_tag_to_story(text: str, story_id: str, tag: str) -> tuple[str, str]:
    """Ensure 'practice:<tag>' is present in the story's topic span. Returns (new_text, status)."""
    full_tag = f"practice:{tag}"
    found = find_topic_span_for_story(text, story_id)
    if not found:
        return text, "NO_SPAN"
    s, e, ana = found
    parts = [p.strip() for p in ana.split(";") if p.strip()]
    if full_tag in parts:
        return text, "already-present"
    # Replace TBD:Unknown if it is the sole content
    if parts == ["TBD:Unknown"]:
        new_parts = [full_tag]
    else:
        new_parts = parts + [full_tag]
    # merge monetary->nefesh and dedup as a side benefit
    new_ana = dedup_and_clean_ana("; ".join(new_parts))
    span_text = text[s:e]
    new_span = re.sub(r'ana="[^"]*"', f'ana="{new_ana}"', span_text, count=1)
    return text[:s] + new_span + text[e:], "added"


# ----------------------- TSV ops -----------------------

TSV_PATHS = [
    REPO / "topics" / "data" / "10HasidicEditionsTopics.tsv",
    REPO / "topics" / "data" / "10HasidicEditionsTopics-full-tier.tsv",
]


def process_tsv(path: Path) -> tuple[list[list[str]], dict[str, int]]:
    """Return (new_rows, stats). stats: merged, added, removed_duplicates."""
    rows = list(csv.reader(path.read_text(encoding="utf-8").splitlines(), delimiter="\t"))
    header = rows[0]
    # cols: 0 div-xml:id, 1 Edition, 2 unique, 3 Story, 4 full tag, 5 top-tag, 6 sub-tag, 7 women
    idx_story = 3
    idx_full = 4
    idx_top = 5
    idx_sub = 6

    stats = {"merged": 0, "added": 0, "removed_dup": 0}

    # 1) merge monetary -> nefesh
    for r in rows[1:]:
        if len(r) > idx_full and r[idx_full] == "practice:pidyon_monetary_gift":
            r[idx_full] = "practice:pidyon_nefesh"
            r[idx_top] = "practice"
            r[idx_sub] = "pidyon_nefesh"
            stats["merged"] += 1

    # 2) dedup: same (story, full_tag)
    seen: set[tuple[str, str]] = set()
    dedup_rows = [header]
    for r in rows[1:]:
        if len(r) <= idx_full:
            dedup_rows.append(r)
            continue
        key = (r[idx_story], r[idx_full])
        if key in seen:
            stats["removed_dup"] += 1
            continue
        seen.add(key)
        dedup_rows.append(r)
    rows = dedup_rows

    # Build lookup: story -> template row (for adding new tags), and existing tags per story
    story_rows: dict[str, list[list[str]]] = {}
    for r in rows[1:]:
        if len(r) > idx_story:
            story_rows.setdefault(r[idx_story], []).append(r)

    # 3) ensure per-story adds (only for stories that already exist in the TSV — these
    # TSVs are scoped to the 9 article editions, so out-of-scope stories will be skipped)
    for story_id, tag in PER_STORY_ADDS:
        if story_id not in story_rows:
            continue
        full_tag = f"practice:{tag}"
        if any(r[idx_full] == full_tag for r in story_rows[story_id]):
            continue
        template = story_rows[story_id][0]
        new_row = list(template)
        new_row[idx_full] = full_tag
        new_row[idx_top] = "practice"
        new_row[idx_sub] = tag
        new_row[0] = ""  # additional rows leave div-xml:id blank, mirroring existing pattern
        rows.append(new_row)
        story_rows[story_id].append(new_row)
        stats["added"] += 1

    return rows, stats


# ----------------------- driver -----------------------

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    xml_files = collect_xml_files()
    print(f"Scanning {len(xml_files)} XML files (online + corrected)...")

    # XML global merge + per-story adds
    xml_changes: dict[Path, tuple[int, list[str]]] = {}  # path -> (merge_count, [story:tag status])

    # Index story -> file (first match)
    story_file: dict[str, Path] = {}
    pats = {sid: re.compile(rf'xml:id="{re.escape(sid)}"') for sid, _ in PER_STORY_ADDS}

    file_texts: dict[Path, str] = {p: p.read_text(encoding="utf-8") for p in xml_files}
    for p, text in file_texts.items():
        for sid, pat in pats.items():
            if sid not in story_file and pat.search(text):
                story_file[sid] = p

    missing = [sid for sid, _ in PER_STORY_ADDS if sid not in story_file]
    if missing:
        print(f"WARN: story IDs not found in any XML: {missing}")

    # Apply per-file
    new_texts: dict[Path, str] = {}
    for p, text in file_texts.items():
        merged_text, merge_count = global_merge_xml(text)
        statuses: list[str] = []
        for sid, tag in PER_STORY_ADDS:
            if story_file.get(sid) != p:
                continue
            merged_text, status = add_tag_to_story(merged_text, sid, tag)
            statuses.append(f"{sid}+{tag}:{status}")
        if merged_text != text:
            new_texts[p] = merged_text
            xml_changes[p] = (merge_count, statuses)

    # TSV
    tsv_changes: dict[Path, dict[str, int]] = {}
    new_tsv_rows: dict[Path, list[list[str]]] = {}
    for tp in TSV_PATHS:
        if not tp.exists():
            continue
        rows, stats = process_tsv(tp)
        new_tsv_rows[tp] = rows
        tsv_changes[tp] = stats

    # Report
    print("\n=== XML CHANGES ===")
    for p, (mc, statuses) in sorted(xml_changes.items()):
        rel = p.relative_to(REPO)
        print(f"  {rel}: monetary→nefesh dedup in {mc} ana(s); story adds: {statuses or '-'}")
    print(f"  Total XML files modified: {len(xml_changes)}")

    print("\n=== TSV CHANGES ===")
    for p, stats in tsv_changes.items():
        rel = p.relative_to(REPO)
        print(f"  {rel}: merged={stats['merged']} added={stats['added']} dedup_removed={stats['removed_dup']}")

    if args.dry_run:
        print("\nDry run — no files written.")
        return 0

    # Apply
    for p, text in new_texts.items():
        p.write_text(text, encoding="utf-8")
    for p, rows in new_tsv_rows.items():
        with p.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t", lineterminator="\n")
            w.writerows(rows)
    print("\nApplied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
