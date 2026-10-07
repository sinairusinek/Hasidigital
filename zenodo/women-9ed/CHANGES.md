# Changes and corpus history

## Version 1.0.0 — nine editions

First published version. Covers the nine editions analysed in Mandel-Edrei, Rusinek and Sagiv, "Rethinking Women in Hasidic Literature: Between Close and Distant Reading": 652 stories.

### How this snapshot was produced

1. **Manual thematic annotation.** Research assistants tagged every story with story-level thematic tags from a schema developed jointly by historians and literary scholars (~15 top-level categories, ~120 sub-tags).
2. **Tag audit (2026-06).** An LLM-assisted sweep proposed additional tags for stories where the manual pass had missed a theme, followed by an adjudication pass over the candidates.
3. **Precision audit (2026-06-30).** Every LLM-proposed insertion was re-judged; **789 insertions were removed** as false positives. The dominant source of over-tagging was automatic propagation to near-duplicate stories (64% reject rate) rather than direct proposal (9%).
4. **Five-tier women re-annotation.** The earlier binary major/minor women tags were replaced by the five-tier scheme below, which distinguishes women who act in a narrative from women who are merely referred to.

### Women tiers in this version

| Tier | Stories |
|---|---|
| major | 38 |
| catalyst | 51 |
| minor | 103 |
| mention-only | 102 |
| none | 358 |
| **total** | **652** |

Derived: **any** = 294 (45.1%), **character** = 192 (29.4%).

> Earlier internal drafts of this dataset (unpublished) reported a women rate of roughly 26–27%. That figure came from the pre-audit corpus under the old binary scheme. The current numbers differ because of both the audited tag layer and the five-tier re-annotation, which identified more stories containing women overall.

### Relation to the article's text

Every count in the article was recomputed from the edition XMLs included in this deposit, using the same extractor that generates the article's figures. The deposit and the article are built from one source.

## Planned: version 2.0.0 — full corpus

A later version of this record will extend the dataset beyond the nine editions to the wider Hasidigital corpus. Version 1.0.0 remains citable at its own version DOI, so the article's statistics stay reproducible.
