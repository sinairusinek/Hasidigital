"""
Per-tag detectability regime + Hebrew/Yiddish lexical signatures for the tag audit.

DETECTABILITY[full_tag] -> "lexical-strong" | "semantic" | "interpretive"
  lexical-strong: a concrete term reliably marks the phenomenon -> lexical signal usable
  semantic:       a theme/relation with no reliable keyword       -> embeddings + LLM
  interpretive:   a genre/structural judgment                     -> criteria-guided LLM only

LEXICONS[full_tag] = {"terms": [...], "homographs": [...]}
  terms:      substrings whose presence flags a candidate (matched on raw text)
  homographs: substrings that look like a term but mean something else (false friends),
              e.g. פ"נ = "פה נקבר" (buried here) rather than pidyon nefesh.

Only lexical-strong tags need a LEXICONS entry. Tags absent from DETECTABILITY default
to "semantic". This file currently covers the `practice` pilot category.
"""

# ── Detectability regime for the practice category ─────────────────────────────

DETECTABILITY = {
    # lexical-strong — concrete object/act with a reliable term
    "practice:pidyon_nefesh":            "lexical-strong",
    "practice:redemption_of_captives":   "lexical-strong",
    "practice:tvilah":                   "lexical-strong",
    "practice:smoking":                  "lexical-strong",
    "practice:dance":                    "lexical-strong",
    "practice:fasting":                  "lexical-strong",
    "practice:asceticism_fasting":       "lexical-strong",
    "practice:drinking_alcohol":         "lexical-strong",
    "practice:music":                    "lexical-strong",
    "practice:writing_amulets":          "lexical-strong",
    "practice:use_of_holy_names":        "lexical-strong",
    "practice:pilgrimage_to_the_graves_of_tsaddikim": "lexical-strong",
    "practice:releasing_agunot":         "lexical-strong",
    "practice:recitation_of_psalms":     "lexical-strong",
    "practice:ritual_slaughtering":      "lexical-strong",

    # semantic — themes/relations without a reliable keyword
    "practice:study":                    "semantic",
    "practice:protection":               "semantic",
    "practice:travel_to_the_tsaddik":    "semantic",
    "practice:sermon":                   "semantic",
    "practice:healing":                  "semantic",
    "practice:storytelling":             "semantic",
    "practice:reception_of_hasidim":     "semantic",
    "practice:meditation":               "semantic",
    "practice:lifesaving":               "semantic",
    "practice:asceticism":               "semantic",
    "practice:devekut":                  "semantic",
    "practice:healing_of_the_soul":      "semantic",
    "practice:solitude":                 "semantic",
    "practice:travel_to_other_tsaddik":  "semantic",
    "practice:sexual_abstinence":        "semantic",
    "practice:coping_with_alien_thoughts": "semantic",
    "practice:the_travels_of_the_tsaddik": "semantic",
    "practice:business_advice":          "semantic",
    "practice:conversing_with_angels":   "semantic",

    # interpretive — genre/structural/value judgments
    "practice:torat_ha_tsaddik":         "interpretive",
    "practice:failure":                  "interpretive",
    "practice:worship_through_corporeality": "interpretive",
}

# ── Lexical signatures (lexical-strong tags only) ──────────────────────────────
# Terms are matched as plain substrings against the raw story text. Hebrew has no
# casing; abbreviations appear with gershayim variants (" ' ׳ ״), so list the bare
# letter pairs and let substring matching catch punctuation variants.

