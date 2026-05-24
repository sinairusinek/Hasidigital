# Hasidigital → Kima matching workspace

Aligns **every toponym in the Hasidigital corpus** to the
[Kima Historical Gazetteer](https://data.geo-kima.org/) and prepares contributions
back to Kima. Adapted from the Dybbuk / *zibn-shtern* workflow:
**assemble → match the unlinked → route by decidability → curate donations**.

## Pipeline

```
1. assemble    Authorities/scripts/build_kimatch_inventory.py
2. match       kimatch match -c jobs/hasidigital.json -o matched.tsv --split-by-grade
3. route       Authorities/scripts/route_kimatch_results.py
4. donate      Authorities/scripts/export_kima_donations.py   (after review)
```

### 1. Assemble — `build_kimatch_inventory.py`
Scans `editions/online/*.xml` + `editions/incoming/ready/*.xml` for every
`<placeName>` (with/without `ref`) and loads all `<place>` entries from the
authority file. Aggregates occurrences, editions, and surrounding-paragraph
context per toponym; records Kima link status.
- `toponyms_all.tsv` — full inventory (1,977 distinct toponyms, all link states)
- `kimatch_input.tsv` — the **Kima-unlinked** subset (1,580): 210 authority places
  without a Kima id + 1,370 edition-only toponyms (mostly fresh NER from `incoming/ready`)

### 2. Match — Kimatch engine (run from the `Kimatch` repo venv)
```bash
cd /Users/sinairusinek/Documents/GitHub/Kimatch
.venv/bin/kimatch match -c /Users/.../Hasidigital/editions/kimatch/jobs/hasidigital.json \
    -o /Users/.../Hasidigital/editions/kimatch/matched.tsv --split-by-grade \
    --prior-resolutions /Users/.../editions/kimatch/confirmed_priors.tsv \
    --blocked-matches   /Users/.../editions/kimatch/wrong_matches.tsv
```
Wikidata-QID → exact name/variant → fuzzy trigram → phonetic (Yiddish→IPA +
Daitch-Mokotoff + Beider-Morse). Grades **A_autolink / B_review / C_review**.
Result (2026-05-23): 193 name_exact, 16 name_ambiguous, 540 fuzzy, 831 no_match;
grades A=105, B=78, C=1,397.

### 2b. Auto-reclassify — `auto_reclassify_kimatch.py`  (run from the Kimatch venv)
Shrinks the manual burden the way zibn-shtern's `auto_reclassify` does. Partitions
all 1,580 toponyms into mechanical buckets so a human only touches the remainder
(2026-05-23: **1,580 → 632 manual, 40%**). Writes `auto_reclassify/` + `manual_review.tsv`.
- `grade_a` (105) → spot-check loop
- `auto_linked` (187, 152 places) — confident single-candidate fuzzy (conf ≥ 0.9) +
  **collapsed sibling spellings** (e.g. מאגלניצא/מאגליניצא/מגלניצא → one Mogielnica).
  Safety-guarded (implausible region, short Hebrew homograph, concept words like
  ישראל/ציון fall to manual). **Still spot-checked** — fuzzy auto-links can be wrong
  (לויצק→Drahichyn), so they join the grade-A sheet via `spotcheck_grade_a.py`.
- `rejected` (6) — non-place stoplist (עכו״ם, פרעה…) → appended to `reject_stoplist.tsv`
- `quick_confirm` (100) — acronym tokens (mostly honorifics זצ״ל/ז״ל; a human bulk-rejects)
- `parked` (550) — single-occurrence no-match long tail
- `manual` (632) — the real review → the Kimatch app queue

### 3. Route — `route_kimatch_results.py`
The *zibn-shtern decidability test*: **can the reviewer decide from the row alone?**
- **OpenRefine** (yes — 1,228 rows) → `openrefine_review_queue.tsv`. Bulk
  candidate-pick / spelling / no-match residue. Reconcile `name_heb`/`name_rom`
  against Wikidata + Kima; fill `decision`, `chosen_kima_id`, `reviewer_notes`.
- **Kimatch app — Hasidigital Review** (needs context/cards): the review work is
  done in the **Kimatch app** (`/Users/.../Kimatch` → `Hasidigital Review` page),
  same card layout as the Zylbercweig/E-GERET pages — disambiguation cards with
  full Kima details (coords, NLI/VIAF/Wikidata/GeoNames, variants), context, and a
  Kima search box. Queue = everything that isn't a grade-A auto-link (1,475:
  16 ambiguous + 628 fuzzy + 831 no_match), filterable by status + source.
  Build/refresh the queue with `Authorities/scripts/build_kima_review_queue.py`
  (writes `<Kimatch repo>/data/hasidigital/kima_review.tsv` — **632 rows** from
  `manual_review.tsv` when auto-reclassify has run, else the full non-A set); decisions persist to
  `<Kimatch repo>/data/hasidigital/kima_decisions.json` (GitHub-synced).
  - The older Integration-Tool *Kima Review* page (`kima_review_queue.csv` +
    `kima_review_report.tsv`) is superseded by this and can be retired.
