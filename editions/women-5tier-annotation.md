# Women 5-Tier Annotation — Scheme, Statistics, Examples

Companion document to the women-in-stories annotation study. The live prompt is in [women-criteria.md](women-criteria.md); per-story results are in [women-5tier-9editions-full.tsv](women-5tier-9editions-full.tsv) and [women-5tier-9editions-summary.tsv](women-5tier-9editions-summary.tsv).

## 1. The exact prompt language (from [women-criteria.md](women-criteria.md))

> You are annotating Hasidic stories (18th–19th century Hebrew/Yiddish) for the presence and role of women characters.
>
> Assign **exactly one** primary category — pick the highest applicable tier:
>
> - **no-women**: No women appear or are referenced in any way.
> - **mention-only**: A woman is referenced as a relation, status, or context (e.g., "his wife", "the rabbi's mother", "his daughters and wife"), with no presence as a character. She does not act, speak, suffer in a depicted way, decide, or appear in a depicted scene. Anonymous group references that function purely as backdrop ("the women wept", "many widows came") count here unless a member acts or speaks individually.
> - **minor-character**: A woman appears in the story as a character — she acts, speaks, is described, or is present in a depicted scene — but the story's main thrust does not depend on her. Removing her would diminish texture, not core plot.
> - **catalyst-character**: A woman's situation (suffering, illness, plea, death, request, demand) is the *reason* the story exists, but a male protagonist is the active agent (travels, prays, intervenes, performs the miracle). The narrative orbits around her predicament; she may be unconscious, offstage, or passive during the central scene. Without her there is no story.
> - **major-character**: She is an active driver. Her decisions, actions, or speech *visibly* shape the plot — not only its motivation. She acts, not just is acted upon.
>
> Then, **independently**, set `collective_women: true` if anonymous female groups appear ("the women of the town", "many widows", "his daughters and wife as a group"). This flag may co-occur with any tier except no-women.
>
> Then, set `confidence` to one of:
> - **high**: The text plainly fits the chosen tier; no other tier is plausible.
> - **medium**: The choice is reasonable but a different tier is defensible.
> - **low**: Genuine ambiguity — multiple tiers are plausible; please review.
>
> Notes:
> - Unnamed individual women count the same as named women.
> - Legendary/biblical female figures count as characters only if they appear in the story's action — not when mentioned in a quoted verse, blessing, or genealogy.
> - When uncertain between two adjacent tiers, choose the lower one.
> - A wife giving birth offstage to enable the plot ("his wife bore him a son") is **mention-only**.
>
> Respond in JSON only:
> `{"category": "<no-women|mention-only|minor-character|catalyst-character|major-character>", "collective_women": <true|false>, "confidence": "<high|medium|low>", "reasoning": "<1-2 sentences>"}`

XML tokens used downstream: `women:mention_only`, `women:minor_character`, `women:catalyst_character`, `women:major_character`, `women:collective`. Absence of any `women:*` token = no-women.

## 2. Statistics across the 9 previously-tagged editions

652 stories total. Distribution (Claude 5-tier, Anthropic SDK run, cache at `editions/women-llm-results-v2.tsv`):

| Tier | Count | % |
|---|---:|---:|
| no-women | 362 | 55.5% |
| mention-only | 100 | 15.3% |
| minor-character | 103 | 15.8% |
| catalyst-character | 54 | 8.3% |
| major-character | 33 | 5.1% |

**Collective-women flag** set on 39 stories (6.0%). **Confidence**: high 499 (76.5%), medium 152 (23.3%), low 1 (0.2%).

### Per edition

| edition | no-women | mention | minor | catalyst | major | total |
|---|---:|---:|---:|---:|---:|---:|
| Adat-Zadikim | 6 | 6 | 7 | 2 | 3 | 24 |
| Khal-Hasidim | 136 | 38 | 42 | 26 | 12 | 254 |
| Khal-Kdoshim | 5 | 3 | 4 | 0 | 0 | 12 |
| Mifalot-HaZadikim | 38 | 4 | 9 | 1 | 2 | 54 |
| PeerMikdoshim | 6 | 2 | 2 | 5 | 3 | 18 |
| Shivhei-Habesht | 127 | 37 | 30 | 14 | 8 | 216 |
| Shivhei-Harav | 11 | 2 | 3 | 2 | 1 | 19 |
| Sipurei-Zadikim | 9 | 2 | 1 | 1 | 1 | 14 |
| maase-zadikim | 24 | 6 | 5 | 3 | 3 | 41 |

## 3. Examples for the three middle categories

All three are Claude-tagged, high-confidence; reasoning is verbatim from the run.

### mention-only

