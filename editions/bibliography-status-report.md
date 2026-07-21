# Bibliography Status Report
**Project:** Historical Digital Analysis of Hasidic Stories Until 1914
**Date:** 2026-03-10
**Prepared by:** automated analysis of `Hasidic-editions-status - hasidic editions.tsv`

---

## 1. Overview of the Edition Dataset

The main working spreadsheet (`Hasidic-editions-status - hasidic editions.tsv`) contains **268 edition rows** representing **144 distinct works**. This dataset was compiled from multiple sources: the Kitsis catalogue, the Bibliography of the Hebrew Book (BHB), the DiJeSt database, and manual research.

### Language distribution
| Language | Count |
|----------|-------|
| Hebrew (`heb`) | 238 |
| Yiddish (`yid`) | 22 |
| Judeo-Arabic (`jrb`) | 1 |
| Missing | 7 |

The corpus is heavily Hebrew-dominant. Yiddish editions are clustered in the later period (1900–1914), particularly cheap popular pamphlets ("groschenshriften") produced in Piotrków and Warsaw.

---

## 2. Work Completed in This Session

### DBid Matching against the Editions-Report (Oct 2025)

The `Editions-Report-20251008-1730-xlsx.tsv` (264 rows, all with DiJeSt `Id` values) was cross-referenced against the 41 edition rows in the main TSV that were missing their `DBid`.

**Matching method:**
1. Primary match: unique (kima_ID, Gregorian year) pair
2. Secondary match: same kima+year candidates filtered by title similarity

**Results:**

| Outcome | Count |
|---------|-------|
| Auto-filled (clear match) | **11** |
| Truly ambiguous — two identical records in report | 4 pairs (8 rows) |
| Not found in Editions-Report | 19 rows |
| Probable match (needs human confirmation) | 1 row |
| Unresolvable without title | 2 rows |
| No kima ID (cannot match automatically) | 6 rows |

**The 11 auto-filled DBids** (already written to the TSV):

| Row | Title | Year | Kima | DBid filled |
|-----|-------|------|------|------------|
| 15 | שבחי הבעש"ט | 1907 | 166 (Lvov) | 3579 |
| 26 | סיפורי מעשיות | 1909 | 953 (Warsaw) | 3588 |
| 33 | מעגלי צדק | 1850 | 953 (Warsaw) | 3595 |
| 64 | קהל חסידים | 1875 | 166 (Lvov) | 3649 |
| 97 | בוצינא דנהורא | 1884 | 166 (Lvov) | 3671 |
| 99 | בוצינא דנהורא | 1889 | 250 (Piotrków) | 3656 |
| 108 | שבחי צדיקים | 1895 | 953 (Warsaw) | 3665 |
| 140 | דרך האמונה ומעשה רב | 1925 | 953 (Warsaw) | 3695 |
| 158 | עין הבדולח | 1901 | 250 (Piotrków) | 3707 |
| 228 | אהל נפתלי | 1911 | 953 (Warsaw) | 3772 |
| 233 | פאר וכבוד | 1912 | 1638 (Mukachevo) | 3777 |

---

## 3. Remaining DBid Issues (30 rows still missing)

All issues are documented in `editions/issues-for-review.tsv` with detailed notes. A summary by category:

### 3a. Truly Ambiguous — Identical Twin Records in DiJeSt (4 cases)
The Editions-Report contains two records with the same title, year, and kima, making automatic disambiguation impossible. These need to be resolved by inspecting the DiJeSt database directly.

| Row | Title | Year | Candidates |
|-----|-------|------|-----------|
| 17 | שבחי בעל שם טוב | 1850 | DBid 3572 vs 3573 |
| 23 | סיפורי מעשיות | 1881 | DBid 3584 vs 3585 |
| 252 | דרך צדיקים | 1913 | DBid 3788 vs 3789 |
| 264 | דור ודור ודורשיו | 1914 | DBid 3799 vs 3800 |

**Action needed:** Check hasidic-stories.dh-dev.com to distinguish the two records (e.g. by printer, format, or NLI scan link).

### 3b. Probable Match — Needs Human Confirmation (1 case)

| Row | Title | Year | Probable DBid | Reason |
|-----|-------|------|---------------|--------|
| 177 | דברים ערבים חלק שני | 1905 | **4113** | Report has DBid=4113 "דברים ערבים ב" (part 2) vs DBid=3721 "דברים ערבים" (part 1) |

**Action needed:** Confirm that DBid=4113 corresponds to this edition and enter it.

### 3c. Unresolvable Without Title (2 cases)
These rows have a kima ID but no `Final Edition Title for the DB`, making it impossible to select from among the many report candidates.

| Row | Year | Kima | Candidates in report |
|-----|------|------|---------------------|
| 154 | 1891 | 953 (Warsaw) | 72 records for kima=953; none in year 1891 |
| 202 | 1908 | 250 (Piotrków) | 4 records: DBid 3743, 3749, 3744, 3746 |

**Action needed:** Identify the correct title and add it to the main TSV, then retry matching.