- **Auto-confirmed** (grade A — 105) → `auto_confirmed.tsv`. Seeds donations.

### 4. Donate — `export_kima_donations.py`
Curates a manual hand-off file for the Kima team (the Kima API is read-only).
Reads confirmed rows from `auto_confirmed.tsv` (grade A) + reviewer decisions in
the OpenRefine queue (`decision ∈ {confirm, map_to}`) + Streamlit report
(`action == map_to:<id>`). Emits, under `donations/`:
- `donations_variants.tsv` — new Hebrew/Yiddish spellings per Kima place
- `donations_external_ids_NEEDS_REVIEW.tsv` — Wikidata QIDs to gap-fill (verify
  Kima isn't already holding them; never overwrite)
- `donations.json` — grouped per place

> ⚠️ **Grade-A is a seed, not final.** It needs a light spot-check before donating:
> exact-name auto-links can still pick the wrong same-name place (e.g.
> `מעזעריטש`→Międzyrzec Podlaski vs the Maggid's Mezhyrichi; `גליל` as a generic
> "district" vs Galilee; `מינס`→Minas, Uruguay). Confirm before hand-off.

### Spot-checking grade A — `spotcheck_grade_a.py`
Nothing is ever written to the corpus automatically — grade is just the engine's
confidence tier, re-derived deterministically on every run. To make a human
correction *persist across re-runs*, review and feed it back:

```bash
python3 Authorities/scripts/spotcheck_grade_a.py          # build risk-ranked sheet
#   → spotcheck_grade_a.tsv (HIGH/MED/LOW). Review HIGH first; fill
#     decision = keep|reject  and  correct_kima_id (if keeping a wrong pick).
python3 Authorities/scripts/spotcheck_grade_a.py apply     # emit feedback files
```
Risk = implausible region for the corpus (Uruguay/Ethiopia/Wis…), common-word /
biblical homograph (`גליל`, `יהודה`, `חרן`), or a very short Hebrew spelling.
`apply` writes two durable channels:
- `confirmed_priors.tsv` (keeps) → re-run the match with
  `--prior-resolutions confirmed_priors.tsv` (locks the identity, breaks ties).
- `reject_stoplist.tsv` (rejects) → `build_kimatch_inventory.py` reads it
  automatically and drops those bare tokens from future matcher input (they stay
  in `toponyms_all.tsv` marked `stoplisted=yes` for transparency).

## Files
| file | what |
|---|---|
| `jobs/hasidigital.json` | Kimatch job config (fields, script=hebrew, lang=yiddish, donate block) |
| `toponyms_all.tsv` | full inventory, every toponym + link status |
| `kimatch_input.tsv` | unlinked subset fed to the matcher |
| `matched.tsv` (+ `.A_autolink/.B_review/.C_review`) | matcher output (CSV) |
| `openrefine_review_queue.tsv` | decide-from-row queue |
| `kima_review_queue.csv` / `kima_review_report.tsv` | context-needed queue (Streamlit) |
| `auto_confirmed.tsv` | grade-A seed for donations |
| `routing_summary.md` | counts per grade / status / route |
| `donations/` | Stage-2 hand-off files |

## Re-running
Re-run steps 1→3 any time editions or the authority file change. Pass a previous
confirmed-decisions file as `--prior-resolutions` to the matcher to reuse human
answers and break exact-name ties by identical spelling.