- **[Shivhei-Habesht_0118](https://www.hasidic-stories.org/Story/Shivhei-Habesht/Shivhei-Habesht_0118)** — A woman is referenced only as "he married a wife" (נשא אשה), providing context for why R' Aharon no longer wanted to serve. She plays no active role, speaks nothing, and does not appear in any depicted scene.
- **[Shivhei-Habesht_0137](https://www.hasidic-stories.org/Story/Shivhei-Habesht/Shivhei-Habesht_0137)** — A wife is implicitly referenced through the phrase "שמשת מטתך" (marital relations), functioning only as contextual backdrop for the sin being discussed. She does not appear, act, or speak.
- **[Shivhei-Habesht_0035](https://www.hasidic-stories.org/Story/Shivhei-Habesht/Shivhei-Habesht_0035)** — The rabbi's wife ("הרבנית") is referenced only as someone whose fate is inquired about and who is reportedly taken to Jerusalem. She does not speak, act, or appear in any depicted scene.
- **[Shivhei-Habesht_0199](https://www.hasidic-stories.org/Story/Shivhei-Habesht/Shivhei-Habesht_0199)** — Women are referenced only as abstract concepts (potential wives, a nobleman's daughter) in the Baal Shem Tov's rhetorical argument to the priest; no woman appears as a character, acts, speaks, or is present in any depicted scene.
- **[Khal-Hasidim_0172](https://www.hasidic-stories.org/Story/Khal-Hasidim/Khal-Hasidim_0172)** — Women appear only once as part of the anonymous collective phrase "אנשים ונשים" (men and women) who followed the mokhiach to the funeral — a pure backdrop reference with no individual woman acting, speaking, or driving any part of the plot.
- **[Adat-Zadikim_0022](https://www.hasidic-stories.org/Story/Adat-Zadikim/Adat-Zadikim_0022)** — Women appear only in the bishop's threat to destroy all the Jews "from women to children" (מנשים ועד טף), a formulaic expression with no individual female character acting or appearing in a scene.

### minor-character

- **[Mifalot-HaZadikim_0013](https://www.hasidic-stories.org/Story/Mifalot-HaZadikim/Mifalot-HaZadikim_0013)** — A specific unnamed woman enters the rabbi's room and is depicted in the scene, directly triggering his dramatic flight and the subsequent dialogue. She is present as a character, but the story's focus is on the rabbi's extreme piety.
- **[Shivhei-Habesht_0140](https://www.hasidic-stories.org/Story/Shivhei-Habesht/Shivhei-Habesht_0140)** — The householder's wife (אשת בעה"ב) is addressed by the slaughterer and acts by granting permission to slaughter — more than a mere mention, but peripheral to the story's main thrust about the Besht and the slaughterer.
- **[Khal-Hasidim_0036](https://www.hasidic-stories.org/Story/Khal-Hasidim/Khal-Hasidim_0036)** — An unnamed elderly woman cries out warnings and argues with the Besht at the window. She acts, speaks, and is described — but only brief texture in the middle of a story whose main thrust is the bishop's repentance.

### catalyst-character

- **[Khal-Hasidim_0112](https://www.hasidic-stories.org/Story/Khal-Hasidim/Khal-Hasidim_0112)** — A woman who has just given birth and has no food is the reason the Rebbe sends money via his servant — her predicament drives the entire story. She herself does not act or speak; the Rebbe and his servant are the active agents.
- **[Shivhei-Habesht_0194](https://www.hasidic-stories.org/Story/Shivhei-Habesht/Shivhei-Habesht_0194)** — The young woman who has just given birth and has no food is the reason the story exists — her predicament motivates the rabbi's command and the servant's errand — but she is entirely passive and offstage.
- **[Khal-Hasidim_0083](https://www.hasidic-stories.org/Story/Khal-Hasidim/Khal-Hasidim_0083)** — The mother's distress over her missing son is the reason the story exists — she pressures her skeptical husband to go consult the Besht. Without her worry and insistence, there is no visit and no story, but she remains offstage once the husband departs.

## Pointers

- Prompt: [women-criteria.md](women-criteria.md) (cache invalidates when its hash changes)
- Full per-story results (with story text + reasoning): [women-5tier-9editions-full.tsv](women-5tier-9editions-full.tsv)
- Summary (no text): [women-5tier-9editions-summary.tsv](women-5tier-9editions-summary.tsv)
- Pipeline code: [Authorities/integration_tool/women_llm.py](../Authorities/integration_tool/women_llm.py), [women_data.py](../Authorities/integration_tool/women_data.py)
- Run script: [Authorities/integration_tool/run_5tier_full_9.py](../Authorities/integration_tool/run_5tier_full_9.py)
- Old → new shift visualization: `women-alluvial-old-to-new.png` / `.html`
