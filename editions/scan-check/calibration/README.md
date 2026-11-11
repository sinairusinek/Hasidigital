# Calibration of the scan check (2026-11-11)

Run from a scratch folder holding `fulldoc/` and `calib/` (the scripts use relative paths) with a venv that has
opencv-python-headless, numpy, scipy and rapidfuzz.

1. `fetch_fulldoc.py fulldoc`: every doc's Transkribus version history (collection 49371).
2. `count_current.py`: per page, whether the current models produced a version (Field Recognition 313993,
   LA 51962, PyLaia 52805) and whether a person edited it afterwards → `current-model-pages.tsv`.
3. `fetch_calib.py`: for finished pages with a 52805 version, that version's PAGE XML, the final PAGE XML and the image.
4. `calib_cer.py`: text CER of 52805 against the final text on lines present in both, the share of lines the
   RA deleted or redrew (`line_change`), and the scan measurements → `calib-pages.tsv`.
5. `analyse_calib.py`: correlations and flag-vs-CER tables.

Results (1,331 pages, 39 docs): text CER median 0.8%, mean 1.6%, 3.8% of pages above 5%. Optimistic, as some
pages were probably in 52805's training data. 13.7% of pages had over 10% of lines deleted or redrawn by the RA,
so line structure, not reading, is the larger error. Scan measurements predict CER only weakly (|Spearman rho|
at most 0.3: sharpness -0.25, off-paper colour +0.30), so the scan check targets hard defects.
