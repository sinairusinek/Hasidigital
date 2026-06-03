"""
Generate the reviewer-facing document for a tag category.

Structure (per the PI's spec):
  1. Plain-language introduction — what this is and how it was made (no jargon/abbreviations).
  2. Deeper questions — should any category boundaries be redrawn (the high-value discussion).
  3. Tagging issues that need the reviewer's input (only those a human must decide).
  4. Suggested taggings to confirm, tag by tag — each with the most relevant Hebrew
     sentence and plain-text "confirm / reject" cells (Markdown checkbox glyphs do not
     survive conversion to Google Docs, so we use written words).

Run after the audit:  python3 tag_review.py practice
"""
import os
import re
import csv
import sys

import tag_data
import tag_embeddings
import tag_lexicons
from config import PROJECT_DIR

AUDIT_DIR = os.path.join(PROJECT_DIR, "editions", "tag-audit")


def _read(path):
    return list(csv.DictReader(open(path, encoding="utf-8"), delimiter="\t")) if os.path.exists(path) else []


def _link(story_id):
    ed = re.sub(r"_\d+[A-Za-z]?$", "", story_id)
    return f"[{story_id}](https://www.hasidic-stories.org/Story/{ed}/{story_id})"


# ── Relevant-sentence extraction ────────────────────────────────────────────────

_HEB = re.compile(r"[֐-׿]")


