# Tag-audit — global decisions

Decisions that apply across many tags / whole categories. Recorded from the
shared review sheet (rows 3–4 of `tag-definitions-review`, Google Drive copy).
Per-tag decisions live in [tag-definitions-review.csv](tag-definitions-review.csv).

## G1 — Merge `halakhah:*` into `practice:*`

Move all sub-categories of `halakhah:` to `practice:`.

**Affected tags** (from [legitimate-tags.tsv](legitimate-tags.tsv)):

| current | proposed | n_stories |
| --- | --- | --- |
| halakhah:prayer | practice:prayer | 169 |
| halakhah:tefillin | practice:tefillin | 24 |
| halakhah:kosher_slaughtering | practice:ritual_slaughtering (merge) | 18 |
| halakhah:circumcision | practice:circumcision | 14 |
| halakhah:tvilah | practice:tvilah (merge — already exists, 41 stories) | 4 |

Notes:
- `practice:tvilah` already exists with 41 stories — `halakhah:tvilah` merges into it.
- `practice:ritual_slaughtering` exists (1 story); `halakhah:kosher_slaughtering`
  (18) covers the halakhic dimension of slaughter and folds in here. The
  *character* (the shochet) stays under `characters-and-roles:ritual_slaughterer`.
- The bare `halakhah` anomaly (24 stories with no sub-tag — see anomaly row 147
  in the sheet) is also rehomed under practice: per-story triage required to
  map to a specific `practice:*` sub-tag or to a generic `practice:halakhah`.
- `not-a-hasidic-story:halakhah` (1 story) is outside this rule — it stays
  in the not-a-hasidic-story category.

## G2 — Fold `profession:*` into `characters-and-roles:*`

The whole `profession:` category collapses into `characters-and-roles:`.
Gadi: "fold into characters-and-roles". Chen agreed on the tavern_keeper row.

**Affected tags**:

| current | proposed | n_stories |
| --- | --- | --- |
| profession:melamed | characters-and-roles:melamed | 1 |
| profession:scribe | characters-and-roles:scribe | 1 |
| profession:tavern_keeper | characters-and-roles:tavern_keeper | 1 |

Also fixes the anomalous rows in the sheet (122, 123, 128) where
`assistant:scribe`, `profession:scribe`, and `profession:tavern_keeping,tavern_owner`
were comma-glued — these become `characters-and-roles:scribe` and
`characters-and-roles:tavern_keeper` after split.

The orphan `communal-position:ritual_slaughterer` (1 story) similarly merges
into `characters-and-roles:ritual_slaughterer` (17 stories).

## CHANGES applied to taxonomy.tsv

Per-row decisions from the Drive sheet `tag-definitions-review`. The
`proposed_canonical` column in [taxonomy.tsv](taxonomy.tsv) now records each.
"DROP" = retire the tag; an existing tag name = merge into that tag;
"SPLIT:..." = the source row is a comma-glued anomaly that needs to be split
into two separate spans in the XML.

### Drops
- `custom:hasidic_custom` (22 stories) — too broad; Chen+Gadi agreed drop.
- `experience:mystical` (19 stories) — redundant umbrella over the specific
  experience:* tags.

### Merges
- `characters-and-roles:tsaddik_wife` (33) → `characters-and-roles:the_family_of_the_tsaddik` (78), skip stories already double-tagged.
- `custom:pilgrimage_to_the_graves_of_tsaddikim` (10) → `practice:pilgrimage_to_the_graves_of_tsaddikim` (10).
- `ethics-and-emotions:prohibition_to_write` (1) → `ethics-and-emotions:prohibitions`.
- `experience:visions` (17) → `supernatural:mystical_vision` (10).
- `experience:communion_with_god` (1) → `experience:devekut`.
- `experience:enlightenment` (1) → `experience:revelation`.

### Renames (flatten 3-level paths)
- `experience:mystical:gilui_eliyahu` (1) → `experience:gilui_eliyahu`.
- `practice:prayer:outside` (1) → `practice:prayer`.
- `practice:prayer:sigh` (1) → `practice:prayer`.

### Definition refinements (no rename, audit-prompt change)
- `characters-and-roles:preacher`: covers human maggidim (itinerant *or* settled); angelic maggidim move to `supernatural:angels`.
- `characters-and-roles:magician` vs `:witch`: keep both — different cultural types, not a gender variant.
- `characters-and-roles:baal_shem`: only stories where a *different* baal shem is named, or the *function* (someone using divine names for magic); not the Besht himself.
- `ethics-and-emotions:prohibitions`: sharpen — only when a specific prohibition is *named/cited* (sex, food, oath, Shabbat), not any moral lapse.
- `ethics-and-emotions:fear` vs `:awe`: fear = human emotion, awe = religious value (יראת שמים).
- `ethics-and-emotions:sadness`: covers any grief or sadness (no distinction between vice and ordinary sorrow).
- `ethics-and-emotions:virtues`: try specific sub-tags first; if a story has a specific virtue tag, do not add the umbrella.
- `experience:devekut` + `practice:devekut`: keep both (practice = the cultivation, experience = the achieved state).

