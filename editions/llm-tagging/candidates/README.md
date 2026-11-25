# Candidate editions: recall-pass additions (NOT the repo's editions)

Written 2026-11-25. These are **copies** of `editions/online/{Khal-Hasidim,Shivhei-Habesht}.xml`
with the recall pass's proposed tag additions written in. They exist so Sinai can upload them,
survey them on the site, and then decide whether to keep them. The repo's own editions in
`editions/online/` are UNTOUCHED.

| Edition | Curated tags (kept) | Added | Stories gaining tags |
|---|---|---|---|
| Khal-Hasidim | 2,737 on 254 stories | 1,320 | 230 |
| Shivhei-Habesht | 1,866 on 218 stories | 908 | 188 |

## What was done

`writeback_additions.py` put every addition in a SECOND span after the curated one:

    <span ana="...">תיוגים</span>                          <- the RA's tags, untouched
    <span ana="..." resp="#llm-recall">תיוגים</span>        <- additions

Verified on these exact files:
  * the 472 curated spans are byte-identical, in the same order, with the same `resp`;
  * the narrative text is unchanged apart from the תיוגים marker word;
  * deleting the 418 `resp="#llm-recall"` spans plus the header respStmt/change restores
    each file to `editions/online/` byte-for-byte (canonical serialisation compared);
  * both files are well-formed.

Filters applied: confidence >= 2; tags on the DROP list never added; four low-precision tags
added only at confidence 3; divisions the tagger read as several stories skipped (20 and 19).

## Caveat on quality

Precision of the additions is **0.81, model-judged** on 233 sampled additions
(`../adjudication.tsv`, step 3). No human has read them. That figure is an estimate by the
same family of model that proposed the tags, so it is not independent evidence.

## If Sinai keeps them

Copy over `editions/online/`, run `preupload_check.py` (PIPELINE step 12 gate), commit.

## If Sinai rejects them

Delete this folder. Nothing else to undo.

## Note on uploading these

Both files also carry the pending inline-span/label fixes from 2026-11-24 (TODO Sinai item 2),
so uploading these candidates covers that item for these two editions as well.
Uploading Shivhei-Habesht REMOVES three malformed tags that exist only on the server:
`practice:magic:make_it_rain` (0005B), `practice:magic,besht_as_kabbalist` (0014),
`practice:prayer,experience:shaking_during_prayer` (0015). None is in the vocabulary.
