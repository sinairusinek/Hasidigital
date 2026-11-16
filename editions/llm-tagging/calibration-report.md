# Tagger calibration on 100 curated stories

unit kinds: {'hasidic_story': 82, 'several_stories': 5, 'saying_or_teaching': 7, 'non_hasidic_story': 5, 'continuation_or_fragment': 1}
quotes not found verbatim: 1/1725

| set vs reference | predicted | reference | agree | precision | recall | F1 |
|---|---|---|---|---|---|---|
| conf>=1 vs RA | 1380 | 682 | 523 | 0.38 | 0.77 | 0.51 |
| conf>=1 vs RA+audit | 1380 | 912 | 650 | 0.47 | 0.71 | 0.57 |
| conf>=2 vs RA | 1161 | 682 | 503 | 0.43 | 0.74 | 0.55 |
| conf>=2 vs RA+audit | 1161 | 912 | 613 | 0.53 | 0.67 | 0.59 |
| conf>=3 vs RA | 636 | 682 | 380 | 0.60 | 0.56 | 0.58 |
| conf>=3 vs RA+audit | 636 | 912 | 435 | 0.68 | 0.48 | 0.56 |

| category | predicted | RA+audit | agree | precision | recall |
|---|---|---|---|---|---|
| characters-and-roles | 64 | 42 | 32 | 0.50 | 0.76 |
| ethics-and-emotions | 168 | 145 | 96 | 0.57 | 0.66 |
| experience | 41 | 42 | 21 | 0.51 | 0.50 |
| folkloristics | 59 | 56 | 24 | 0.41 | 0.43 |
| kabbalah | 6 | 7 | 5 | 0.83 | 0.71 |
| knowledge | 8 | 19 | 4 | 0.50 | 0.21 |
| not-a-hasidic-story | 8 | 13 | 2 | 0.25 | 0.15 |
| practice | 331 | 172 | 141 | 0.43 | 0.82 |
| social | 184 | 168 | 114 | 0.62 | 0.68 |
| spaces | 30 | 17 | 13 | 0.43 | 0.76 |
| supernatural | 147 | 149 | 104 | 0.71 | 0.70 |
| times | 72 | 42 | 30 | 0.42 | 0.71 |
| women | 43 | 37 | 27 | 0.63 | 0.73 |

Most frequent concepts the tagger found missing from the vocabulary:
- blood libel (4)
- haunted house (2)
- imprisonment of the tzaddik (2)
- childlessness (2)
- testing the tzaddik (לתהות על קנקנו) (2)
- trust in god (bitachon) as the central theme (1)
- a layman's blessings as a heavenly reward (1)
- testing whether a wonder-worker is from the side of holiness (1)
- god as business partner (1)
- trust in god (bitachon) as a virtue (1)
- saving life (pikuach nefesh) by a layman (1)
- reward for a good deed (1)
- illness and loss of speech of a tzaddik, with the community's lament (1)
- the tzaddik's coded biographical story (an allegorical tale that encodes a life) (1)
- humility concealed under outward pride or finery (1)
- trust in god (bitachon) (1)
- the tzaddik learning a virtue from a simple jew (1)
- arenda rent owed to the lord and the threat of imprisonment (1)
- blindness (1)
- reversal or withdrawal of a miracle (1)
- skepticism toward the tzaddik (1)
- refusal of payment / sanctification of the name (kiddush ha-shem) (1)
- ottoman istanbul setting (1)
- public ban on mentioning the besht's name or teachings (a herem-like decree) (1)
- lay court of the seven good men of the town (שבעה טובי העיר) (1)

## Adjudicated estimate (independent Opus judge, tagger confidence >= 2)

- judge says present: AGREE 95% (n=60), EXTRA 83% (n=200), MISSED 38% (n=120)
- estimated tagger precision 0.89, estimated recall 0.90 (population: 613 agree, 548 extra, 299 missed)
- for comparison, the RA+audit reference: estimated precision 0.95 on agreed tags; estimated recall of the reference 0.61

| category | EXTRA judged present | MISSED judged present |
|---|---|---|
| characters-and-roles | 8/11 | 3/6 |
| ethics-and-emotions | 16/20 | 5/20 |
| experience | 10/11 | 4/9 |
| folkloristics | 10/11 | 3/12 |
| kabbalah | 1/1 | - |
| knowledge | - | 2/5 |
| not-a-hasidic-story | 1/1 | 2/5 |
| practice | 55/68 | 2/12 |
| social | 25/30 | 16/23 |
| spaces | 3/5 | 0/3 |
| supernatural | 19/21 | 4/15 |
| times | 12/14 | 2/4 |
| women | 6/7 | 3/6 |
