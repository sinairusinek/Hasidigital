"""Generate `editions/tag-audit/tag-definitions-review.csv` — the PI-facing
sheet of draft definitions for every tag in the 13 unaudited categories
(practice already has its own PI-reviewed sheet).

Format: one row per tag.
  category, tag, n_stories, draft_definition, doubts_or_questions,
  example_stories (URLs, ONLY populated when there's a doubt that needs an example),
  decision (blank — PI marks ok/revise/split/merge/drop),
  refined_definition (blank — PI rewrites)

Doubts are flagged only where I have a genuine uncertainty about the boundary.
Examples are pulled from stories ALREADY tagged with the tag and chosen to
illustrate the specific doubt (e.g. a borderline case under the current usage).
"""
from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INVENTORY = PROJECT_ROOT / "editions" / "tag-audit" / "tag-inventory.tsv"
OUT = PROJECT_ROOT / "editions" / "tag-audit" / "tag-definitions-review.csv"

CATEGORIES = [
    "kabbalah", "knowledge", "custom", "profession", "halakhah",
    "times", "spaces", "folkloristics", "experience",
    "characters-and-roles", "supernatural", "ethics-and-emotions",
    "social-relations",
]


# ── Definitions + doubts ──────────────────────────────────────────────────────
# For each tag: (definition, doubts_or_questions, example_story_ids_for_doubt)
# When doubts is "", no examples are needed and example list should be [].
# When doubts is non-empty, examples must be specific stories that EXEMPLIFY
# the ambiguity (not just stories that happen to carry the tag).

