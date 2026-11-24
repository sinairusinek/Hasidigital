# Open work: editions and the site

Saved 2026-11-23, updated 2026-11-24 (inline-span removal, label normalisation,
upload state re-checked against the live server). Status page:
https://claude.ai/artifact/27VbvGDoUqFXUDRs3qy2Lu (built by `editions/build_edition_registry.py`,
which also writes `editions/edition-status.html`; the Topics and Online columns show what is
untagged and what needs a re-upload).

## Sinai

1. **Re-upload Shaarei-Haemuna and test it on the site.** Use `editions/online/Shaarei-Haemuna.xml`.
   Check:
   - **Page images**: they should show on every page now. Before the fix they stopped after page 3.
   - **The 13 split stories**:
     - in the edition view: https://www.hasidic-stories.org/Edition/Shaarei-Haemuna
     - on their story pages, e.g. https://www.hasidic-stories.org/Story/Shaarei-Haemuna/Shaarei-Haemuna_non-story-005_s1
     - in the story list, which should hold 101 stories.
2. **Re-upload 4 editions** (via oXygen into `data/`). Everything else is current: checked
   against the live eXist server on 2026-11-24 after your morning upload — 36 of 40 files are
   byte-identical to the repo in the body, so **do not re-upload those**.
   | Edition | Why |
   |---|---|
   | Shivhei-Habesht | the 114 unwrapped inline spans (סוס and 113 other swallowed words) + label normalisation |
   | Shivhei-Harav | `,תיוגים` labels normalised to `תיוגים` |
   | Khal-Hasidim | 1 inline span unwrapped (`double` on והוא) |
   | Maase-Zadikim | 1 inline span unwrapped (`double` on כל) |
3. *(folded into item 2)*
4. **Decide on Shemen-Hatov.** The tagger found 6 stories inside its non-story text. The RA
   drew those sections, so they were not split. One of the six (`non-story-178`, quotations
   praising the Maharal) is probably not a story.
5. **Spot-check the genre tags.** 359 story sections were judged to be something other than a
   story and carry only a genre tag:
   - `not-a-hasidic-story:sermon`: 264
   - `not-a-hasidic-story:halakhah`: 48
   - `not-a-hasidic-story:hagiography`: 47 (genealogies, approbations, praise; the vocabulary has no paratext tag)
   The tag is chosen by keywords in the tagger's reason (`editions/llm-tagging/writeback.py`), so
   halakhah may be over-assigned. Most of them are in Eser-Orot (149), Eser-Kedushot (79) and Derech-Haemuna (64).
6. **Eser-Orot section `non-story-003`.** 18 stories were found inside it and split out. It is
   probably a run of stories that Transkribus marked as one non-story region. Fix the
   segmentation later if needed ("restructure in retrospect", Sinai 2026-11-23).
7. **Delete `tmimei_derech.xml`** (lowercase, the April copy) from the server. It duplicates `Tmimei_Derech.xml`.
8. **Shaarei-Haemuna running heads.** Some real section titles were marked as running heads in
   Transkribus (e.g. the title of the book list on page 4), so the site hides them. Fixing them means
   re-marking the regions.
9. **Website issues list.** It is still to be written (see the memory note on website issues).

13. **`editions/online/` now means "ready to upload", not "live".** The 4 new editions were
    moved there before upload, which inverts PIPELINE step 17 (move after upload). Worth a line
    in PIPELINE.md if the convention should hold.

## Claude (next session)

1. After Sinai's Shaarei-Haemuna test, fix whatever the split breaks on the site, in all 46 split
   stories:
   | Edition | Split stories |
   |---|---|
   | Eser-Orot | 19 |
   | Shaarei-Haemuna | 13 |
   | Eser-Kedushot | 7 |
   | Derech-Haemuna | 2 |
   | Tiferet-Hayyim | 2 |
   | Torat-Haramal | 1 |
   | Maim-Rabim | 1 |
   | Toldot-Haniflaot | 1 |
2. **Verify the uploads**: canonical-XML compare of each uploaded file against the public REST read.
3. **Plan B, after Paris (1 Dec)**: topic-tag the 18 online editions that have almost no topic
   tags (Shemen-Hatov, Kokhvei-Or, shivheiZadikim, Buzina_Denehora, Hitgalut-HaZadikim, ...; the
   Topics column on the status page lists them). That is about 1,800 stories, possibly on Sonnet
   after a 100-story recalibration, and it unblocks Zenodo v2. See the memory note on LLM tagging.
