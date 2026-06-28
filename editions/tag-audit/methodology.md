# Tag-audit methodology — Hasidic-stories corpus

A four-layer annotation pipeline producing the per-story tag set in the
9 "core" editions. Each layer adds; nothing was removed by the LLM layers.
This document records both what was done and the methodological caveats
that should accompany any quantitative claim about the result.

## Layer 1 — RA (human annotator), pre-2026

A research assistant manually annotated each story's themes in the
story-level `<span ana="...">תיוגים</span>` (or `תיוגים*` in
Shivhei-Habesht). 4,890 (story, tag) pairs across 652 stories.

## Layer 2 — Gemini 3 Flash Preview pilot (practice + kabbalah, May 2026)

For each tag, the audit pipeline (`Authorities/integration_tool/tag_audit.py`)
generated *candidate* stories from a combination of lexical hits (against a
hand-curated Hebrew/Yiddish term lexicon, `tag_lexicons.py`) and embedding
similarity (e5-base on story-mean-pooled chunks). Each candidate was sent to
Gemini 3 Flash with the tag's definition and asked to return JSON
`{"applies": true|false, "confidence": ..., "reasoning": ...}`.

- **Why Gemini, not Claude:** Anthropic API was out of credit at the time.
- **Why Gemini 3, not 2.5:** user rejected 2.5 (less semantically refined).
- **Scope:** practice (43 tags) + kabbalah (2 tags via claude-cli).
- **Results:** 382 missed positives in practice, 11 in kabbalah.

Hand-adjudication via Claude Opus 4.7 over the CLI (`claude -p`) produced
258 high-priority verdicts that override any later model's verdict on the
same `(story, tag, prompt_hash)`. This was the "second judge" comparing
Gemini and Opus on practice tags.

## Layer 3 — Sonnet 4.6 via Claude CLI (10 remaining categories, Jun 25-27)

Identical method to Layer 2, applied to social, ethics-and-emotions,
supernatural, characters-and-roles, experience, folkloristics, times, spaces,
knowledge. Run at workers=1 to stay under Max-plan throttle.

- **Total calls:** ~5,019 cache rows.
- **Outcome:** 1,455 candidates returned True (Sonnet "missed positives");
  3,564 returned False.

### KNOWN ISSUE (fixed 2026-06-28): Sonnet used weak definitions

`tag_lexicons.DEFINITIONS` only covered ~40 practice/kabbalah tags at the
time of the Sonnet sweep. For all other tags, `tag_lexicons.definition()`
returned the humanized sub-tag name alone (e.g. *"retrospective recognition"*
for `social:retrospective_recognition`). So Sonnet's prompts for non-pilot
categories had **3 words of definition**, not the Drive-sheet refined text.

Patched 2026-06-28: `tag_lexicons.definition()` now falls through to
`editions/tag-audit/tag-definitions-merged.tsv` (98/100 queried tags
covered). **The Sonnet sweep has NOT been re-run** with the patched
definitions — see "Open work" below.

## Layer 4 — Opus 4.7 via Claude CLI refinement (Jun 26-27)

For each of Sonnet's 1,455 True verdicts (1,452 actually processed),
re-judged with Opus 4.7 using the proper Drive-sheet definitions.

- **Result:** 821 Opus-confirmed (AGREE), 631 Opus-rejected (DISAGREE),
  3 errored. Overall agreement: **56.5%** — Sonnet over-tagged on
  ~43% of its Trues.
- Per-category agreement ranges 40% (knowledge) to 73% (supernatural);
  see `opus-refinement-full.tsv`.
- Confidence calibration: Sonnet-high → 63% agreement, Sonnet-medium →
  33%. Both-high-confidence subset → 70%.

A separate 100-story sample of Sonnet **False** verdicts re-judged by Opus
found 11 disagreements (Sonnet under-tagged in 11% of cases sampled).

## Layer 5 — propagation and writeback

For every Opus-confirmed True verdict on story A, the (tag) was also added
to every near-duplicate story B from `story-duplicates.tsv` (cosine
similarity ≥ 0.99 on e5-base story embeddings), provided B did not already
carry the tag. 836 direct verdicts → 1,148 propagated.

The combined 1,984 (story, tag) inserts were applied to the story-level
`<span ana="...">תיוגים</span>` of `editions/online/*.xml`. 70 were already
present and skipped; 1,914 written.

**RA tags were preserved unchanged.** No LLM ever caused a tag to be
removed from a story. The pipeline is strictly enrichment.

## Where the data lives

- `editions/tag-audit/.cache/llm-presence.tsv` — every LLM verdict
  (story_id, tag, prompt_hash, model, applies, confidence, reasoning, ts).
  Authoritative.
- `editions/tag-audit/<category>/<cat>-audit.tsv` — per-tag summary stats
  for each audited category.
- `editions/tag-audit/opus-refinement-full.tsv` — 1,455-row Sonnet × Opus
  comparison table.
