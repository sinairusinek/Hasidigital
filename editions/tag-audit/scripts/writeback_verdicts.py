#!/usr/bin/env python3
"""Write Opus-confirmed verdicts (direct + propagated) into the XML corpus.

Reads editions/tag-audit/llm-confirmed-verdicts.tsv and inserts each
(story_id, tag) pair into the matching story's story-level תיוגים span in
editions/online/*.xml. Idempotent (tags already present are skipped).

Usage:
  python3 writeback_verdicts.py --dry-run
  python3 writeback_verdicts.py --apply
"""
import argparse, csv, re, sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
AUDIT = REPO / "editions" / "tag-audit"
ONLINE = REPO / "editions" / "online"

VERDICTS_TSV = AUDIT / "llm-confirmed-verdicts.tsv"

STORY_TAGSPAN_RE = re.compile(
    r'(<span\s+[^>]*?ana=")([^"]+)("[^>]*>)(תיוגים\*?)(</span>)', re.UNICODE)
STORY_DIV_RE = re.compile(
    r'<div\b(?=[^>]*\btype="story")(?=[^>]*\bxml:id="([^"]+)")[^>]*>', re.UNICODE)


def load_verdicts(path=VERDICTS_TSV):
    by_story = defaultdict(list)  # story_id -> [tag, ...]
    with open(path) as f:
        for r in csv.DictReader(f, delimiter="\t"):
            by_story[r["story_id"]].append(r["tag"])
    return by_story


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verdicts", default=str(VERDICTS_TSV),
                    help="verdicts TSV to apply (default: llm-confirmed-verdicts.tsv)")
    args = ap.parse_args()
    if args.dry_run == args.apply:
        sys.exit("Use exactly one of --dry-run or --apply")

    verdicts = load_verdicts(args.verdicts)
    print(f"Verdicts loaded for {len(verdicts)} stories, "
          f"{sum(len(v) for v in verdicts.values())} (story,tag) inserts.")

    per_edition_inserts = defaultdict(int)
    per_edition_stories = defaultdict(int)
    per_category_inserts = defaultdict(int)
    inserts_done = 0
    inserts_skipped = 0  # already present

    for xml_path in sorted(ONLINE.glob("*.xml")):
        txt = xml_path.read_text()
        edition = xml_path.stem
        # Find stories
        matches = list(STORY_DIV_RE.finditer(txt))
        if not matches:
            continue
        bounds = []
        for i, m in enumerate(matches):
            sid = m.group(1)
            end = matches[i+1].start() if i+1 < len(matches) else len(txt)
            bounds.append((sid, m.start(), end))

        # Process each story
        new_chunks = []
        last_pos = 0
        edition_changed = False
        for sid, start, end in bounds:
            chunk = txt[start:end]
            tags_to_add = verdicts.get(sid, [])
            if not tags_to_add:
                new_chunks.append(txt[last_pos:end])
                last_pos = end
                continue

            def sub(m):
                nonlocal inserts_done, inserts_skipped, edition_changed
                opening, ana_value, post, body, closing = m.groups()
                current = [t.strip() for t in ana_value.split(";") if t.strip()]
                current_set = set(current)
                added_here = []
                for t in tags_to_add:
                    if t in current_set:
                        inserts_skipped += 1
                    else:
                        current.append(t)
                        current_set.add(t)
                        added_here.append(t)
                        inserts_done += 1
                        per_category_inserts[t.split(":")[0]] += 1
                if added_here:
                    edition_changed = True
                    per_edition_inserts[edition] += len(added_here)
                    per_edition_stories[edition] += 1
                    return opening + "; ".join(current) + post + body + closing
                return m.group(0)

            new_chunk = STORY_TAGSPAN_RE.sub(sub, chunk)
            new_chunks.append(txt[last_pos:start])
            new_chunks.append(new_chunk)
            last_pos = end

        new_chunks.append(txt[last_pos:])
        new_txt = "".join(new_chunks)

        if edition_changed and args.apply:
            xml_path.write_text(new_txt)

    print(f"\n=== Summary ({'DRY-RUN' if args.dry_run else 'APPLIED'}) ===")
    print(f"Inserts done:    {inserts_done}")
    print(f"Skipped (already present): {inserts_skipped}")
    print(f"\nPer edition:")
    for ed, n in sorted(per_edition_inserts.items(), key=lambda x: -x[1]):
        print(f"  {ed:40s} {n:>5} inserts in {per_edition_stories[ed]} stories")
    print(f"\nPer category:")
    for cat, n in sorted(per_category_inserts.items(), key=lambda x: -x[1]):
        print(f"  {cat:25s} {n:>5}")


if __name__ == "__main__":
    main()
