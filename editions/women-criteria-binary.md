You are annotating Hasidic stories (18th–19th century Hebrew/Yiddish) for
a single binary question: does the story include women, or not?

## Definition

A "woman" for our purposes is any direct reference to a real woman in the
story-world — whether she is active or passive in the plot, whether she
appears individually or as part of a collective (e.g. "the women of the
town", "many widows", "his daughters"). A passive, unnamed, or offstage
woman still counts as long as she is a real person in the depicted world.

## Exclusions

The following do NOT count as a female reference:

1. **Marriage as a category.** Formulaic mentions of marriage with no
   real woman in view — e.g. "נשא אשה" ("he married a wife"), "שמשת מטתך"
   ("marital relations"), references to the institution of marriage.
2. **Biblical / quoted women.** A woman appearing inside a quoted verse,
   blessing, prayer, or genealogy — unless she also appears as a figure
   acting in the story itself.
3. **Halakhic or abstract categories.** "Woman" used as an abstract legal
   or conceptual category, or as a metaphor for a state of the world,
   with no concrete woman in the story-world.
4. **Adultery without a woman.** A reference to adultery, illicit
   relations, or sexual sin that does not directly name or depict a
   real woman.
5. **Purely formulaic idioms** of the type "from women to children"
   (מנשים ועד טף) used as rhetorical scope-markers rather than as a
   reference to specific women in the scene.

## The per-mention rule (important)

Exclusions apply to individual references, NOT to the whole story. If
ANY single reference in the story names or depicts a real woman in the
story-world (active or passive, individual or collective), the answer
is `true` — even if every other female reference in the same story
falls under one of the exclusions above.

Only answer `false` if EVERY female reference in the story falls under
an exclusion (or there are no female references at all).

## Notes

- Unnamed individual women count the same as named women.
- Legendary or biblical female figures count only when they appear in
  the story's action — not when mentioned in a quoted verse, blessing,
  or genealogy.
- A formulaic birth notice that exists only to introduce a male
  character ("his wife bore him a son", "ונולד לו בן") does NOT
  count — the wife here is a genealogical pivot, not a presence.
  But if the woman is depicted in the scene — named, addressed,
  suffering, speaking, acting, or the object of someone's
  intervention — she counts, whether or not she gives birth.
- Collectives of real women in the story-world DO count
  (e.g. "the women wept", "men and women followed him to the funeral").

## Output

Respond in JSON only:

{"women_in_story": <true|false>,
 "confidence": "<high|medium|low>",
 "reasoning": "<1-2 sentences citing the specific reference(s) that
               drove the decision, in the original language where helpful>"}
