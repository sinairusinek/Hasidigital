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
| Kehal Hasidim (`Khal-Hasidim.xml`) | Warsaw, 1866 | 254 | 118 (46.5%) | 80 (31.5%) |
| Kehal Kdoshim (`Khal-Kdoshim.xml`) | Lemberg, 1865 | 12 | 7 (58.3%) | 4 (33.3%) |
| Ma'ase Tsadikim (`Maase-Zadikim.xml`) | Lemberg, 1864 | 41 | 17 (41.5%) | 11 (26.8%) |
| Mif'alot ha-Tsadikim (`Mifalot-HaZadikim.xml`) | Lemberg, 1866 | 54 | 16 (29.6%) | 12 (22.2%) |
| Pe'er mi-Kdoshim (`Peer-MiKdoshim.xml`) | Lemberg, 1865 | 18 | 12 (66.7%) | 10 (55.6%) |
| Shivhei ha-Besht (`Shivhei-Habesht.xml`) | Kopys, 1814 | 216 | 89 (41.2%) | 52 (24.1%) |
| Shivhei ha-Rav (`Shivhei-Harav.xml`) | Lemberg, 1864 | 19 | 8 (42.1%) | 6 (31.6%) |
| Sipurei Tsadikim (`Sipurei-Zadikim.xml`) | Lemberg, 1864 | 14 | 5 (35.7%) | 3 (21.4%) |
| **Total** | | **652** | **290 (44.5%)** | **190 (29.1%)** |

## Annotation

### Thematic tags

Each story carries story-level thematic tags — about 15 top-level categories (`practice`, `ethics-and-emotions`, `social`, …) and about 120 sub-tags (`pidyon_nefesh`, `poverty`, `agunah`, …), written as `top-tag:sub-tag`. Tags mark the **presence of a theme in a story**, not the frequency of its textual occurrences. In the XML they are `<span ana="…">` elements on the story `<div>`.

### Women's presence — five tiers

| Tier | `ana` tag | Meaning | Stories |
|---|---|---|---|
| major | `women:major_character` | A woman is a central actor with her own agency | 36 |
| catalyst | `women:catalyst_character` | A woman triggers the plot or is the reason for events, without being a central actor | 52 |
| minor | `women:minor_character` | A woman appears in a small or peripheral role | 102 |
| mention-only | `women:mention_only` | A woman is referred to but does not act in the narrative | 100 |
| none | *(no `women:` tag)* | No women in the story | 362 |

The article reports **two** definitions of women's presence, and this dataset keeps both as separate columns rather than privileging either:

- **any** — all four women tiers, including mention-only: **290 / 652 (44.5%)**
- **character** — major + catalyst + minor, excluding mention-only: **190 / 652 (29.1%)**

## Table schemas

### `story_women.tsv`

| Column | Description |
|---|---|
| `story_id` | Story id; matches `<div xml:id="…">` in the edition XML |
| `edition` | Edition short name |
| `women_tier` | `major` / `catalyst` / `minor` / `mention_only` / `none` |
| `women_ana_tag` | The `ana` value carrying the tier in the XML; blank for `none` |
| `women_any` | `yes` if any tier incl. mention-only |
| `women_character` | `yes` if major, catalyst or minor |

### `story_tags.tsv`

One row per (story, tag) — the unit of the article's tag-level analysis.

| Column | Description |
|---|---|
| `story_id`, `edition` | As above |
| `top_tag`, `sub_tag`, `full_tag` | The tag, split and joined (`top-tag:sub-tag`) |
| `women_tier`, `women_any`, `women_character` | The story's women annotation, repeated for convenience |

### `tag_women_summary.tsv`

Per-tag aggregate — the table behind the article's Figures 2 and 3.

| Column | Description |
|---|---|
| `full_tag`, `top_tag`, `sub_tag` | The tag |
| `n_stories` | Stories carrying the tag |
| `n_women_any`, `pct_women_any` | Count and % with women under the **any** definition |
| `n_women_character`, `pct_women_character` | Count and % under the **character** definition |

## Reproducing the article's figures

`tag_women_summary.tsv` reproduces the per-tag rates directly. For example, the economic finding (article §Step 2) reads off the `poverty`, `business_advice` and `pidyon_nefesh` rows; the under-representation cases read off `coping_with_alien_thoughts`, `trembling`, `awe` and `inter_hasidic_master_disciple_relationship`.

Figure-generating code lives in the project repository (`topics/women_and_topics/figures/generate_figures.py`), which reads the same edition XMLs included here.

## Caveats

Please read these before quoting any statistic:

- Tag counts are **floors, not exact censuses**. The LLM-assisted tagging pass had an estimated candidate-retrieval recall of **87–93% per category**, so a tag's story count may understate its true extent.
- The adjudication pass was benchmarked against a 100-story human anchor but was **not fully human-validated**.
- Several category definitions were patched mid-audit; affected tags were audited under the patched definitions.
- The five-tier women annotation is LLM-produced with human curation. The **mention-only boundary is the least stable tier** — which is why the article reports both the *any* and *character* definitions, and why both are preserved here.
- A small number of anomalous tag tokens from the taxonomy-consolidation backlog are excluded from the article's figures.

## License

**CC-BY 4.0.** The underlying edition texts are nineteenth-century works in the public domain; the annotation layer, encoding and derived tables are the contribution licensed here. Please cite both the article and this dataset.

## Citation

> Mandel-Edrei, Chen; Rusinek, Sinai; Sagiv, Gadi. *Rethinking Women in Hasidic Literature: Between Close and Distant Reading — Annotated Corpus*. Version 1.0.0. Zenodo. https://doi.org/TBD