DEFS: dict[str, tuple[str, str, list[str]]] = {

    # ─── kabbalah ─────────────────────────────────────────────────────────
    "kabbalah:kabbalistic_terms_kavvanot": (
        "Use of Lurianic kavvanot (כוונות) — mystical intentions assigned to specific words of prayer or ritual actions. The story depicts a character praying/acting WITH explicit kavvanot, or discusses kavvanot as a kabbalistic concept.",
        "Does generic 'with kavvanah' (בכוונה) in prayer count, or only Lurianic-style named kavvanot tied to specific divine names/sefirot? Khal-Hasidim_0028 says the Yom Kippur prayers ascended because they were prayed 'with kavvanah' — should this kind of story be tagged kavvanot, or is it too generic?",
        ["Khal-Hasidim_0028"],
    ),
    "kabbalah:kabbalistic_terms_yihudim": (
        "Use of Lurianic yihudim (יחודים, ייחודים) — mystical 'unifications' of divine names or sefirot performed contemplatively, typically by a tzaddik or kabbalist.",
        "Should the definition explicitly exclude the marital-seclusion sense of יחוד (a couple alone together)? Khal-Hasidim_0105 uses bare יחוד in a non-mystical sense and was correctly rejected by the audit — confirm the definition is sharp enough.",
        ["Khal-Hasidim_0105"],
    ),

    # ─── knowledge ────────────────────────────────────────────────────────
    "knowledge:esoteric": (
        "Esoteric / hidden knowledge (תורת הסוד, נסתר) — kabbalah, mystical doctrines, knowledge accessible only to initiates.",
        "",
        [],
    ),
    "knowledge:secret_texts": (
        "Possession, transmission, or use of secret/hidden manuscripts (כתבים, כתבי הסוד) — typically kabbalistic.",
        "",
        [],
    ),
    "knowledge:practical_kabbalah": (
        "Practical kabbalah (קבלה מעשית) — use of mystical knowledge to effect concrete results (amulets, healings, manipulation of names/spirits).",
        "MERGE CANDIDATE: is this the umbrella for practice:use_of_holy_names + practice:writing_amulets, or genuinely a third orthogonal tag? Currently 3 stories.",
        [],
    ),

    # ─── custom ───────────────────────────────────────────────────────────
    "custom:hasidic_custom": (
        "A Hasidic custom (מנהג) as explicitly Hasidic — something done because 'this is what the Hasidim do' or 'this is our custom'.",
        "DEFINITION TIGHTENING NEEDED: how to apply this without it becoming a catch-all? Should it only apply when the text uses the word מנהג or explicitly frames an act as customary, not when the story merely depicts a Hasid doing a Hasidic thing?",
        [],
    ),
    "custom:pilgrimage_to_the_graves_of_tsaddikim": (
        "Visiting/prostrating at the graves of tzaddikim (השתטחות, ציון, אוהל) — pilgrimage as a custom.",
        "MERGE CANDIDATE: there is also `practice:pilgrimage_to_the_graves_of_tsaddikim` with the same name in the practice category. Are these meant to be the same tag accidentally duplicated, or is one the custom and the other the act?",
        [],
    ),
    "custom:clothing": (
        "Distinctive Hasidic clothing as the focus of attention (kapota, gartel, shtreimel, beket, white garments).",
        "",
        [],
    ),

    # ─── profession ───────────────────────────────────────────────────────
    "profession:melamed": (
        "A character whose profession is melamed (teacher of young children) — central enough to be tagged.",
        "",
        [],
    ),
    "profession:scribe": (
        "A character whose profession is sofer (scribe of Torah scrolls / amulets).",
        "",
        [],
    ),
    "profession:tavern_keeper": (
        "A character whose profession is tavern-keeper / innkeeper (אורנדאר, פונדקאי).",
        "CATEGORY VIABILITY: the whole `profession:*` category has only 3 tags, 1 story each. Fold all into `characters-and-roles:*` and drop the category?",
        [],
    ),

    # ─── halakhah ─────────────────────────────────────────────────────────
    "halakhah:prayer": (
        "Prayer (תפילה) as a depicted activity — formal recitation of liturgy (Shacharit/Mincha/Maariv, the Amidah, Shema, etc.).",
        "",
        [],
    ),
    "halakhah:tefillin": (
        "Putting on / use / discussion of tefillin (phylacteries).",
        "",
        [],
    ),
    "halakhah:kosher_slaughtering": (
        "The kashrut/halakhic dimension of slaughter — whether an animal is kosher, treif, problems with the act.",
        "SCOPE QUESTION: is this tag the *halakhic question* (was the slaughter kosher? was the animal treif?) — distinct from practice:ritual_slaughtering (the act) and characters-and-roles:ritual_slaughterer (the person)? Please confirm so the audit prompt can distinguish.",
        [],
    ),
    "halakhah:circumcision": (
        "Circumcision (ברית מילה) as a halakhic event in the story.",
        "",
        [],
    ),
    "halakhah:tvilah": (
        "Halakhic ritual immersion (טבילה) — the legal/halakhic dimension specifically.",
        "MERGE CANDIDATE: also exists as `practice:tvilah`. Are these the same thing accidentally split (suggest merge), or is the distinction halakhic-rule vs practice-act (keep both with sharper definitions)?",
        [],
    ),

    # ─── times ────────────────────────────────────────────────────────────
    "times:death": (
        "A death is a depicted event in the story (of a tzaddik, a relative, an antagonist, etc.).",
        "",
        [],
    ),
    "times:shabbat": (
        "The story takes place on / centers on Shabbat (שבת קודש, ערב שבת, מוצאי שבת).",
        "",
        [],
    ),
    "times:holidays": (
        "The story takes place on a Jewish holiday (Pesach, Sukkot, Yom Kippur, Rosh Hashana, Purim, Chanukah, etc.).",
        "GRANULARITY: should specific holidays each get their own sub-tag (times:yom_kippur, times:purim, …)? Currently the lump covers ~40 stories with no internal distinction. Worth splitting before the audit, or keep as one?",
        [],
    ),
    "times:historical_event": (
        "A historical event is part of the story's setting (a war, a decree, a famous gathering).",
        "SCOPE: a passing reference vs. a plot-driving event — where to draw the line?",
        [],
    ),
    "times:birth": (
        "A birth is a depicted event in the story (typically the birth of a future tzaddik, or of a child whose birth required a miracle).",
        "",
        [],
    ),
    "times:inauguration": (
        "Inauguration / installation of a tzaddik as rebbe of a community (kabbalat malkhut, accepting leadership).",
        "MERGE CANDIDATE: probably the same tag as `folkloristics:story_type_inauguration`, just classified as event vs genre. Confirm: keep both with sharper line, or merge?",
        [],
    ),
    "times:eschatology": (
        "Eschatological events / end-of-days themes — coming of messiah, end-times signs, world-to-come (עולם הבא).",
        "",
        [],
    ),

    # ─── spaces ───────────────────────────────────────────────────────────
    "spaces:heaven": (
        "Heaven / upper worlds (שמים, גן עדן, היכלות) appears in the story as a SETTING — the action happens there, or a character ascends.",
        "",
        [],
    ),
    "spaces:hell": (
        "Hell / gehinnom / the punishment-realm appears as a setting.",
        "",
        [],
    ),
    "spaces:the_land_of_israel": (
        "The Land of Israel (ארץ ישראל, א״י, ירושלים, צפת, חברון) is the setting or the destination of travel.",
        "SCOPE: does a mere mention (e.g. 'he sent money for the poor of Israel', 'they prayed for the return to Zion') count, or only a story whose setting is actually there or characters who actually travel there?",
        [],
    ),
    "spaces:mikveh": (
        "A mikveh (ritual bath) is a setting in the story — a scene takes place there.",
        "",
        [],
    ),
    "spaces:institutions_beth_midrash": (
        "A beit midrash / yeshiva (study hall) is a setting.",
        "",
        [],
    ),
    "spaces:institutions_hassidic_court": (
        "The hasidic court (חצר הצדיק, חצר) — the rebbe's residence/community space.",
        "",
        [],
    ),
    "spaces:rabbinical_court": (
        "A rabbinical court (בית דין) is a setting — legal/halakhic proceedings.",
        "RENAME: confusing — at first glance reads as 'court of a rabbi' (which is the rebbe's hasidic court). Consider renaming to `spaces:beit_din`.",
        [],
    ),

    # ─── folkloristics — story-type classifications ───────────────────────
    "folkloristics:story_type_rapprochement": (
        "Story whose narrative arc is rapprochement: an outsider/skeptic is drawn close to a tzaddik / Hasidism through the events of the story.",
        "BOUNDARY: where exactly does this end and `story_type_advent` begin? Working hypothesis: rapprochement = a SKEPTIC/opponent is won over; advent = a NEUTRAL outsider discovers the tzaddik for the first time. Confirm or rephrase.",
        [],
    ),
    "folkloristics:story_type_prognostication": (
        "Story whose narrative arc is a prediction/prophecy by a tzaddik that comes true.",
        "",
        [],
    ),
    "folkloristics:story_type_virtues": (
        "Story whose point is to illustrate the virtues (humility, charity, faith, etc.) of a tzaddik.",
        "",
        [],
    ),
    "folkloristics:story_type_death_of_the_tsaddik": (
        "Story whose central narrative is the death of a tzaddik (deathbed scene, last teachings, succession).",
        "",
        [],
    ),
    "folkloristics:story_type_protection": (
        "Story whose central narrative is the tzaddik protecting someone from danger (illness, hostile authorities, demons).",
        "",
        [],
    ),
    "folkloristics:story_type_advent": (
        "Story whose narrative is the first encounter / 'finding' of a tzaddik — a neutral character discovers him.",
        "",
        [],
    ),
    "folkloristics:story_type_birth_of_the_tsaddik": (
        "Story about the birth of a tzaddik — typically miraculous circumstances.",
        "",
        [],
    ),
    "folkloristics:story_type_revelation": (
        "Story whose narrative is the revelation (giluy) of a hidden tzaddik to others or himself.",
        "",
        [],
    ),
    "folkloristics:story_type_inauguration": (
        "Story whose central event is a tzaddik's inauguration as rebbe.",
        "MERGE CANDIDATE with `times:inauguration`. See that tag's note.",
        [],
    ),
    "folkloristics:story_type_parable": (
        "Story that is structured as a parable / mashal told BY a tzaddik (not a story ABOUT a tzaddik).",
        "VIABILITY: only 2 stories. Keep, or absorb into a broader rhetorical-form tag? Should there be a sub-type for parables with an explicit nimshal (interpretation)?",
        [],
    ),
    "folkloristics:story_type_ joke": (
        "Story whose point is a witticism / joke told by a tzaddik (or about one).",
        "TYPO in the tag itself — there's an erroneous space after the underscore. Rename to `folkloristics:story_type_joke`.",
        [],
    ),

    # ─── experience ───────────────────────────────────────────────────────
    "experience:dream": (
        "A character has a dream that is depicted in the story (and typically matters for the plot — revelation, warning, etc.).",
        "",
        [],
    ),
    "experience:revelation": (
        "A character experiences a revelation (giluy) — direct mystical/supernatural disclosure.",
        "",
        [],
    ),
    "experience:enthusiasm": (
        "A character experiences hitlahavut — religious enthusiasm/burning fervor.",
        "",
        [],
    ),
    "experience:devekut": (
        "A character experiences devekut — mystical cleaving / communion with God.",
        "PARALLEL TAG: also exists as `practice:devekut`. Is the convention practice = the cultivation, experience = the achieved state? Or accidental duplicate?",
        [],
    ),
    "experience:mystical": (
        "A character has a mystical experience — broad. Vision, ascent, devekut, possession, etc.",
        "VIABILITY: this looks like a redundant umbrella — stories tagged with the more-specific experience:* tags would also get this one. Drop, or keep as catch-all for unspecified mystical states?",
        [],
    ),
    "experience:journey_to_heaven": (
        "Aliyat neshamah — ascent of the soul / journey to upper worlds while alive.",
        "",
        [],
    ),
    "experience:visions": (
        "A character sees visions — supernatural sights in waking state.",
        "MERGE CANDIDATE with `supernatural:mystical_vision`. Both seem to describe the same thing across categories.",
        [],
    ),
    "experience:trembling": (
        "A character trembles (רעד, חרדה) — physical trembling as religious or supernatural response.",
        "",
        [],
    ),
    "experience:communion_with_god": (
        "Communion with God as a direct experiential category.",
        "VIABILITY: only 1 story. Redundant with `experience:devekut` — merge or drop?",
        [],
    ),
    "experience:enlightenment": (
        "A character experiences a flash of enlightenment / understanding.",
        "VIABILITY: only 1 story. If kept, define sharply — what distinguishes 'enlightenment' from 'revelation' / 'mystical'?",
        [],
    ),
    "experience:mystical:gilui_eliyahu": (
        "Gilui Eliyahu — a revelation of the prophet Elijah to a character.",
        "TAXONOMY ANOMALY: this is a three-level token (`a:b:c`) when all other tags are two-level. Either flatten to `experience:gilui_eliyahu`, or merge into `characters-and-roles:elijah_the_prophet`.",
        [],
    ),

    # ─── characters-and-roles ─────────────────────────────────────────────
    "characters-and-roles:the_family_of_the_tsaddik": (
        "Members of the tzaddik's immediate family (wife, sons, daughters, parents) appear as characters.",
        "",
        [],
    ),
    "characters-and-roles:tsaddik_wife": (
        "The tzaddik's wife (רבנית) appears as a character with some role.",
        "",
        [],
    ),
    "characters-and-roles:hidden_righteous": (
        "A nistar / hidden righteous person (often a lamed-vavnik) is a character.",
        "",
        [],
    ),
    "characters-and-roles:ritual_slaughterer": (
        "A shochet (ritual slaughterer) appears as a character with some role.",
        "",
        [],
    ),
    "characters-and-roles:elijah_the_prophet": (
        "Elijah the prophet appears as a character (in disguise, in dream, in revelation).",
        "",
        [],
    ),
    "characters-and-roles:preacher": (
        "A maggid (preacher) appears as a distinct character — typically a different role than the rebbe.",
        "DISAMBIGUATION: 'maggid' in Hebrew/Yiddish can mean either (a) an itinerant human preacher, or (b) an angelic maggid revealed to a kabbalist. Does this tag cover only (a)? Should (b) live under `supernatural:angels`?",
        [],
    ),
    "characters-and-roles:agunah": (
        "An agunah (chained wife — husband missing) appears as a character / her case is the subject.",
        "",
        [],
    ),
    "characters-and-roles:messiah": (
        "The messiah (משיח) appears in some role, or messianic expectations are central.",
        "",
        [],
    ),
    "characters-and-roles:magician": (
        "A character who is a magician / wonder-worker (כושף, מכשף) — typically non-Jewish.",
        "MERGE CANDIDATE with `characters-and-roles:witch` (3 stories) — gender variant of the same role, or genuinely a different cultural type?",
        [],
    ),
    "characters-and-roles:sabbatai_zevi": (
        "Sabbatai Zevi or Sabbatean themes appear.",
        "",
        [],
    ),
    "characters-and-roles:baal_shem": (
        "A baal shem (master of the Name) appears as a character — typically a pre-Hasidic figure or a non-Hasidic kabbalistic healer; NOT the Besht.",
        "DISAMBIGUATION: 'baal shem' is also the opening of 'Baal Shem Tov'. Currently 3 stories — confirm none of them actually refers to the Besht himself; if they do, definition needs to broaden or those rows are misnamed.",
        [],
    ),
    "characters-and-roles:witch": (
        "A witch / female magician character appears.",
        "See `characters-and-roles:magician` merge note.",
        [],
    ),

    # ─── supernatural ─────────────────────────────────────────────────────
    "supernatural:perception": (
        "A character perceives supernaturally — sees things others can't, knows things he couldn't know normally (ruach hakodesh).",
        "SHARPEN: this is by far the most-tagged tag in the corpus (295 stories) and risks being applied trivially. Should it require an *explicit* perception event (the tzaddik says something he couldn't know, sees through walls, etc.), not just 'is a tzaddik with insight'?",
        [],
    ),
    "supernatural:prognostication": (
        "A character (typically a tzaddik) predicts a future event that comes true.",
        "",
        [],
    ),
    "supernatural:magic": (
        "Magic / sorcery (כישוף) — performed by witches, non-Jewish magicians, or Jews using forbidden practices.",
        "SCOPE: when a Jew uses divine names to effect concrete change, is that `magic` (suggesting forbidden) or `practice:use_of_holy_names` / `knowledge:practical_kabbalah` (suggesting legitimate)? Likely depends on the text's framing — confirm convention.",
        [],
    ),
    "supernatural:conversing_with_the_dead": (
        "A living character converses with a dead person (typically a tzaddik communing with the soul of a deceased rebbe).",
        "",
        [],
    ),
    "supernatural:demons": (
        "Demons / evil spirits (שדים, מזיקים) appear in the story.",
        "",
        [],
    ),
    "supernatural:light_or_fire_as_a_sign_of_righteousness": (
        "Light or fire appears around a character as a sign of his righteousness (typical: Torah-study illuminated by celestial fire).",
        "",
        [],
    ),
    "supernatural:communicating_with_the_invisible": (
        "A character communicates with invisible beings — angels, souls, voices from heaven (bat kol), etc.",
        "VIABILITY: appears to be an umbrella for several more-specific tags (`conversing_with_the_dead`, `angels`, …). Is this kept as the catch-all when none of the specifics fits, or should it always co-occur with one of them?",
        [],
    ),
    "supernatural:miracle": (
        "A miracle (נס) is depicted — a specific supernatural intervention.",
        "SHARPEN: what *isn't* a miracle in a Hasidic story? To avoid trivial application, propose: only apply when the text itself uses the word נס / מופת, or when the supernatural intervention is structured as a discrete event with a before/after (vs. ambient miraculousness).",
        [],
    ),
    "supernatural:reincarnation": (
        "Reincarnation (gilgul) of a soul is depicted or central to the plot.",
        "",
        [],
    ),
    "supernatural:angels": (
        "Angels (מלאכים) appear in the story.",
        "",
        [],
    ),
    "supernatural:pregnancy": (
        "Miraculous / supernatural pregnancy or conception (typically: a childless woman conceives via a tzaddik's blessing).",
        "RENAME: the bare word 'pregnancy' doesn't communicate 'miraculous'. Rename to `supernatural:miraculous_pregnancy`?",
        [],
    ),
    "supernatural:mystical_vision": (
        "A character has a mystical vision of something supernatural (faces glowing, the upper worlds, etc.).",
        "MERGE CANDIDATE with `experience:visions`.",
        [],
    ),
    "supernatural:contraction_of_the_road": (
        "Kefitzat ha-derekh — miraculous contraction of distance / fast travel.",
        "",
        [],
    ),
    "supernatural:angel_of_death": (
        "The Angel of Death (מלאך המוות, סמאל) appears as an agent in the story.",
        "",
        [],
    ),

    # ─── ethics-and-emotions ──────────────────────────────────────────────
    "ethics-and-emotions:prohibitions": (
        "Religious / moral prohibitions (אסור) are at issue in the story — typically a character is told not to do something, or violates a prohibition.",
        "SHARPEN: nearly every sin-story would qualify under a broad reading. Propose tightening: apply only when a specific prohibition is *named/cited* in the text (sex, food, oath, Shabbat), not just any moral lapse.",
        [],
    ),
    "ethics-and-emotions:punishment": (
        "A character is punished for wrongdoing (often by Heaven, sometimes by the tzaddik).",
        "",
        [],
    ),
    "ethics-and-emotions:fear": (
        "A character experiences fear (פחד, חרדה) — typically of God, of a tzaddik, of danger.",
        "BOUNDARY with `ethics-and-emotions:awe`: יראת שמים (fear/awe of Heaven) can be read both ways. Which tag — or both? Define the line so the audit applies consistently.",
        [],
    ),
    "ethics-and-emotions:repentance": (
        "Repentance (teshuvah) is depicted — a character turns from sin.",
        "",
        [],
    ),
    "ethics-and-emotions:sadness": (
        "Sadness / melancholy (עצבות, מרה שחורה) — typically as a spiritual problem the story addresses.",
        "SCOPE: is this specifically the Hasidic vice (atzvut, condemned in Hasidic doctrine), or also generic grief? E.g. when a parent mourns a dead child, is that this tag, or out-of-scope as ordinary sorrow?",
        [],
    ),
    "ethics-and-emotions:anger": (
        "A character is angry — typically as a moral failing or a heated moment.",
        "",
        [],
    ),
    "ethics-and-emotions:virtues": (
        "A general/unspecified virtue is at issue. Often the story's point is to illustrate one.",
        "UMBRELLA TAG QUESTION: should this always co-occur with a specific virtue tag (`virtues_humility`/`virtues_poverty`/…), or is it the catch-all for virtues that don't have their own sub-tag?",
        [],
    ),
    "ethics-and-emotions:virtues_humility": (
        "Humility (ענוה) as a depicted/discussed virtue.",
        "",
        [],
    ),
    "ethics-and-emotions:virtues_poverty": (
        "Poverty embraced as a virtue (typically the tzaddik refusing wealth, or living in voluntary poverty).",
        "",
        [],
    ),
    "ethics-and-emotions:joy": (
        "Joy (שמחה) as a depicted state, often religious — joy in serving God, joy on a holiday.",
        "",
        [],
    ),
    "ethics-and-emotions:charity": (
        "Charity (צדקה) — giving alms, providing for the poor.",
        "",
        [],
    ),
    "ethics-and-emotions:adultery": (
        "Adultery (ניאוף) is at issue in the story.",
        "",
        [],
    ),
    "ethics-and-emotions:shame": (
        "A character is shamed (בושה) — typically as a spiritual or social consequence.",
        "",
        [],
    ),
    "ethics-and-emotions:lust": (
        "Lust / desire (תאוה) is at issue.",
        "",
        [],
    ),
    "ethics-and-emotions:lying": (
        "Lying / deception by a character.",
        "",
        [],
    ),
    "ethics-and-emotions:pride": (
        "Pride / arrogance (גאוה) as a moral failing.",
        "",
        [],
    ),
    "ethics-and-emotions:awe": (
        "Awe (יראה, יראת שמים) — religious awe of God or of a tzaddik.",
        "See `ethics-and-emotions:fear` for the boundary question.",
        [],
    ),
    "ethics-and-emotions:resisting_temptation": (
        "A character resists a temptation (lust, profit, fame).",
        "",
        [],
    ),
    "ethics-and-emotions:prohibition_to_write": (
        "A specific prohibition against writing something down (typically esoteric teaching).",
        "VIABILITY: only 1 story. Keep as a narrow tag, or fold into `prohibitions` (with the secret content covered by `knowledge:secret_texts`)?",
        [],
    ),

    # ─── social-relations ─────────────────────────────────────────────────
    "social-relations:inter_hasidic_master_disciple_relationship": (
        "The relationship between a Hasidic master (rebbe) and his disciple is central.",
        "SHARPEN: the most-tagged social-relations tag (213 stories). Risk of being a default applied to nearly any Hasidic story. Propose: apply only when the relationship itself is the *subject* of the story (mentoring, succession, testing, breaking off), not when a disciple merely appears alongside his master.",
        [],
    ),
    "social-relations:with_non_jews": (
        "Interaction with non-Jews (גוים, ערלים) — including nobles, peasants, priests, etc.",
        "",
        [],
    ),
    "social-relations:with_non_hasidim": (
        "Interaction with mitnagdim / non-Hasidic Jews (typically maskilim or opponents).",
        "SCOPE: is this specifically *opposition-tinged* (mitnagdim, maskilim), or also any non-Hasidic Jew (e.g. an outsider rabbi who is friendly)?",
        [],
    ),
    "social-relations:conflict": (
        "Conflict — typically the tzaddik in conflict with an antagonist (Jewish opponent, non-Jew, demon).",
        "UMBRELLA TAG QUESTION: should this always co-occur with a more-specific `with_*` tag that names the counter-party, or stand alone when the conflict is unspecified?",
        [],
    ),
    "social-relations:retrospective_recognition": (
        "A character belatedly recognizes the tzaddik's identity / righteousness / past actions.",
        "",
        [],
    ),
    "social-relations:inter_hasidic": (
        "Interaction among Hasidim — not specifically the master-disciple relationship.",
        "BOUNDARY with `inter_hasidic_master_disciple_relationship`: when is one and when the other? Default to disciple-relationship when both apply, or always tag both?",
        [],
    ),
    "social-relations:with_the_authorities": (
        "Interaction with state authorities — government officials, governors, the Tsar, etc.",
        "BOUNDARY with `with_non_jews`: the authorities are almost always non-Jewish, so this tag effectively overlaps. Is it kept distinct because *power asymmetry* is the salient feature, while `with_non_jews` is about ethnicity? Confirm.",
        [],
    ),
    "social-relations:with_non_jews_hostility_against_jews": (
        "Non-Jewish hostility / antisemitism / pogrom-style violence against Jews.",
        "",
        [],
    ),
    "social-relations:marital_relationship": (
        "The marital relationship between two characters (typically a married couple) is depicted.",
        "",
        [],
    ),
    "social-relations:marriage_matchmaking": (
        "Matchmaking (שידוך) — arranging a marriage.",
        "",
        [],
    ),
    "social-relations:disobedience": (
        "A character disobeys an instruction — usually from the tzaddik, with consequences.",
        "",
        [],
    ),
    "social-relations:marriage": (
        "Marriage — the event, or the institution as the subject.",
        "BOUNDARY with `marriage_matchmaking`: is this only the wedding event itself, while matchmaking covers everything pre-wedding (search, negotiation, agreement)? Sharpen.",
        [],
    ),
    "social-relations:inter_hasidic_inheritance_of_leadership": (
        "Succession of leadership from one rebbe to the next (usually father-to-son).",
        "",
        [],
    ),
    "social-relations:competition": (
        "Competition between two tzaddikim, or between a tzaddik and a rival.",
        "MERGE CANDIDATE with `social-relations:inter_hasidic_conflict_between_tsaddikim` — is `competition` the milder form (rivalry without open conflict) and the longer name reserved for open conflict? Or accidental duplicate?",
        [],
    ),
    "social-relations:converts_and_conversion": (
        "Conversion to Judaism (or apostasy from it) is at issue.",
        "SCOPE: should the definition distinguish conversion-IN (גר) from conversion-OUT (apostasy)? They're very different phenomena and deserve different tags or at least different sub-types.",
        [],
    ),
    "social-relations:with_sinners": (
        "Interaction with Jewish sinners (averyianim) — the tzaddik reaching out, drawing back, judging.",
        "",
        [],
    ),
    "social-relations:inter_hasidic_conflict_between_tsaddikim": (
        "Conflict specifically between two tzaddikim (rebbes).",
        "See `competition` for the merge / sub-type question.",
        [],
    ),
    "social-relations:divorce": (
        "Divorce is depicted or at issue.",
        "",
        [],
    ),
    "social-relations:excommunication": (
        "Excommunication (חרם, נדה) imposed on someone.",
        "",
        [],
    ),
}


