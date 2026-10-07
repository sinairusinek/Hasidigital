# Rethinking Women in Hasidic Literature — Annotated Corpus

Companion dataset to:

> Mandel-Edrei, Chen; Rusinek, Sinai; Sagiv, Gadi. *Rethinking Women in Hasidic Literature: Between Close and Distant Reading* (forthcoming).

Part of the **Hasidigital** project — <https://www.hasidic-stories.org/>.

## Versioning

This is **version 1** of the Hasidigital story-corpus dataset. It covers the nine editions analysed in the article above. The annotated corpus continues to grow; later versions of this same Zenodo record extend it to further editions.

Cite the **version DOI** to reproduce the article's statistics; cite the **concept DOI** to point at the dataset in general.

## Contents

```
editions/                   The 9 annotated TEI-XML editions
story_women.tsv             Per-story women annotation (5-tier + both binaries)
story_tags.tsv              Long format: one row per (story, tag)
tag_women_summary.tsv       Per-tag story counts and women rates
README.md
CHANGES.md
```

## The corpus

**652 stories** across 9 editions.

| Edition | Imprint | Stories | Women (any) | Women (character) |
|---|---|---|---|---|
| Adat Tsadikim (`Adat-Zadikim.xml`) | Lemberg, 1864 | 24 | 18 (75.0%) | 12 (50.0%) |
| Kehal Hasidim (`Khal-Hasidim.xml`) | Warsaw, 1866 | 254 | 121 (47.6%) | 81 (31.9%) |
| Kehal Kdoshim (`Khal-Kdoshim.xml`) | Lemberg, 1865 | 12 | 7 (58.3%) | 4 (33.3%) |
| Ma'ase Tsadikim (`Maase-Zadikim.xml`) | Lemberg, 1864 | 41 | 17 (41.5%) | 11 (26.8%) |
| Mif'alot ha-Tsadikim (`Mifalot-HaZadikim.xml`) | Lemberg, 1866 | 54 | 16 (29.6%) | 12 (22.2%) |
| Pe'er mi-Kdoshim (`Peer-MiKdoshim.xml`) | Lemberg, 1865 | 18 | 12 (66.7%) | 10 (55.6%) |
| Shivhei ha-Besht (`Shivhei-Habesht.xml`) | Kopys, 1814 | 216 | 89 (41.2%) | 52 (24.1%) |
| Shivhei ha-Rav (`Shivhei-Harav.xml`) | Lemberg, 1864 | 19 | 8 (42.1%) | 6 (31.6%) |
| Sipurei Tsadikim (`Sipurei-Zadikim.xml`) | Lemberg, 1864 | 14 | 6 (42.9%) | 4 (28.6%) |
| **Total** | | **652** | **294 (45.1%)** | **192 (29.4%)** |

## Annotation

### Thematic tags

Each story carries story-level thematic tags — about 15 top-level categories (`practice`, `ethics-and-emotions`, `social`, …) and about 120 sub-tags (`pidyon_nefesh`, `poverty`, `agunah`, …), written as `top-tag:sub-tag`. Tags mark the **presence of a theme in a story**, not the frequency of its textual occurrences. In the XML they are `<span ana="…">` elements on the story `<div>`.

### Women's presence — the article's measure

The article records **presence alone**: whether a story refers to a woman at all, whether she acts in the narrative, serves as a catalyst, or appears only in passing. That is the `women_present` column, and it is the measure behind every figure and statistic in the article:

- **women present: 294 / 652 (45.1%)**

This is a deliberately modest measure. It does not claim to capture how much narrative weight a woman carries — that is recovered by close reading, not by counting. It is, however, the one judgement independent readers of these stories proved able to agree on, and it can be checked by anyone who consults the corpus.

### The graded scheme — a superseded attempt, retained for transparency

The project first tried to record not merely whether a woman is present but how substantially, on the five-tier scale below. **That attempt did not succeed**: sufficient agreement could not be reached between human annotators, nor between LLM annotators, and the article reports it as a negative methodological result rather than using it.

