# Tag-audit methodology & complete stage ledger — Hasidic-stories corpus

The per-story thematic tag set in the 9 "core" editions is the product of a
multi-stage human + LLM annotation pipeline. This document is the canonical,
detailed record of **every stage** — the original additive run (Layers 1–5),
the definition patch and full re-run (Layers 6–7), the reconciliation finding
that invalidated a naive removal approach, and the direct precision audit that
produced the first non-additive cleanup (Layer 8). It also records the final
corpus numbers, the application surfaces, the full file/script inventory, and
the methodological caveats that must accompany any quantitative claim.

Last updated: 2026-06-30 (precision-audit removals applied, commit `815d694`).

---

## 0. Corpus & key facts

- **9 core editions**, 652 stories with story-level thematic annotation.
- Tags live in the story-level `<span ana="tag1; tag2; …">תיוגים</span>`
  (`תיוגים*` in Shivhei-Habesht), one span per `<div type="story">`.
- **~142 thematic tags** across categories: social, ethics-and-emotions,
  supernatural, characters-and-roles, experience, folkloristics, times, spaces,
  knowledge, practice, kabbalah.
- **All LLM calls go through `claude -p` (Max plan OAuth)**, never the API
  (the API key has no credit). This dictates single-threaded runs, throttle
  pacing, and that cloud/headless automation cannot run the pipeline.
- **Authoritative verdict store:** `editions/tag-audit/.cache/llm-presence.tsv`
  (git-ignored). Columns: story_id, tag, prompt_hash, model, applies,
  confidence, reasoning, ts. A verdict is keyed by `(story, tag, prompt_hash,
  model)`; `prompt_hash = md5(presence_prompt(tag, definition))[:8]`, so a
  changed definition produces a new hash and a fresh verdict.

### Pipeline at a glance

| Stage | When | Model | Scope | Result |
|---|---|---|---|---|
| L1 RA | pre-2026 | human | 9 editions | 4,890 (story,tag) |
| L2 Gemini pilot | May 2026 | Gemini 3 Flash + Opus 4.7 adj. | practice (43) + kabbalah | 382 + 11 missed positives |
| L3 Sonnet sweep | Jun 25–27 | Sonnet 4.6 | 9 thematic categories | 1,455 True / 3,564 False (weak defs) |
| L4 Opus refine | Jun 26–27 | Opus 4.7 | L3 Trues | 821 confirm / 631 reject (56.5%) |
| L5 propagate+writeback | Jun 27 | — | near-dups | **1,914 inserts written** |
| **L6 definition patch + Sonnet re-run** | Jun 28 | Sonnet 4.6 | 9 categories, proper defs | 601 True (re-run complete) |
| **L7 Opus re-refine** | Jun 29 | Opus 4.7 | 601 re-run Trues | 361 confirm (60.2%) |
| **L5′ patched writeback** | Jun 29 | — | + near-dup propagation | **610 additive inserts (commit 06da94b)** |
| **L8 precision audit + removals** | Jun 29–30 | Opus 4.7 | all 1,971 old weak-def inserts | 1,162 confirm / 809 reject → **789 removed (commit 815d694)** |

---

## Layer 1 — RA (human annotator), pre-2026

A research assistant manually annotated each story's themes. **4,890
(story, tag) pairs across 652 stories.** This is the baseline; no LLM layer
ever removes an RA tag, and the precision audit (L8) is hard-guarded against
touching RA pairs.

## Layer 2 — Gemini 3 Flash pilot (practice + kabbalah, May 2026)

