# Hasidigital

Annotated TEI-XML corpus of Hasidic hagiographic story collections (18th–19th
century Hebrew), with the code that produces and analyses the annotation.

Stories are browsable at **<https://www.hasidic-stories.org/>**.

This repository is under active development. The corpus continues to grow and
the pipeline continues to change, so **work tied to a publication is pinned to a
tag** — see *Reproducing a publication* below.

---

## Reproducing a publication

### Rethinking Women in Hasidic Literature (Mandel-Edrei, Rusinek & Sagiv)

| | |
|---|---|
| **Code version** | tag [`women-article-v1.0.0`](https://github.com/sinairusinek/Hasidigital/releases/tag/women-article-v1.0.0) |
| **Data** | Zenodo, version DOI [10.5281/zenodo.20524710](https://doi.org/10.5281/zenodo.20524710) |
| **Corpus** | 9 editions, 652 stories; women present in 294 (45.1%) |

The tag marks the exact commit whose output the article reports. `main` has
moved on since; to reproduce the article's numbers, start from the tag:

```bash
git clone https://github.com/sinairusinek/Hasidigital.git
cd Hasidigital
git checkout women-article-v1.0.0
```

The Zenodo deposit is self-contained — it carries the nine annotated editions
and the derived tables, so the article's figures and proportions can be
recomputed from the deposit alone, without this repository. Use the repository
when you want to see *how* the annotation was produced rather than to re-analyse
its output.

**The pipeline, in order.** Each step reads the previous step's output:

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

Steps 1–3 call an LLM and are **not** deterministic; steps 4–5 are pure
functions of the XML and reproduce exactly. To verify the article's numbers
without re-annotating, run step 4 (or step 5) against the tagged XML.

---

## Layout

```
editions/
  online/                  the current annotated editions (TEI XML)
  women-criteria.md        women-annotation guidelines (the LLM prompt)
  women-5tier-*.tsv/md     women annotation: per-story labels + scheme
  story-duplicates.tsv     cross-edition near-duplicate story pairs
  tag-audit/               thematic-tag audit: methodology, per-category runs
  incoming/                editions being prepared (not yet in online/)
Authorities/
  Authorities.xml          person & place authority file
  scripts/                 pipeline scripts (XML writers, deposit builder)
  integration_tool/        Streamlit review app (annotation + curation UI)
ner_pipeline/              named-entity recognition & correction
topics/
  data/                    per-story topic assignments
  women_and_topics/        the women × topics strand: figures, notebooks
women_dashboard/           Streamlit dashboard for the women analysis
zenodo/                    assembled Zenodo deposits (built, not hand-edited)
```

Not in the repository, by design: page images, embedding caches, run logs, and
superseded dated edition snapshots. The authoritative frozen copies of the nine
article editions live in the Zenodo deposit, not here — `editions/online/` keeps
moving.

## Annotation

Each story is a TEI `<div type="story">` carrying story-level annotation on a
`<span ana="…">`:

- **Thematic tags** — `top-tag:sub-tag` (about 15 top-level categories, about 120
  sub-tags), e.g. `practice:pidyon_nefesh`, `social:poverty`. Tags mark the
  *presence* of a theme in a story, not its textual frequency.
- **Women's presence** — `women:major_character`, `women:catalyst_character`,
  `women:minor_character`, `women:mention_only`; a story with no women carries no
  `women:` tag.

The article counts **presence alone** (any `women:` tag). The four-way gradation
was an attempt to record *how substantially* a woman figures; it did not reach
sufficient annotator agreement and the article reports it as a negative result,
so the tiers are retained for transparency and reuse rather than as a measure.
See the deposit's `README.md` and `CHANGES.md` for the full history and caveats.

## Running the code

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Scripts that call an LLM expect credentials in the environment and are the only
non-deterministic part of the pipeline. The review app runs with:

```bash
cd Authorities/integration_tool && streamlit run app.py
```

## Caveats

Please read these before quoting any count from this repository:

- Thematic tag counts are **floors, not censuses**. The LLM-assisted tagging pass
  had an estimated candidate-retrieval recall of 87–93% per category.
- The adjudication pass was benchmarked against a 100-story human anchor but was
  **not fully human-validated**.
- Several category definitions were patched mid-audit; affected tags were audited
  under the patched definitions.
- `editions/online/` is a moving target. Cite the Zenodo DOI, not this directory,
  for anything that needs to stay reproducible.

## License

Code: MIT (see [LICENSE](LICENSE)).

Annotation, encoding and derived data: CC-BY 4.0. The underlying edition texts
are 19th-century works in the public domain; the annotation layer is the
contribution licensed here.

## Citation

If you use the corpus or the annotation, please cite the dataset:

> Mandel-Edrei, Chen, Sinai Rusinek, and Gadi Sagiv. *Rethinking Women in
> Hasidic Literature — Annotated Corpus of Nine Hasidic Story Editions
> (Hasidigital)*. Version 1.0.0. Zenodo, 2026.
> <https://doi.org/10.5281/zenodo.20524710>
