"""
Print funnel candidates for one tag, with the most useful context for judging:
  - lexical-strong tags: a window around the first matched Hebrew term
  - other tags: the story opening
Used by the Opus-in-CLI adjudication of the practice pilot.

Usage: python3 show_candidates.py practice:tvilah [window]
"""
import sys
import csv
import tag_data
import tag_lexicons
from config import PROJECT_DIR
import os

tag = sys.argv[1]
win = int(sys.argv[2]) if len(sys.argv) > 2 else 110
queue = os.path.join(PROJECT_DIR, "editions", "tag-audit", "practice", "adjudication-queue.tsv")
stories = {s["story_id"]: s for s in tag_data.load_stories("core")}
lex = tag_lexicons.lexicon(tag)

rows = [r for r in csv.DictReader(open(queue, encoding="utf-8"), delimiter="\t")
        if r["tag"] == tag and r["kind"] == "candidate"]
print(f"# {tag}  ({len(rows)} candidates)\n# def: {tag_lexicons.definition(tag)}\n")
for r in rows:
    txt = stories[r["story_id"]]["text"]
    shown = None
    if lex:
        for t in lex["terms"]:
            if tag_lexicons.term_in_text(t, txt):
                i = txt.find(t)
                w = txt[max(0, i - win):i + win].replace("\n", " ")
                shown = f"[{t}] …{w}…"
                break
    if shown is None:
        shown = txt[:2 * win].replace("\n", " ")
    print(f"{r['story_id']:26s} {shown}")
