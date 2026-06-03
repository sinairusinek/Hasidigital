# General tag audit — plan for the 9 fully-annotated editions

**Scope.** Apply the practice-pilot audit method to **all 14 top-level categories**
(181 tags, 652 stories), and add a complementary **near-duplicate pass** that closes
the textual-parallel gap found during the practice review.

**Why now.** The practice pilot is reviewer-ready and surfaced a methodological gap
(textual parallels missed by top-K retrieval — see [practice-review.md](practice/practice-review.md)
*Known limitation* and [README.md](README.md)). Fixing this for *all* tags
before the PI does heavy review is much cheaper than re-running per-category.

## The 14 categories to audit

Tag counts from `editions/tag-audit/all-tags.tsv`:

| Category | tags | priority |
|---|---:|---|
| practice (done) | 43 | — |
| social-relations | 19 | high (largest unaudited; 903 story-mentions) |
| ethics-and-emotions | 19 | high |
| supernatural | 14 | high (797 mentions) |
| characters-and-roles | 12 | high |
| folkloristics | 11 | medium |
| experience | 11 | medium |
| times | 7 | medium |
| spaces | 7 | medium |
| halakhah | 5 | medium |
| knowledge | 3 | low |
| custom | 3 | low |
| kabbalah | 2 | low |
| profession | 3 | low |
| (others: ritual, esoteric-knowledge, appearance, property, …) | ≤2 each | absorb into adjacent or drop after taxonomy cleanup |

Long-tail one-off prefixes (clothing, body, beverage, business, economy, book, possession, …)
likely belong to the taxonomy-cleanup pass, not the audit proper — see [`taxonomy.tsv`](taxonomy.tsv).

## Pipeline (per category, then once across all)

### Phase 1 — sweep (per category, as in the practice pilot)
1. Refresh inventory: `python3 tag_data.py`.
2. `python3 tag_audit.py --category <cat>` — produces `<cat>-mentions.tsv`, `<cat>-audit.tsv`.
3. `python3 tag_review.py <cat>` — produces `<cat>-review.md` + `<cat>-suggested-taggings.csv`.
4. Adjudicator: Gemini 3 Flash until Anthropic credit is restored, then Opus on
   lexical-strong tags. Verdicts are pinned by `(tag, story_id, model)` so later
   model sweeps can supersede only same-cell verdicts.

### Phase 2 — complementary near-duplicate pass (new)
1. **Build a story near-duplicate index** across all 9 editions.
   - Re-use existing chunk embeddings from `tag_embeddings.py` (already cached) — max-pool
     to one vector per story, then all-pairs cosine within the 652 stories. A
     candidate-pair cutoff around 0.93 captures known textual twins
     (e.g. Khal-Hasidim_0126 ↔ Peer-MiKdoshim_0006) without flooding.
   - Persist as `editions/tag-audit/story-duplicates.tsv`: `story_a, story_b, sim, evidence_snippet`.
2. **Propagate every confirmed suggestion** from the per-category sheets to every
   near-duplicate before XML write-back. The propagation rule:
   - If story A is confirmed for tag T and (A, B, sim) is in the duplicate index
     with sim ≥ threshold, B inherits T's *confirm* verdict.
   - If B was already evaluated by the adjudicator for T with verdict `reject`,
     surface as a **conflict** for the PI rather than auto-overriding.
3. **Propagate rejections too.** Same logic in reverse: a reject on A becomes a
   reject on B for the same tag (modulo conflict surfacing).
4. **Output**: `editions/tag-audit/duplicate-propagations.tsv` with columns
   `source_story, target_story, tag, source_verdict, action (auto-confirm/auto-reject/conflict)`.
   PI reviews only the conflicts; the rest auto-applies on write-back.

### Phase 3 — taxonomy cleanup
1. Drop or rehome the 43 anomalous tokens in `taxonomy.tsv` (comma-glued pairs,
   bare values, three-level tokens, one-off categories). Most can be auto-fixed
   by string substitution; a small set needs PI input — list in each per-category
   review.
2. After the per-category sweeps, run a single **cross-category merger review**:
   tags that overlap across category boundaries (e.g. `practice:healing` vs
   `supernatural:miracle` for the same story-set) get a unified Sankey + PI question.

### Phase 4 — XML write-back
1. One commit per category, gated by the PI-reviewed sheet.
2. Each commit also applies the duplicate-propagated tags from Phase 2.
3. Streamlit Cloud picks up automatically (already plumbed for the 9-edition view).

## Open questions for the PI before kickoff

1. **Adjudicator budget.** If Anthropic credit is restored, do we re-run the
   practice pilot under Opus for lexical-strong tags (~$5–10), or accept the
   Gemini verdicts already on disk?
2. **Near-duplicate threshold.** Default 0.93 cosine on max-pooled story
   embeddings — confirm or adjust after a 50-pair manual look.
3. **Conflict policy.** When a near-duplicate inherits a confirm but was already
   adjudicated as reject for the same tag, default = surface to PI. Alternative:
   auto-trust the higher-confidence verdict; risky.
4. **Cross-category boundary review.** Done once at the end (Phase 3.2)? Or
   inline per-category as the pilot did?
5. **Order.** Suggested order: social-relations → supernatural → ethics-and-emotions →
   characters-and-roles → folkloristics → experience → times → spaces → halakhah →
   knowledge / custom / kabbalah / profession. Confirm.

## Estimated effort

- Phase 1 sweeps: ~1–2 days of API runtime per medium-large category at Gemini
  pricing (sub-$10 each); reviewer reading time dominates total wall-clock.
- Phase 2 near-duplicate pass: hours, not days (embeddings already cached).
- Phase 3 taxonomy cleanup: half-day plus PI input on the boundary cases.
- Phase 4 write-back: minutes per category.

## Deliverables

- 13 new `<cat>-review.md` + `<cat>-suggested-taggings.csv` files (one per
  unaudited category).
- `story-duplicates.tsv`, `duplicate-propagations.tsv`.
- Updated `editions/tag-audit/README.md` status board.
- Cleaned `taxonomy.tsv`.
- A series of XML write-back commits, one per category.
