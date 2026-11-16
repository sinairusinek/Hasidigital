"""LLM tagger for the project's own topic scheme, reading CONTENT, not only structure.

For one text division (a TEI <div> of any type: story, non-story, preface, paratext...)
Opus decides what the division really holds, then tags every Hasidic story in it:

  unit.kind  hasidic_story | several_stories | non_hasidic_story | saying_or_teaching |
             paratext_with_story | paratext_no_story | continuation_or_fragment | other
  stories    one entry per story found (start/end quoted verbatim when the division holds
             more than one story, or a story inside paratext)
  tags       vocabulary tags only, each with verbatim Hebrew quotes (spans) or scope 'story'

Verbatim quotes are checked against the division text afterwards; failures are recorded,
not silently dropped."""
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "talks/paris-inalco-2026-11/motif-experiment"))
from common import call_claude  # noqa: E402

VOCAB = list(csv.DictReader(open(HERE / "vocab.tsv"), delimiter="\t"))
VOCAB_SET = {v["tag"] for v in VOCAB}


def vocab_block():
    by_cat = {}
    for v in VOCAB:
        by_cat.setdefault(v["tag"].split(":")[0], []).append(v)
    L = []
    for cat, vs in by_cat.items():
        L.append(f"\n## {cat}")
        for v in vs:
            L.append(f"- {v['tag']}: {v['definition'] or '(no definition; apply only if the tag name is unambiguous)'}")
    return "\n".join(L)


SYSTEM = """You are annotating 19th-century Hasidic books (Hebrew, some Yiddish) for a digital edition.
You get ONE text division of a book as the edition currently divides it, with its current label
(e.g. story, non-story, preface, paratext) and the end of the previous / start of the next division.
Current labels are unreliable: judge by CONTENT.

STEP 1. Decide what the division holds ("unit"):
- hasidic_story: one narrative about Hasidic figures/life (a tale, anecdote, memorate, legend).
- several_stories: two or more separate narratives in one division.
- non_hasidic_story: a narrative that is not Hasidic (e.g. talmudic/midrashic legend retold, general folktale, history) but stands as a story.
- saying_or_teaching: a saying, homily, teaching, halakhic or kabbalistic discussion, trait list, without a narrative.
- paratext_with_story: preface, approbation, note, letter, title matter etc. that CONTAINS a narrative.
- paratext_no_story: such paratext without a narrative.
- continuation_or_fragment: the division continues a story begun in the previous division, or is a fragment (catchword, footnote stub).
- other.
A narrative needs at least an event happening to someone; a saying introduced by "he said" alone is not a story.

STEP 2. For every story found (hasidic or not), assign tags ONLY from the vocabulary below.
Tag what the story is about or depicts per the definitions; do not tag passing words. For each tag give
either scope "story" (applies to the whole tale: genre/story_type tags, a setting that frames everything)
or scope "span" with 1-3 verbatim Hebrew quotes (3-12 words each, copied EXACTLY from the text) where it is expressed.
confidence: 3 = clearly applies, 2 = probably, 1 = borderline.
Typical stories carry 5-15 tags. Be complete within the definitions, but do not stretch them.

Return ONLY JSON:
{"unit": {"kind": "...", "why": "<one sentence>", "boundary_note": "<'' or e.g. 'story continues into next division'>"},
 "stories": [
   {"k": 1, "start_quote": "<first 4-8 words, verbatim>", "end_quote": "<last 4-8 words, verbatim>",
    "hasidic": true, "summary_en": "<one sentence>",
    "tags": [{"tag": "<vocabulary tag>", "scope": "story"|"span", "quotes": ["..."], "confidence": 3, "why": "<short>"}],
    "missing_concepts": ["<short English: important topic of this story that NO vocabulary tag covers>"]}
 ]}
"stories" is [] when there is no story. Quote exactly; never translate inside quotes.

VOCABULARY:
""" + vocab_block()


def clean_text(t, sid=""):
    t = re.sub(r"\s+", " ", t).strip()
    if sid and t.startswith(sid):
        t = t[len(sid):].strip()
    return t.replace("תיוגים*", "").replace("תיוגים", "").strip()


def norm(s):
    return re.sub(r"\s+", " ", s.replace("״", '"').replace("׳", "'")).strip()


def tag_unit(unit):
    """unit: dict(id, edition, label, text, prev_tail, next_head). Returns result dict."""
    user = (f"Book: {unit['edition']}\nDivision: {unit['id']} (current label: {unit['label']})\n"
            f"...end of previous division: «{unit.get('prev_tail', '')}»\n\nDIVISION TEXT:\n{unit['text']}\n\n"
            f"start of next division...: «{unit.get('next_head', '')}»")
    res = call_claude(SYSTEM, user, timeout=900)
    T = norm(unit["text"])
    bad_tags, bad_quotes, nq = [], 0, 0
    for s in res.get("stories", []):
        keep = []
        for t in s.get("tags", []):
            if t.get("tag") not in VOCAB_SET:
                bad_tags.append(t.get("tag"))
                continue
            ok = []
            for q in t.get("quotes", []) or []:
                nq += 1
                if norm(q) in T:
                    ok.append(q)
                else:
                    bad_quotes += 1
            t["quotes"] = ok
            t["quotes_failed"] = len(t.get("quotes", []) or []) != len(ok)
            keep.append(t)
        s["tags"] = keep
        for k in ("start_quote", "end_quote"):
            s[k + "_found"] = bool(s.get(k)) and norm(s[k]) in T
    res["check"] = {"non_vocab_tags": bad_tags, "quotes": nq, "quotes_not_found": bad_quotes}
    res["id"] = unit["id"]
    return res
