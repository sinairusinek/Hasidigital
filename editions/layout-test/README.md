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

## Stage 3: free local layout (2026-11-11)

Every option is scored on books it never saw: YOLO was trained twice (`yolo_regions.py`, folds in the script),
each time leaving out the test books it is then scored on. Transkribus 313993 was probably trained on pages of
these same finished books, so the comparison favours it.

**Boxes and labels** (`ink_score.py`, letter by letter against FINAL, 209 set-A pages):

| Option | Pages with an error | Letters mislabelled |
|---|---|---|
| Transkribus Field Recognition 313993 | 121 (58%) | 7.7% |
| Geometric rules on Kraken lines alone (`rules.py label`) | 186 (89%) | 8.6% |
| YOLO (yolo11n, unseen books) | 143 (68%) | 8.5% |
| **YOLO + footnote rules + boxes for stray lines** | 129 (62%) | **5.0%** |

**Lines** (`line_score.py`; each letter goes to the baseline just under it, since older FINAL outlines can sit
half a line off the print):

| Option | 61 pages with a Transkribus line version | all 224–264 pages |
|---|---|---|
| Transkribus LA 51962 | 9.6% wrong; 43% of pages >10% | n/a |
| Kraken default model | 8.9%; 26% | 11.7% |
| **Kraken, lines cut where they cross from one YOLO box into another** (`fix_lines.py`) | **3.1%; 8%** | 6.8% (224 pages) |

Kraken's main error is running one line across both columns (611 of 612 merges were side by side). Cutting at
wide spaces made things worse (spaces inside ordinary lines); cutting at box borders fixes it. Extending short
lines added 0.1 points and is left out. Weak books for lines: בית ישראל (Hebrew and Yiddish, 41% wrong),
עשר אורות (19%), שבע רצון (17%).

**Line post-correction, second round (2026-11-12, `fix_lines.py --join --refill`, now used by `run_layout.py`).**
What the 724 wrong lines (all 224 pages) actually were: 41% one line in two or more pieces, 27% "merged" (mostly
the RA's own line stopping a few letters short of the print, which the score counts against us), 24% partly
missing, 7% missing. Three fixes:
- keep Kraken's baseline points when a line is cut (the old step drew a straight line from end to end, so sloping
  and curved lines lost letters);
- join pieces on one baseline within a box unless the gap is a gutter. A gap counts as a gutter when the lines
  above and below mostly stop there too: in two columns every line has its partner across the gutter, while in one
  column the lines run straight through. Joining across boxes merged columns again (11% wrong) and is not used;
- add a line wherever a row of at least five letters, four letter heights wide, has no line (Kraken skipped it).
  Fully missing lines went from 49 to 2.

| | wrong lines (all 224) | set A, not counting RA-short lines | pages >10% wrong |
|---|---|---|---|
| before | 724 (6.8%) | 566 (5.5%) | 49 |
| after | 560 (5.2%) | 403 (3.9%) | 31 |

Set C (a book the settings were not tuned on): 18 → 5 wrong lines of 461. What is left: 245 splits, mostly a large
opening word or a centred phrase set apart, and lines cut at a false box border on one-column pages; 101 partly
missing; 59 merged. בית ישראל (Hebrew and Yiddish) still holds a quarter of the errors.

**Kraken line model fine-tuned on our pages (2026-11-12, `kraken_gt.py`; now used by `run_layout.py`).**
Ground truth: every page whose lines a person checked in Transkribus. Many more pages had their layout corrected
than were marked FINAL, so the version histories of all 174 documents were compared: for each page, the lines of
the last line-tool version against the latest lines. Pool (`gt-pool.tsv`): 1,837 FINAL pages plus 476 pages not
marked final whose lines were corrected, in 18 books where that happened on at least half the pages (checked by
eye); 2,313 pages, 104,000 lines, 63 documents (48 works). Test pages and the two pages either side of them are
left out. Fine-tuned from Kraken's default model (`ketos segtrain -i blla.mlmodel --resize both`, early stopping,
lag 5) on the Mac GPU: 12 epochs, about 8 hours; best epoch 8 (validation mean IU 0.584, baseline F1 0.966).

| set A, 209 pages | wrong lines | not counting RA-short lines | pages >10% wrong |
|---|---|---|---|
| default model, raw | 11.4% | 10.0% | 56 |
| fine-tuned, raw | 4.9% | 3.3% | 15 |
| default + cut at YOLO borders + join + refill | 5.4% | 3.9% | 27 |
| **fine-tuned + cut at YOLO borders + join + refill** | **3.9%** | **2.1%** | **10** |

