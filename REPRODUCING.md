# Reproducing a publication

This repository is under active development: the corpus grows and the pipeline
changes. Work tied to a publication is therefore **pinned to a git tag**, and the
data it reports is **deposited in Zenodo under a version DOI**. Cite those, not
`main` and not a path in this repository.

Each publication below gives its tag, its DOI, and the steps to re-derive its
numbers.

| Publication | Code tag | Data DOI |
|---|---|---|
| Mandel-Edrei, Rusinek & Sagiv, *Rethinking Women in Hasidic Literature* | [`women-article-v1.0.0`](https://github.com/sinairusinek/Hasidigital/releases/tag/women-article-v1.0.0) | [10.5281/zenodo.20524710](https://doi.org/10.5281/zenodo.20524710) |

---

## Rethinking Women in Hasidic Literature

Chen Mandel-Edrei, Sinai Rusinek and Gadi Sagiv, "Rethinking Women in Hasidic
Literature: Between Close and Distant Reading."

| | |
|---|---|
| **Code version** | tag [`women-article-v1.0.0`](https://github.com/sinairusinek/Hasidigital/releases/tag/women-article-v1.0.0) (commit `9a1145c`) |
| **Data** | Zenodo, version DOI [10.5281/zenodo.20524710](https://doi.org/10.5281/zenodo.20524710) |
| **Corpus** | 9 editions, 652 stories |
| **Headline** | women present in **294 stories (45.1%)** |

### Two ways in

**From the Zenodo deposit — simplest.** The deposit is self-contained: it carries
the nine annotated editions and the derived tables, so every figure and
proportion in the article can be recomputed from it alone, without this
repository. `tag_women_summary.tsv` reproduces the per-tag rates behind the
article's Figures 2 and 3 directly.

**From this repository — to see how the annotation was produced.** Start from the
tag, not `main`:

```bash
git clone https://github.com/sinairusinek/Hasidigital.git
cd Hasidigital
git checkout women-article-v1.0.0
pip install -r requirements.txt
python topics/women_and_topics/figures/generate_figures.py
```

That prints the headline counts and writes the article's figures. Verified to
reproduce `652 stories; any: 294 (45.1%); char: 192 (29.4%)` from a clean clone
of the tag.

### The pipeline, in order

Each step reads the previous step's output:

| Step | Script | Produces |
|---|---|---|
| 1. Annotation criteria | [`editions/women-criteria.md`](editions/women-criteria.md) | the prompt given to the annotators (human and LLM) |
| 2. Annotate | [`Authorities/integration_tool/run_5tier_full_9.py`](Authorities/integration_tool/run_5tier_full_9.py) → [`women_llm.py`](Authorities/integration_tool/women_llm.py) | `editions/women-5tier-9editions-full.tsv` |
| 3. Write to XML | [`Authorities/scripts/apply_women_5tier_to_xml.py`](Authorities/scripts/apply_women_5tier_to_xml.py) | `women:*` spans in `editions/online/*.xml` |
| 4. Figures & numbers | [`topics/women_and_topics/figures/generate_figures.py`](topics/women_and_topics/figures/generate_figures.py) | the article's figures, `story_tags_post_audit.tsv`, [`numbers-for-article.md`](topics/women_and_topics/figures/numbers-for-article.md) |
| 5. Build the deposit | [`Authorities/scripts/build_zenodo_deposit.py`](Authorities/scripts/build_zenodo_deposit.py) | `zenodo/women-9ed/` |

Step 4 is the authority for every statistic in the article: it reads the edition
XML directly, and step 5 re-derives the deposit through the same extractor, so
the deposit cannot silently disagree with the published figures.

**Steps 1–3 call an LLM and are not deterministic. Steps 4–5 are pure functions
of the XML and reproduce exactly.** To verify the article's numbers without
re-annotating, run step 4 against the tagged XML; re-running steps 1–3 will not
return bit-identical labels.

### What the article counts

The article counts **presence alone** — whether a story refers to a woman at
all, whether she acts, serves as a catalyst, or appears only in passing. In the
TEI that is any `women:` tag; in the deposit's tables it is the `women_present`
column.

The four-way gradation (`major` / `catalyst` / `minor` / `mention_only`) was an
attempt to record *how substantially* a woman figures. It did not reach
sufficient annotator agreement — between humans or between LLMs — and the
article reports that as a negative methodological result. The tier labels ship
in the deposit as `women_tier` and `women_graded_character` so the result is
inspectable and the labels are reusable, **not** as an alternative measure.
`women_graded_character` (192, 29.4%) should not be quoted as the corpus's women
rate.

### Known issues in this version

Published data is frozen, so these stand on the record:

- The **Sabbath-chicken twins** `Maase-Zadikim_0002` (`mention_only`) and
  `Khal-Hasidim_0018` (`none`) are labelled inconsistently. They are
  near-duplicate tellings of one story and fall just below the 0.98 similarity
  threshold used to detect twins, so the consistency sweep missed them.
- That sweep is a **floor, not a census**: it only compares pairs above 0.98, so
  further inconsistencies may remain among looser parallels.

### Caveats on the counts

- Thematic tag counts are **floors, not censuses**: the LLM-assisted tagging pass
  had an estimated candidate-retrieval recall of 87–93% per category.
- The adjudication pass was benchmarked against a 100-story human anchor but was
  **not fully human-validated**.
- Several category definitions were patched mid-audit; affected tags were audited
  under the patched definitions.
- The `mention_only` boundary is the least stable distinction in the annotation —
  which is why the article does not rest on it.

Fuller history and caveats are in the deposit's `README.md` and `CHANGES.md`, and
in [`topics/women_and_topics/figures/numbers-for-article.md`](topics/women_and_topics/figures/numbers-for-article.md).

---

## Adding a publication

When a new paper is pinned:

1. Tag the commit whose output it reports:
   `git tag -a <paper>-v1.0.0 <sha> -m "…"` and push the tag.
2. Publish the data as a **new version** of the Zenodo concept record
   ([10.5281/zenodo.20524709](https://doi.org/10.5281/zenodo.20524709)) so earlier
   versions stay citable:
   `python Authorities/scripts/zenodo_upload.py --prod --version <v> --new-version-of 20524709`
3. Add a row to the table at the top and a section below it.

Tag the commit that actually produced the numbers, even if the repository was
tidied afterwards — the tag's job is to mark what the paper reports, not to look
clean.
