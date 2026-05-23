# Kimatch routing summary

Total unlinked toponyms matched: **1580**

## By grade
- A_autolink: 105
- B_review: 78
- C_review: 1397

## By match status
- name_exact: 193
- name_ambiguous: 16
- fuzzy: 540
- no_match: 831

## Routing (zibn-shtern decidability test)
- **OpenRefine** (decide from row alone): 1228 → `openrefine_review_queue.tsv`
- **Streamlit Kima Review** (needs context/map): 352 → `kima_review_queue.csv` + `kima_review_report.tsv`
- **Auto-confirmed (grade A, donation seed)**: 105 → `auto_confirmed.tsv`

Streamlit route = name_ambiguous, phonetic_mismatch-flagged, or multi-candidate fuzzy.
