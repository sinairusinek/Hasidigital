"""Apply editions/tag-audit/irregular-tags-mapping.tsv to the edition XMLs.

Malformed topic tags are the ones the pre-upload gate rejects: they do not match
^[a-z-]+:[a-z0-9_]+$ — a bare word with no category ('kabbalah', 'clothing'), a
double colon ('practice:magic:make_it_rain'), or a comma used as a separator so
the tag never got split ('practice:prayer,experience:shaking_during_prayer').

Only the rows the mapping marks 'sure' or 'likely' are applied. Rows marked
'you decide' are left alone and listed at the end: childhood, custom,
not-a-hasidic-story, financial-support-to-the-tsaddik, self_esteem.

Special case, as the mapping specifies: 'kabbalah' is dropped in stories that
already carry knowledge:esoteric and replaced by it in the 11 that do not.

Edits the files as text, so the diff shows only the changed @ana attributes
rather than a full ElementTree reflow. Run with --dry to preview.
"""
import argparse
import csv
import glob
import re
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MAPPING = REPO / "editions" / "tag-audit" / "irregular-tags-mapping.tsv"
TAG = re.compile(r"^[a-z-]+:[a-z0-9_]+$")
STORY = re.compile(r'(<div\b[^>]*\btype="story".*?</div>)', re.S)
# only <span ana="...">: that is what the gate reads as topic tags. placeName
# carries ana="bio" and notes carry prose, neither of which is a topic tag.
ANA = re.compile(r'(?<=<span )ana="([^"]*)"')


def load_rules():
    """current_tag -> list of replacement tags ([] = drop). Decided rows only."""
    rules = {}
    for r in csv.DictReader(MAPPING.open(encoding="utf-8"), delimiter="\t"):
        if r["action"].strip() == "you decide" or r["confidence"].strip() == "you decide":
            continue
        prop = r["proposed"].strip()
        if prop.startswith("drop") or r["action"].strip() == "drop":
            rules[r["current_tag"]] = []
        else:
            rules[r["current_tag"]] = [t.strip() for t in prop.split(";") if t.strip()]
    return rules


def tokens(ana):
    """Split an @ana value the way the gate does, keeping order."""
    return [t for t in re.split(r"[;\s]+", ana) if t]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("files", nargs="*")
    args = ap.parse_args()

    rules = load_rules()
    files = args.files or sorted(glob.glob(str(REPO / "editions" / "online" / "*.xml")))
    applied, skipped = Counter(), Counter()

    for fp in map(Path, files):
        src = fp.read_text(encoding="utf-8")
        changed = 0

        def fix_story(m):
            nonlocal changed
            block = m.group(1)
            # tags present anywhere in this story, for the kabbalah rule
            present = {t for a in ANA.findall(block) for t in tokens(a)}

            def fix_ana(am):
                nonlocal changed
                toks = tokens(am.group(1))
                out, hit = [], False
                for t in toks:
                    if t == "TBD:Unknown" or TAG.match(t):
                        out.append(t)
                        continue
                    if t == "kabbalah":
                        hit = True
                        applied["kabbalah"] += 1
                        # drop if the story already has knowledge:esoteric, else replace
                        if "knowledge:esoteric" not in present:
                            out.append("knowledge:esoteric")
                            present.add("knowledge:esoteric")
                        continue
                    if t in rules:
                        hit = True
                        applied[t] += 1
                        out += rules[t]
                        continue
                    skipped[t] += 1
                    out.append(t)
                if not hit:
                    return am.group(0)
                seen, uniq = set(), []
                for t in out:
                    if t not in seen:
                        seen.add(t)
                        uniq.append(t)
                changed += 1
                return 'ana="' + "; ".join(uniq) + '"'

            return ANA.sub(fix_ana, block)

        out = STORY.sub(fix_story, src)
        if changed:
            print(f"{fp.name}: {changed} @ana attributes rewritten")
            if not args.dry:
                fp.write_text(out, encoding="utf-8")

    print("\napplied:", sum(applied.values()), "tag fixes")
    for t, c in applied.most_common():
        print(f"   {c:4d}  {t}")
    if skipped:
        print("\nLEFT ALONE (mapping says 'you decide'):")
        for t, c in skipped.most_common():
            print(f"   {c:4d}  {t}")
    if args.dry:
        print("\n(DRY RUN, nothing written)")


if __name__ == "__main__":
    main()