The tier labels are nevertheless shipped here — as `women_tier`, and collapsed into `women_graded_character` (major + catalyst + minor, excluding mention-only) — so that the failure is inspectable rather than merely asserted, and so the labels can be reused by anyone who wants to attack the boundary problem differently. **They are not the article's measure, and `women_graded_character` should not be quoted as the corpus's women rate.**

| Tier | `ana` tag | Meaning | Stories |
|---|---|---|---|
| major | `women:major_character` | A woman is a central actor with her own agency | 38 |
| catalyst | `women:catalyst_character` | A woman triggers the plot or is the reason for events, without being a central actor | 51 |
| minor | `women:minor_character` | A woman appears in a small or peripheral role | 103 |
| mention-only | `women:mention_only` | A woman is referred to but does not act in the narrative | 102 |
| none | *(no `women:` tag)* | No women in the story | 358 |

Collapsing the tiers to `women_graded_character` would give 192 / 652 (29.4%) — reported here only for completeness, and **not** the article's figure.

## Table schemas

### `story_women.tsv`

| Column | Description |
|---|---|
| `story_id` | Story id; matches `<div xml:id="…">` in the edition XML |
| `edition` | Edition short name |
| `women_tier` | `major` / `catalyst` / `minor` / `mention_only` / `none` |
| `women_ana_tag` | The `ana` value carrying the tier in the XML; blank for `none` |
| `women_present` | **The article's measure.** `yes` if the story refers to a woman at all |
| `women_graded_character` | From the superseded graded scheme: `yes` if major, catalyst or minor. Not the article's measure |

### `story_tags.tsv`

One row per (story, tag) — the unit of the article's tag-level analysis.

| Column | Description |
|---|---|
| `story_id`, `edition` | As above |
| `top_tag`, `sub_tag`, `full_tag` | The tag, split and joined (`top-tag:sub-tag`) |
| `women_tier`, `women_present`, `women_graded_character` | The story's women annotation, repeated for convenience |

### `tag_women_summary.tsv`

Per-tag aggregate — the table behind the article's Figures 2 and 3.

| Column | Description |
|---|---|
| `full_tag`, `top_tag`, `sub_tag` | The tag |
| `n_stories` | Stories carrying the tag |
| `n_women_present`, `pct_women_present` | **The article's measure**: count and % of the tag's stories that refer to a woman |
| `n_women_graded_character`, `pct_women_graded_character` | The same under the superseded graded scheme; not the article's measure |

## Reproducing the article's figures

`tag_women_summary.tsv` reproduces the per-tag rates directly. For example, the economic finding (article §Step 2) reads off the `poverty`, `business_advice` and `pidyon_nefesh` rows; the under-representation cases read off `coping_with_alien_thoughts`, `trembling`, `awe` and `inter_hasidic_master_disciple_relationship`.

Figure-generating code lives in the project repository (`topics/women_and_topics/figures/generate_figures.py`), which reads the same edition XMLs included here.

## Caveats

Please read these before quoting any statistic:

- Tag counts are **floors, not exact censuses**. The LLM-assisted tagging pass had an estimated candidate-retrieval recall of **87–93% per category**, so a tag's story count may understate its true extent.
- The adjudication pass was benchmarked against a 100-story human anchor but was **not fully human-validated**.
- Several category definitions were patched mid-audit; affected tags were audited under the patched definitions.
- The five-tier graded labels are LLM-produced with human curation, and the **mention-only boundary is their least stable distinction** — which is why the graded scheme was abandoned and the article counts presence alone. Treat `women_tier` and `women_graded_character` as exploratory.
- A small number of anomalous tag tokens from the taxonomy-consolidation backlog are excluded from the article's figures.

## License

**CC-BY 4.0.** The underlying edition texts are nineteenth-century works in the public domain; the annotation layer, encoding and derived tables are the contribution licensed here. Please cite both the article and this dataset.

## Citation

> Mandel-Edrei, Chen; Rusinek, Sinai; Sagiv, Gadi. *Rethinking Women in Hasidic Literature: Between Close and Distant Reading — Annotated Corpus*. Version 1.0.0. Zenodo. https://doi.org/TBD