4. **Malformed topic tags** in Adat-Zadikim, Khal-Hasidim, Khal-Kdoshim and Maase-Zadikim (`kabbalah`,
   `double`). Apply `editions/tag-audit/irregular-tags-mapping.tsv`; its 9 rows still wait for Sinai.
5. **Shivhei-Habesht**: the header lacks `editionStmt/edition/@n`.
6. **Person linking**: waits for the Shidduch expert review (`~/Documents/GitHub/Shidduch`).
7. **Unmatched places**: 1,672 place names are unmatched
   (`editions/kimatch/unmatched-after-link-2026-11-23.tsv`). Feed them to the Kima matching pipeline.

10. **Smichat-Moshe — RESOLVED, no action.** Its repo copy has fewer `type="check"` flags than
    the server had (24 -> 5) and fewer `ana="bio"` (22 -> 20), with byte-identical body text. On
    inspection this is deliberate curation, not a stripped file: three flags sat on tagging errors
    (`מענדיל` is a personal name, `מלך` is the word "king", `בוב קראקא` is a bad split of
    "לבוב קראקא" — all three are no longer placeName at all), and the rest were resolved by
    assigning an authority id (טשערנאוויץ H-LOC_462, פולדא H-LOC_718, בריסק H-LOC_136, לבוב
    H-LOC_40, לובלין H-LOC_56). The 5 still flagged are the genuinely unresolved ones. It was
    uploaded with the rest on 2026-11-24.
    Loose end: ביקאווסק, שרייביטש and מעליטץ stayed untagged with no `ref` — they belong with the
    1,672 unmatched place names in item 7.

11. **Inline `<span ana>` removed (2026-11-24).** 116 spans that wrapped individual words inside
    stories were an abandoned experiment; the site's renderer swallowed the wrapped word, so the
    Besht's stolen horse read "שהי׳ לבעש״ט אחד ונגנב ממנו" online. Unwrapped in Shivhei-Habesht
    (114), Khal-Hasidim (1) and Maase-Zadikim (1); 67 tags that existed only inline were merged
    into their story's תיוגים span, so nothing was lost. Script:
    `editions/scripts/unwrap_inline_ana_spans.py`.
    - KEPT: 731 EMPTY `<span ana>`. They are not the experiment — they are the only tag record in
      18 editions that never got the תיוגים text, and 18 of them carry a real tag
      (practice:pidyon_nefesh / pidyon_shvuyim / pidyon_haben, all correctly story-level).
    - The תיוגים label is now one spelling in all 39 editions (was also `תיוגים*` in
      Shivhei-Habesht and `,תיוגים` in Shivhei-Harav; 208 normalised).
    - Khal-Hasidim_0045 now visibly reads "והוא והוא". Decide whether that is a print error
      (`<choice><sic>`) or an OCR doubling (delete).
    - **The women article is unaffected**: none of this touched the counts. Recomputed against
      `zenodo/women-9ed/story_women.tsv` — 294/652 = 45.1%, every per-edition figure unchanged.

12. **Topic tagging (plan B) is NOT run and is on hold** (Sinai, 2026-11-24: do not continue).
    706 stories in 18 editions have no topic tag — each already carries an empty
    `<span ana="TBD:Unknown">` where its tags would go, so a future run can fill the existing span.
    By edition: Shemen-Hatov 207, shivheiZadikim 64, Kokhvei-Or 51, Buzina_Denehora 47,
    Shlosha-edrei-zon 45, Hitgalut-HaZadikim 43, MaasiyotUmaamarimYekarim 41,
    Maasiot-veSihot-Zadikim 37, SipurimUmaamarimYekarim 37, Sipurim-Nehmadim 33, Maasiot-Pliot 24,
    SipureiAnsheiShem 20, Sipurei-Kdoshim 16, Sefer-Moraim-Gdolim 15,
    MaasyiotMzadikeiYesodeiOlam 13, Dvarim-Yekarim 6, Tmimei_Derech 5, Smichat-Moshe 2.
    (`editions/llm-tagging/runs/` looks populated but holds the November *non-story* results, not
    story tagging. The older figure of ~1,800 predates the recent tagging.)
    This blocks Zenodo v2.
