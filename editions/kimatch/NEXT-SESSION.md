# Kima toponym pipeline — handoff & remaining TODOs

Snapshot for starting a fresh session. Full design is in `README.md`; this is the
"where we are + what's left" page.

## Where things stand (2026-05-24)
- **Pipeline built & live**: assemble → match → auto-reclassify → review → donate.
  `Authorities/scripts/`: build_kimatch_inventory · auto_reclassify_kimatch ·
  spotcheck_grade_a · build_kima_review_queue · apply_context_rules ·
  export_kima_donations · normalize_edition · route_kimatch_results.
- **Review surface = Kimatch app → "Hasidigital Review"** (card layout, per-mention
  for items with candidates, flat+search for no_match, sorted by frequency, Hebrew
  display names). Queue = **624 manual rows** (15 ambiguous + 406 fuzzy + 203 no_match).
- **Decisions live on the Kimatch repo `data` branch** (`data/hasidigital/kima_decisions.json`):
  currently גאליציען + the Maggid-of-Mezritch prefills (39 mentions → 19737).
- **Editions cleaned**: `incoming/ready` got `normalize_edition.py` (117 ישראל + 339
  bad NER tags removed; quality flags 434→17 residual). `online/` were already clean.
- **Engine**: matcher now supports `--prior-resolutions` (confirm) and
  `--blocked-matches` (suppress wrong picks). Spot-check verdicts: keep /
  not_a_place (→reject_stoplist) / wrong_match (→wrong_matches.tsv).

> **After any change: Reboot the Streamlit Cloud app** (Manage app → Reboot) — a
> browser refresh won't reload the cached backend or the queue/decisions.

## Remaining TODOs

### A. Review labor (human, in the app / sheets)
1. **Spot-check grade-A auto-links** — `editions/kimatch/spotcheck_grade_a.tsv`
   (287 rows; do the **33 HIGH** first). Set `decision` = keep | not_a_place |
   wrong_match (+ `correct_kima_id` if keeping a wrong pick). Then
   `python3 Authorities/scripts/spotcheck_grade_a.py apply`.
2. **Quick-confirm acronyms** — `editions/kimatch/auto_reclassify/quick_confirm.tsv`
   (100 rows; mostly honorifics זצ״ל/ז״ל → bulk reject).
3. **Work the 624 manual rows** in the app (per-mention disambiguation for the
   ambiguous, search+map for no_match). Decisions auto-save to the `data` branch.

### B. Apply links back to the sources (NOT yet built — biggest open piece)
4. Write confirmed Kima links into:
   - **edition XML**: add `ref="#H-LOC_x"` to bare `<placeName>` occurrences. The
     per-mention `rid = <edition>#<n>` is the locator.
   - **authority file**: add `<idno type="Kima">` to the ~210 unlinked places; create
     new `<place>` entries for edition-only toponyms.
   Source of truth: `data` branch `kima_decisions.json` + `confirmed_priors.tsv`.
   Repoint the existing `apply_kima_*.py` scripts at these.

### C. Donate to Kima (after spot-check)
5. Re-run `export_kima_donations.py` once `confirmed_priors.tsv` has keeps → hand
   `donations/` to the Kima team (manual; API is read-only). Includes new Hebrew
   variants (e.g. add **נישחיז** as a variant of Kima/H-LOC_198 "Volia").

### D. Finish normalizing the rest of the editions
6. Run `normalize_edition.py --dir <d>` on the editions still in the NER backlog
   before they enter the pipeline: the 4 incoming not-yet-"ready", plus
   Torat-Haramal & Shaarei-Haemuna (need Transkribus re-export) and
   Eser-Kedushot/Eser-Orot (story-structure review). Clear the 17 residual quality
   flags in `incoming/ready` (manual).
7. **Re-run the full pipeline** after edition changes:
   inventory → match (`--prior-resolutions confirmed_priors.tsv --blocked-matches
   wrong_matches.tsv`) → auto_reclassify → build_kima_review_queue →
   apply_context_rules → push `data` branch. This also re-includes the 5 wrong_match
   names (רמה/מנשה/הרר/מינס/הית), now auto-pre-marked.

### E. Authority enrichment (improves matching + donations)
8. The ~210 unlinked authority places — many lack a Hebrew name (Volia, Ołpiny,
   Prussia…). Add Hebrew variants harvested from corpus surface forms; this lifts
   match rates and feeds variant donations.

### F. Persons (parallel track, mostly not started)
9. Shidduch / person linking (step 08) is separate and largely unstarted — the same
   assemble→match→review→donate shape for `<persName>`.

### G. Ops
10. Add a reviewer: Cloud secrets `reviewers = [...]` + Settings → Sharing (email).

### Done this arc (for reference)
Pipeline build · auto-reclassify (1,580→624 manual) · Kimatch-app review page w/
cards+per-mention+search · ישראל & NER-garbage cleanup + `normalize_edition` ·
context-rule prefill (Maggid) · spot-check reject split (not_a_place/wrong_match) ·
matcher `--blocked-matches` · Hebrew display names.
