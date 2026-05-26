# Review of the **practice** tags — a consistency check

## What this document is

Every story in the collection carries theme tags — short labels for what the story is
about. Because these were added by many hands over the years, they are applied
unevenly: a story that plainly shows a given theme was sometimes never tagged with it.

This document checks one group of tags — the **practice** tags — for that kind of gap.
For each tag it lists stories that appear to belong to it but are **not currently tagged**,
so you can confirm or reject each suggestion. It also raises a few larger questions about
where the boundaries of these categories should lie.

## How it was made

For each tag we took the stories already marked with it, then searched the whole
collection for other stories that resemble them — both by the relevant Hebrew words and
by *meaning* (a language model places stories with similar content near one another, so we
can find related stories even when they share no keyword). Every story that came up was
then read in full by an automated reader, which judged whether the theme is really present
and gave a short reason. **Only the stories it judged a genuine match are listed below**
for your decision. We also spot-checked a random handful of stories that the search did
*not* surface, to estimate whether anything was missed.

A few words as they are used here:

- **Tag** — a theme label on a story (for example, *fasting*).
- **Suggested tagging** — a story that seems to show the theme but is not yet tagged with
  it. You confirm or reject each one.
- **Category boundary** — the question of which stories a tag should and should not cover
  (for example: does giving money to a holy man for a blessing belong to the same tag as
  ransoming a captive, or to a different one?).

**How to record a decision:** every suggestion has a **Confirm** column and a **Reject**
column, each holding the word *confirm* / *reject*. Mark the one that applies — highlight or
bold it, or delete the other — whichever is easiest. (We use plain words rather than
tick-boxes because tick-box symbols do not survive the conversion into Google Docs.)


## Deeper questions — should some category boundaries be redrawn?

These are the larger decisions the audit surfaced. They matter more than any single
tagging, because they change how a whole group of stories is classified. (In the earlier
*pidyon* review, a discussion like this led to splitting one blurred tag into clearer ones.)

1. **The redemption / pidyon family is half-built.** The tag now called *redemption of
   captives* is, in fact, the "pidyon for redeeming captives" that the pidyon review
   proposed creating — so should it be renamed for consistency with *pidyon nefesh*
   (the money-gift to a holy man)? And the third kind, *pidyon ha-ben* (redemption of a
   first-born son), has **no tag at all** even though such stories exist. Do you want a
   tag for it?

2. **Three "travel" tags that nearly coincide** — *travel to the holy man*, *travel to
   another holy man*, and *the travels of the holy man*. They differ only by who travels
   to whom, and in practice they overlap heavily. Keep the three-way distinction, or
   simplify it?

3. **A cluster about rescue and cure** — *healing*, *saving a life*, *healing of the soul*,
   and *protection* — sit very close together and are often applied to the same story.
   Where is the line between curing a body, saving a life, repairing a soul, and warding
   off harm? Clear conditions would help.

4. **Arrival as one event or two.** *Travel to the holy man* and *reception of the
   followers* describe the two halves of a single scene (the follower comes; the holy man
   receives him). Should they be one tag, or kept as two deliberate viewpoints?

5. **The ascetic-practice trio** — *asceticism*, *ascetic fasting*, and *fasting*. Is
   *ascetic fasting* a real sub-type worth its own tag, or should it fold into *fasting*
   or *asceticism*?

6. **Conditions of application (when does a passing detail count?)** A few recurring
   judgment calls, like the pidyon "does the commercial sense count?" question:
   - Does merely *mentioning* a ritual slaughterer count as the *ritual slaughtering* tag,
     or only a story that actually depicts the slaughtering?
   - Does taking snuff count as *smoking*?
   - Does the wine of Kiddush or Havdalah count as *drinking alcohol*?
   - Does singing a psalm in prayer count as *reciting psalms*, as *music*, or both?


## A few tagging issues that need your input

Most technical problems found in the audit (such as Hebrew word-matching and duplicate handling) we have already corrected on our side. The items below need a human decision:

**Garbled or incomplete tag labels** — these look like data-entry slips. For each, say what it was meant to be, or whether to drop it:

| label | on how many stories | what it should be (or 'drop') |
|---|---|---|
| `assistant:scribe,practice:writing_amulets` | 1 | |
| `practice:magic,besht_as_kabbalist` | 1 | |
| `practice:prayer,experience:shaking_during_prayer` | 1 | |
| `practice:ritual_bathing, practice:prayer` | 1 | |

**Three-level labels** (a tag inside a tag) — keep as a finer sub-type, or simplify?

| label | on how many stories | keep / simplify |
|---|---|---|
| `practice:magic:make_it_rain` | 1 | |
| `practice:prayer:outside` | 1 | |
| `practice:prayer:sigh` | 1 | |

## Suggested taggings — summary

Of the **43 tags audited**, **32** have at least one suggested tagging below. The remainder yield nothing to review: **3** had look-alike stories that the reader rejected on inspection (for example *dance*, where every match was the מחול / מחל spelling coincidence), and **8** had no resembling untagged stories at all (mostly the one- or two-story tags). (43 audited = 32 with suggestions + 3 all-rejected + 8 no candidates.)