- `editions/tag-audit/llm-confirmed-verdicts.tsv` — exactly what was
  inserted into the XMLs (direct + propagated).
- `editions/tag-audit/disagreement-report.tsv` — 17 incidental cases where
  an LLM disagreed with an RA tag (limited sample from gemini-3 controls).
- `editions/tag-audit/venns/*.png` — Sonnet/Opus/RA overlap diagrams.
- `editions/tag-audit/scripts/*.py` — the runner scripts.

## Methodological caveats — read before drawing conclusions

### Coverage is asymmetric

- **Over-tagging by Sonnet** is measured *precisely* — every Sonnet True was
  re-judged by Opus.
- **Under-tagging by Sonnet** is measured *roughly* — only a 100-story
  sample (CI ~5–19% at 95%).
- **Over-tagging by RA** is measured *very loosely* — 17 incidental
  disagreements + embedding outlier check (`n_fp_candidates`=1 across all
  tags, suggesting RA is internally consistent).
- **Under-tagging by RA** ≈ "missed positives" the LLMs found = 1,914
  applied. This is a lower bound (capped by the candidate funnel).

### The candidate funnel is itself a ceiling — but its recall IS measured

The audit only sent the LLM stories the funnel surfaced (lexical hit or
top-K embedding similarity to the tag centroid). Funneling is a token-cost
choice: querying every (story, tag) pair would mean 652 × 142 = ~93,000
calls per model. The funnel cuts that to ~5,000.

**This choice is only defensible if the funnel itself has high recall.**
The audit's built-in `control_n=10` per tag measures this: for each tag,
10 stories that the funnel did NOT flag are sent to the LLM as a recall
probe. Aggregate across 142 tags:

- Random un-flagged un-tagged stories the LLM judged True: **183 / 1,420
  = 12.9%** (Sonnet-raw)
- Opus-adjusted (×0.57 to account for Sonnet's known over-tagging rate):
  **~7.3%**

So the funnel has **87–93% recall** of true positives, depending on which
model you trust. Per-category breakdown reveals where the funnel is weakest:

| category | funnel-miss rate | character |
|---|---:|---|
| kabbalah | 0% | lexical-strong terms |
| characters-and-roles | 5.3% | named-entity dominant |
| spaces | 8.6% | physical locations |
| practice | 9.3% | mostly lexical-strong |
| times | 10.0% | calendar/lifecycle |
| social | 11.1% | relationship terms |
| experience | 16.2% | semi-abstract themes |
| folkloristics | 20.0% | story-type judgments |
| ethics-and-emotions | 21.8% | abstract themes |
| knowledge | 23.3% | abstract themes |
| supernatural | 24.4% | abstract themes |

**Implication:** the funnel is a strong filter for lexical/named-entity
tags but a weak one for abstract-thematic tags. Any claim about recall on
the abstract categories should carry the 20-24% funnel-miss caveat.

To improve funnel recall on the abstract categories specifically, options
include: (a) lowering the top-K threshold (more candidates, more LLM cost),
(b) using a sharper embedding model finetuned on the tag definitions,
(c) extending the lexicon with seed terms even for semantic tags.

### Opus is treated as gold standard but is not human-validated

We chose Opus's verdict over Sonnet's when they disagreed. Opus's own
accuracy against expert human judgment was not measured in this run. The
56.5% Sonnet/Opus agreement could mean "Sonnet is generous" or "Opus is too
strict" — we don't know without human adjudication.

### Definition stability

The Drive-sheet definitions (Chen/Gadi feedback) were finalized 2026-06-23
to 2026-06-25, *during* the Sonnet sweep. Categories audited late in the
sweep used slightly more stable definitions than those audited early. This
is in addition to the Sonnet-used-weak-definitions issue above.

### Throttle silent-failures

Multiple times the Max-plan throttle caused CLI calls to error; the script
swallowed those errors as `applies=False` and incremented counters,
producing temporarily inflated False counts in per-category audit TSVs. The
cache-write guard prevented these bad verdicts from poisoning the
authoritative cache, but the per-category summary TSVs in the repo reflect
the state at the time of their last successful write, which may have been
in a partially-throttled state. The cache is the truth.

## Open work

1. **Re-run Sonnet with the patched definitions** for the categories where
   `tag_lexicons.DEFINITIONS` was previously empty. Cache hits will be
   invalidated by the new prompt hash, so this is roughly the same scope as
   the original sweep (~3,800 calls). Decision pending.
2. **Larger Sonnet-False sample (~500)** to tighten the under-tagging
   confidence interval.
3. **Human adjudication anchor** — sample ~100 disagreement cases (50 from
   each direction) for a domain expert to judge, then recompute Sonnet and
   Opus accuracy against that anchor.
4. **RA precision pass** — Opus on a stratified sample of RA-tagged pairs,
   roughly 500 calls, to measure RA over-tagging rate (currently unknown
   except for incidental signal).
