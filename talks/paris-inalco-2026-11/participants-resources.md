# INALCO workshop: participants' projects, data, schemas, tools

Compiled 2026-11-10 from web research. Most entries come from research agents and have not been checked by hand, so open the links before quoting anything. **UNVERIFIED** means the item could not be confirmed online.

Workshop page: https://www.fabula.org/actualites/137620/international-workshop-digital-humanities-and-intangible-cultural-heritage-the-case-of-narratives.html (the workshop is organized within SephaNar)

## Bottom line

- Almost none of these projects publish machine-readable data, schemas, annotation guidelines or code. Most are early-stage, announced, or print-oriented.
- Our TEI corpus, tag taxonomy, LLM tagging pipeline and precision-audit method would therefore be offered as **infrastructure** to the room, not just as results.
- The shared vocabulary of this field is **AT/ATU** (IFA, CLO, Haboucha for Judeo-Spanish) and motif indexes (Thompson; El-Shamy for Arabic material). That makes the Propp/ATU/motif experiment in the talk directly legible to them.

---

## Israel Folktale Archives (IFA), University of Haifa: Michal Rubin (Mon 18:30)

Site: https://lib.haifa.ac.il/ifa/ (English: https://lib.haifa.ac.il/en/ifa/). The old ifa.haifa.ac.il now redirects there. Checked directly.

- **Scale:** more than 25,000 tales from about 70 communities. Founded by Dov Noy in 1955 and at Haifa since 1983. UNESCO Memory of the World. Academic head: Prof. Dina Stein (since 2016). Coordinator: Michal Rubin (since 2023).
- **Catalogue:** Primo, https://haifa.primo.exlibrisgroup.com/nde/home?vid=972HAI_MAIN:IFA. Record permalinks follow the pattern `.../permalink/f/1t5m5kj/ASAI_XML0000000NNNNN`. The XML IDs suggest an XML source behind the catalogue. Primo renders with JavaScript, so a full record was not inspected (it could be checked in Chrome).
- **Search fields** (per the search-tips page):
  - narrator (שם המספר/ת)
  - recorder (שם הרושם/ת)
  - community (עדה)
  - genre (סוגה)
  - **tale type, Aarne–Thompson** (טיפוס סיפורי)
  - keywords (objects, places, characters)
  - year recorded
  
  The 1973 AT index is used; ATU 2004 is available in print only. There is no separate motif field.
- **Sample texts:** "Selected tales" pages give full Hebrew text plus IFA no., recorder, narrator and community:
  - https://lib.haifa.ac.il/ifa/סיפורים-מהאסף/
  - https://lib.haifa.ac.il/en/ifa/selected-tales-from-the-archives/
  
  Some displayed IFA numbers do not match their permalinks.