# ── Build the deliverable ─────────────────────────────────────────────────────

def _story_url(story_id: str) -> str:
    ed = re.sub(r"_\d+[A-Za-z]?$", "", story_id)
    # File-name has special-case for PeerMikdoshim vs Peer-MiKdoshim
    return f"https://www.hasidic-stories.org/Story/{ed}/{story_id}"


def main() -> None:
    if not INVENTORY.exists():
        sys.exit(f"Missing {INVENTORY} — run `python3 tag_data.py` first.")
    inv = list(csv.DictReader(open(INVENTORY, encoding="utf-8"), delimiter="\t"))
    inv_by_tag = {r["full_tag"]: r for r in inv}

    missing = [t for t in DEFS if t not in inv_by_tag]
    if missing:
        print(f"WARN: {len(missing)} draft definitions don't match any tag in the inventory:",
              file=sys.stderr)
        for t in missing:
            print(f"  - {t}", file=sys.stderr)

    cols = ["category", "tag", "n_stories", "n_editions",
            "draft_definition", "doubts_or_questions", "example_stories",
            "decision", "refined_definition"]

    rows = []
    for row in inv:
        tag = row["full_tag"]
        cat = row["top_tag"]
        if cat not in CATEGORIES:
            continue
        if tag not in DEFS:
            rows.append({
                "category": cat, "tag": tag,
                "n_stories": row["n_stories"], "n_editions": row["n_editions"],
                "draft_definition": "",
                "doubts_or_questions": "(no draft — please write one)",
                "example_stories": "",
                "decision": "", "refined_definition": "",
            })
            continue
        definition, doubts, exs = DEFS[tag]
        ex_urls = "; ".join(_story_url(sid) for sid in exs) if exs else ""
        rows.append({
            "category": cat, "tag": tag,
            "n_stories": row["n_stories"], "n_editions": row["n_editions"],
            "draft_definition": definition,
            "doubts_or_questions": doubts,
            "example_stories": ex_urls,
            "decision": "", "refined_definition": "",
        })

    # Sort: category, then "tags with doubts first" within category, then n_stories desc.
    rows.sort(key=lambda r: (r["category"],
                             0 if r["doubts_or_questions"] else 1,
                             -int(r["n_stories"])))

    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=cols)
        wr.writeheader()
        wr.writerows(rows)

    n_doubts = sum(1 for r in rows if r["doubts_or_questions"])
    print(f"Wrote {OUT}")
    print(f"  Total tags: {len(rows)}")
    print(f"  With doubts (PI should linger): {n_doubts}")
    print(f"  Straightforward: {len(rows) - n_doubts}")


if __name__ == "__main__":
    main()