The audit proposes **382 taggings to add** across 32 tags. The individual suggestions are in the companion spreadsheet **`practice-suggested-taggings.csv`** (opens in Google Sheets). Each row has the story link, the relevant Hebrew sentence, and a **decision** column already set to *confirm* — please change it to *reject* (or *unsure*) only on the rows you disagree with; everything left as *confirm* will be added.

| tag | definition | already tagged | suggested additions | search looks leaky? |
|---|---|---|---|---|
| protection | Protecting someone from harm, danger, or evil (often by the tzaddik). | 85 | 27 |  |
| travel to the tsaddik | A hasid/petitioner traveling to visit the tzaddik/rebbe. | 70 | 23 | yes — ~50% (consider wider scan) |
| reception of hasidim | The tzaddik receiving/hosting hasidim or petitioners (קבלת קהל). | 34 | 23 |  |
| asceticism fasting | Ascetic self-mortification through fasting and afflictions (סיגופים, תעניות, פרישות). | 1 | 23 |  |
| recitation of psalms | Reciting Psalms (תהלים, מזמורים) as a practice. | 1 | 23 |  |
| drinking alcohol | Drinking alcohol (יין, משקה, יי"ש) in a depicted scene. | 14 | 21 |  |
| healing of the soul | Spiritual/psychological healing or repair of the soul, as opposed to bodily healing. | 22 | 19 |  |
| use of holy names | Use of divine/holy names, name-combinations, or yichudim (שמות הקדושים, שם המפורש) to effect something. | 13 | 19 |  |
| music | Music, melody, or song (ניגון, כלי זמר) as a depicted practice. | 4 | 19 |  |
| study | Torah study / learning as a depicted activity of a character. | 105 | 18 |  |
| devekut | Mystical cleaving/communion with God (דבקות). | 23 | 18 |  |
| storytelling | Telling stories (esp. of tzaddikim) as a depicted act within the story. | 53 | 16 |  |
| ritual slaughtering | Ritual slaughter / shechita (שחיטה, שוחט) and its kashrut. | 1 | 16 |  |
| tvilah | Ritual immersion in a mikveh (טבילה / מקוה) for purity. | 41 | 15 |  |
| lifesaving | Saving someone's life from mortal danger. | 27 | 15 |  |
| meditation | Contemplative/meditative practice (התבוננות). | 27 | 11 |  |
| asceticism | Ascetic self-denial and mortification (סיגוף, פרישות), broadly. | 26 | 11 |  |
| sermon | A tzaddik delivering a sermon, teaching, or homily (דרשה, תורה). | 66 | 10 |  |
| healing | Healing of bodily illness through the tzaddik's intervention/blessing. | 63 | 8 |  |
| smoking | Smoking a pipe/tobacco (לולקע, מקטרת, טאבאק). | 20 | 8 |  |
| fasting | Fasting / a fast (תענית, צום) as a religious practice. | 24 | 7 |  |
| the travels of the tsaddik | The tzaddik's own journeys/travels (not a petitioner traveling to him). | 9 | 7 | yes — ~40% (consider wider scan) |
| pidyon nefesh | A monetary gift (pidyon / פדיון נפש / פ"נ) given to a tzaddik in exchange for his prayer or intercession on one's behalf. NOT pidyon shvuyim (ransom of captives), NOT pidyon haben (redemption of firstborn), NOT commercial revenue, NOT the verse 'פדה בשלום נפשי'. | 7 | 6 |  |
| solitude | Solitary withdrawal (התבודדות) for spiritual purposes. | 19 | 3 |  |
| travel to other tsaddik | A tzaddik traveling to visit another tzaddik. | 13 | 3 |  |
| redemption of captives | Pidyon shvuyim — raising or paying money to ransom/free Jewish captives or prisoners. NOT a personal monetary gift to a tzaddik (that is pidyon_nefesh). | 11 | 3 |  |
| pilgrimage to the graves of tsaddikim | Visiting/prostrating at the graves of tzaddikim (השתטחות, ציון, אוהל). | 10 | 2 |  |
| releasing agunot | Acting to free an aguna — a 'chained' wife whose husband is missing (עגונה). | 7 | 2 |  |
| writing amulets | Writing/giving amulets (קמיע, קמיעות). | 6 | 2 |  |
| torat ha tsaddik | Exposition of the tzaddik's own teaching/doctrine (a teaching-focused story). | 5 | 2 |  |
| sexual abstinence | Sexual abstinence/celibacy as a practice (פרישות מאשה). | 10 | 1 |  |
| business advice | The tzaddik giving practical/business/financial advice. | 9 | 1 |  |

**Tags with no missing taggings found** (existing tagging looks complete): clothing, conversing with angels, coping with alien thoughts, dance, failure, joke, make it rain, outside, sigh, spiritual, worship through corporeality.
