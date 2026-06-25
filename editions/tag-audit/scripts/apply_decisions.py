#!/usr/bin/env python3
"""
Apply the tag-audit decisions to the edition XMLs in editions/online/.

Operates on `ana` attribute values on `<span>` elements, both:
  - story-level: `<span ana="...">תיוגים</span>` (semicolon-separated tag list)
  - inline:     `<span ana="...">specific text</span>`

Sources of truth:
  - editions/tag-audit/taxonomy.tsv  (column `proposed_canonical`)
  - editions/tag-audit/halakhah-bare-triage.tsv  (per-story bare-halakhah decisions)
  - editions/tag-audit/practice/adjudication-verdicts.tsv  (LLM positives, applies=true)
  - editions/tag-audit/story-duplicates.tsv  (parallel-story propagation pairs)

The script preserves whitespace by editing `ana` attribute values in place via
regex; it does not reparse and reserialize the whole XML. Only the bytes inside
the `ana="..."` quotes change (and, for fully-dropped inline spans, the span
tags are removed leaving the text content).

Usage:
  python3 apply_decisions.py --dry-run     # writes a diff summary, no XML changes
  python3 apply_decisions.py --apply       # writes XMLs in place
"""

from __future__ import annotations
import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
AUDIT = REPO / "editions" / "tag-audit"
ONLINE = REPO / "editions" / "online"

TAXONOMY_TSV = AUDIT / "taxonomy.tsv"
HALAKHAH_TRIAGE_TSV = AUDIT / "halakhah-bare-triage.tsv"
PRACTICE_VERDICTS_TSV = AUDIT / "practice" / "adjudication-verdicts.tsv"
DUPLICATES_TSV = AUDIT / "story-duplicates.tsv"


# --------------------------------------------------------------------------
# Load decisions
# --------------------------------------------------------------------------

def load_taxonomy_decisions():
    """Return (rename_map, drop_set, split_map).

    rename_map[tag] = new_tag  (covers renames + merges)
    drop_set       = {tag, ...}
    split_map[tag] = [new_tag1, new_tag2, ...]  (only for bad-sep SPLIT directives)
    """
    rename, drop, split = {}, set(), {}
    with TAXONOMY_TSV.open() as f:
        for r in csv.DictReader(f, delimiter="\t"):
            tag = r["full_tag"]
            pc = (r.get("proposed_canonical") or "").strip()
            if not pc:
                continue
            if pc == "DROP":
                drop.add(tag)
            elif pc.startswith("SPLIT:"):
                # e.g. SPLIT:experience:mystical(DROP)+appearance:shaking
                payload = pc[len("SPLIT:"):]
                parts = payload.split("+")
                resolved = []
                for p in parts:
                    p = p.strip()
                    m = re.match(r"^([^()]+?)(\(DROP\))?$", p)
                    if m and not m.group(2):
                        resolved.append(m.group(1).strip())
                split[tag] = resolved
            elif pc.startswith("TBD") or pc.startswith("SHARPEN"):
                # not a deterministic rename — skip
                continue
            else:
                rename[tag] = pc
    return rename, drop, split


def load_global_rules():
    """G1+G2: not all source tags appear in taxonomy.tsv proposed_canonical
    (some were not pre-loaded because the file is a snapshot). We hardcode
    the global rules here as a safety net. These overlap with taxonomy.tsv
    decisions; the merged map below dedups.
    """
    rename = {
        # G1: halakhah:* → practice:*
        "halakhah:prayer": "practice:prayer",
        "halakhah:tefillin": "practice:tefillin",
        "halakhah:kosher_slaughtering": "practice:ritual_slaughtering",
        "halakhah:circumcision": "practice:circumcision",
        "halakhah:tvilah": "practice:tvilah",
        # G2: profession:* → characters-and-roles:*
        "profession:melamed": "characters-and-roles:melamed",
        "profession:scribe": "characters-and-roles:scribe",
        "profession:tavern_keeper": "characters-and-roles:tavern_keeper",
        # communal-position orphan
        "communal-position:ritual_slaughterer": "characters-and-roles:ritual_slaughterer",
    }
    return rename


def load_halakhah_triage():
    """Returns {(edition, story_id): "DROP" | "practice:halakhah"}."""
    triage = {}
    with HALAKHAH_TRIAGE_TSV.open() as f:
        for r in csv.DictReader(f, delimiter="\t"):
            triage[(r["edition"], r["story_id"])] = r["decision"].strip()
    return triage