Set C: 2.6% → 0.2% raw (461 lines). Headings and text out of order: 34 → 30 pages; tags unchanged (they come from
YOLO). Caveat: every test book also has other pages in the training pool, so this measures new pages of known
books; on books never seen the gain may be smaller. Remaining misses on 40 pages checked by eye: no line missed
entirely; the left end of a large-type title (9561376 p1); on בית ישראל the model's baselines run under the
letters where the RA drew them through, which the score counts as partly missed.

**Reading order (2026-11-12, `order_score.py`; the rule is `rules.reading_order`, written by `page_xml`).**
Until now our pipeline wrote no reading order and none of the scores looked at it. The score: our lines are
matched to FINAL lines through their letters; walking our lines in our order, the lines that break the longest
increasing run of FINAL positions are out of place. Only headings, main text and footnotes count: running heads,
page numbers and catch-words are not shown on the site and are taken out of the stories.

How the RA orders a page (224 test pages): page number and running head first; two columns right then left (all
86 cases); footnotes always after all main text; a catch-word printed above the footnotes comes before them (all
26 cases), otherwise last; on pages with two columns each column ends with its own catch-word.

The rule: page number, running heads; then headings and text, split into bands at any box that spans two columns
lying side by side (a heading over both columns), columns right to left and each top to bottom; then a catch-word
above the footnotes; then footnotes; then a catch-word below them. Regions are placed by where their lines are,
not by their boxes (detected boxes nest), and only boxes about three lines tall count as columns. The same rule
orders the lines inside a region, so pieces of one cut line are read right to left.

| | pages with headings or text out of order | lines out of place |
|---|---|---|
| RA regions and tags, our rule | 7 / 224 | 41 / 10,696 |
| our pipeline, no order written (before) | 207 | 3,496 |
| our pipeline with the rule | 43 | 186 |
| same, on the joined and refilled lines | 34 | 181 |

What is left comes from layout errors, not the rule: main text tagged footnote (read after everything else), and
column boxes drawn too long, which cut full-width lines in two. Two flags in `run_layout.py` point at these pages:
a footnote line above a main-text or heading line, and two or more lines cut at a box border where the letters run
on with no gap. Together they flag 66 of 224 pages and catch 26 of the 34 pages with an order error, and 11 of the
12 with five or more lines out of place; the 8 missed have 1 to 4 lines out of place. A third flag, whether the
order changes when the rule's thresholds are nudged, caught almost nothing and was dropped.

Loghi was not tested: it ships as Docker images built for CUDA GPUs, and this Mac has neither.

**Checks on the pipeline's output** (`score_flags.py`): 117 of 142 error pages caught (82%), but 80% of pages
flagged. On these footnote-heavy books most pages have some error, so the checks don't yet cut the pages to
review much. Per book: `pipeline-by-book.tsv`. The main remaining error is footnote/main-text confusion.

**Speed on the Mac:** YOLO under a second per page; Kraken ~15–20 s per page with 4 processes. Training a
YOLO model: about 45 minutes, once.

**Paragraph regions (2026-11-12, `paragraphs.py`; called from `rules.tidy`).** The RA split main text into one
region per paragraph. Our old `tidy` merged main-text boxes stacked in a column, so pages came out sometimes per
paragraph and sometimes per column. Now the detector's boxes are kept and each main-text region is cut where a row
stops short of the left margin, a blank gap opens, or the next row starts with a larger word (fitted on the test set;
indentation is not a paragraph mark in most of these books). Paragraphs matched against FINAL: old tidy 32%, the
detector's boxes 92%, with the splitter 92% on our lines and 94% on the RA's lines (story books alone: 95% / 97%).
What is left: front matter, בית ישראל, some detector over-splits, and paragraphs ending at the full margin with ":",
which only the text shows. `upload_layout.py DOCID NOTE` uploads a book's layout as new versions, skipping every page
someone has saved since our last upload.

**Pipeline for new books:** `run_layout.py DOCID` (page-instructions, holds, deskew/crop, YOLO trained on all
tagged books, Kraken, line cutting, footnote rules, PAGE XML in the original image's coordinates, checks).
`build_layout_review.py DOCID` makes the review page of flagged pages.
