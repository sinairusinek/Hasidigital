"""Build the tagging vocabulary for the LLM tagger.

Vocabulary = the tags used on >= 3 stories in the 9 curated editions' current XML (144 tags,
2026-11-16; legitimate-tags.tsv is stale: old 'social-relations' name, one-off tags), so the
LLM-tagged tier is comparable with the curated tier. Rarer tags are listed in vocab-excluded.tsv.
For each tag:
  women tiers: the published definitions (zenodo/women-9ed/README.md)       -> source "women-study"
  definition from tag-definitions.tsv / tag-definitions-merged.tsv  -> source "written"
  else a definition DERIVED from the curated stories that carry it  -> source "derived"
Derived definitions: one Opus call per category, shown up to 6 example stories per tag
(openings, 600 chars) plus the written definitions of the category's other tags.
Output: vocab.tsv (tag, n_stories, source, definition)."""
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "talks/paris-inalco-2026-11/motif-experiment"))
from common import call_claude  # noqa: E402  (claude -p on Max, no tools)
from tag_data import load_stories  # noqa: E402

AUD = REPO / "editions/tag-audit"
OUT = HERE / "vocab.tsv"

from collections import Counter as _C
_cnt = _C(t for s in load_stories("core") for t in set(s["tags"]))
used = {t: n for t, n in _cnt.items() if n >= 3}
with open(HERE / "vocab-excluded.tsv", "w") as _f:
    _f.write("tag\tn_stories\treason\n")
    for t, n in sorted(_cnt.items()):
        if n < 3:
            _f.write(f"{t}\t{n}\tused on fewer than 3 curated stories\n")
WOMEN = {
    "women:major_character": "A woman is a central actor in the story with her own agency.",
    "women:catalyst_character": "A woman triggers the plot or is the reason for events, without being a central actor.",
    "women:minor_character": "A woman appears in a small or peripheral role and acts in the narrative.",
    "women:mention_only": "A woman is referred to but does not act in the narrative.",
}
written = dict(WOMEN)
for fn in ("tag-definitions.tsv", "tag-definitions-merged.tsv"):   # merged wins (later, patched)
    for r in csv.DictReader(open(AUD / fn), delimiter="\t"):
        if r["definition"].strip() and r["tag"] not in WOMEN:
            written[r["tag"]] = r["definition"].strip()

SYSTEM = """You help document an annotation scheme for 19th-century Hasidic tales (Hebrew).
Research assistants applied topic tags to stories, but some tags never got a written definition.
For each undefined tag you get its name and example stories that carry it. Write the definition
the annotators were evidently applying: one or two sentences, in the style of the written
definitions you are shown, saying what in a story makes the tag apply (and, if the examples
show it, what does not suffice). Do not invent a broader meaning than the examples support.
Return ONLY JSON: {"definitions": {"<tag>": "<definition>", ...}}"""


def main():
    stories = load_stories("core")
    by_tag = defaultdict(list)
    for s in stories:
        for t in set(s["tags"]):
            by_tag[t].append(s)
    todo = defaultdict(list)
    for t in used:
        if t not in written:
            todo[t.split(":")[0]].append(t)
    derived = {}
    for cat, tags in sorted(todo.items()):
        rng = random.Random(cat)
        L = [f"CATEGORY: {cat}", "", "Written definitions of other tags in this category (style reference):"]
        L += [f"- {t}: {d}" for t, d in written.items() if t.startswith(cat + ":")][:25]
        L += ["", "UNDEFINED TAGS AND EXAMPLES:"]
        for t in tags:
            ex = rng.sample(by_tag[t], min(6, len(by_tag[t])))
            L.append(f"\n## {t}  (used on {used[t]} stories)")
            for s in ex:
                L.append(f"- [{s['story_id']}] {' '.join(s['text'].split())[:600]}")
        res = call_claude(SYSTEM, "\n".join(L))
        for t, d in res.get("definitions", {}).items():
            if t in used and t not in written:
                derived[t] = d
        print(cat, f"{len(tags)} undefined -> {sum(t in derived for t in tags)} derived", flush=True)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["tag", "n_stories", "source", "definition"])
        for t in sorted(used):
            if t in written:
                w.writerow([t, used[t], "women-study" if t in WOMEN else "written", written[t]])
            else:
                w.writerow([t, used[t], "derived" if t in derived else "missing", derived.get(t, "")])
    print("->", OUT)


if __name__ == "__main__":
    main()
