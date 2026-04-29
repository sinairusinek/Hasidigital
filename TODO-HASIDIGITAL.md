# Hasidigital NER & Edition Management — Master Todo List

## ✅ Completed

- [x] Process 10 incoming editions through story structure pipeline (2026-04-29)
  - Source: `editions/incoming/new xmls WITH story tags/` (exported from Transkribus WITHOUT "force valid TEI")
  - Steps: story_structure.py → facsimile strip → story heads → namespace fix
  - 6 clean editions → `editions/incoming/ready/`
  - 4 editions with flags → `editions/incoming/ready/check/` (for human review)
  - `story_structure.py` enhanced: handles all known rend values, multi-story-per-paragraph, marginal/non-marginal → `ana="marginal"`, `end story` → closes story + opens non-story
- [x] Archive all 27 flawed `*_corrected.xml` and `*_gemini.xml` files (moved to `archived-editions/` with `_flawed` suffix)
- [x] Rebuild 26 fresh `*_corrected.xml` files from raw XMLs (without Gemini damage, clean processing: nisba-fix, ישראל fix, place linking, currency annotation, story heads, namespace fix)
- [x] Verify all 26 raw editions have matching fresh corrected versions
- [x] Verify all files in `editions/incoming/` currently exist as raw + `_corrected` pairs (26 bases / 52 XML files)
- [x] Remove 1199 `<pb facs="..."/>` facsimile elements from all 26 corrected files
- [x] Update NER pipeline (`ner_pipeline/text_extraction.py`) to strip facsimile elements before processing

---

## 📋 Active Work

### Incoming Editions Pipeline (10 of 12 done)

- [ ] **Human review** of `editions/incoming/ready/check/` — resolve flags in Peulat-Hatzadikim, Eser-Kedushot, Eser-Orot, Tiferet-Hayyim; move to `ready/` when done
- [ ] **Download remaining 2 editions** from Transkribus WITHOUT "force valid TEI": Torat-Haramal (15471223), Shaarei-Haemuna (6705131); place in `new xmls WITH story tags/`; run story_structure + post-processing
- [ ] **Run NER** (DictaBERT) on all editions in `ready/`
- [ ] **Post-NER**: place linking, person linking, currency annotation
- [ ] **Upload** processed editions to website

---

### Phase 1: NER & Correction

**3a. Track A: Deterministic DictaBERT fixes** ✅ COMPLETE (2026-03-25)
- Script: `Authorities/scripts/dicta_fixes.py`
- Applied 845 fixes across 14/26 editions (9 fix types), 0 validation warnings
- See memory file `project_ner_pipeline.md` for full breakdown

**3b. Gemini correction project** ❌ CLOSED / FAILED (2026-03-25)
- Three attempts (2026-03-15, 2026-03-25 pilot, 2026-03-25 batch) all failed
- Root cause: strip-and-reinsert architecture is fundamentally lossy
- Archived in `editions/archived-editions/gemini-corrected-2026-03-25/`
- See memory file `feedback_gemini_correction.md` for lessons

**3c. Research: NER strategy alternatives** (NEW)
- **Status**: Open research question
- **Goal**: Evaluate whether we can get better NER results than DictaBERT (modern Hebrew model) + Track A fixes
- **Key finding**: No NER model for historical/Hasidic Hebrew exists. All models trained on modern Hebrew news. This domain mismatch likely explains many DictaBERT errors. See memory file `reference_ner_tools.md` for full landscape.
- **Concrete next steps** (in priority order):
  1. [ ] **Try DictaBERT-Large** (`dicta-il/dictabert-large-ner`, 400M params vs 110M): Swap model in `ner_pipeline/config.py`, run on Kokhvei-Or, compare entity counts and error rate vs. current. Low-effort, may improve accuracy.
  2. [ ] **Benchmark LLM-only NER on Kokhvei-Or**: Send raw text (no prior annotations) to Claude Opus and/or Gemini 2.5, ask for entity list. Compare precision/recall vs. DictaBERT + Track A. Key question: do LLMs avoid the systematic errors (ק״ק, nested tags, empty tags) that DictaBERT makes?
  3. [ ] **Contact Dicta about API access**: Email dicta@dicta.org.il asking about:
     - API for abbreviation expander (abbreviation.dicta.org.il) — useful for our abbreviation errors
     - API for citation finder (citation.dicta.org.il) — useful for future citation annotation task
     - Whether BEREL (rabbinic Hebrew BERT) has been fine-tuned for NER internally
  4. [ ] **Evaluate BEREL for NER fine-tuning**: `dicta-il/BEREL_3.0` is pre-trained on rabbinic Hebrew (Sefaria corpus) — closest to our domain. Would need labeled training data to fine-tune for NER. Assess feasibility and data requirements.
  5. [ ] **Design diff-based LLM correction (Track B)**: If LLM benchmark shows good precision, design an approach where the LLM returns a list of specific changes (not a full entity list) applied as surgical XML edits preserving all attributes.
- **Constraint**: Any approach must preserve existing ref attributes and not require strip-and-reinsert

---

## 🔄 Execution Plan (Pending)

### Phase 2: NER Reprocessing