### Per-story triage (bare `halakhah`, 24 stories) — ACCEPTED
Confirmed by Sinai. See [halakhah-bare-triage.tsv](halakhah-bare-triage.tsv).
Result: 13 DROP (bare tag redundant with an existing specific halakhah:* /
practice:* / ethics-and-emotions:* tag on the same story), 11 →
`practice:halakhah` (new catch-all for halakhic discussion without an existing
specific sub-tag — yaaleh v'yavo, netilat yadayim, kiddushin/ketubah,
tzaar baalei chayim d'oraita-vs-derabbanan, Rambam pasak on perishut, etc.).

A new tag `practice:halakhah` will be introduced by this audit (no current
stories under it; will receive 11). It serves as the residual for halakhic
content that doesn't fit the named sub-tags.

### Verification for G1 merge (`halakhah:kosher_slaughtering` → `practice:ritual_slaughtering`)
Spot-checked Khal-Hasidim_0062: a shochet-and-knife story where the Besht
inspects the knife and the act of שחיטה is depicted — practice, not pure
halakhic discussion. The "halakhic dimension always implies the practice in
Hasidic stories" assumption holds for this case. Merge is safe.

### Anomalous bad-sep rows (split first, then apply)
- `experience:mystical,appearance_shaking` (1) → split spans → `experience:mystical` (DROP) + `appearance:shaking` (keep).
- `profession:tavern_keeping,tavern_owner` (1) → split spans → both map to `characters-and-roles:tavern_keeper`.

## Round 2 — 2026-06-23 (Chen/Gadi second pass, Sheet1)

Decisions from the second pass through the Drive sheet. Confirmed rows where
the reviewer comment unambiguously resolved the question; eight remaining rows
have follow-up questions sent to Chen/Gadi and are HELD.

### Renames
- `ethics-and-emotions:virtues_humility` (33) → `ethics-and-emotions:humility`
  (Gadi: drop the `virtues_` prefix; humility is a specific virtue, per the
  global virtues-umbrella rule — don't co-tag with the umbrella).
- `spaces:institutions_beth_midrash` (6) → `spaces:beth_midrash` (Chen + Gadi
  agree: no separate "institutions" layer; beit din is also an institution and
  lives flat).

### Merges
- `social-relations:with_non_jews_hostility_against_jews` (37) →
  `social-relations:with_non_jews` (Chen: distinction creates unnecessary
  complexity; hostility is a sub-case).
- `social-relations:marital_relationship` (36) → `social-relations:marriage`
  (Chen: redundant with existing 21-story marriage tag; fold both event/
  institution and relationship under one tag).
- `social-relations:marriage_matchmaking` (31) → `social-relations:marriage`
  (Chen: over-detail; matchmaking is a sub-case).
- `supernatural:conversing_with_the_dead` (70) →
  `supernatural:communicating_with_the_invisible` (Chen: duplicate; conversing
  with the dead is a sub-case).

### Sharpens (definition refined, no rename)
- `supernatural:miracle` (29): apply only when the text uses נס / מופת, OR
  when the supernatural intervention is structured as a discrete event with a
  before/after. Excludes ambient miraculousness. Distinguish from
  `supernatural:magic` (which attaches to the magician, not the recipient).
  Gadi: "magic relates to the magician; miracle relates to the person having
  the miracle."

### Direction reversal (previously HELD, now RESOLVED)
- `supernatural:mystical_vision` (10) → `experience:visions` (17). Previous
  draft had the opposite direction. Confirmed 2026-06-23 via Sheet2 column C.
  `experience:visions`' own proposed_canonical entry (which had pointed at
  `supernatural:mystical_vision`) is cleared.

### Sheet2 replacements (column C "replace with")
All applied as merges/renames to the proposed_canonical column:

| current | proposed |
| --- | --- |
| clothing:white | practice:clothing |
| experience:mystical:gilui_eliyahu | experience:gilui_eliyahu |
| practice:asceticism_fasting | practice:fasting |
| practice:conversing_with_angels | supernatural:angels |
| practice:prayer:outside | practice:prayer |
| custom:clothing | practice:clothing |
| supernatural:mystical_vision | experience:visions |
| practice:spiritual | DROP |

### Resolutions to the WhatsApp questions (Sinai, 2026-06-25)

**G3 — Top-level rename `social-relations:` → `social:`**
The whole `social-relations:` top-level becomes `social:`. Relational
sub-tags that started with `with_` get rewritten to `relations_with_*`
(e.g. `social-relations:with_non_jews` → `social:relations_with_non_jews`).
All other sub-tags just swap the prefix. The new `social:` category also
receives `social:poverty` (moved from `ethics-and-emotions:virtues_poverty`),
broadening its scope from purely relational to social phenomena at large.

| current | new |
| --- | --- |
| social-relations:with_non_jews (96) | social:relations_with_non_jews |
| social-relations:with_non_hasidim (89) | social:relations_with_non_hasidim |
| social-relations:with_the_authorities (62) | social:relations_with_the_authorities |
| social-relations:with_sinners (12) | social:relations_with_sinners |
| social-relations:inter_hasidic_master_disciple_relationship (213) | social:inter_hasidic_master_disciple_relationship |
| social-relations:conflict (81) | social:conflict |
| social-relations:retrospective_recognition (69) | social:retrospective_recognition (+ widened def, see below) |
| social-relations:inter_hasidic (65) | social:inter_hasidic |
| social-relations:disobedience (24) | social:disobedience |
| social-relations:marriage (21) | social:marriage |
| social-relations:inter_hasidic_inheritance_of_leadership (17) | social:inter_hasidic_inheritance_of_leadership |
| social-relations:competition (16) | social:competition |
| social-relations:converts_and_conversion (13) | social:converts_and_conversion |
| social-relations:inter_hasidic_conflict_between_tsaddikim (8) | social:inter_hasidic_conflict_between_tsaddikim |
| social-relations:divorce (7) | social:divorce |
| social-relations:excommunication (6) | social:excommunication |
| social-relations:with_non_jews_hostility_against_jews (37) | social:relations_with_non_jews (merge) |
| social-relations:marital_relationship (36) | social:marital_relationship (rename only — Sinai 2026-06-25: marital relationship is distinct from marriage, do NOT merge) |
| social-relations:marriage_matchmaking (31) | social:marriage (merge) |
| ethics-and-emotions:virtues_poverty (22) | social:poverty |

**G4 — Supernatural-character group → `characters-and-roles:`**
Demons, angels, and the angel of death are character types, not modes of
supernatural communication. Move all three to the `characters-and-roles:`
top-level. No duplication: when a story already has both the supernatural
form and a characters-and-roles form, drop the supernatural form.

| current | new |
| --- | --- |
| supernatural:demons (31) | characters-and-roles:demons |
| supernatural:angels (25) | characters-and-roles:angels |
| supernatural:angel_of_death (7) | characters-and-roles:angel_of_death |

**Definition widening**
- `social:retrospective_recognition` (was `social-relations:retrospective_recognition`):
  widen — any retrospective realization by a character, not only realization
  about the tsaddik. Stranger-revealed-as-tzaddik remains the prototypical
  case, but the tag now applies to any belated recognition (someone was
  righteous, someone was a sinner, an event had hidden meaning, etc.).

**Keep-as-is rulings (ignore reviewer comment)**
- `knowledge:esoteric` (66): keep current scope; Sinai overruled Chen's
  scope-clarification request.
- `social:relations_with_non_jews` (96, after rename): keep current scope;
  Sinai overruled Chen's overlap-with-conflict comment.

### Bare `scriptures` (1 story, anomaly) — RESOLVED 2026-06-25
Merge → `knowledge:secret_texts`. The lone occurrence is in
`Shivhei-Habesht_0004` on the span "כתבים שהגיעו לידי" (Besht receives mystical
writings, seals them in a stone in a mountain). The same story already carries
`knowledge:secret_texts` on the immediately following span "הכתבים" referring to
the same writings, so merging is essentially a deduplication.

Sinai's reasoning on Gadi's `texts:` proposal: per-story tags vs. inline `<bibl>`
annotations (future task 20) are different layers — a `texts:` top-level would
be redundant once the bibliography annotation pass runs. Bibliography annotation
covers *named* works; the secret/unnamed texts case is what we still need a
per-story tag for, which `knowledge:secret_texts` already does.

**Uncertainty note kept open**: not every story now under `knowledge:secret_texts`
is necessarily about *secret* texts (vs. merely unnamed or esoteric ones). The
tag's scope should be revisited during the general audit; expect some splitting
or sharpening if the LLM pass surfaces stories that don't fit a "secret"
reading.