def load_practice_positives():
    """Returns {story_id: [tag, ...]} of LLM-confirmed positives (applies=true)."""
    by_story = defaultdict(list)
    with PRACTICE_VERDICTS_TSV.open() as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["applies"].strip().lower() == "true":
                by_story[r["story_id"]].append(r["tag"])
    return dict(by_story)


def load_duplicates():
    """Returns {story_id: [other_story_id, ...]} undirected adjacency."""
    adj = defaultdict(set)
    with DUPLICATES_TSV.open() as f:
        for r in csv.DictReader(f, delimiter="\t"):
            a, b = r["story_a"], r["story_b"]
            adj[a].add(b)
            adj[b].add(a)
    return {k: sorted(v) for k, v in adj.items()}


# --------------------------------------------------------------------------
# Tag-list transformation
# --------------------------------------------------------------------------

def split_tag_list(ana_value: str) -> list[str]:
    return [t.strip() for t in ana_value.split(";") if t.strip()]


def join_tag_list(tags: list[str]) -> str:
    return "; ".join(tags)


def transform_tags(
    tags: list[str],
    rename: dict,
    drop: set,
    split: dict,
    bare_halakhah_decision: str | None = None,
) -> list[str]:
    """Apply all transformations to a tag list. Returns a new deduped list
    preserving first-seen order.
    """
    out = []
    seen = set()

    def add(t: str):
        if t and t not in seen:
            out.append(t)
            seen.add(t)

    for t in tags:
        if t == "halakhah":
            # per-story decision
            if bare_halakhah_decision == "DROP":
                continue
            elif bare_halakhah_decision and bare_halakhah_decision != "DROP":
                add(bare_halakhah_decision)
            else:
                # no decision recorded — keep as-is (shouldn't happen if triage is complete)
                add(t)
            continue
        if t in drop:
            continue
        if t in split:
            for nt in split[t]:
                add(nt)
            continue
        if t in rename:
            add(rename[t])
            continue
        add(t)
    return out


# --------------------------------------------------------------------------
# XML rewrite
# --------------------------------------------------------------------------

# Match story-level תיוגים span (allow optional trailing asterisk used by Shivhei-Habesht)
STORY_TAGSPAN_RE = re.compile(
    r'(<span\s+[^>]*?ana=")([^"]+)("[^>]*>)(תיוגים\*?)(</span>)',
    re.UNICODE,
)
# Match any inline span with ana=
INLINE_ANA_RE = re.compile(
    r'(<span\s+[^>]*?ana=")([^"]+)("[^>]*>)([^<]*?)(</span>)',
    re.UNICODE,
)
# Match just the opening of a span with ana= (no body), for renaming the
# attribute on spans whose body contains nested XML (persName, etc.).
SPAN_OPEN_ANA_RE = re.compile(
    r'(<span\s+[^>]*?ana=")([^"]+)("[^>]*>)',
    re.UNICODE,
)
# Match div type="story" with xml:id (attributes in any order)
STORY_DIV_RE = re.compile(
    r'<div\b(?=[^>]*\btype="story")(?=[^>]*\bxml:id="([^"]+)")[^>]*>',
    re.UNICODE,
)


