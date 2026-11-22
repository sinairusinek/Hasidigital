# From Transkribus to hasidic-stories.org: the steps for a new edition

This is the single checklist for bringing an edition to the site. Do the steps in order. **Steps 1–14 must all be done before an edition is offered for upload.** Step 14 is a script that checks this.

Why this file exists: in November 2026 the 8 April editions were uploaded with no topic tags. The old status report ([edition-pipeline-status.md](edition-pipeline-status.md)) had no topic-tagging step, so nothing stopped it. Topic tagging is now step 12, and the pre-upload check (step 14) fails any edition whose stories have no topic tags.

If a step is skipped on purpose, say so to Sinai before the upload and record it in the edition's `<revisionDesc>`. A step is never skipped silently.

## A. Source and structure

1. **Metadata.** Add the edition to `editions/edition-metadata.json`: title, `xml_filename`, Transkribus id, HebrewBooks or NLI id, and first edition. Also add it to the edition registry. The header in step 9 is built from this.
2. **Scan check.** Check for scan problems such as duplicate or torn pages. An `open` issue blocks the edition; an `after-ocr` issue does not.
3. **Transkribus work.** In collection 49371: layout, HTR, text correction, and the story tags marked by the segmenter (`story` with `rend` = non story / introduction / approbation / letters / marginal…, and `n`).
4. **TEI export with the story tags.** Use the TrpServer API (`POST /collections/49371/{doc}/export` with `doWriteTei`). Do **not** use "force valid TEI", which drops the story tags. Keep the raw export as `editions/incoming/{doc}/transkribus-export-{date}.xml` (tracked) and as the `.bak` next to it (gitignored).
5. **Story structure.**
   - `editions/scripts/prep_transkribus_export.py EXPORT.xml SLUG OUT.xml`. It decodes escapes, keeps `fw`/`head`/`note`, splits paragraphs at story tags and names the images.
   - Then `python Authorities/scripts/story_structure.py {doc}`.
   - Then `prep_transkribus_export.py --post`.
   - Add a `<head type="storyHead">` to each story and remove `<facsimile>`.
   - Check: `restore_pb.py` must find **every** export line in the result. The only exceptions are lines split at a story tag.
6. **Boundary review.** Run `editions/incoming/ready/check/boundary_check.py`. Wrap catchwords with `editions/scripts/mark_catchwords.py`; fix the divisions whose start does not match the story tags.

## B. Entities

7. **DictaBERT.** `python -m ner_pipeline.cli --input X.xml --no-gemini`. Check that the text and the `lb` count are unchanged, then commit this version: it is the base for any replay.
8. **NER correction.**
   - Command: `python -m ner_pipeline.cli --input X.xml --correct --max-removal-pct 60 --output-suffix ""`.
   - Choosing the engine: see memory `project-ner-correction-engine-comparison`.
   - **Paid runs: pilot first, then ask Sinai to approve the measured cost.** Keep the `gemini-correction-log-*.tsv`.
   - Then the text outside stories (Sinai, 2026-11-22: paratext and non-story text are corrected and linked too, though the site does not show them): `python3 editions/scripts/correct_non_story.py X.xml X.xml` with `GEMINI_THINKING_BUDGET=1024`. Linked tags are never dropped or re-spanned.
9. **Finish.** `editions/scripts/finish_corrected.py CORRECTED OUT BAK "note"`. It removes empty tags and FLAGGED notes, puts the root in the default namespace, writes the site header (`site_header.py`) and restores the page breaks (`restore_pb.py`). Then run `editions/scripts/hoist_pb.py OUT --write`: a page that starts with a running head gets its `<pb>` inside the `<fw>`, and the site's edition view never shows that page's image (Shaarei-Haemuna, 2026-11-22). The gate fails on it.
10. **Places.** `python3 editions/scripts/link_places.py X.xml --write` links by exact name variant, in stories and outside them. It does not touch the Kima Review file. The names it leaves unmatched go to the Kima pipeline (`editions/kimatch/`).
11. **Persons.** Link persons with Shidduch (`~/Documents/GitHub/Shidduch`). Not yet applied to any edition: say so at upload.

## C. Topics

12. **Topic tagging. Required before upload.**
    - Tag every division with `editions/llm-tagging/tagger.py`, the project's scheme. Its README has the vocabulary, the calibration and the caveats.
    - Write the tags into the XML as `<span ana="family:tag">`, in the form the curated editions use.
    - Mark the edition as LLM-tagged; the site labels the curation tier.
    - How:
      - `CLAUDE_CLI_BIN=… python3 editions/llm-tagging/tag_edition.py X.xml` runs one Opus call per division, on the Max plan, cached in `editions/llm-tagging/runs/{slug}/`. Divisions over 30,000 characters are skipped and listed.
      - Then `python3 editions/llm-tagging/writeback.py X.xml --write`. It writes the tags (confidence ≥ 2) as `<span ana="…" resp="#llm-tagging">תיוגים</span>` after each storyHead, and adds `respStmt xml:id="llm-tagging"` to the header. It never overwrites curated tags, and it reports any story division the tagger judged not to be a story.
      - Story divisions the tagger judges to be teachings or fragments get a genre tag, `not-a-hasidic-story:sermon` or `not-a-hasidic-story:halakhah` (Sinai's option b: keep the author's division and mark its genre). `runs/{slug}/genre.json` overrides it.
      - Stories found inside non-story divisions: `python3 editions/scripts/split_embedded_story.py X.xml --write`, **before** the write-back. Each such story becomes a story div nested in its paratext div (`subtype="in-…"`), so the site lists it. Then run its NER correction: `--correct --story-id ID1,ID2`.
      - Queue for the remaining editions: `editions/llm-tagging/tag_queue.sh`.
      - First run: Torat-Haramal, 2026-11-22.
    - The vocabulary is `editions/llm-tagging/vocab.tsv`, not `legitimate-tags.tsv`.
13. **Women tags.** These are the `women:*` tags (major / minor / catalyst / mention_only), part of the vocabulary in step 12. Check that they are present, because the women dashboard and the article read them.

## D. Publication

14. **Pre-upload check.** `python3 editions/scripts/preupload_check.py X.xml --images`. **It must print PASS.** It fails on any of:
    - XML or namespace errors;
    - missing header fields the site reads;
    - no page breaks, or missing images on the server;
    - a story with no `xml:id` or no storyHead;
    - duplicate ids or leftover FLAGGED notes;
    - no NER tags;
    - **stories without topic tags**;
    - malformed topic tags.
15. **Upload.**
    - Page images go to `/db/apps/HasidicImages`.
    - The XML goes to `/db/apps/HasidicStoriesServer/data`, by Sinai, with oXygen → Data Source Explorer → Import.
16. **Verify.** Compare each file with the server copy (canonical XML, `strip_text=True`). Check the site's header lookups (`api/parts/{doc}/json?...pubPlace`, `.../date`): both must return 200.
17. **Record.** Move the file to `editions/online/`, commit and push, and update the registry and status page.