**5. Re-run NER annotation with chosen strategy**
- [ ] Apply strategy from task 3 to 26 fresh corrected editions
- [ ] Generate NER diff reports (removed/added entities)
- [ ] Spot-check 3–5 high-loss editions
- [ ] If loss is acceptable, commit results

**5b. Unmatched entity recovery (fuzzy search + human review)**
- **Status**: Planned
- **Context**: During Gemini correction, some entities can't be relocated in the source text (Gemini modifies spelling, garbles text, or expands spans). These are logged to `ner_pipeline/unmatched_entities.jsonl` with source file, story ID, and passage preview (enriched 2026-03-25).
- **Tasks**:
  - [ ] Build a recovery tool (CLI or Streamlit page) that:
    - Loads `unmatched_entities.jsonl`
    - For each unmatched entity, runs fuzzy search (Levenshtein) against the passage text
    - Shows top candidate matches with surrounding context
    - Lets the reviewer approve/reject and fix the entity text
  - [ ] Approved entities get inserted into the corrected XML
  - [ ] Track recovery rate (how many of the unmatched were legitimately lost vs. hallucinated)

**6. Re-run place linking**
- [ ] Use batch_link_places.py on fresh annotated editions
- [ ] Update unmatched-places-report.tsv
- [ ] Log any new unmatched entities

**7. Re-run currency annotation**
- [ ] Run annotate_currencies.py on linked editions

### Phase 3: Post-NER Validation

- [ ] Trial upload 2 corrected editions to the website **after** NER strategy is improved and re-run
- [ ] Verify topic rendering (including `TBD:Unknown`) and story/topic display behavior
- [ ] Document upload results and follow-up fixes

### Phase 4: Edition Management Migration

- [x] One-time migration: move uncorrected/raw editions from `editions/incoming/` to `editions/archived-editions/uncorrected/`
- [x] One-time migration: remove dates and `_corrected` suffix from filenames of incoming corrected editions
- [x] One-time migration: add/update XML header version in `editionStmt/edition/@n`
- [x] One-time migration: add/update last-change date in `revisionDesc/change/@when`
- [x] Ongoing policy check: enforce incoming filename + header metadata conventions

---

## 📚 Supporting Scripts & Tools

**Created in this session:**
- `Authorities/scripts/archive_flawed_editions.py` — Move flawed files to archive
- `Authorities/scripts/rebuild_corrected.py` — Clean rebuild from raw XMLs (7-phase processing)
- `Authorities/scripts/ner_diff_report.py` — Compare entity tags between raw and corrected
- `ner_pipeline/gemini_corrector.py` (modified) — Added `max_removal_pct` retention guard
- `ner_pipeline/cli.py` (modified) — Added `--max-removal-pct` flag
- `ner_pipeline/pipeline.py` (modified) — Wired retention guard through pipeline
- `ner_pipeline/text_extraction.py` (modified) — Strip facsimile elements before NER

**Created in Phase 1 implementation kickoff (2026-03-19):**
- `Authorities/scripts/audit_annotation_provenance.py` — Audit editions and flag likely Gemini-only provenance cohorts
- `ner_pipeline/cli.py` (modified) — Added `--passages-per-call` to support story-by-story pilot chunking
- `run_all_corrections.sh` (modified) — Defaults to `--max-removal-pct 40` and configurable `PASSAGES_PER_CALL`
- `editions/phase1-dicta-failures-review-template.tsv` — Reviewer template for obvious Dicta NER failures

**Existing tools:**
- `Authorities/scripts/fix_yisrael_tags.py` — Remove false ישראל tags
- `Authorities/scripts/batch_link_places.py` — Link unlinked place names
- `Authorities/scripts/annotate_currencies.py` — Wrap currency terms
- `Authorities/scripts/apply_kima_decisions.py` — Apply authority decisions, add story heads, fix namespaces
- `Authorities/integration_tool/app.py` — Streamlit UI for person/place review

---

## 📊 Current Status

**Editions processed:** 26 raw → 26 fresh corrected (0% Gemini damage, 0% NER loss from rebuild)  
**Facsimile elements cleaned:** 1199 `<pb/>` removed  
**Pipeline updated:** facsimile stripping now automatic  
**Edition management migration:** applied (raw archived, incoming canonicalized, header version/date policy enabled)  

**Current focus:** Phase 1 pilot implementation and review loop (task 3 + task 4)  
**Pending final decision:** strategy lock + full-batch rollout after pilot

---

## 🎯 Success Criteria

- [ ] **Task 3 done**: Document agreed-upon NER correction strategy, with rationale
- [ ] **Task 4 done**: Design decision on story-by-story processing, with trade-offs documented
- [ ] **Re-annotation done**: Entity loss < 5% (vs. current 70% from flawed Gemini run)
- [ ] **Diff reports clean**: No spurious large removals in any edition
- [ ] **All 26 editions fully processed**: annotated, corrected, linked, currencies added
- [ ] **Namespace fix applied**: All files ready for TEI Publisher

---

## Notes

- The fresh corrected files in `editions/incoming/` are clean, Gemini-free baselines
- Facsimile elements stripped from all files (both newly built and old ones left in archive)
- Retention guard is in place and ready to test on the next Gemini run
- Story-by-story processing may unlock better quality + parallelization
- Trial upload is intentionally deferred to post-NER validation (Phase 3)