LEXICONS = {
    "practice:pidyon_nefesh": {
        "terms": ["פדיון", "פדיונות", "פדיו", "פ\"נ", "פ'נ", "פ״נ", "פדה", "פודה"],
        "homographs": ["פה נקבר", "פ\"נ הרב", "פ\"נ ר'", "סחורה", "פדיון סחורה"],
    },
    "practice:redemption_of_captives": {
        "terms": ["פדיון שבוים", "פדיון שבויים", "שבוים", "שבויים", "שבוי", "פדיון שביים"],
        "homographs": [],
    },
    "practice:tvilah": {
        "terms": ["טבילה", "טבל", "מקוה", "מקווה", "טהרה", "מקואות", "נטבל"],
        "homographs": [],
    },
    "practice:smoking": {
        "terms": ["לולקע", "ליולקע", "מקטרת", "טאבאק", "טוטון", "עישן", "פיפקע", "מעשן", "טיטון"],
        "homographs": [],
    },
    "practice:dance": {
        "terms": ["ריקוד", "רקוד", "ריקודים", "ריקודין", "רקד", "ירקד", "במחולות", "מחולות"],  # NOT bare מחול (homograph of מחל "forgiven")
        "homographs": [],
    },
    "practice:fasting": {
        "terms": ["תענית", "תעניות", "צום", "צם", "התענה", "מתענה", "יתענה"],
        "homographs": [],
    },
    "practice:asceticism_fasting": {
        "terms": ["תענית", "תעניות", "סיגוף", "סיגופים", "פרישות"],
        "homographs": [],
    },
    "practice:drinking_alcohol": {
        "terms": ["יין", "משקה", "יי\"ש", "יי'ש", "שתה", "שיכור", "יין שרף", "בראנפן",
                  "שכרות", "לחיים", "כוס", "ישתה", "שתו"],
        "homographs": [],
    },
    "practice:music": {
        "terms": ["ניגון", "ניגונים", "נגן", "כלי זמר", "זמר", "שיר", "מנגן", "כינור", "זמרה"],
        "homographs": [],
    },
    "practice:writing_amulets": {
        "terms": ["קמיע", "קמיעות", "קמיעא", "קמיעין", "כתב קמיע"],
        "homographs": [],
    },
    "practice:use_of_holy_names": {
        "terms": ["שם המפורש", "שמות הקדושים", "שם הקדוש", "שמות קדושים", "השבעות",
                  "שם הוי", "צירופי שמות", "יחודים"],
        "homographs": [],
    },
    "practice:pilgrimage_to_the_graves_of_tsaddikim": {
        "terms": ["השתטחות", "השתטח", "ציון", "על הקבר", "אוהל", "קברי", "קבר הצדיק",
                  "על קברו", "ציון הקדוש"],
        "homographs": [],
    },
    "practice:releasing_agunot": {
        "terms": ["עגונה", "עגונות", "עגונא", "להתיר עגונ", "עיגון"],
        "homographs": [],
    },
    "practice:recitation_of_psalms": {
        "terms": ["תהלים", "תהילים", "מזמור", "מזמורי", "אמירת תהלים", "ספר תהלים"],
        "homographs": [],
    },
    "practice:ritual_slaughtering": {
        "terms": ["שחיטה", "שוחט", "שחט", "סכין", "טריפה", "כשרות", "חלף"],
        "homographs": [],
    },
}


# ── Working definitions (the "criteria" passed to the adjudicating LLM) ─────────
# Bilingual-friendly English glosses describing the phenomenon as currently used.
# These are draft definitions for the audit; the PI review refines them. Sharper
# definitions (esp. drawing boundaries between adjacent tags) reduce false verdicts.

