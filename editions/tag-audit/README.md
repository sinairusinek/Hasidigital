# Tag Audit — consistency & refinement of story tags

Generalizes the proven **women** (refinement) and **pidyon** (consistency-audit) work to
*all* story theme tags. For each tag it finds stories that should carry the tag but don't
(missed taggings), flags possible over-tagging, surfaces redundant/overlapping tags, and
poses category-boundary questions for the PI. Plan:
`~/.claude/plans/look-at-the-work-purring-harp.md`.

## Scope

- **In scope:** story-level theme tags — the `<span ana="...">` tokens on each
  `<div type="story">`. 181 well-formed `top:sub` tags across the **9 fully-annotated
  editions** (652 stories). Lexical search may widen to all 27 `editions/online/*.xml`.
- **Out of scope (noted, not audited):** the inline annotation layer —
  `<placeName ana="bio">` (383) and `<persName ana>` (7 one-offs). Revisit separately.

## How it works (per tag)

1. **Find candidates (a funnel).**
   - *Keyword* signal — Hebrew/Yiddish terms, matched as whole words with prefixes/suffixes
     (`tag_lexicons.term_in_text`), not naive substrings (avoids `שיר`⊂`עשיר` homographs).
   - *Meaning* signal — story embeddings (`multilingual-e5`, local). Long stories are
     **chunked** into ~1000-char windows and a story matches if *any* chunk is near the
     tag's centroid (so middle/end content isn't lost). Threshold = 40th percentile of the
     tagged stories' own similarity; up to 60 candidates per tag.
2. **Adjudicate.** Each candidate is read in full by a model that judges whether the tag
   truly applies. **Lexical-strong tags** were hand-judged by Claude Opus (highest quality
   where a keyword anchors the call); **meaning-based / interpretive tags** by **Gemini 3
   Flash** (reads the whole story — the right tool for abstract themes). Opus verdicts always
   take precedence over a later model sweep.
3. **Recall check.** A random sample of *un-flagged* stories is also judged; if some come
   back as matches, the search is too narrow (flagged as "search looks leaky" in the report).

## Known limitation: textual parallels are not symmetric in retrieval

Top-K-per-story embedding retrieval is **not** symmetric for textual parallels.
Two near-duplicate stories across editions can land in different candidate sets,
so one gets a suggestion that its twin never sees. Concrete case:
Khal-Hasidim_0126 was suggested for `practice:business_advice` (sim 0.96); its
twin Peer-MiKdoshim_0006 was never even evaluated for that tag.

This means the current per-tag results **under-count missed taggings on cross-edition
twins**. The general audit (see [`general-audit-plan.md`](general-audit-plan.md))
adds a complementary near-duplicate pass that propagates every confirmed/rejected
verdict to all story-level near-duplicates before XML write-back.


## Tooling (`Authorities/integration_tool/`)

| file | role |
|---|---|
| `tag_data.py` | extract stories + tags; emit `taxonomy.tsv`, `tag-inventory.tsv` |
| `tag_embeddings.py` | chunked multilingual embeddings + centroid/max-pool helpers (cached) |
| `tag_lexicons.py` | per-tag detectability, Hebrew lexicons, definitions, morphological matcher |
| `tag_audit.py` | the funnel + adjudication + recall check; writes per-tag results + progress |
| `tag_review.py` | builds the reviewer **report (`.md`)** + **decision spreadsheet (`.csv`)** |
| `tag_viz.py` | story-landscape, tag-similarity, audit-overlay figures |
| `tag_progress.py` | live progress + ETA of a running audit (`tag_progress.py <cat> --watch`) |
| `tag_fp_experiment.py` | side experiment: false-positive check on a tag's *existing* taggings |
| `show_candidates.py` | print a tag's candidates with term/sentence context (for hand-judging) |

## Outputs (per category, e.g. `practice/`)

- `<cat>-review.md` — reviewer report: intro · deeper boundary questions · issues needing
  input · per-tag summary. (Plain language, links to hasidic-stories.org.)
- `<cat>-suggested-taggings.csv` — one row per suggested tagging; `decision` pre-set to
  `confirm`, reviewer changes only the rejects (opens in Google Sheets, UTF-8).
- `<cat>-mentions.tsv` — one combined file for the whole category (every candidate, with
  `tag` + `story_url`); `<cat>-audit.tsv` — per-tag summary counts.
- `story-landscape.png`, `<cat>-tag-similarity.png`, `audit-overlay.png` — figures.
- Top level: `taxonomy.tsv` (all tokens + anomalies), `tag-inventory.tsv`, `all-tags.tsv`.

## Status board

| Category | tags | audited | report+sheet | PI-reviewed | applied |
|---|---|---|---|---|---|
| practice (pilot) | 43 | yes | yes | — | — |
| (13 other categories) | 138 | — | — | — | — |

## Running it

```
cd Authorities/integration_tool
python3 tag_data.py                      # refresh taxonomy + inventory
TAG_AUDIT_MODEL=gemini-3 python3 tag_audit.py --category <cat>   # the sweep
python3 tag_progress.py <cat> --watch    # monitor ETA in another shell
python3 tag_review.py <cat>              # report + decision spreadsheet
python3 tag_viz.py                       # figures
```

## Notes

- Anthropic API key currently has no credit, so the API adjudicator is Gemini (3 Flash via
  the `google-genai` SDK; 2.0 Flash via the legacy SDK). Switches back to Claude when funded.
- The XML has drifted ahead of `topics/data/10HasidicEditionsTopics.tsv` (a stale 158-tag
  snapshot); the live XML (181 tags) is ground truth. `practice:pidyon_monetary_gift` was
  already merged into `practice:pidyon_nefesh`.
- 43 anomalous tokens in `taxonomy.tsv` (comma-glued pairs, bare values, three-level tokens)
  need cleanup; the few needing a human decision are listed in each report.
