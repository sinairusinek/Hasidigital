# Open work: editions and the site

Saved 2026-11-23 at the end of the non-story NER session. Status page:
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
2. **Upload from `editions/online/` (everything now lives there; 39 files).** Checked against the
   live eXist server on 2026-11-24 (fetch + body compare, whitespace normalised):
   - **4 new on the site**: Eser-Kedushot, Eser-Orot, Shaarei-Haemuna, Torat-Haramal (all PASS the gate).
   - **8 whose text changed**, not just links (non-story correction; the first five also gained split
     stories): Derech-Haemuna (+2 stories), Toldot-Haniflaot (+1), Tiferet-Hayyim (+1), Maim-Rabim (+1),
     Peulat-Hatzadikim, Likutim-Hadashim, Maasim-Tovim, Seva-Ratzon.
   - **21 with new place links / topic tags only**: Hitgalut-HaZadikim, Buzina_Denehora, Shemen-Hatov,
     Maasiot-veSihot-Zadikim, SipureiAnsheiShem, Maase-Zadikim, Adat-Zadikim, Shivhei-Habesht,
     Maasiot-Pliot, Shivhei-Harav, Sipurim-Nehmadim, SipurimUmaamarimYekarim, Dvarim-Yekarim,
     Khal-Kdoshim, MaasyiotMzadikeiYesodeiOlam, Mifalot-HaZadikim, Sipurei-Zadikim,
     MaasiyotUmaamarimYekarim, Sefer-Moraim-Gdolim, Shlosha-edrei-zon, Tmimei_Derech.
   - **ALREADY CURRENT, skip**: Khal-Hasidim, Kokhvei-Or, PeerMikdoshim, Sipurei-Kdoshim, shivheiZadikim.
   - **HOLD: Smichat-Moshe** — see item 10.
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

10. **Smichat-Moshe: do not upload yet.** Its repo copy has *lost* annotation the live server still
    has, while the body text is byte-identical:
    - `type="check"` (the "place id needs verifying" flag): 24 live -> 5 in the repo, **19 lost**;
    - `ana="bio"`: 22 live -> 20 in the repo (6 lost: 4x פראג, לובלין, וויזנעצע; 4 others added).
    Uploading would overwrite the live flags for good. Decide whether those 19 `check` marks were
    resolved on purpose or stripped by a script pass, and restore them if needed.
    Khal-Kdoshim has the same shape but much smaller (`type` -2, text identical) — worth a glance.
