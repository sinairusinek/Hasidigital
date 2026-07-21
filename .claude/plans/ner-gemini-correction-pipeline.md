# NER Gemini Correction Pipeline — Build Plan

## Status: Ready to build (prompt finalized 2026-03-14)

## What exists already
- `ner_pipeline/gemini_correction_prompt.txt` — finalized system prompt (3 test iterations)
- `ner_pipeline/gemini_correction.py` — stub (exists but likely empty/partial, needs implementation)
- `ner_pipeline/annotation_inserter.py` — has `extract_existing_entities_simple()` for pulling annotations out of XML
- `ner_pipeline/pipeline.py` — main pipeline orchestration
- `ner_pipeline/cli.py` — CLI entrypoint

## What needs to be built

### 1. `ner_pipeline/gemini_corrector.py` (core module)
- Load prompt from `gemini_correction_prompt.txt`
- `correct_entities(plain_text, existing_entities, model="gemini-2.0-flash")` → corrected entity list
  - Calls Gemini API via `google-generativeai` (or `google-genai` SDK)
  - Sends: passage text + existing entities JSON
  - Returns: `{"entities": [...], "corrections": [...]}`
- `locate_entities_in_text(entities, plain_text)` — maps entity text strings back to char offsets
  - Try exact match first
  - Fuzzy fallback: strip geresh/gershayim (׳/״/"/) and try again
  - Log unmatched to a review file

### 2. `ner_pipeline/pipeline.py` — add `--correct` mode
- New `run_correction_pass(input_path, output_path)` function:
  1. Parse XML
  2. Check `has_existing_annotations()` — if not, error out (use full NER mode instead)
  3. `extract_existing_entities_simple()` → get current entities + plain text
  4. Strip existing annotations from XML (`strip_existing_annotations()`)
  5. Chunk plain text by div[@type="story"] or by token limit
  6. For each chunk: call `correct_entities()`
  7. Locate corrected entities in text → get char offsets
  8. Re-insert via standoffconverter (`insert_annotations()`)
  9. Save output XML

### 3. `ner_pipeline/cli.py` — add `--correct` flag
```
python -m ner_pipeline.cli --input editions/incoming/Kokhvei-Or2025-11-29.xml --correct
python -m ner_pipeline.cli --input editions/incoming/ --correct --batch
```

### 4. Streamlit page: `Authorities/integration_tool/pages/ner_annotator.py` (future)
- File picker for unannotated/annotated editions
- Run correction pass in-browser
- Show diff: original vs. corrected entities (green=added, red=removed, yellow=relabelled)
- Human override before writing back to XML

## Key design decisions
- **Chunking strategy**: chunk by `<div type="story">` where possible (natural unit).
  If no story divs, chunk by ~2000 chars at sentence boundaries.
  Pass 2-3 stories per Gemini call to give context.
- **Fuzzy matching**: normalize by stripping `׳ ״ " '` and trying again;
  also try prefix stripping (מ/ל/ב/ו/ה). Log failures to `ner_pipeline/unmatched_entities.jsonl`.
- **Ref preservation**: existing `ref` attributes must be preserved on entities that survive correction.
  Map by (original_text, label) → ref from the pre-correction entity list.
- **API key**: read from `GOOGLE_API_KEY` env var or `.env` file at repo root.
- **Model**: default `gemini-2.0-flash` (fast, cheap). Override via `--model` flag.

## File targets (annotated editions to process first)
Priority order — smaller files first for testing:
1. `Kokhvei-Or2025-11-29.xml` (265 entities) ← test file used in prompt development
2. `Khal-Kdoshim2025-06-22.xml` (139 entities)
3. `Maasiot-Pliot2026-01-10.xml` (355 entities)
... then the remaining 18

## Unannotated editions (need full DictaBERT + correction pass)
- `Dvarim-Yekarim2025-12-01.xml`
- `Hitgalut-HaZadikim2025-12-01.xml`
- `Shemen-Hatov2025-12-01.xml`
- `SipureiAnsheiShem2025-12-01.xml`
- `SipurimUmaamarimYekarim_Hebrewbooks_org_3804.xml`
