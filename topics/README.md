# Topics

Workspace for the topic/theme dimension of the Hasidic-stories corpus — the topic
taxonomy, per-story topic assignments, topic networks, and related analysis and
literature.

## Layout

- `computational-folkloristics-motif-review.md` — deep-research literature review of LLM-based motif/tale-type detection (computational folkloristics, 2024–2026)
- `data/` — topic taxonomy and assignment data
  - `topics.txt`, `translatetopics.txt` — topic list and translations
  - `10HasidicEditionsTopics.tsv` — per-story topic assignments, women tiers collapsed (`-NoMinorMajor` variant)
  - `10HasidicEditionsTopics-full-tier.tsv` — same assignments, full women tiers
  - `hasidic-topic-networks.csv` — topic co-occurrence / network data
  - `labour_topic_articles.tsv` — labour-topic subset
- `analysis/` — notebooks
  - `Women_topics_2024-07-15.ipynb` — women × topic distribution, chi-square significance, Besht-vs-later comparison
  - `assign_topics_to_stories.ipynb` — topic assignment pipeline
- `women_and_topics/` — the women + topics strand
  - `women-in-folktales-computational-review.md` — deep-research review (computational gender-in-folktales studies, 2024–2026)
  - `Women in Hasidic Literature - Between Close and Distant Reading - Draft 0.{docx,pdf}` — article draft (Mandel-Edrei, Rusinek, Sagiv)
  - `women_dashboard/` — Streamlit dashboard app + proposed charts
- `references/` — scholarship PDFs
  - Eklund, Hagedorn & Daranyi (2023), *Teaching Tale Types to a Computer* (Fabula) — computational tale-type/motif classification

## Notes

- Data files were copied from `~/Downloads` working copies (not previously version-controlled).
- `women_dashboard/` was relocated here from the repo root; if any launch script or
  docs reference the old `women_dashboard/` path, update them.
