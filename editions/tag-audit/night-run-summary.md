# Night-run summary — general tag audit (2026-06-25 to 2026-06-27)

## Headline

**1,914 LLM-confirmed positive (story, tag) assignments added to the 9-edition
corpus**, drawn from a two-stage Sonnet → Opus pipeline run over all 142 tags
in 10 categories (everything except the previously-completed practice +
kabbalah pilots). Two commits on `main`:

- `e999fa4` — audit pipeline, scripts, per-category audit TSVs, Sonnet/Opus
  comparison report, visualizations.
- `d5c1891` — XML writeback of the 1,914 confirmed inserts across 9 editions.

Not pushed to remote.

## Pipeline

1. **Sonnet sweep** (claude-sonnet-4-6 via Claude CLI, workers=1 sustained):
   ~5,000 candidate-adjudication calls across social, ethics-and-emotions,
   supernatural, characters-and-roles, experience, folkloristics, times,
   spaces, knowledge categories. 1,455 candidates returned True.
2. **Opus refinement** (claude-opus-4-7 via Claude CLI, workers=1):
   1,452/1,455 Sonnet Trues re-adjudicated by Opus. **821 confirmed,
   631 rejected** (Sonnet over-tagged 43%).
3. **Sonnet-False sample** (n=100): 89 confirmed correct, **11 Sonnet
   under-tags** (Opus said True where Sonnet said False). Extrapolation
   suggests ~390 additional true positives across the full 3,560 Sonnet
   Falses that we are NOT adding (conservative writeback).
4. **Duplicate propagation**: 836 direct Opus True verdicts propagated to
   1,148 additional near-duplicate stories per `story-duplicates.tsv`.
5. **Writeback**: 1,984 proposed inserts → 1,914 applied (70 skipped as
   already present). Across 9 editions, 300 stories.

## Sonnet accuracy by category (Opus as gold standard)

| category | Sonnet True | Opus confirmed | Opus rejected | agreement |
|---|---:|---:|---:|---:|
| supernatural | 229 | 166 | 62 | 73% |
| experience | 125 | 86 | 39 | 69% |
| spaces | 34 | 22 | 12 | 65% |
| kabbalah (refinement on prior) | 11 | 7 | 4 | 64% |
| folkloristics | 150 | 95 | 55 | 63% |
| times | 91 | 56 | 34 | 62% |
| social | 282 | 155 | 127 | 55% |
| characters-and-roles | 77 | 41 | 36 | 53% |
| ethics-and-emotions | 400 | 171 | 229 | 43% |
| knowledge | 55 | 22 | 33 | 40% |

## Throttle history

- 4 separate Max-plan throttle walls were hit during the runs. Each was
  caused by either parallel workers (workers≥2) or the Opus refinement's
  higher token cost. Cache-aware resume avoided losing work each time.
- Final workable cadence: **single-threaded (workers=1), small inter-category
  pauses**. Sustained ~2,000–3,000 calls per Max window without throttling.

## Decisions deferred

- **RA precision pass** — would query Opus on the ~4,890 RA-tagged pairs to
  catch RA over-tagging. Not done because (a) the audit's embedding-based
  precision check found only 1 outlier across all 142 tags, suggesting RA
  tagging is internally consistent; (b) ~8h of additional Opus quota.
- **Bulk Sonnet-False re-check** — only sampled 100 pairs for the under-tag
  rate. Full re-check would be ~3,560 calls. Recommend revisit only if the
  current under-tag estimate (11%) feels too low and you want the extra
  ~390 missed positives.

## Open questions for Sinai

(None this run — no genuinely ambiguous calls needed flagging.)

## Files of note

- `editions/tag-audit/opus-refinement-full.tsv` — 1,455-row Sonnet-vs-Opus
  agreement table; sortable by category, by confidence, by verdict.
- `editions/tag-audit/llm-confirmed-verdicts.tsv` — exactly what was inserted
  (with direct vs propagated source).
- `editions/tag-audit/disagreement-report.tsv` — small RA-vs-LLM
  disagreement set (mostly from May Gemini pilot; only 17 cases).
- `editions/tag-audit/venns/` — Sonnet/Opus/RA overlap diagrams.
- `editions/tag-audit/story-landscape.png` — corpus-wide t-SNE map.
