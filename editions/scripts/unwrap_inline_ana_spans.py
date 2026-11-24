"""Remove the abandoned inline <span ana="..."> experiment from the edition XMLs.

Background (Sinai, 2026-11-24): a few editions wrap individual words inside a
story in <span ana="tag">. It was an experiment that was never followed up, the
site does not use it, and the renderer SWALLOWS the wrapped word: the Besht's
stolen horse read "שהי׳ לבעש״ט אחד ונגנב ממנו" online, with סוס missing.

KEPT, because they are the story's real tag record:
  * the marker span whose text contains תיוגים (drives the site's topic sidebar;
    it appears as 'תיוגים*' and also as ',תיוגים');
  * EMPTY spans — 731 of them, in editions that never got the תיוגים text. They
    carry the only tags those stories have (e.g. practice:pidyon_nefesh in
    Buzina_Denehora).

REMOVED: only a span that wraps actual words (116 of them, in 3 editions).
Its tags, if the story's marker does not already list them, are appended to
that marker, so no annotation is lost. Placeholders (TBD:Unknown, complete,
double) are dropped rather than merged.

This edits the file as TEXT, with a regex, rather than re-serialising the tree:
ElementTree would rewrite <lb/> as <lb />, change the encoding declaration and
reflow the whole document, burying a 116-line change in a 2000-line diff.

Run with --dry to see what would change.
"""
import argparse
import glob
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

PLACEHOLDER = {"TBD:Unknown", "complete", "double"}

# a <span ana="..."> ... </span> with no nested <span> inside it
SPAN = re.compile(r'<span\s+ana="([^"]*)"\s*>(.*?)</span>', re.S)
STORY = re.compile(r'(<div\b[^>]*\btype="story".*?</div>)', re.S)


def tags_of(s):
    return [t.strip() for t in s.split(";") if t.strip()]


def is_marker(inner_text):
    """Empty span, or one labelled תיוגים: the story's own tag list, not the experiment."""
    bare = re.sub(r"<[^>]+>", "", inner_text).strip()
    return bare == "" or ("תיוגים" in bare and len(bare) <= 20)


def process_story(block):
    """Unwrap word-wrapping spans in one story; merge their tags into its marker."""
    spans = list(SPAN.finditer(block))
    markers = [m for m in spans if is_marker(m.group(2))]
    inline = [m for m in spans if not is_marker(m.group(2))]
    if not inline:
        return block, 0, []

    have = {t for m in markers for t in tags_of(m.group(1))}
    # prefer the תיוגים list as the place to add to
    target = next((m for m in markers if "תיוגים" in re.sub(r"<[^>]+>", "", m.group(2))),
                  markers[0] if markers else None)

    add, merged = [], []
    for m in inline:
        for t in tags_of(m.group(1)):
            if t not in PLACEHOLDER and t not in have:
                have.add(t)
                add.append(t)
                merged.append(t)

    # rebuild right-to-left so earlier offsets stay valid
    edits = [(m.start(), m.end(), m.group(2)) for m in inline]
    if add and target is not None:
        newana = "; ".join(tags_of(target.group(1)) + add)
        edits.append((target.start(), target.end(),
                      f'<span ana="{newana}">{target.group(2)}</span>'))
    for a, b, repl in sorted(edits, reverse=True):
        block = block[:a] + repl + block[b:]
    return block, len(inline), merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="report only, write nothing")
    ap.add_argument("files", nargs="*", help="default: editions/online/*.xml")
    args = ap.parse_args()

    files = args.files or sorted(glob.glob(str(REPO / "editions" / "online" / "*.xml")))
    grand = 0
    for fp in map(Path, files):
        src = fp.read_text(encoding="utf-8")
        total, merged_all = 0, []

        def repl(m):
            nonlocal total, merged_all
            new, n, merged = process_story(m.group(1))
            total += n
            merged_all += merged
            return new

        out = STORY.sub(repl, src)
        if total:
            grand += total
            print(f"{fp.name}: unwrapped {total} word-wrapping spans"
                  + (f", merged {len(merged_all)} tags into the story markers" if merged_all else ""))
            if not args.dry:
                fp.write_text(out, encoding="utf-8")
    print(f"\n{grand} spans" + ("  (DRY RUN, nothing written)" if args.dry else "  — written"))


if __name__ == "__main__":
    main()
