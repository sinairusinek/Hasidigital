# Kimatch routing summary

Total unlinked toponyms matched: **1556**

## By grade
- A_autolink: 100
- B_review: 77
- C_review: 1379

## By match status
- name_exact: 187
- name_ambiguous: 15
- fuzzy: 535
- no_match: 819

## Routing (zibn-shtern decidability test)
- **OpenRefine** (decide from row alone): 1206 → `openrefine_review_queue.tsv`
- **Streamlit Kima Review** (needs context/map): 350 → `kima_review_queue.csv` + `kima_review_report.tsv`
- **Auto-confirmed (grade A, donation seed)**: 100 → `auto_confirmed.tsv`

Streamlit route = name_ambiguous, phonetic_mismatch-flagged, or multi-candidate fuzzy.
