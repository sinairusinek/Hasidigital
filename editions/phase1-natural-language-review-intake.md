# Phase 1 Natural-Language Review Intake

You can report errors in plain language. I will normalize each note into structured rows for review/action.

## Minimal note format (free text)
- Edition name
- Where in text (story title, opening words, or short quote)
- What is wrong
- What should happen instead

## Examples
1) "In Buzina_Denehora, in the story starting 'מעשה ברבי...', Dicta wrapped `<persName>` inside another `<persName>` around 'רבי נחמן'. Keep only one `persName`."
2) "In Adat-Zadikim, paragraph with 'נסע ללובלין', 'לובלין' is wrapped twice as `<placeName>`. Flatten to one tag."
3) "In Sipurei-Kdoshim, 'בעל שם טוב' got split into two entities; should be one `persName`."
4) "In Buzina_Denehora, I have the following line: <lb />בשמו מפי ר<persName>׳</persName> <persName>יוסקי</persName> ז״ל נכד בעמ״ח ספר <name type="work">דגל מחנה אפרים מסדילקיב</name>
indeed many '/׳ marks are annotated and this is wrong. 
5) "in line 164, and in other places with other titles, we have  <persName>מו"ה</persName> and this is also wrong. 
6) in line 170 the error is a simple false positive: <persName>יפרח</persName> . יפרח might be a name mainly in modern Hebrew but in that context it is not.
7) <placeName>ק"ק</placeName> is definitely wrong. ק״ק is an abreviation of קרית קודש and not a place name. It appears always in front of a placeName. 
8) <persName>בהשי<orgName />״ת</persName> is similar: השי״ת is an abbreviation of השם יתברך and means God. It can be annotated as name type="misc".
9) lines 291, 292 - וירצה ג״כ לעבוד את <name type="misc"><lb />ד</name>׳ בעבודה the expression ד׳ also reffers to God and can be annotated as name type="misc".
10) in Maasiot-Pliot line 40, >ב<date>שנת תרנ"ו</date> ל<placeName>פ"ק</placeName>: לפ״ק is an abbreviation which does not mean a placeName. 
11) Empty self-closing NER tags inside abbreviations: DictaBERT inserts empty `<orgName />`, `<persName />`, `<placeName />` tags right before abbreviation marks (״ or ׳). For example in Buzina_Denehora: `<name type="misc">שי<orgName />״</name>ת` — the orgName is vacant and should be removed; also the surrounding name tag stops too short (should include the ת). Same pattern with הקב״ה → `הקב״<orgName />ה`, רש״י → `רש<persName />״<orgName />י`. Found 91 instances (49 persName, 32 orgName, 10 placeName) across 11 editions.

## How I map notes to error types
- nested person tag -> `nested_duplicate_persName`
- nested place tag -> `nested_duplicate_placeName`
- same-type overlap -> `overlap_same_type`
- entity missing -> `missed_entity`
- boundary too long/short -> `wrong_boundary`
- wrong class/tag -> `wrong_label`
- tag should not exist -> `false_positive`
- valid entity removed -> `spurious_removal`

## Output targets
- Structured table: editions/phase1-dicta-failures-review-template.tsv
- Pilot decision inputs: editions/annotation-provenance.tsv + ner diff reports
