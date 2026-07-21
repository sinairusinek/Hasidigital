# Changes applied to produce this deposit

This deposit is a curated snapshot of the Hasidigital editions and their topic annotations, prepared to accompany Mandel-Edrei, Rusinek & Sagiv's article on women in Hasidic literature.

## Women annotation — five-tier scheme

The article's "women in story" indicator is derived from a five-tier annotation produced by Claude (LLM) with human curation, replacing the earlier binary `women:major_character` / `women:minor_character` manual tags. The new five-tier categories are:

| Tier | Meaning | Count |
|---|---|---|
| `women:major_character` | Woman is a central actor with her own agency | 33 |
| `women:catalyst_character` | Woman triggers the plot or is the reason for events but is not a central actor | 54 |
| `women:minor_character` | Woman appears in a small or peripheral role | 103 |
| `women:mention_only` | Woman is referenced but does not appear as an actor | 100 |
| *(no tag)* | No women in the story | 362 |

The five-tier values are written on each story's topic span (`<span ana="…">`) in the edition XMLs included in this deposit.

For the article itself and the TSV in this deposit, a **presence-strict binary** is used:

- **Yes** = major + catalyst + minor (190 / 652 stories, ~29 %)
- **No Women** = mention-only + no-women (462 / 652 stories, ~71 %)

Stories where a woman is only named or referenced without participating in the narrative are excluded from the binary, so the indicator measures narrative presence rather than mere reference.

`women_binary_source.tsv` carries the full 5-tier value per story alongside the derived binary, so any downstream analysis can recover the finer-grained labels.

## Reproducibility

The transformations were produced by two scripts in `Authorities/scripts/` of the source repository, runnable in order:

```
apply_women_5tier_to_xml.py --apply
build_zenodo_women_deposit.py
```
