# Topics

Workspace for the topic/theme dimension of the Hasidic-stories corpus — the topic
taxonomy, per-story topic assignments, topic networks, and related analysis and
literature.

## Layout

- `data/` — topic taxonomy and assignment data
  - `topics.txt`, `translatetopics.txt` — topic list and translations
  - `10HasidicEditionsTopics.tsv` — per-story topic assignments (10 editions)
  - `hasidic-topic-networks.csv` — topic co-occurrence / network data
  - `labour_topic_articles.tsv` — labour-topic subset
- `analysis/` — notebooks
  - `Women_topics_2024-07-15.ipynb` — women × topic distribution, chi-square significance, Besht-vs-later comparison
  - `assign_topics_to_stories.ipynb` — topic assignment pipeline
- `women_and_topics/` — the women + topics strand
  - `women-in-folktales-computational-review.md` — deep-research literature review (computational gender-in-folktales studies, 2024–2026)
- `references/` — scholarship PDFs
  - Eklund, Hagedorn & Daranyi (2023), *Teaching Tale Types to a Computer* (Fabula) — computational tale-type/motif classification

## Notes

- Data files were copied from `~/Downloads` working copies; the canonical TSV was
  the most recent `10HasidicEditionsTopics-NoMinorMajor` variant (women tiers collapsed).
  Confirm whether the full-tier version should also live here.
