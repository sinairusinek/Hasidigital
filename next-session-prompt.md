# Next Session — Entity Review follow-up (2026-04-30)

## What was built this session

Three pipeline fixes:
1. **`ner_pipeline/annotation_inserter.py`** — fixed duplicate xml:id bug (exact-span dedup + `used_span_ids` guard); added `strip_annotations_from_heads()` to remove NER tags from `<head>` elements
2. **`ner_pipeline/gemini_corrector.py`** — added `_repair_json()`: handles trailing commas, Python literals (`None/True/False`), truncated arrays, markdown fences before retry
3. **`Authorities/scripts/scan_annotation_quality.py`** (new) — scans `editions/online/*.xml` for short_fragment / punct_only / xmlid_leak; output: `editions/online/annotation-quality-report.tsv` (1,135 flags); 7 xmlid_leak cases fixed in Shemen-Hatov.xml + SipurimUmaamarimYekarim.xml

Entity Review page built and wired into the Integration Tool:
- **`Authorities/integration_tool/entity_review_backend.py`** — loads Gemini diff + quality flags, groups by (norm_text, tag), assigns tiers (review / auto_accept / auto_reject), GitHub write-back
- **`Authorities/integration_tool/pages/entity_review.py`** — Streamlit page: tier sections, per-group + per-occurrence decision buttons, context rendering (RTL, whitespace-normalized), progress bar, filters
- Decisions save to: `editions/incoming/ready/entity-review-decisions.tsv`
- Key rendering fix: whitespace normalization (`re.sub(r"\s+", " ", ...)`) in `_ctx_html()` prevents tab chars from XML indentation triggering Markdown code-block rendering
- Default sort: within each tier, by number of occurrences descending

Start the app: `cd /Users/sinairusinek/Documents/GitHub/Hasidigital/Authorities/integration_tool && streamlit run app.py`
Then go to Review → Entity Review.

## Deferred question — answer before writing more code

**Are Entity Review decisions a logging tool or an editing tool?**

The Gemini correction step already wrote the corrected XMLs to disk. So:
- If **logging tool**: the reviewer simply records agreement/disagreement for audit. No XML is touched.
- If **editing tool**: a follow-up script reads `entity-review-decisions.tsv` and patches the XML files — removing entities the reviewer rejected, restoring ones Gemini wrongly removed.

This determines whether we need an apply-decisions script next.

## Next tasks (after answering the question)

1. **User tests Entity Review page** — try filters, make some decisions, verify save works, report UX issues
2. **If editing tool**: implement `apply_entity_decisions.py` — reads decisions TSV, patches `editions/incoming/ready/*.xml`
3. **Track A fixes on incoming editions**: `python Authorities/scripts/dicta_fixes.py --dir editions/incoming/ready/`
4. **Nisba fix + place linking**: run post-NER on ready/ editions
5. **Eser-Kedushot + Eser-Orot** (in `ready/check/`): human review of story structure flags → move to `ready/` → NER pipeline
6. **Torat-Haramal + Shaarei-Haemuna**: re-export from Transkribus without "force valid TEI" → full pipeline