For each tag, `Authorities/integration_tool/tag_audit.py` generates *candidate*
stories from lexical hits (hand-curated Hebrew/Yiddish lexicon in
`tag_lexicons.py`) ∪ embedding similarity (e5-base, story-mean-pooled chunks,
top-K above a per-tag percentile threshold of the positive set's self-similarity).
Each candidate → Gemini 3 Flash with the tag definition → JSON
`{applies, confidence, reasoning}`.

- **Why Gemini, not Claude:** API was out of credit then.
- **Why Gemini 3, not 2.5:** user judged 2.5 less semantically refined.
- **Scope:** practice (43 tags) + kabbalah (2 tags via claude-cli).
- **Results:** 382 missed positives in practice, 11 in kabbalah.
- Hand-adjudication via Opus 4.7 (`claude -p`) produced **258** high-priority
  verdicts that override later models on the same `(story, tag, prompt_hash)`.

These categories had **real definitions** in `tag_lexicons.DEFINITIONS`, so
they are excluded from the L8 precision audit (no weak-definition problem).

## Layer 3 — Sonnet 4.6 sweep, ORIGINAL (weak definitions, Jun 25–27)

Same method as L2 applied to the 9 thematic categories, workers=1 for throttle.

- ~5,019 cache rows. **1,455 True / 3,564 False.**
- **KNOWN FLAW (the reason for L6):** at the time, `tag_lexicons.DEFINITIONS`
  covered only the ~40 practice/kabbalah tags. For all other tags,
  `definition()` returned just the humanized sub-tag name (e.g. *"retrospective
  recognition"*) — **3 words, not the Drive-sheet refined text.** Sonnet's True
  rate was therefore inflated by definition-vagueness.

## Layer 4 — Opus 4.7 refinement, ORIGINAL (Jun 26–27)

Re-judged Sonnet's 1,455 Trues (1,452 processed) with Opus 4.7 using proper
Drive-sheet definitions.

- **821 confirm / 631 reject / 3 error. Agreement 56.5%** (Sonnet over-tagged
  ~43% of its Trues). Per-category agreement 40% (knowledge) → 73%
  (supernatural). See `opus-refinement-full.tsv`.
- Confidence calibration: Sonnet-high → 63% agree, Sonnet-medium → 33%,
  both-high → 70%.
- Separate 100-story sample of Sonnet **False** verdicts re-judged by Opus:
  11 disagreements (~11% under-tag rate, wide CI).

## Layer 5 — propagation + writeback, ORIGINAL (Jun 27)

Every Opus-confirmed True on story A was also added to each near-duplicate B
in `story-duplicates.tsv` (cosine ≥ 0.99, e5-base) not already carrying the
tag. **836 direct → 1,148 propagated = 1,984 combined; 1,914 written** (70
already present). Recorded in `llm-confirmed-verdicts.tsv`. Strictly additive.

---

## Layer 6 — Definition patch + Sonnet re-run (Jun 28)

**The patch (commit `a39df89`).** `tag_lexicons.definition()` was changed to
fall through to `editions/tag-audit/tag-definitions-merged.tsv` (100 tags, 98
of those queried covered) when a tag isn't in the hand-curated `DEFINITIONS`
dict. The merged file unions (a) the Chen/Gadi Drive-sheet refined definitions
and (b) original definitions under pre-rewrite tag names. **Only `definition()`
changed — the candidate funnel code was untouched.**

**The re-run.** The full Sonnet 4.6 sweep was re-run for all 9 categories with
the patched definitions (`run_category_chain.sh` / `overnight_run.sh`). Because
a changed definition changes `prompt_hash`, these are fresh verdicts; where a
patched definition came out identical to the old text, the hash is unchanged
and the cached verdict is reused (a no-op). All 9 categories completed
(`rc=0`, `calls N/N`).

- **Result at current (patched) hash: 601 Sonnet-True candidates.**
- **Important subtlety — the funnel shifted between runs.** The candidate
  funnel selects from *untagged* (`neg`) stories, with the embedding centroid
  built from *currently-tagged* (`pos`) stories. The L5 writeback (run between
  the original and patched sweeps) grew `pos` by 1,914, which (i) excluded
  those now-tagged stories from candidacy and (ii) moved the centroid and
  similarity threshold. So the patched sweep evaluated a **different, smaller**
  candidate set than the original — **not** a bug, a consequence of auditing an
  already-enriched corpus. This is why the patched run cannot, by itself,
  re-judge the existing inserts (they sit in `pos`) — which is exactly why the
  L8 direct audit was needed.

## Layer 7 — Opus re-refinement (Jun 29)

All 601 patched Sonnet-Trues re-judged by Opus 4.7 under the patched
definitions (`opus_refine_patched.py`).

- **361 confirm / 239 reject / 1 unjudged (a JSON-parse error on
  Khal-Hasidim_0120 × times:shabbat). Agreement 60.2%** — up from the original
  56.5%, i.e. proper definitions made Sonnet's Trues more accurate.
- Confirmed by category: ethics 86, social 84, supernatural 60, folkloristics
  44, spaces 26, times 20, knowledge 16, characters 10, experience 9,
  kabbalah 6.

## Layer 5′ — Patched writeback (Jun 29, commit `06da94b`)

The 361 confirmed patched-definition positives, propagated to near-duplicates
and filtered against tags already in the XML, yielded **636 adds (356 direct +
280 propagated); 610 actually written** (26 propagated to story-IDs not present
as story divs). Recorded in `llm-confirmed-verdicts-patched.tsv`. Still
additive; RA untouched.

---

## Reconciliation attempt — and why funnel-based removal was INVALID

After L7 a funnel-based reconciliation (`reconcile_patched.py`) was run to find
old inserts the patched audit contradicts. It surfaced **436 "removal
candidates"** — but these were **discarded as invalid**. Diagnosis:

- Only ~6 were genuine Opus rejections at the patched hash.
- The other ~430 were flagged because their `(story, tag)` had **no verdict at
  the current patched hash** — i.e. they were *not re-evaluated*, not *rejected*.
- Root cause: the funnel shifted between runs (see L6). 3,241 original-run
  candidate pairs were never re-judged under patched defs — 35% because they
  became `pos` (already tagged), 65% because the centroid/threshold moved.
  "Not in the patched candidate set" means "the funnel moved," **not** "the tag
  is wrong."

**Lesson:** to audit already-inserted tags you must judge them **directly**,
not via the funnel (which only looks at untagged stories). That is Layer 8.

## Layer 8 — Old-insert precision audit + removals (Jun 29–30, commit `815d694`)

**Direct Opus-4.7 re-judgment** of every old weak-definition insert under the
patched definitions (`precision_audit_old_inserts.py`). Scope: the 1,971 old
inserts in the 9 thematic categories whose tags were *not* in
`tag_lexicons.DEFINITIONS` (practice/kabbalah excluded — they had real defs).
No funnel — each `(story, tag)` is asked directly. Run in paced 250–300-call
batches (`audit_batch.sh`) across several throttle windows, with a
consecutive-error circuit-breaker.

- **1,971 judged (100%). 1,162 confirm / 809 reject (41% over-tag rate).**
- **The over-tagging is overwhelmingly in the propagation layer:**
  **73 of 809 rejects were directly-judged inserts (~9% reject), 736 were
  propagated inserts (~64% reject).** Near-duplicate propagation — copying a
  verdict from story A to its ≥0.99-similar twin B without judging B — is the
  dominant false-positive source. Near-duplicates are not identical; a tag
  valid for A often fails on B. Spot-check (15 direct + 15 propagated) found
  the rejection reasoning consistently definition-aware and correct.
- **Removal applied** (`remove_verdicts.py --apply`): of the 809 rejected,
  **789 were present in the XML and removed** (20 were propagated to story-IDs
  never actually written). Removals by category: ethics 207, social 207,
  folkloristics 80, supernatural 70, characters 69, times 51, experience 47,
  knowledge 34, spaces 24. By edition: Khal-Hasidim 333 (the anthology hub,
  hence most near-dups), Adat-Zadikim 112, Shivhei-Habesht 104, PeerMikdoshim
  101, Mifalot 45, Sipurei-Zadikim 39, maase-zadikim 29, Shivhei-Harav 26.
- **Safety:** removal targets come solely from `llm-confirmed-verdicts.tsv`
  (LLM inserts). `remove_verdicts.py` loads the RA-original set (XML − all LLM
  inserts) and **aborts if any removal collides with it**. The run reported
  "RA-collision check: clean." RA's 4,890 tags are untouched.

This is the **first non-additive step** in the program.

---

## Final corpus state (2026-06-30)

| Component | (story,tag) pairs |
|---|---:|
| **Total in XML** | **6,625** |
| RA-original (untouched) | 4,890 |
| LLM net contribution | 1,735 |
|  — surviving old-definition inserts | 1,125 |
|  — patched-definition adds | 610 |

The LLM layer peaked at +2,524 inserts (1,914 original + 610 patched) and the
precision audit pruned it to **+1,735 net** by removing 789 over-tags.

---

## Application surfaces (where the results are consumed)

- **Tag Audit page** — `Authorities/integration_tool/pages/tag_audit.py`, in
  the Integration Tool Streamlit app (Tags → Tag Audit). Live read-only
  dashboard: corpus breakdown, patched sweep → Opus agreement, precision-audit
  progress + reject rates + removal-candidate table. Reads the live cache
  locally; falls back to the committed `audit-cache-snapshot.tsv` on Streamlit
  Cloud (the cache is git-ignored). Refresh the snapshot with
  `export_audit_snapshot.py` after each audit change.
- **Women dashboard** — `women_dashboard/app.py`
  (women-in-hasidic-stories.streamlit.app). Parses the edition XMLs directly,
  so it reflects the audit automatically. Two audit-aware features added
  2026-06-30:
  - **Tag-provenance toggle** (sidebar): RA-only vs RA+LLM-audited, filtering
    the Topics-tab charts by the `llm-confirmed-verdicts*.tsv` insert set.
  - **Length-normalized topic view**: "tagged stories per 1,000 words" diff,
    correcting the confound that women stories are longer (avg 661 vs 276
    words) and accumulate more tags. Generic narrative themes
    (prognostication, conflict, retrospective_recognition) drop out; genuinely
    women-associated domestic themes (marriage, marital_relationship, birth,
    adultery) rise.

---

## Where the data lives

Authoritative / inputs:
- `.cache/llm-presence.tsv` — every LLM verdict (git-ignored, authoritative).
- `audit-cache-snapshot.tsv` — committed current-hash subset for Cloud.
- `tag-definitions-merged.tsv` — patched definitions (the L6 fix source).
- `story-duplicates.tsv` — near-duplicate adjacency (cosine ≥ 0.99).
- `<category>/<cat>-audit.tsv`, `<category>/<cat>-mentions.tsv` — per-category
  summary + per-candidate Sonnet verdicts (regenerated by the runner).

Verdict / decision records:
- `llm-confirmed-verdicts.tsv` — the 1,984 original (L5) inserts.
- `llm-confirmed-verdicts-patched.tsv` — the 636 patched (L5′) adds.
- `opus-refinement-full.tsv` — original 1,455-row Sonnet×Opus table.
- `opus-refine-patched-results.tsv` — L7 verdicts (601).
- `old-inserts-precision-audit.tsv` — L8 per-batch results.
- `old-inserts-removals.tsv` — the 809 rejected old inserts (removal list).
- `reconcile-summary.txt` / `reconcile-removals.tsv` — the INVALID funnel-based
  reconciliation (kept for the record; superseded by L8).
- `disagreement-report.tsv` — 17 incidental LLM-vs-RA disagreements.
- `venns/*.png` — Sonnet/Opus/RA overlap diagrams.

## Scripts inventory (`editions/tag-audit/scripts/`)

- `run_category_chain.sh`, `overnight_run.sh` — the patched Sonnet re-run (L6).
- `opus_refine_patched.py` — Opus re-refinement of patched Sonnet-Trues (L7).
- `reconcile_patched.py` — the (invalid) funnel-based reconciliation.
- `precision_audit_old_inserts.py` — direct Opus audit of old inserts (L8).
- `audit_batch.sh` — one paced batch of the above (`audit_batch.sh 250`).
- `remove_verdicts.py` — apply removals (RA-guarded; `--dry-run`/`--apply`).
- `writeback_verdicts.py` — apply additive inserts (`--verdicts PATH`).
- `propagate_verdicts.py` — near-duplicate propagation.
- `export_audit_snapshot.py` — refresh the committed Cloud snapshot.
- `build_rerun_comparison.py`, `opus_check.py`, `draw_venns.py` — analysis/viz.

The runner itself: `Authorities/integration_tool/tag_audit.py` (funnel + LLM
adjudication); `tag_lexicons.py` (definitions + lexicon); `tag_data.py`,
`tag_embeddings.py` (data + embeddings).

---

## Methodological caveats — read before drawing conclusions

### Coverage is asymmetric
- **Sonnet over-tagging**: measured precisely (every True re-judged by Opus).
- **Sonnet under-tagging**: measured roughly (100-story sample, CI ~5–19%).
- **RA over-tagging**: measured loosely (17 incidental disagreements +
  embedding outlier check, `n_fp_candidates`=1 across all tags).
- **RA under-tagging** ≈ the missed positives the LLMs found (lower bound,
  capped by the funnel).

### The candidate funnel is a ceiling — but its recall IS measured
Querying every (story,tag) pair would be 652 × 142 ≈ 93,000 calls/model; the
funnel cuts that to ~5,000. Built-in `control_n=10` per tag (10 un-flagged
stories sent as a recall probe) measures funnel recall:

- Sonnet-raw funnel-miss: 183/1,420 = **12.9%**; Opus-adjusted **~7.3%** →
  **funnel recall ≈ 87–93%**.

Per-category funnel-miss (the funnel is strong for lexical/named-entity tags,
weak for abstract-thematic ones):

| category | miss rate | character |
|---|---:|---|
| kabbalah | 0% | lexical-strong |
| characters-and-roles | 5.3% | named-entity |
| spaces | 8.6% | physical locations |
| practice | 9.3% | lexical-strong |
| times | 10.0% | calendar/lifecycle |
| social | 11.1% | relationship terms |
| experience | 16.2% | semi-abstract |
| folkloristics | 20.0% | story-type |
| ethics-and-emotions | 21.8% | abstract |
| knowledge | 23.3% | abstract |
| supernatural | 24.4% | abstract |

Any recall claim on the abstract categories must carry the 20–24% caveat.

### Opus is the gold standard but is NOT human-validated
We chose Opus over Sonnet on disagreement, and over the old inserts in L8.
Opus's own accuracy against expert human judgment was never measured. The
60.2%/41% figures could partly reflect Opus strictness rather than truth.
**This is the single biggest open validation gap.**

### Propagation is the main over-tagging mechanism
L8 showed 64% of propagated inserts fail direct re-judgment vs 9% of direct
inserts. The L5′ patched adds also include 280 propagated tags (from
properly-defined confirmed sources, so likely cleaner — but not directly
audited). Treat propagated tags as lower-confidence than directly-judged ones.

### Definition stability
Drive-sheet definitions were finalized 2026-06-23→25, partly *during* the
original sweep; the patched re-run (L6) used the frozen merged file.

### Throttle realities
Max-plan Opus ceiling ≈ 700–750 calls per rolling 5-hour window (plus a weekly
cap). Throttled calls error; the runner never caches errors, and L8's
circuit-breaker stops cleanly on a wall. Per-category summary TSVs reflect
their last successful write; **the cache is the truth**, not the summary TSVs.

---

## Open work

1. **Human adjudication anchor** — ~100 disagreement cases (50 each direction),
   expert-judged, to measure Opus's *own* accuracy. Highest-value next step.
2. **Audit the L5′ patched propagated adds (280)** directly, the same way L8
   audited the old propagated inserts — they were not directly judged.
3. **Larger Sonnet-False sample (~500)** to tighten the under-tag CI.
4. **RA precision pass** — Opus on a stratified ~500 RA-tagged sample to put a
   number on RA over-tagging.
5. **Funnel recall on abstract categories** — lower top-K / sharper embeddings
   / extended lexicon to close the 20–24% miss on ethics/knowledge/supernatural.