def rewrite_edition(
    xml_path: Path,
    rename: dict,
    drop: set,
    split: dict,
    halakhah_triage: dict,
    practice_positives_by_story: dict,
    duplicates: dict,
) -> tuple[str, list[dict]]:
    """Rewrite one edition XML. Returns (new_text, events) where events lists
    per-story changes for the diff summary.
    """
    edition = xml_path.stem
    txt = xml_path.read_text()

    # Build a list of stories in this edition (story_id, span [a,b)) where the
    # span is the byte range from this story's div opening tag to the next
    # story's div opening tag (or end of body).
    story_bounds = []
    matches = list(STORY_DIV_RE.finditer(txt))
    for i, m in enumerate(matches):
        story_id = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(txt)
        story_bounds.append((story_id, start, end))

    # Precompute LLM positives propagated by duplicates: a verdict targets one
    # story; propagate to every duplicate so the corpus stays internally
    # consistent.
    def positives_for(story_id: str) -> list[str]:
        pos = set(practice_positives_by_story.get(story_id, []))
        for dup in duplicates.get(story_id, []):
            pos.update(practice_positives_by_story.get(dup, []))
        return sorted(pos)

    events = []
    # Process stories last-to-first so byte offsets remain valid as we splice.
    new_parts = []
    cursor = 0
    new_txt_chunks = []
    last_pos = 0

    for story_id, start, end in story_bounds:
        chunk = txt[start:end]
        original_chunk = chunk
        ev = {
            "edition": edition,
            "story_id": story_id,
            "story_renames": 0,
            "story_drops": 0,
            "story_adds": 0,
            "inline_renames": 0,
            "inline_drops": 0,
            "inline_splits": 0,
            "details": [],
        }

        # 1. Story-level תיוגים span
        def story_span_sub(m):
            opening, ana_value, post, body, closing = m.groups()
            old_tags = split_tag_list(ana_value)
            bare_halakhah = halakhah_triage.get((edition, story_id))
            new_tags = transform_tags(old_tags, rename, drop, split, bare_halakhah)
            # Insert LLM positives (deduped)
            for pos in positives_for(story_id):
                if pos not in new_tags:
                    new_tags.append(pos)
                    ev["story_adds"] += 1
                    ev["details"].append(f"+story-tag {pos}")
            # Count renames vs drops
            added_via_rename = sum(1 for t in old_tags if t in rename and rename[t] not in old_tags)
            ev["story_renames"] += added_via_rename
            ev["story_drops"] += sum(1 for t in old_tags if t in drop)
            return opening + join_tag_list(new_tags) + post + body + closing

        chunk = STORY_TAGSPAN_RE.sub(story_span_sub, chunk)

        # 2. Inline spans (non-תיוגים)
        def inline_span_sub(m):
            opening, ana_value, post, body, closing = m.groups()
            if body.strip() in ("תיוגים", "תיוגים*"):
                return m.group(0)  # already handled
            bare_halakhah = halakhah_triage.get((edition, story_id))
            old_tags = split_tag_list(ana_value)
            new_tags = transform_tags(old_tags, rename, drop, split, bare_halakhah)
            if not new_tags:
                # All tags dropped — unwrap span, keep body text only.
                ev["inline_drops"] += 1
                ev["details"].append(f"-inline-span (all tags dropped: {old_tags})")
                return body
            if new_tags != old_tags:
                if len(new_tags) > len(old_tags):
                    ev["inline_splits"] += 1
                else:
                    ev["inline_renames"] += 1
                ev["details"].append(f"~inline {old_tags} → {new_tags}")
            return opening + join_tag_list(new_tags) + post + body + closing

        # Loop inline substitution until stable so nested spans get unwrapped
        # layer-by-layer (a span whose body contains another span is invisible
        # to the regex until the inner span has been processed).
        prev = None
        while prev != chunk:
            prev = chunk
            chunk = INLINE_ANA_RE.sub(inline_span_sub, chunk)

        # 3. Opening-tag-only rename pass: catches spans whose body contains
        # nested XML (persName etc.) which the structural inline regex can't
        # match. Renames only — no drops handled here (would leave ana="").
        def span_open_sub(m):
            opening, ana_value, post = m.groups()
            if "תיוגים" in (post + ana_value):
                # Avoid touching story-level spans (post contains the body
                # close, but only when matched against the FULL pattern; we
                # need a different guard). Defer to story-level handler if the
                # body that follows is תיוגים — checked by re-matching here:
                pass
            old_tags = split_tag_list(ana_value)
            new_tags_ren = []
            for t in old_tags:
                if t in drop:
                    new_tags_ren.append(t)  # keep; drop only happens in structural pass
                elif t in split:
                    # Apply split (no DROP-marked items in split lists at this point)
                    new_tags_ren.extend(split[t])
                elif t in rename:
                    new_tags_ren.append(rename[t])
                else:
                    new_tags_ren.append(t)
            # Dedup preserving order
            dedup = []
            seen = set()
            for t in new_tags_ren:
                if t not in seen:
                    dedup.append(t)
                    seen.add(t)
            if dedup == old_tags:
                return m.group(0)
            ev["inline_renames"] += 1
            ev["details"].append(f"~span-open {old_tags} → {dedup}")
            return opening + join_tag_list(dedup) + post

        # Re-run open-pass only on chunks that didn't get covered by structural
        # pass (i.e. spans with complex bodies). We re-process the whole chunk
        # but the per-tag transformations are idempotent.
        chunk = SPAN_OPEN_ANA_RE.sub(span_open_sub, chunk)

        if chunk != original_chunk:
            events.append(ev)

        new_txt_chunks.append(txt[last_pos:start])
        new_txt_chunks.append(chunk)
        last_pos = end

    new_txt_chunks.append(txt[last_pos:])
    new_txt = "".join(new_txt_chunks)
    return new_txt, events


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--diff-out", default=str(AUDIT / "rewrite-diff.md"))
    args = ap.parse_args()

    if args.dry_run == args.apply:
        sys.exit("Specify exactly one of --dry-run or --apply")

    tax_rename, drop, split = load_taxonomy_decisions()
    global_rename = load_global_rules()
    # Merge: global rules act as a safety net but taxonomy.tsv wins on conflict.
    rename = {**global_rename, **tax_rename}

    halakhah_triage = load_halakhah_triage()
    practice_positives = load_practice_positives()
    duplicates = load_duplicates()

    # Resolve transitive closure of rename map so multi-hop chains
    # (e.g. practice:conversing_with_angels → supernatural:angels →
    # characters-and-roles:angels) collapse to a single hop. Also: if a final
    # target lands in `drop`, fold the source into `drop` too.
    def _resolve(t, seen):
        if t in seen:
            return t  # cycle — keep current
        if t in drop:
            return None  # dropped
        if t not in rename:
            return t
        return _resolve(rename[t], seen | {t})

    resolved = {}
    new_drops = set()
    for src in list(rename.keys()):
        tgt = _resolve(rename[src], {src})
        if tgt is None:
            new_drops.add(src)
        else:
            resolved[src] = tgt
    rename = resolved
    drop |= new_drops

    print(f"Decisions loaded:")
    print(f"  renames/merges: {len(rename)}")
    print(f"  drops:          {len(drop)}")
    print(f"  splits:         {len(split)}")
    print(f"  halakhah triage rows: {len(halakhah_triage)}")
    print(f"  practice positives (stories): {len(practice_positives)}, total tag-story pairs: {sum(len(v) for v in practice_positives.values())}")
    print(f"  duplicate pairs (stories with at least one duplicate): {len(duplicates)}")
    print()

    summary = defaultdict(int)
    file_summaries = []
    diff_lines = []

    for xml_path in sorted(ONLINE.glob("*.xml")):
        new_txt, events = rewrite_edition(
            xml_path, rename, drop, split, halakhah_triage, practice_positives, duplicates,
        )
        if not events:
            continue
        changed_bytes = sum(1 for a, b in zip(xml_path.read_text(), new_txt) if a != b)
        file_summary = {
            "file": xml_path.name,
            "stories_changed": len(events),
            "story_renames": sum(e["story_renames"] for e in events),
            "story_drops": sum(e["story_drops"] for e in events),
            "story_adds": sum(e["story_adds"] for e in events),
            "inline_renames": sum(e["inline_renames"] for e in events),
            "inline_drops": sum(e["inline_drops"] for e in events),
            "inline_splits": sum(e["inline_splits"] for e in events),
        }
        file_summaries.append(file_summary)
        for k, v in file_summary.items():
            if isinstance(v, int):
                summary[k] += v

        diff_lines.append(f"## {xml_path.name}")
        diff_lines.append(f"- stories changed: {file_summary['stories_changed']}")
        diff_lines.append(f"- story-level: renames={file_summary['story_renames']}  drops={file_summary['story_drops']}  adds={file_summary['story_adds']}")
        diff_lines.append(f"- inline:      renames={file_summary['inline_renames']}  drops={file_summary['inline_drops']}  splits={file_summary['inline_splits']}")
        diff_lines.append("")
        for e in events[:25]:
            diff_lines.append(f"  - **{e['story_id']}**")
            for d in e["details"]:
                diff_lines.append(f"    - {d}")
        if len(events) > 25:
            diff_lines.append(f"  - ... ({len(events) - 25} more stories)")
        diff_lines.append("")

        if args.apply:
            xml_path.write_text(new_txt)

    # Overall summary
    print("=== Summary across all editions ===")
    for k in ("stories_changed", "story_renames", "story_drops", "story_adds",
              "inline_renames", "inline_drops", "inline_splits"):
        print(f"  {k:18s} {summary[k]}")

    diff_md = (
        f"# Tag-audit rewrite — {'dry-run' if args.dry_run else 'applied'}\n\n"
        f"## Summary\n\n"
        + "\n".join(f"- {k}: {summary[k]}" for k in
                    ("stories_changed", "story_renames", "story_drops", "story_adds",
                     "inline_renames", "inline_drops", "inline_splits"))
        + "\n\n## Per-file detail\n\n"
        + "\n".join(diff_lines)
    )
    Path(args.diff_out).write_text(diff_md)
    print(f"\nDiff summary written to {args.diff_out}")


if __name__ == "__main__":
    main()