DEFINITIONS = {
    "practice:pidyon_nefesh": "A monetary gift (pidyon / פדיון נפש / פ\"נ) given to a tzaddik in exchange for his prayer or intercession on one's behalf. NOT pidyon shvuyim (ransom of captives), NOT pidyon haben (redemption of firstborn), NOT commercial revenue, NOT the verse 'פדה בשלום נפשי'.",
    "practice:redemption_of_captives": "Pidyon shvuyim — raising or paying money to ransom/free Jewish captives or prisoners. NOT a personal monetary gift to a tzaddik (that is pidyon_nefesh).",
    "practice:tvilah": "Ritual immersion in a mikveh (טבילה / מקוה) for purity.",
    "practice:smoking": "Smoking a pipe/tobacco (לולקע, מקטרת, טאבאק).",
    "practice:dance": "Dancing (ריקוד, מחול), typically in a religious/joyous context.",
    "practice:fasting": "Fasting / a fast (תענית, צום) as a religious practice.",
    "practice:asceticism_fasting": "Ascetic self-mortification through fasting and afflictions (סיגופים, תעניות, פרישות).",
    "practice:drinking_alcohol": "Drinking alcohol (יין, משקה, יי\"ש) in a depicted scene.",
    "practice:music": "Music, melody, or song (ניגון, כלי זמר) as a depicted practice.",
    "practice:writing_amulets": "Writing/giving amulets (קמיע, קמיעות).",
    "practice:use_of_holy_names": "Use of divine/holy names, name-combinations, or yichudim (שמות הקדושים, שם המפורש) to effect something.",
    "practice:pilgrimage_to_the_graves_of_tsaddikim": "Visiting/prostrating at the graves of tzaddikim (השתטחות, ציון, אוהל).",
    "practice:releasing_agunot": "Acting to free an aguna — a 'chained' wife whose husband is missing (עגונה).",
    "practice:recitation_of_psalms": "Reciting Psalms (תהלים, מזמורים) as a practice.",
    "practice:ritual_slaughtering": "Ritual slaughter / shechita (שחיטה, שוחט) and its kashrut.",
    "practice:study": "Torah study / learning as a depicted activity of a character.",
    "practice:protection": "Protecting someone from harm, danger, or evil (often by the tzaddik).",
    "practice:travel_to_the_tsaddik": "A hasid/petitioner traveling to visit the tzaddik/rebbe.",
    "practice:sermon": "A tzaddik delivering a sermon, teaching, or homily (דרשה, תורה).",
    "practice:healing": "Healing of bodily illness through the tzaddik's intervention/blessing.",
    "practice:storytelling": "Telling stories (esp. of tzaddikim) as a depicted act within the story.",
    "practice:reception_of_hasidim": "The tzaddik receiving/hosting hasidim or petitioners (קבלת קהל).",
    "practice:meditation": "Contemplative/meditative practice (התבוננות).",
    "practice:lifesaving": "Saving someone's life from mortal danger.",
    "practice:asceticism": "Ascetic self-denial and mortification (סיגוף, פרישות), broadly.",
    "practice:devekut": "Mystical cleaving/communion with God (דבקות).",
    "practice:healing_of_the_soul": "Spiritual/psychological healing or repair of the soul, as opposed to bodily healing.",
    "practice:solitude": "Solitary withdrawal (התבודדות) for spiritual purposes.",
    "practice:travel_to_other_tsaddik": "A tzaddik traveling to visit another tzaddik.",
    "practice:sexual_abstinence": "Sexual abstinence/celibacy as a practice (פרישות מאשה).",
    "practice:coping_with_alien_thoughts": "Dealing with intrusive/alien thoughts during prayer or study (מחשבות זרות).",
    "practice:the_travels_of_the_tsaddik": "The tzaddik's own journeys/travels (not a petitioner traveling to him).",
    "practice:business_advice": "The tzaddik giving practical/business/financial advice.",
    "practice:conversing_with_angels": "Conversing with or receiving angels/maggidim.",
    "practice:torat_ha_tsaddik": "Exposition of the tzaddik's own teaching/doctrine (a teaching-focused story).",
    "practice:failure": "A practice or attempt that fails / does not succeed.",
    "practice:worship_through_corporeality": "Avodah be-gashmiut — worship/elevation through physical/material acts (עבודה בגשמיות).",
}


def definition(full_tag: str) -> str:
    return DEFINITIONS.get(full_tag, full_tag.split(":")[-1].replace("_", " "))


def detectability(full_tag: str) -> str:
    return DETECTABILITY.get(full_tag, "semantic")


def lexicon(full_tag: str):
    return LEXICONS.get(full_tag)


# ── Morphology-aware Hebrew matching ───────────────────────────────────────────
# Substring matching produces homographs: שיר (song) matches inside עשיר (rich),
# צום (fast) inside עצום (mighty), יין (wine) inside מעיין (gazing). We match a
# term as a whole Hebrew TOKEN, allowing standard attached prefixes/suffixes.
import re as _re

_HEB_TOKEN = _re.compile(r"[֐-׿]+")
_PREFIX = "והבלמכשדיתנא"   # particle (ו ה ב ל מ כ ש ד) + verb (י ת נ א) prefixes
_SUFFIX = "יהםותןךנ"   # י ה ם ו ת ן ך נ
_morph_cache = {}


def _is_plain(term: str) -> bool:
    """A plain single Hebrew word (no spaces, gershayim, or apostrophes)."""
    return bool(term) and all("֐" <= ch <= "׿" for ch in term)


def _morph_re(term: str):
    r = _morph_cache.get(term)
    if r is None:
        r = _re.compile(rf"^[{_PREFIX}]{{0,3}}{_re.escape(term)}[{_SUFFIX}]{{0,3}}$")
        _morph_cache[term] = r
    return r


def term_in_text(term: str, text: str) -> bool:
    """True if term occurs in text. Plain Hebrew words match as whole tokens
    (with optional standard prefixes/suffixes); multiword/abbreviation terms
    (spaces, gershayim) fall back to substring matching."""
    if not _is_plain(term):
        return term in text                      # multiword / פ"נ / יי"ש etc.
    rx = _morph_re(term)
    return any(rx.match(tok) for tok in _HEB_TOKEN.findall(text))
