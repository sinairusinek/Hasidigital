# Hasidigital

Annotated TEI-XML corpus of Hasidic hagiographic story collections (18th–19th
century Hebrew), with the code that produces and analyses the annotation.

Stories are browsable at **<https://www.hasidic-stories.org/>**.

This repository is under active development: the corpus grows and the pipeline
changes.

---

## Reproducing a publication

Work tied to a publication is pinned to a git tag, and its data deposited in
Zenodo under a version DOI. Cite those, not `main`.

| Publication | Code tag | Data DOI |
|---|---|---|
| Mandel-Edrei, Rusinek & Sagiv, *Rethinking Women in Hasidic Literature* | [`women-article-v1.0.0`](https://github.com/sinairusinek/Hasidigital/releases/tag/women-article-v1.0.0) | [10.5281/zenodo.20524710](https://doi.org/10.5281/zenodo.20524710) |

**See [REPRODUCING.md](REPRODUCING.md)** for the pipeline steps, what is and is
not deterministic, and the caveats that belong with any count.

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

The women article counts **presence alone** (any `women:` tag); the four-way
gradation did not reach sufficient annotator agreement and is retained for
transparency rather than as a measure. See
[REPRODUCING.md](REPRODUCING.md#what-the-article-counts).

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

Before quoting any count from this repository:

- Tag counts are **floors, not censuses** (estimated candidate-retrieval recall
  87–93% per category), and the adjudication pass was **not fully
  human-validated**.
- `editions/online/` is a moving target. Cite the Zenodo DOI, not a path here,
  for anything that needs to stay reproducible.

The full caveats belong with any published statistic — see
[REPRODUCING.md](REPRODUCING.md#caveats-on-the-counts).

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