### 3d. Not Found in Editions-Report (19 rows)
These rows have no matching record in the Oct-2025 Editions-Report export, either because the book is not yet entered in DiJeSt, or because the kima ID in the spreadsheet is incorrect.

**Sub-categories:**

*Kima not in report at all (3 rows):*
- Row 16: שבחי הבעש"ט (1816, kima=675 — Karetz). Not in report.
- Row 39: מעשה נפלאה ונורא... (1863, kima=6918). Not in report.
- Row 38: מגיד שיחות (no date, no kima).

*Year/title mismatch — kima exists but book absent or kima wrong (16 rows):*
- Row 35.5: מסעות הים (1850, kima=1703) — report shows only שבחי הבעש"ט at kima=1703/1850
- Row 77: מפעלות הצדיקים (1866, kima=166) — 1866 candidates at kima=166 are unrelated titles
- Row 89/empty: ספורי קדושים (1911, kima=250) — three 1911 candidates, none match
- Rows 133/133.2: קבוצת יעקב (1896/1897, kima=571/424) — years absent from report
- Row 160: ספורי נפלאות (1901, kima=957) — year absent, titles differ
- Row 210: שיחת חולין (1909, kima=1638) — year absent from kima=1638 entries
- Rows 237/238: נפלאות בעל שם טוב / נפלאות בית לוי (1911, kima=250) — titles absent
- Row 242: סיפורי קדושים (1866, kima=250) — year predates all kima=250 entries
- Rows 243–245: עטרת זקנים, אהלי צדיק, תפארת מנחם (1911) — titles absent from respective kima entries
- Row 249: תפארת היהודי (1912, kima=250) — title absent from 1912 entries
- Row 260: סיפורי יעקב חלק שני (1913, kima=166) — no 1913 entries at kima=166
- Row 266: ספרן של צדיקים (1914, kima=953) — title absent from 1914 entries

**Action needed:** These books are likely absent from the Oct-2025 export of DiJeSt. They may need to be added to DiJeSt, or the kima IDs in the spreadsheet require correction. Lower priority — address via hasidic-stories.dh-dev.com when time permits.

---

## 4. Other Outstanding Issues in the Dataset

### Date Issues (6 rows)
| Row | Title | Problem |
|-----|-------|---------|
| 5 | שבחי הבעש"ט | Hebrew date תר-? (approx. 1840s) — no precise year |
| 75 | סדר הדורות מתלמידי הבעש"ט | No date in any column |
| 128/130 | מעשיות פליאות / מעשיות נוראים ונפלאים | No date in any column |
| 38 | מגיד שיחות | Year unknown, no Hebrew date |
| 191 | ספר אהבת שלום תנינא | No date in any column |

### Place Ambiguities (5 rows)
Five rows have uncertain or conflicting publication place data (e.g. "Warsaw?,Warsaw?",  "Krakow?,Tarnow"). These require verification against the original scanned title pages.

### Language Issues (8 rows)
- 7 rows completely missing language code
- 1 row marked "כנראה heb" (probably Hebrew, uncertain) — appears in two editions of קבוצת יעקב

Note: The TSV uses `heb`, `yid`, `jrb` as codes. Missing language should be entered before final bibliography generation.

### Title Issues (5 rows)
- 4 rows missing `Final Edition Title for the DB`
- 1 row with conflicting titles between BHB and Kitsis sources

---

## 5. Current Data Quality Summary

| Field | Total | Complete | Missing / Issues |
|-------|-------|----------|-----------------|
| DBid | 268 | 238 (89%) | **30** missing |
| Title | 268 | 264 (99%) | 4 missing |
| Date | 268 | 262 (98%) | 6 missing |
| Pub place | 268 | 265 (99%) | 3 missing, 5 ambiguous |
| Language | 268 | 261 (97%) | 7 missing |
| Kima ID | 268 | 245+ (91%) | ~23 missing or uncertain |

---

## 6. Next Steps (in recommended order)

1. **Confirm DBid=4113** for row 177 (דברים ערבים חלק שני) — quick check.
2. **Resolve 4 ambiguous twin-record cases** (rows 17, 23, 252, 264) by inspecting DiJeSt directly.
3. **Add titles** for rows 154 and 202 to enable matching.
4. **Fill missing languages** for 7 rows (see issues-for-review.tsv).
5. **Clarify ambiguous places** for 5 rows.
6. **Resolve 19 not-found cases** — lower priority; requires either DiJeSt data entry or kima correction.
7. **Regenerate `editions/bibliography.xml`** from the cleaned TSV once the above are addressed.

---

## 7. Files

| File | Status |
|------|--------|
| `Hasidic-editions-status - hasidic editions.tsv` | **Updated** — 11 DBids filled in this session |
| `editions/issues-for-review.tsv` | **Updated** — all 50 rows have detailed review notes |
| `editions/bibliography.xml` | **Stale** — needs regeneration |
| `Editions-Report-20251008-1730-xlsx.tsv` | Source for matching; 264 records (Oct 2025) |
