# INALCO workshop, Paris — talk outline (draft)

**International Workshop "Digital Humanities and Intangible Cultural Heritage: The Case of Narratives"**
30 Nov – 1 Dec 2026, INALCO, 2 rue de Lille, 75007 Paris, Auditorium Dumézil (program: `~/Downloads/DH_ICH_NARR_DIPT_WEB.pdf`)

**Our slot:** Tue 1 Dec, 10:55–11:20 (25 min), Panel V "Hasidic Stories Go Digital", chaired by Chen Mandel-Edrei.
Title: **"The Mayse Tagging Machine, between the AI and the PI"**
- Right before us, 10:30–10:55: Gadi Sagiv, "From Close Reading to Distant Reading and Back: Digital Analysis of the First Century of Hasidic Stories (1814–1914)". Coordinate to avoid overlap.
- Respondent: Marcin Wodziński, 11:20–11:30.

### Who is in the room (possible collaborators)
- Mon, Panel I: Jovanović (WEAVE, Sephardic proverbs); Belinko Sabah (Israeli Proverb Indexing Project); Bikard & Fedchenko (online resource of narratives in Jewish languages, with translations; relevant to a bilingual interface)
- Mon, Panel II: Šmid (SephaNar digital catalog); Rollet, Thuillier & de la Rosa (LabHD-ILC, CSIC; sources → annotated data platform)
- Mon, Panel III: Rubin (Israel Folktale Archives digitization); Hasan-Rokem (IFA folktales). The IFA's tale-type and motif classification is the natural audience for the Propp and motif-index experiment.
- Tue, Panel IV: Shenhav (Talmudic reception trees); Papo (Sarajevo Sephardic Circle); Rotman (netlore)
- Tue, Written Tradition: Khalfallah (Kalīla wa-Dimna variants); Kacprzak (Thousand and One Nights in Judeo-Spanish); Mañero Lozano (Corpus de Literatura Oral); Abenójar Sanjuán (multilingual oral literature corpora)
- Tue 15:00–16:00: concluding discussion; 17:00: visit to the Alliance Israélite Universelle
- Organizers: Katja Šmid (ILC-CSIC), Željko Jovanović (CERMOM-INALCO), Marta Kacprzak (Warsaw)

## Intentions

- Shape the talk for the other workshop participants. Make it interesting to them and, ideally, tempt them into collaborating.
- The audience does not read Yiddish. Still, show the OCR pipeline, and possibly hint at a bilingual or transcription interface.
- The main focus is the stories, centered on annotating them for topics.
- Experiment with automatic annotation using schemas the audience would know: Propp, and the folk-story motif index. We tried these earlier in the project and decided they would not be good.
- Include results from our annotation tests.
- Include earlier work: building annotator personalities with different backgrounds to propose tagging schemas.

## Order of points

1. Our project has been advancing while AI sprang up and gradually developed. Briefly mention our pipeline (layout, text recognition, place and person annotation) as evolving along the axis: manual with the help of a digital platform / ML-trained / LLM + agentic.
2. Approaching content (topic/theme/motive?) annotation: the bewildered PI (because thinking of other users rather than his own scholarly interests). Trying a Nagelian "view from nowhere". Asking the chat, naive and incognito: superficial answers.
3. Multi-view: building "you are a scholar of" agents. Going a little into the workings of LLM interaction (the agentic LLM goes to learn, then proposes).
4. (How to lead to...) our eventual topic selection and the AI review of the team's annotation: the humans' low recall, high (but not perfect) precision.

## Theme to weave in (added 2026-11-10)

**The back and forth between rules and the scholars' intuition, and between rules and existing practice.** Category descriptions and guidelines can be written in advance from first principles, or derived after the fact from what annotators actually did, and then fed back.

- Material from our own project:
  - The tag definitions began thin. The LLM audit exposed where definitions and the team's practice diverged, and the definitions were patched. The tag-definitions review with Chen and Gadi continues this.
  - The audit found that human tagging has high precision but low recall. The humans' intuition was right when it fired, but it did not apply the rules exhaustively.
  - The LLM applies written rules literally, and so exposes what the rules leave unsaid.
- Parallel in the room: the starred local types (Haboucha's 930\*J, IFA's local types) are extensions created from practice, often without written descriptions. Offer: LLM drafts descriptions from the tales filed under a type → experts audit.
- Possible placement: a hinge between point 3 (the agents propose schemas = rules from outside) and point 4 (the audit of the team's annotation = rules confronted with practice).
