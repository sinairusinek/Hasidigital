# Layout test set (2026-11-11)

Can a free local layout step replace Transkribus Field Recognition, and can automatic checks replace the RA's
layout check? The RA's corrected FINAL pages are the answer key.

## The set: 274 pages (`test-set.tsv`)

Runs of 5 consecutive pages, so the catch-word and page-number checks have neighbours. Two-column,
footnote and large-initial pages were preferred, so the set is harder than an average book.

| Set | Pages | What it has | Used for |
|---|---|---|---|
| A | 209 from 13 books, 1898–1907 (Warsaw, Piotrków, Podgórze, Sighet) | Field Recognition 313993 output + FINAL; 61 pages also LA 51962 output | region tags and lines; Transkribus baseline |
| B | 40 from 4 Lemberg books, 1864–66 | FINAL lines only (no region tags in these books) | lines |
| C | 15 from בוצינא דנהורא, Lemberg 1879 | FINAL tagged with older models (244709) | region tags, no current-model baseline |
| D | 10 from מסעות הים (doc 20149799, pp. 20–29) | image only, nothing finished | large initial words, judged by eye |

No finished page from the 1860s has a current-model (313993) version, so Lemberg has no Transkribus baseline
unless the current models are re-run there (about 50 credits; not done).

`xml/<docId>/<page>.{fr,la,final}.xml` are the PAGE XML versions. The images are outside the repo in
`~/Documents/Hasidigital-data/layout-test/<docId>/<page>.jpg` (279 MB).

## Scripts

- `select_pages.py`: chooses the pages. Run from the scratch folder with `fulldoc/` and `fr_profile.tsv` (see
  `../scan-check/calibration/`).
- `fetch_test_set.py FULLDOC_DIR [IMAGE_DIR]`: downloads images and XML. Uses no credits.
- `measure_baseline.py`: how much the RA changed → `baseline-pages.tsv`.

## Baseline to beat (what the RA had to fix)

Regions, Field Recognition 313993 against FINAL, 209 pages:
- 165 pages (79%) needed real fixes; 15 (7%) only had stray boxes on empty paper removed; 29 (14%) were untouched.
- Of 1,810 automatic regions: 132 relabelled (most often main-text → footnote), 286 removed in a split or merge,
  222 stray boxes removed; 261 regions drawn by hand.
- Across all 840 finished FR-313993 pages, the share with real fixes is about 70%; the set is harder by design.
- Per book it ranges from 1/10 (שבע רצון) to 30/30 (תפארת חיים) and 25/25 (שמן הטוב, two columns).

Lines, LA 51962 against FINAL, 61 pages (תפארת חיים, שמן הטוב, התגלות הצדיקים):
- 92% of automatic lines kept; 325 deleted and 354 added by hand, of 4,099 final lines.
- 37 pages (61%) had over 10% of their lines deleted or added.
- These are hard books, and only 61 pages have a current line-model version.
