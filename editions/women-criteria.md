You are annotating Hasidic stories (18th–19th century Hebrew/Yiddish) for the presence and role of women characters.

Assign **exactly one** primary category — pick the highest applicable tier:

- **no-women**: No women appear or are referenced in any way.

- **mention-only**: A woman is referenced as a relation, status, or context (e.g., "his wife", "the rabbi's mother", "his daughters and wife"), with no presence as a character. She does not act, speak, suffer in a depicted way, decide, or appear in a depicted scene. Anonymous group references that function purely as backdrop ("the women wept", "many widows came") count here unless a member acts or speaks individually.

- **minor-character**: A woman appears in the story as a character — she acts, speaks, is described, or is present in a depicted scene — but the story's main thrust does not depend on her. Removing her would diminish texture, not core plot.

- **catalyst-character**: A woman's situation (suffering, illness, plea, death, request, demand) is the *reason* the story exists, but a male protagonist is the active agent (travels, prays, intervenes, performs the miracle). The narrative orbits around her predicament; she may be unconscious, offstage, or passive during the central scene. Without her there is no story.

- **major-character**: She is an active driver. Her decisions, actions, or speech *visibly* shape the plot — not only its motivation. She acts, not just is acted upon.

Then, **independently**, set `collective_women: true` if anonymous female groups appear ("the women of the town", "many widows", "his daughters and wife as a group"). This flag may co-occur with any tier except no-women. Set `collective_women: false` otherwise.

Then, set `confidence` to one of:
- **high**: The text plainly fits the chosen tier; no other tier is plausible.
- **medium**: The choice is reasonable but a different tier is defensible (e.g., between mention-only and minor-character, or between catalyst and major).
- **low**: Genuine ambiguity — multiple tiers are plausible; please review.

Notes:
- Unnamed individual women count the same as named women.
- Legendary/biblical female figures count as characters only if they appear in the story's action — not when mentioned in a quoted verse, blessing, or genealogy.
- When uncertain between two adjacent tiers, choose the lower one.
- A wife giving birth offstage to enable the plot ("his wife bore him a son") is **mention-only**.

Respond in JSON only:
{"category": "<no-women|mention-only|minor-character|catalyst-character|major-character>", "collective_women": <true|false>, "confidence": "<high|medium|low>", "reasoning": "<1-2 sentences>"}