- **Past computational projects** (https://lib.haifa.ac.il/en/ifa/research/):
  - **ISF comparative digitized research (to 2009/2011):**
    - Database of more than 7,000 tales.
    - Fields: bibliographic accounts, informant biography, telling context, **content abstract**, genres.
    - Classification: AT type plus Uther's updates, plus **IFA oicotypes**; 9 new oicotypes were identified.
    - **Thematic indexing:** characters, space, time, customs, beliefs, transformation, objects, linguistic idioms.
    - Public accessibility of this database is not stated.
  - **"Focus Project" (1978–79):** a computerized "storyteller", based on Ščeglov and Žolkovskij's generative poetics (post-Propp) and applied to IFA legends of Moroccan Jews. A good historical hook for the "Mayse Machine" framing.
- **Type indexes in print:** the JPS *Folktales of the Jews* volumes (ed. Ben-Amos) include AT/ATU-to-IFA-number indexes, and the Sephardic volume also has a motif index. *The Power of a Tale* (2019, ed. Rotman et al.): https://muse.jhu.edu/book/68567. One reviewer notes that ATU fits only about half its tales, which echoes our own Propp/motif verdict.
- **Peer archives:** IFA's "additional resources" page lists the Dutch Folktale Database (https://www.verhalenbank.nl/), ISEBEL (https://search.isebel.eu/), Dúchas, WossiDiA, Sefer HaAggada (https://agadastories.org.il/) and Mas"a (https://folkmasa.org/).
- **Hook:** IFA has decades of expert AT, oicotype and thematic labels on Hebrew text, which is exactly what is needed to benchmark LLM tale-type and theme tagging. Our pipeline (OCR → TEI → LLM tagging → audit) could serve their typing and indexing backlog. Ask whether the 7,000-tale research database (abstracts and thematic index) can be exported.

## Galit Hasan-Rokem (HUJI, emerita): Mon 19:00

- No digital project of her own was found. Related work: Folklore Research Center fieldwork digitization and return to the community (Fogel & Schrire, *Ethnologia Europaea* 53/1, https://ee.openlibhums.org/article/id/9433).
- She founded the HUJI **Proverb Indexing Project** (see Belinko Sabah below).
- **Direct Hasidic link:** Hasan-Rokem & Magid, "Folk Narratives", in Wodziński (ed.), *Studying Hasidism* (2019), pp. 127–143.
- **Hook:** she could validate whether LLM type and motif annotation transfers from fieldwork transcripts to printed Hasidic anthologies.

## SephaNar (Katja Šmid, ILC-CSIC) and the LabHD-ILC platform: Mon 17:30–18:15

- Project: https://ilc.csic.es/es/research-project/narraciones-sefardies-edicion-estudio-creacion-primer-catalogo-digital-sefanar (PID2023-150221NB-I00, 2024–2028).
- **Corpus:** 16th–21st-century Judeo-Spanish narratives (aljamía, Latin script, oral). Genres include **hagiography, rabbinic tales**, legends, fables and midrash, so the genre overlap with Hasidic tales is high.
- **Catalogue:** not public yet, and its schema is unpublished. The field's standard index is Haboucha, *Types and Motifs of the Judeo-Spanish Folktales* (1992, ATU-style), which Šmid uses in her articles. Adoption of it for the catalogue is UNVERIFIED.
- Open-access output: Šmid, *Musar Literature in Ladino* (2025), https://digital.csic.es/bitstream/10261/405953/1/Musar_Literature_Ladino.pdf
- **LabHD:**
  - Page: https://ilc.csic.es/en/org-structure/digital-humanities-laboratory-hd-lab
  - Staff: Nadège Rollet and Sabine Thuillier.
  - CSIC offers TEI/XML/IIIF annotation services.
  - No GitHub or Zenodo output found.
- **Javier de la Rosa Sánchez:** CSIC technical staff, https://github.com/delarosajav (ML and NLP pipelines). **Not** the Javier de la Rosa of the National Library of Norway (ALBERTI).
- **Hook (strongest):** a catalogue still being designed, an in-house developer, and adjacent genres. Offer our TEI and taxonomy model plus the LLM pipeline and audit method, and propose a shared Haboucha/ATU layer for cross-corpus parallel-story detection. Rotman, Papo, Kacprzak and Jovanović all sit on the SephaNar team.

## WEAVE (Željko Jovanović, CERMOM-INALCO): Mon 16:10

- No website or funding record found (UNVERIFIED).
- Background: MSCA "LadinoProverbs" (2019–21), https://cordis.europa.eu/project/id/792150; "Judeo-Spanish Proverbs from Bosnia", *EJJS* 2023.
- **Hook:** a shared "proverb/saying-in-narrative" tag, since Hasidic tales also carry sayings and morals.

## Israeli Proverb Indexing Project (Lital Belinko Sabah, HUJI): Mon 16:35

- No public database found.
- **Facet scheme (secondhand, UNVERIFIED):** Hasan-Rokem & Kats 2009, cited in Lauhakangas 2023 (https://omp.zrc-sazu.si/zalozba/catalog/download/2148/8771/2729?inline=1). Facets:
  - textual form
  - syntactic structure
  - usage context
  - literary source
  - time/place of origin
  - semantic field
- Related: Bar-Ilan proverb ontology (Zhitomirsky-Geffet et al., *JASIST* 2017).
- **Hook:** a controlled facet vocabulary like this is what LLM labeling with human audit is for.

## Jewish-languages narrative resource (Arnaud Bikard and Valentina Fedchenko, INALCO): Mon 17:00

- Probable parent project: ANR **LJTRAD** (ANR-18-CE27-0014), https://anr.fr/Project-ANR-18-CE27-0014. Its site, http://ljtrad.yiddish.nu, currently returns an error.
- **Data:** Yiddish–French–Russian aligned parallel literary corpus, CLARIN 2025, https://doi.org/10.3384/ecp222.1604. Distribution is planned via ORTOLANG.
- Fedchenko's papers: https://aclanthology.org/people/valentina-fedchenko/
- **Hook:** the natural partners for a **bilingual / translation interface**, and **Yiddish** is shared. Test whether narrative tags survive translation.

## Ghilad Shenhav (LMU): Tue 9:00

- Project "Talmudic Ilanot", which maps the modern reception of the Talmud: https://www.en.zis.geschichte.uni-muenchen.de/people/faculty-staff/ghilad-shenhav/index.html. No public data or methods.
- **Hook:** our planned text-reuse and citation work (Dicta, Sefaria). Hasidic tales retell aggadot, so the two projects could share "source → retelling" links, and an LLM could classify the reuse type.

## Eliezer Papo (BGU): Tue 9:25

- ISF 2024–27: Sarajevo Sephardic Circle, a scholarly edition with Hebrew translation, https://cris.bgu.ac.il/en/persons/eliezer-papo/. Its digital or TEI status is unknown.
- Laura Papo Bohoreta papers: https://portal.ehri-project.eu/units/ba-006040-o_bp_168
- Earlier: annotated Ladino Me'am Lo'ez editions.
- **Hook:** the edition is still being built, so a TEI model and LLM annotation (NER, `<foreign>`, motifs) could still be adopted, giving a Ladino low-resource test.

## David Rotman (HUJI): Tue 9:50

- Site: https://davidrotman.huji.ac.il/. ISF project on the cult of Rachel the Matriarch, which includes online narratives. No public dataset.
- Co-editor of *The Power of a Tale* (IFA); "Folk Stories about Rabbi Mordechai Eliyahu…", *JSJF* 35 (2023).
- **Hook:** legends about modern rabbis online continue the Hasidic tale genre, so our taxonomy could be tested on his web corpus as a cross-period transfer test.

## Gadi Sagiv (OUI): Tue 10:30, right before us

- The ISF project page "Toward Automatic Annotation of Hasidic Stories", https://www.openu.ac.il/en/dhsshub/projects/pages/Toward-Automatic-Annotati.aspx, does not mention hasidic-stories.org or the schema. Worth updating it before Paris.
- Wodziński, Gellman & Sagiv, "Marriage, leadership, and dynasties in Hasidism: big data approach", *Religion* 55(1).

## Khouloud Khalfallah: AnonymClassic / Kalīla wa-Dimna (FU Berlin, ERC 742635): Tue 11:30

- Preview edition: https://kalila-and-dimna.fu-berlin.de/about. About 130 digitized manuscripts, each with facsimile, Arabic transcription, English translation and description.
- **Model:** numbered narrative **segments** aligned across versions. They rejected TEI as too steep and not Arabic-specific, and built their own platform (https://refubium.fu-berlin.de/handle/fub188/33230).
- Guidelines (in development): /guides/transcription-guidelines, /guides/segmentation-and-collation-principles.
- Collation tool: LERA (https://lera.uzi.uni-halle.de).
- No bulk download or licence found.
- **Hook:** a counterpoint to our TEI approach, and close to our cross-edition near-duplicate detection. Test LLM segment alignment against their manual survey.

## Marta Kacprzak (Warsaw): Tue 11:55

- Edited Ladino adaptations of European fiction (*Robinson Crusoe*, *Gulliver*). No *Nights* publication or dataset found (UNVERIFIED).
- Likely sources: Bibliotheca Sefarad (https://www.bibliothecasefarad.com/digitalizados/) and the UW Sephardic Studies collection (https://content.lib.washington.edu/sephardicweb).
- **Hook:** Hebrew-script narrative from the same print world as ours. OCR/HTR, segmentation and NER are shared problems.

## David Mañero Lozano: Corpus de Literatura Oral (Jaén): Tue 12:20

- https://corpusdeliteraturaoral.ujaen.es: about 9,840 published records (of more than 50,000 deposited), mostly Spain plus the Mediterranean and Latin America. **CC BY-NC 4.0.**
- **Each record:** recording, transcription, cataloguing data, notes, bibliography and **plot summary**. Some narrative titles carry **ATU numbers**.
- **Genre codes:** r = romancero, c = cancionero, n = narrativa.
- No API or export is mentioned (UNVERIFIED that none exists).
- Related: CONOCOM (PID2021-122438NB-I00); *Boletín de Literatura Oral*, https://revistaselectronicas.ujaen.es/index.php/blo
- **Hook (best ready-made benchmark):** partly ATU-coded and summarized, so it can test LLM ATU assignment and LLM summaries against human ones. Ask for an export of the "n" records.

## Óscar Abenójar Sanjuán (Colmex): Tue 12:45

- ATU-based comparative studies, North Africa ↔ Americas (in *BLO*). Contributor to CONOCOM/CLO. No corpus or tool of his own found.
- **Hook:** cross-language tale-type matching, analogous to our cross-edition twin detection.

---

## Generic target schemas and LLM precedents (for the Propp/ATU/motif experiment)

| Resource | What | Where |
|---|---|---|
| Thompson Motif-Index, machine-readable | JSON plus a Python interface | https://github.com/fbkarsdorp/tmi |
| TMI + ATU + annotated tales ("trilogy") | `tmi`, `atu_df`, `atu_seq` (motifs per type); `aft` = Ashliman folktexts with ATU tags; CC BY-SA | https://github.com/j-hagedorn/trilogy · https://doi.org/10.5281/zenodo.6575263 |
| ProppLearner (Finlayson) | 15 Russian tales, double-annotated Propp functions (stand-off XML) | https://dspace.mit.edu/handle/1721.1/100054 · DSH 32(2) 2017 |
| MFTD | multilingual folktales with ATU; may have moved to TEITOK (UNVERIFIED) | DFKI background: https://www.dfki.de/fileadmin/user_upload/import/9705_LT4DH-CEE003.pdf |
| Full ATU (Uther 2004/2024) | print only; no open digital version | — |

LLM papers:

- **Alyami & Finlayson 2026, "Automated Motif Indexing on the Arabian Nights"** (El-Shamy index; fine-tuned Llama3 F1 0.85). https://arxiv.org/abs/2603.19283. The closest precedent to our task.
- Arčon, Robnik-Šikonja & Tratnik 2025, ATU 510A (Cinderella) via motif yes/no checks. They find the typology too fine-grained, which echoes our own verdict. https://arxiv.org/abs/2510.18561
- Meaney, Alex & Lamb 2024 (NLP4DH), ATU classification of Irish and Gaelic tales. An SVM baseline was competitive. https://aclanthology.org/2024.nlp4dh-1.31.pdf
