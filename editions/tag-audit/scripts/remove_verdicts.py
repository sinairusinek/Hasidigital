#!/usr/bin/env python3
"""Remove Opus-rejected old-insert tags from the XML corpus (precision cleanup).

Reads editions/tag-audit/old-inserts-removals.tsv and deletes each
(story_id, tag) from the matching story's story-level תיוגים span in
editions/online/*.xml. The FIRST non-additive step in the pipeline, so it is
deliberately conservative:

  * It only ever removes a (story, tag) that appears in the removal TSV, which
    is built solely from llm-confirmed-verdicts.tsv (LLM inserts). RA-original
    tags are never in that file.
  * As a hard guard it loads the RA-original set (XML pairs minus every LLM
    insert, old + patched) and refuses to remove any pair found there.
  * Tags not present in a story are simply skipped (idempotent).

Usage:
  python3 remove_verdicts.py --dry-run
  python3 remove_verdicts.py --apply
"""
import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
AUDIT = REPO / "editions" / "tag-audit"
ONLINE = REPO / "editions" / "online"

REMOVALS_TSV = AUDIT / "old-inserts-removals.tsv"
OLD_VERDICTS = AUDIT / "llm-confirmed-verdicts.tsv"
PATCHED_ADDS = AUDIT / "llm-confirmed-verdicts-patched.tsv"

STORY_TAGSPAN_RE = re.compile(
    r'(<span\s+[^>]*?ana=")([^"]+)("[^>]*>)(תיוגים\*?)(</span>)', re.UNICODE)
STORY_DIV_RE = re.compile(
    r'<div\b(?=[^>]*\btype="story")(?=[^>]*\bxml:id="([^"]+)")[^>]*>', re.UNICODE)


def load_pairs(path):
    with open(path, encoding="utf-8") as f:
        return {(r["story_id"], r["tag"]) for r in csv.DictReader(f, delimiter="\t")}


def xml_pairs():
    pairs = set()
    span_re = re.compile(r'<span\s+[^>]*ana="([^"]+)"[^>]*>תיוגים\*?</span>')
    for xml in sorted(ONLINE.glob("*.xml")):
        txt = xml.read_text()
        ms = list(STORY_DIV_RE.finditer(txt))
        for i, m in enumerate(ms):
            sid = m.group(1)
            end = ms[i + 1].start() if i + 1 < len(ms) else len(txt)
            sm = span_re.search(txt[m.end():end])
            if sm:
                for t in (x.strip() for x in sm.group(1).split(";")):
                    if t:
                        pairs.add((sid, t))
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.dry_run == args.apply:
        sys.exit("Use exactly one of --dry-run or --apply")

    removals = load_pairs(REMOVALS_TSV)
    # Hard guard: RA-original = in XML but not any LLM insert.
    ra = xml_pairs() - load_pairs(OLD_VERDICTS) - load_pairs(PATCHED_ADDS)
    collision = removals & ra
    if collision:
        sys.exit(f"ABORT: {len(collision)} removals hit RA-original tags, e.g. "
                 f"{sorted(collision)[:5]}")

    by_story = defaultdict(set)
    for sid, tag in removals:
        by_story[sid].add(tag)
    print(f"Removal targets: {len(removals)} (story,tag) across {len(by_story)} stories. "
          f"RA-collision check: clean.")

    per_edition = defaultdict(int)
    per_category = defaultdict(int)
    removed = not_present = 0

    for xml_path in sorted(ONLINE.glob("*.xml")):
        txt = xml_path.read_text()
        edition = xml_path.stem
        matches = list(STORY_DIV_RE.finditer(txt))
        if not matches:
            continue
        bounds = []
        for i, m in enumerate(matches):
            sid = m.group(1)
            end = matches[i + 1].start() if i + 1 < len(matches) else len(txt)
            bounds.append((sid, m.start(), end))

        new_parts = []
        last = 0
        changed = False
        for sid, start, end in bounds:
            tags = by_story.get(sid)
            if not tags:
                continue

            def sub(mm):
                nonlocal removed, not_present, changed
                opening, ana, post, body, closing = mm.groups()
                cur = [t.strip() for t in ana.split(";") if t.strip()]
                kept = []
                for t in cur:
                    if t in tags:
                        removed += 1
                        per_edition[edition] += 1
                        per_category[t.split(":")[0]] += 1
                    else:
                        kept.append(t)
                if len(kept) != len(cur):
                    changed = True
                return opening + "; ".join(kept) + post + body + closing

            seg = txt[start:end]
            # account for tags listed for this story but absent from the span
            span_m = STORY_TAGSPAN_RE.search(seg)
            present = set()
            if span_m:
                present = {t.strip() for t in span_m.group(2).split(";") if t.strip()}
            not_present += len(tags - present)
            new_seg = STORY_TAGSPAN_RE.sub(sub, seg, count=1)
            new_parts.append(txt[last:start])
            new_parts.append(new_seg)
            last = end
        new_parts.append(txt[last:])
        new_txt = "".join(new_parts)

        if changed and args.apply:
            xml_path.write_text(new_txt)

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"\n=== Removal summary ({mode}) ===")
    print(f"Tags removed:        {removed}")
    print(f"Listed but absent:   {not_present}")
    print("\nPer edition:")
    for e in sorted(per_edition, key=lambda k: -per_edition[k]):
        print(f"  {e:34s}{per_edition[e]}")
    print("\nPer category:")
    for c in sorted(per_category, key=lambda k: -per_category[k]):
        print(f"  {c:24s}{per_category[c]}")


if __name__ == "__main__":
    main()
