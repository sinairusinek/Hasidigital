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

## Stage 2: automatic checks

Measure of a real error (`ink_score.py`): every letter on the page takes the tag of the box it sits in; a page
has a **consequential error** when 10 or more letters get a different tag than in FINAL. Splitting or merging
main-text blocks is not counted, since the TEI doesn't see it. By this measure, **121 of 209 Transkribus pages
(58%) have a real error**, and 7.7% of letters are mis-tagged; most of them are footnotes left as main text.

`layout_qa.py SUFFIX` first applies safe clean-ups (drop boxes with no ink, drop nested duplicates, merge
overlapping main-text), then flags pages. The flags look only at the automatic output and the image:
- text outside every box;
- page number, running head or catch-word missing (when the book normally has one), doubled, or off its band;
- a main-text block under a printed rule or under the catch-word (an untagged footnote);
- print size: smaller print at the foot of the main text, larger print inside it, body-size print in a heading;
- too many headings; and, when lines exist, blocks without lines and lines wider than their block.

Transkribus confidence scores were tested and do not separate good boxes from bad ones.

Result on Transkribus FR 313993 output (`score_flags.py fr`): **108 of 121 error pages caught (89%)**, with 156
of 209 pages flagged. The flag rate is high because the input is poor; the same checks will run on the local
layout in stage 3. The 13 that got through: 8 heading/main-text mix-ups, 5 with 12–25 letters outside a box.

`text_checks.py SUFFIX` runs **after HTR**: catch-word against the next page's first word (reading order, one
OCR slip allowed), and page numbers in sequence. On the FINAL text it disagrees on 16 of 73 page pairs; some
are real errors left in FINAL (שמן הטוב p123: the page number "קמ" boxed as main text), some are section titles.