def _sentences(text):
    """Split into sentences; drop the leading 'ID תיוגים' boilerplate and non-Hebrew bits."""
    text = re.sub(r"^\S+\s+תיוגים\*?\s*", "", text or "")   # strip story-id + 'תיוגים'
    parts = re.split(r"(?<=[.!?׃:])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) > 12 and _HEB.search(p)]


def _clip(s, maxlen=130):
    s = s.replace("|", "/").replace("\t", " ").strip().strip("\"'")
    return s if len(s) <= maxlen else s[:maxlen].rsplit(" ", 1)[0] + "…"


class _Extractor:
    """Picks the most tag-relevant sentence of a story: the sentence containing a
    keyword (for keyword tags), else the sentence closest in meaning to the tag centroid."""
    def __init__(self):
        self.stories = {s["story_id"]: s for s in tag_data.load_stories("core")}
        self.ids, self.emb = tag_embeddings.embed_stories(
            [self.stories[k] for k in self.stories])
        self._id2i = {sid: i for i, sid in enumerate(self.ids)}
        self._model = None
        self._sent_cache = {}   # story_id -> (sentences, sent_vectors)

    def centroid(self, tag):
        idx = [self._id2i[s["story_id"]] for s in self.stories.values() if tag in s["tags"]]
        return tag_embeddings.centroid(self.emb, idx) if idx else None

    def _sent_vectors(self, story_id, sents):
        if story_id not in self._sent_cache:
            if self._model is None:
                self._model = tag_embeddings._get_model()
            vecs = self._model.encode([f"passage: {s}" for s in sents],
                                      normalize_embeddings=True, convert_to_numpy=True)
            self._sent_cache[story_id] = vecs
        return self._sent_cache[story_id]

    def extract(self, story_id, tag, centroid_vec):
        st = self.stories.get(story_id)
        if not st:
            return ""
        sents = _sentences(st["text"])
        if not sents:
            return _clip(st["text"])
        lex = tag_lexicons.lexicon(tag)
        if lex:                                   # keyword tag: sentence with the term
            for s in sents:
                if any(tag_lexicons.term_in_text(t, s) for t in lex["terms"]):
                    return _clip(s)
        if centroid_vec is not None:              # meaning tag: closest sentence
            vecs = self._sent_vectors(story_id, sents)
            return _clip(sents[int((vecs @ centroid_vec).argmax())])
        return _clip(sents[0])


# ── 1. Introduction ─────────────────────────────────────────────────────────────

INTRO = """# Review of the **{cat}** tags — a consistency check

## What this document is

Every story in the collection carries theme tags — short labels for what the story is
about. Because these were added by many hands over the years, they are applied
unevenly: a story that plainly shows a given theme was sometimes never tagged with it.

This document checks one group of tags — the **{cat}** tags — for that kind of gap.
For each tag it lists stories that appear to belong to it but are **not currently tagged**,
so you can confirm or reject each suggestion. It also raises a few larger questions about
where the boundaries of these categories should lie.

## How it was made

For each tag we took the stories already marked with it, then searched the whole
collection for other stories that resemble them — both by the relevant Hebrew words and
by *meaning* (a language model places stories with similar content near one another, so we
can find related stories even when they share no keyword). Every story that came up was
then read in full by an automated reader, which judged whether the theme is really present
and gave a short reason. **Only the stories it judged a genuine match are listed below**
for your decision. We also spot-checked a random handful of stories that the search did
*not* surface, to estimate whether anything was missed.

A few words as they are used here:

- **Tag** — a theme label on a story (for example, *fasting*).
- **Suggested tagging** — a story that seems to show the theme but is not yet tagged with
  it. You confirm or reject each one.
- **Category boundary** — the question of which stories a tag should and should not cover
  (for example: does giving money to a holy man for a blessing belong to the same tag as
  ransoming a captive, or to a different one?).

**How to record a decision:** every suggestion has a **Confirm** column and a **Reject**
column, each holding the word *confirm* / *reject*. Mark the one that applies — highlight or
bold it, or delete the other — whichever is easiest. (We use plain words rather than
tick-boxes because tick-box symbols do not survive the conversion into Google Docs.)
"""


# ── 2. Deeper questions (curated for practice) ──────────────────────────────────

DEEPER = {
    "practice": """## Deeper questions — should some category boundaries be redrawn?

These are the larger decisions the audit surfaced. They matter more than any single
tagging, because they change how a whole group of stories is classified. (In the earlier
*pidyon* review, a discussion like this led to splitting one blurred tag into clearer ones.)

1. **The redemption / pidyon family is half-built.** The tag now called *redemption of
   captives* is, in fact, the "pidyon for redeeming captives" that the pidyon review
   proposed creating — so should it be renamed for consistency with *pidyon nefesh*
   (the money-gift to a holy man)? And the third kind, *pidyon ha-ben* (redemption of a
   first-born son), has **no tag at all** even though such stories exist. Do you want a
   tag for it?

2. **Three "travel" tags that nearly coincide** — *travel to the holy man*, *travel to
   another holy man*, and *the travels of the holy man*. They differ only by who travels
   to whom, and in practice they overlap heavily. Keep the three-way distinction, or
   simplify it?

3. **A cluster about rescue and cure** — *healing*, *saving a life*, *healing of the soul*,
   and *protection* — sit very close together and are often applied to the same story.
   Where is the line between curing a body, saving a life, repairing a soul, and warding
   off harm? Clear conditions would help.

4. **Arrival as one event or two.** *Travel to the holy man* and *reception of the
   followers* describe the two halves of a single scene (the follower comes; the holy man
   receives him). Should they be one tag, or kept as two deliberate viewpoints?

5. **The ascetic-practice trio** — *asceticism*, *ascetic fasting*, and *fasting*. Is
   *ascetic fasting* a real sub-type worth its own tag, or should it fold into *fasting*
   or *asceticism*?

6. **Conditions of application (when does a passing detail count?)** A few recurring
   judgment calls, like the pidyon "does the commercial sense count?" question:
   - Does merely *mentioning* a ritual slaughterer count as the *ritual slaughtering* tag,
     or only a story that actually depicts the slaughtering?
   - Does taking snuff count as *smoking*?
   - Does the wine of Kiddush or Havdalah count as *drinking alcohol*?
   - Does singing a psalm in prayer count as *reciting psalms*, as *music*, or both?
"""
}


def _auto_deeper(category, inventory):
    by = {r["full_tag"]: r for r in inventory if r["top_tag"] == category}
    seen, pairs = set(), []
    for t, r in by.items():
        for part in (r.get("top_cooccurring") or "").split(";")[:2]:
            o = part.strip().split("(")[0].strip()
            if o in by and frozenset((t, o)) not in seen:
                seen.add(frozenset((t, o))); pairs.append((t.split(":")[-1], o.split(":")[-1]))
    out = ["## Deeper questions — should some category boundaries be redrawn?\n",
           "These tag pairs are applied together very often; the reviewer may wish to "
           "confirm their boundaries or consider merging:\n"]
    out += [f"- **{a}** and **{b}**" for a, b in pairs[:8]]
    return "\n".join(out) + "\n"


def generate(category):
    cdir = os.path.join(AUDIT_DIR, category)
    audit = _read(os.path.join(cdir, f"{category}-audit.tsv"))
    if not audit:
        print(f"No {category}-audit.tsv yet — run the audit first.")
        return
    taxonomy = _read(os.path.join(AUDIT_DIR, "taxonomy.tsv"))
    inventory = _read(os.path.join(AUDIT_DIR, "tag-inventory.tsv"))
    ext = _Extractor()

    out = []
    w = out.append
    cat_nice = category.replace("-", " ")
    w(INTRO.format(cat=cat_nice)); w("")
    w(DEEPER.get(category) or _auto_deeper(category, inventory)); w("")

    # ── 3. Issues needing reviewer input ──
    anomalies = [r for r in taxonomy if r["status"] in ("bad-sep", "no-colon", "tbd")
                 and (r["top_tag"] == category or category in r["full_tag"])]
    multilevel = [r for r in inventory if r["top_tag"] == category and ":" in r["sub_tag"]]
    w("## A few tagging issues that need your input\n")
    w("Most technical problems found in the audit (such as Hebrew word-matching and "
      "duplicate handling) we have already corrected on our side. The items below need a "
      "human decision:\n")
    if anomalies:
        w("**Garbled or incomplete tag labels** — these look like data-entry slips. For each, "
          "say what it was meant to be, or whether to drop it:\n")
        w("| label | on how many stories | what it should be (or 'drop') |")
        w("|---|---|---|")
        for r in anomalies:
            w(f"| `{r['full_tag']}` | {r['n_stories']} | |")
        w("")
    if multilevel:
        w("**Three-level labels** (a tag inside a tag) — keep as a finer sub-type, or simplify?\n")
        w("| label | on how many stories | keep / simplify |")
        w("|---|---|---|")
        for r in multilevel:
            w(f"| `{r['full_tag']}` | {r['n_stories']} | |")
        w("")

    # gather confirmed suggestions per tag
    # combined mentions file (one per category); group confirmed suggestions by tag
    all_ment = _read(os.path.join(cdir, f"{category}-mentions.tsv"))
    by_tag = {}
    for m in all_ment:
        if m.get("claude_applies") == "True":
            by_tag.setdefault(m["tag"], []).append(m)
    enriched = [(r, by_tag.get(r["tag"], [])) for r in audit]
    enriched.sort(key=lambda x: -len(x[1]))

    # ── 4. Suggested-taggings summary (the per-row decisions live in the CSV) ──
    total = sum(len(ms) for _, ms in enriched)
    n_audited = len(audit)
    n_with_cand = len({m["tag"] for m in all_ment})
    n_with_sugg = sum(1 for _, ms in enriched if ms)
    n_all_rejected = n_with_cand - n_with_sugg
    n_no_cand = n_audited - n_with_cand
    w("## Suggested taggings — summary\n")
    w(f"Of the **{n_audited} tags audited**, **{n_with_sugg}** have at least one suggested "
      f"tagging below. The remainder yield nothing to review: **{n_all_rejected}** had look-alike "
      f"stories that the reader rejected on inspection (for example *dance*, where every match was "
      f"the מחול / מחל spelling coincidence), and **{n_no_cand}** had no resembling untagged stories "
      f"at all (mostly the one- or two-story tags). "
      f"({n_audited} audited = {n_with_sugg} with suggestions + {n_all_rejected} all-rejected + "
      f"{n_no_cand} no candidates.)\n")
    w(f"The audit proposes **{total} taggings to add** across "
      f"{n_with_sugg} tags. The individual suggestions are in the "
      f"companion spreadsheet **`{category}-suggested-taggings.csv`** (opens in Google Sheets). "
      f"Each row has the story link, the relevant Hebrew sentence, and a **decision** column "
      f"already set to *confirm* — please change it to *reject* (or *unsure*) only on the rows "
      f"you disagree with; everything left as *confirm* will be added.\n")
    w("| tag | definition | already tagged | suggested additions | search looks leaky? |")
    w("|---|---|---|---|---|")
    for r, ms in enriched:
        if not ms:
            continue
        try:
            rf = float(r.get("recall_flag") or 0)
        except ValueError:
            rf = 0
        flag = f"yes — ~{rf:.0%} (consider wider scan)" if rf >= 0.3 else ""
        defn = tag_lexicons.definition(r["tag"]).replace("|", "/")
        w(f"| {r['tag'].split(':')[-1].replace('_',' ')} | {defn} | {r['n_tagged']} | {len(ms)} | {flag} |")
    w("")
    none_found = [r["tag"].split(":")[-1] for r, ms in enriched if not ms]
    if none_found:
        w("**Tags with no missing taggings found** (existing tagging looks complete): "
          + ", ".join(sorted(s.replace("_", " ") for s in none_found)) + ".\n")

    path = os.path.join(cdir, f"{category}-review.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))

    # ── companion decision spreadsheet ──
    # Build a per-story lookup of textual twins (cross-edition near-duplicates)
    # so the reviewer sees, for each suggestion, whether there's a parallel
    # story they should look at alongside it.
    twins_path = os.path.join(AUDIT_DIR, "story-duplicates.tsv")
    twins_for: dict[str, str] = {}  # story_id -> "twin_id (sim)"
    if os.path.exists(twins_path):
        # Keep the single closest twin per story (TSV is sorted desc by sim).
        with open(twins_path, encoding="utf-8") as tf:
            for row in csv.DictReader(tf, delimiter="\t"):
                a, b, sim = row["story_a"], row["story_b"], row["sim"]
                if a not in twins_for:
                    twins_for[a] = f"{b} ({sim})"
                if b not in twins_for:
                    twins_for[b] = f"{a} ({sim})"

    csv_path = os.path.join(cdir, f"{category}-suggested-taggings.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:   # BOM → Sheets reads Hebrew/UTF-8
        cols = ["decision", "notes", "tag", "story_id", "story_url",
                "hebrew_extract", "signal", "parallel_story",
                "why_suggested", "edition", "confidence"]
        wr = csv.DictWriter(f, fieldnames=cols)
        wr.writeheader()
        for r, ms in enriched:
            tag = r["tag"]; cen = ext.centroid(tag)
            for m in ms:
                sid = m["story_id"]; ed = re.sub(r"_\d+[A-Za-z]?$", "", sid)
                signals = m.get("signals", "") or "embedding"   # fallback: embedding-only
                wr.writerow({
                    "decision": "confirm",
                    "notes": "",
                    "tag": tag,
                    "story_id": sid,
                    "story_url": f"https://www.hasidic-stories.org/Story/{ed}/{sid}",
                    "hebrew_extract": ext.extract(sid, tag, cen) or _clip(m.get("excerpt", "")),
                    "signal": signals,
                    "parallel_story": twins_for.get(sid, ""),
                    "why_suggested": (m.get("claude_reasoning", "") or "").strip(),
                    "edition": m.get("edition", ""),
                    "confidence": m.get("claude_confidence", ""),
                })
    print(f"Wrote {path}")
    print(f"Wrote {csv_path}  ({total} suggestions, decision pre-set to 'confirm')")


if __name__ == "__main__":
    generate(sys.argv[1] if len(sys.argv) > 1 else "practice")
