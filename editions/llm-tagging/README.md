# LLM tagging of uncurated editions

The project's own topic scheme is applied by Claude Opus 5.5 to the editions that no RA curated. The website will say that these editions are LLM-tagged. There are three tiers: the 9 RA-curated editions, the partly curated editions, and the LLM-tagged ones.

## Files

| File | What it is |
|---|---|
| `vocab.py` → `vocab.tsv` | The vocabulary: 144 tags used on at least 3 stories in the 9 curated editions' XML (2026-11-16). Sources of the definitions: 97 `written` (tag-definitions*.tsv), 4 `women-study` (zenodo/women-9ed README), 43 `derived` (written by Opus from the RA's usage, 6 example stories per tag; not reviewed by a person). Tags used on fewer than 3 stories are listed in `vocab-excluded.tsv`. |
| `tagger.py` | One call per TEI division. It first judges the **content**: one Hasidic story, several stories, a non-Hasidic story, a saying or teaching, paratext with or without a story, or a fragment. It then tags each story it finds, with verbatim Hebrew quotes as spans (checked against the text afterwards) or scope `story`, and a confidence of 1–3. It also lists concepts the vocabulary lacks. |
| `calibrate.py` → `calib/`, `calibration-report.md` | A blind run on 100 curated stories (stratified, twins excluded), scored against the RA's own tags (rebuilt as XML minus every audit insert: 4,894 pairs) and against RA+audit. |
| `adjudicate.py` → `adjudication.tsv` | An independent judge (Opus 5.5, the tag audit's presence prompt, one story–tag pair per call, blind to the source) on samples of the disagreements, so that "differs from the RA" is not read as "wrong". |

## Results (2026-11-16, 100 curated stories)

- **Unit check:** 82 single Hasidic stories, 5 with several stories, 7 sayings or teachings, 5 non-Hasidic stories, 1 fragment. Even curated divisions are not always one story.
- **Quotes:** 1,724 of 1,725 were found verbatim.
- **Raw agreement, confidence ≥ 2, against RA+audit:** precision 0.53, recall 0.67.
- **Adjudicated, confidence ≥ 2:**
  - The judge found **83%** of the tagger's extra tags present.
  - It found **38%** of the RA+audit tags that the tagger missed present.
  - It found **95%** of the agreed tags present.
  - Estimated tagger **precision 0.89, recall 0.90**. The RA+audit reference itself reaches about 0.61 recall.
- **Weak spots:**
  - recall in `social`: 16 of 23 missed social tags were judged present;
  - folkloristics story types: raw agreement around 0.4 (a genre judgment);
  - `practice` over-tagging: 55 of 68 extra practice tags were judged present, so most of the excess is real but not all.

## Caveats

These must go with any figure.

1. **The judge is the same model family as the tagger.** Shared readings and biases inflate the agreement. These figures are model-on-model estimates, not human validation, and no human validation is planned (see below).
2. 43 definitions are derived from usage, not written by the team, and the judge uses the same definitions.
3. The samples are small (60 / 200 / 120 judgments); per-category figures rest on 1–68 cases.
4. The RA+audit reference itself contains LLM-audit inserts (see `editions/tag-audit/methodology.md`).

Decision (Sinai, 2026-11-16): no RA and no validation rounds. Doubts and caveats are documented here. Questions go to Sinai and Gadi only when they are urgent or a matter of principle.
