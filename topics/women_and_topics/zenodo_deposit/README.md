# Women in Hasidic Literature — Dataset

Companion dataset to **Mandel-Edrei, Rusinek & Sagiv, "Women in Hasidic Literature: Between Close and Distant Reading"** (forthcoming).

## What's in the deposit

```
data/
  topics_9editions.tsv         Topic annotations for all 4,878 story-tag rows in the 9 editions,
                               with women_in_story as a binary (Yes / No Women) column.
  women_binary_source.tsv      Per-story provenance: claude_new_5tier → women_in_story_binary.
  editions/                    The 9 TEI-XML editions analysed in the article.
```

## The 9 editions

| Edition | File |
|---|---|
| Adat Zadikim | `editions/Adat-Zadikim.xml` |
| Khal Hasidim | `editions/Khal-Hasidim.xml` |
| Khal Kdoshim | `editions/Khal-Kdoshim.xml` |
| Maase Zadikim | `editions/Maase-Zadikim.xml` |
| Mifalot HaZadikim | `editions/Mifalot-HaZadikim.xml` |
| Peer MiKdoshim | `editions/Peer-MiKdoshim.xml` |
| Shivhei HaBesht | `editions/Shivhei-Habesht.xml` |
| Shivhei HaRav | `editions/Shivhei-Harav.xml` |
| Sipurei Zadikim | `editions/Sipurei-Zadikim.xml` |

Total: 652 individual stories across the 9 editions.

## `topics_9editions.tsv` schema

| Column | Description |
|---|---|
| `div - xml:id` | TEI division id for the first occurrence of the story; blank on continuation rows |
| `Edition` | Edition short name |
| `unique` | Edition (only set on the first row of a story) |
| `Story` | Story id, matches the TEI `<div xml:id="…">` |
| `full tag` | `top-tag:sub-tag`, the manual topic annotation; one row per (story, tag) |
| `top-tag` | Topic category (e.g. `practice`, `social-relations`, `women`) |
| `sub-tag` | Sub-category (e.g. `healing`, `with_the_authorities`) |
| `women-in-story` | Binary: `Yes` if a woman appears as a character; `No Women` otherwise. See note below. |

## "Women in story" — binary cutoff

The article uses a binary presence indicator. It is derived from an internal five-tier annotation (LLM-assisted, human-reviewed) using a **presence-strict** cutoff:

| 5-tier value | Binary |
|---|---|
| `major-character` | **Yes** |
| `catalyst-character` | **Yes** |
| `minor-character` | **Yes** |
| `mention-only` | No Women |
| `no-women` | No Women |

A `mention-only` story names or refers to a woman without her appearing as an actor in the narrative; these are excluded from "women in story" so the indicator tracks narrative presence rather than mere reference.

The full five-tier labels are in `women_binary_source.tsv` for transparency. The 9 edition XMLs themselves carry the full five-tier values on the story-level `<span ana="…">` topic span, using these ana tags:
`women:major_character`, `women:catalyst_character`, `women:minor_character`, `women:mention_only`. Stories with no women carry no `women:*` tag.

## License

CC-BY 4.0. Please cite the article and the Zenodo dataset DOI.

## Citation

> Mandel-Edrei, [given name]; Rusinek, Sinai; Sagiv, [given name]. (forthcoming).
> *Women in Hasidic Literature: Between Close and Distant Reading — Dataset.*
> Zenodo. https://doi.org/TBD

## Provenance and reproducibility

This dataset was generated from the Hasidigital project repository. The transformation scripts are in `Authorities/scripts/` in that repository:

- `apply_women_5tier_to_xml.py` — write 5-tier women tags to XML
- `build_zenodo_women_deposit.py` — assemble this deposit

See `CHANGES.md` for the precise transformations applied to produce this snapshot.
