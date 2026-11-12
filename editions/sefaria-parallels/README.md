# Sefaria parallels (2026-11-12)

- `chasidut_titles.tsv`: Sefaria's Chasidut category (96 works), taken from https://www.sefaria.org/api/index/
- `align.py SCRATCH_DIR XML`: aligns our stories to Sefaria's Hebrew version (expects `SCRATCH_DIR/shivhei_v3.json` from `https://www.sefaria.org/api/v3/texts/Shivchei_HaBesht?version=hebrew`) and word-diffs each pair
- `shivhei_triage.tsv`: one-word differences in שבחי הבעש"ט after removing Sefaria's abbreviation expansions (הי'→היה), with a corpus-frequency guess at which side is wrong. The guess is a heuristic and has not been checked against the scan.
- `shivhei_scan_check.tsv`: every suspect from the triage (177), checked against the page image (Transkribus doc 963168). 39 OCR errors were fixed in `editions/online/Shivhei-Habesht.xml`. 9 look like errors in the print itself and wait for a decision on `<choice><sic>`. 9 could not be read.
