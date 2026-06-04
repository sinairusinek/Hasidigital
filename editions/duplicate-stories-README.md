# Cross-edition duplicate-story detection

Embedding-based detection of near-duplicate stories across `editions/online/*.xml`.
Run on 27 editions / 1,376 stories on 2026-06-01.

## What's in this folder

| File | Purpose |
|---|---|
| `find_duplicate_stories.py` | Main pipeline. Loads stories, embeds with `intfloat/multilingual-e5-base` (chunked 1000 chars / 200 overlap, mean-pooled per story), computes pairwise cosine, writes pair + cluster TSVs. Embeddings cached at `.cache/story-dup-emb.npz` (ignored by git — regenerated on first run, ~90 s on CPU). |
| `plot_duplicate_network.py` | Network plot: editions as nodes (sized by #stories), edges weighted by #duplicate pairs. Outputs `edition-duplication-network.png`. |
| `story-duplicates.tsv` | One row per cross-edition duplicate pair: `sim, edition_a, story_a, edition_b, story_b, chars_a, chars_b`. |
| `story-duplicate-clusters.tsv` | One row per connected component (union-find): `cluster_id, size, n_editions, members`. |
| `edition-duplication-network.png` | The network visual. |

## Method

- Per-story vector = L2-normalized mean of chunk embeddings (e5 multilingual base).
- Pair similarity = cosine of story vectors.
- "Duplicate" = sim ≥ **0.99** AND the two stories live in **different editions**
  AND both stories have ≥ 100 chars (filters out near-empty stubs).
- Clusters formed by union-find over qualifying edges.

### Why 0.99

Same-genre Hasidic narratives in similar Hebrew sit at a high baseline similarity,
so the threshold has to be tight. Empirically:

| threshold | clusters | stories in clusters | largest cluster |
|---:|---:|---:|---:|
| 0.999 | 1 | 2 | 2 |
| 0.995 | 45 | 90 | 2 |
| **0.990** | **112** | **224** | **2** |
| 0.987 | (~115) | ~230 | 6 |
| 0.985 | 130 | 286 | **25** (← false-positive blob from formulaic openings) |
| 0.95 | 73 | 859 | **713** (← entire genre fuses into one component) |

The jump from "all clusters are clean pairs" (≤ 0.99) to "a 25-story
transitively-connected blob appears" (0.985) marks where formulaic
opening-sentence overlap starts polluting recall. 0.987 still surfaces some
genuine multi-edition retellings (e.g. the R' Adam manuscripts cycle, 6 stories
across 5 editions) but mixes them with false positives.

## Headline numbers (2026-06-01 run, sim ≥ 0.99)

### All 27 online editions
- Total stories: **1,376**
- Duplicate clusters: **112** (all pairs)
- Stories in a duplicate cluster: **224**
- Unique stories after dedup: **1,264**

### 9 article editions (Shivhei-Habesht, Mifalot-HaZadikim, Adat-Zadikim, Shivhei-Harav, Sipurei-Zadikim, maase-zadikim, Khal-Kdoshim, PeerMikdoshim, Khal-Hasidim)
- Total stories: **652**
- Duplicate clusters: **111** (all pairs)
- Stories in a duplicate cluster: **222** (≈ 34 %)
- Unique stories after dedup: **541**

Only **1** inter-edition duplicate involves an edition outside the 9
(Mifalot-HaZadikim ↔ Sipurei-Kdoshim). Essentially all the inter-edition
repetition in our corpus is among the 9.

## Findings

- **Khal-Hasidim (1866) is the hub** — it shares duplicates with every other
  one of the 8 article editions. It behaves like an anthology of the 1814
  Shivhei-Habesht and the 1860s collections (consistent with being the latest
  of the 9, published 1866).
- **Adat-Zadikim (24 stories) is fully contained in Khal-Hasidim** — all 24
  of its stories have a near-duplicate in Khal-Hasidim.
- **maase-zadikim** has 19 of its 41 stories duplicated in Khal-Hasidim
  (~46 %).
- Top edges:

| pairs | editions |
|---:|---|
| 49 | Khal-Hasidim ↔ Shivhei-Habesht |
| 20 | Khal-Hasidim ↔ Adat-Zadikim |
| 19 | Khal-Hasidim ↔ maase-zadikim |
|  9 | Khal-Hasidim ↔ Sipurei-Zadikim |
|  6 | Khal-Hasidim ↔ PeerMikdoshim |
|  6 | Khal-Hasidim ↔ Shivhei-Harav |
|  2 | Khal-Hasidim ↔ Khal-Kdoshim |
|  1 | Mifalot-HaZadikim ↔ Sipurei-Kdoshim |

- **No triplets at 0.99.** Genuine multi-edition cycles only emerge at
  ≥ 0.987 (R' Adam manuscripts: 6 stories / 5 editions; Reb Sender / Vilna
  anecdote: 3 stories / 3 editions), but at that band false positives mix in
  and pairs need manual confirmation.

## Open questions (deferred — not addressed in this session)

1. **How should duplicates be treated in distant-reading statistics?**
   - Should women-presence / tag-frequency stats be computed on the full
     1,376 / 652 set (each retelling counted) or on the deduped 1,264 / 541
     set (one canonical version per story cluster)?
   - If deduped: which copy is canonical? Earliest? Longest? Most-annotated?
   - Note that **Khal-Hasidim alone is 39 % of the 9-edition corpus**, and a
     large slice of it is reused material — un-dedup'd stats overweight a
     compilation.

2. **How should duplicates be presented on hasidic-stories.org?**
   - Display siblings (link from each instance to its near-duplicates)?
   - Group as a single "story" with multiple "witnesses"?
   - This intersects with the existing "similar stories references" TODO
     (task 22 in MEMORY pending list).

3. **The 0.987–0.99 band (~57 pairs) likely contains real paraphrased
   retellings mixed with formulaic false positives.** Worth an LLM-judged
   pairwise pass to expand recall before any of the above decisions.

4. **Re-run after the remaining 18 editions get their full annotations** and
   after any text-normalization changes (e.g. canonicalization of
   apostrophes/gershayim) — embeddings are sensitive to surface form, so
   normalization may close some borderline pairs that currently sit at 0.985–0.99.
