#!/usr/bin/env python3
"""Replay the April 2026 Gemini correction pass (commit 58f4166) without calling Gemini.

That pass shuffled text because ner_pipeline's _unwrap_element was broken
(fixed 2026-11-21). The entity corrections themselves are recorded, with
character offsets into the pre-correction plain text, in
editions/incoming/ready/gemini-correction-log.tsv. This script takes the
pre-correction file (commit 2c7750c), applies the logged corrections, and
re-inserts the tags with the (fixed or, for checking, the old) strip code.

Usage:
  replay_gemini_correction.py EDITION_NAME OUT.xml [--buggy]
--buggy uses the old strip code, to check the replay reproduces the April file.
"""
import csv
import subprocess
import sys
from pathlib import Path

from lxml import etree

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from ner_pipeline import annotation_inserter as ai  # noqa: E402
from ner_pipeline.text_extraction import create_standoff_view  # noqa: E402
from ner_pipeline.gemini_corrector import preserve_refs  # noqa: E402
from ner_pipeline.nisba_fixer import fix_nisba_nesting  # noqa: E402

PRE_COMMIT = '2c7750c'
LOG = REPO / 'editions/incoming/ready/gemini-correction-log.tsv'


def _old_unwrap(el):
    """The pre-2026-11-21 _unwrap_element, verbatim in behaviour (buggy)."""
    parent = el.getparent()
    if parent is None:
        return
    idx = list(parent).index(el)
    if el.text:
        if idx > 0:
            prev = parent[idx - 1]
            prev.tail = (prev.tail or "") + el.text
        else:
            parent.text = (parent.text or "") + el.text
    for i, child in enumerate(el):
        parent.insert(idx + i, child)
    if el.tail:
        moved_count = len(el)
        if moved_count > 0:
            last_moved = parent[idx + moved_count - 1]
            last_moved.tail = (last_moved.tail or "") + el.tail
        elif idx > 0:
            prev = parent[idx - 1] if moved_count == 0 else parent[idx + moved_count - 1]
            prev.tail = (prev.tail or "") + el.tail
        else:
            parent.text = (parent.text or "") + el.tail
    parent.remove(el)


def buggy_strip(tree):
    t = "{http://www.tei-c.org/ns/1.0}"
    text_el = tree.find(f".//{t}text")
    for tag in ("persName", "placeName", "orgName", "date"):
        for el in text_el.iter(t + tag):
            _old_unwrap(el)
    for el in list(text_el.iter(t + "name")):
        if el.get("type") in ("misc", "work", "event"):
            _old_unwrap(el)


def corrections_for(name):
    rows = []
    with open(LOG, encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            if r.get('source_file') == f'{name}.xml':
                rows.append(r)
    return rows


def main():
    name, out = sys.argv[1], sys.argv[2]

    xml = subprocess.run(['git', 'show', f'{PRE_COMMIT}:editions/incoming/ready/{name}.xml'],
                         cwd=REPO, capture_output=True, check=True).stdout
    tree = etree.ElementTree(etree.fromstring(xml))

    existing, plain = ai.extract_existing_entities_simple(tree)
    rows = corrections_for(name)
    removed = {(int(r['start']), int(r['end'])) for r in rows if r['action'] == 'removed'}
    reclass = {(int(r['start']), int(r['end'])): r['corrected_label']
               for r in rows if r['action'] == 'reclassified'}
    added = [{'text': r['text'], 'start': int(r['start']), 'end': int(r['end']),
              'label': r['corrected_label']} for r in rows if r['action'] == 'added']

    known = {(e['start'], e['end']) for e in existing}
    missing = [k for k in removed | set(reclass) if k not in known]
    bad_added = [a for a in added if plain[a['start']:a['end']] != a['text']]

    corrected = []
    for e in existing:
        k = (e['start'], e['end'])
        if k in removed:
            continue
        e = dict(e)
        if k in reclass:
            e['label'] = reclass[k]
        corrected.append(e)
    # Maasim-Tovim was corrected by an earlier code version whose offsets drift
    # in 14 places; skip an addition whose text is not at its offset.
    corrected += [a for a in added if plain[a['start']:a['end']] == a['text']]
    corrected.sort(key=lambda e: (e['start'], e['end']))
    corrected = preserve_refs(corrected, existing)

    (buggy_strip if '--buggy' in sys.argv else ai.strip_existing_annotations)(tree)
    so, view, _ = create_standoff_view(tree)
    ai.insert_annotations(so, view, corrected)
    fix_nisba_nesting(tree)
    ai.strip_annotations_from_heads(tree)
    ai.save_annotated_xml(tree, out)
    # drop repeated <anchor xml:id=X/> (April removed Derech-Haemuna's by hand)
    import re
    s = Path(out).read_text(encoding='utf-8')
    seen = set()

    def _dedupe(m):
        if m.group(1) in seen:
            return ''
        seen.add(m.group(1))
        return m.group(0)
    s = re.sub(r'<anchor xml:id="([^"]+)"\s*/>', _dedupe, s)
    Path(out).write_text(s, encoding='utf-8')
    print(f'{name}: {len(existing)} entities before, log rows {len(rows)} '
          f'(removed {len(removed)}, reclassified {len(reclass)}, added {len(added)}); '
          f'log keys not found {len(missing)}; added text not matching {len(bad_added)}; '
          f'{len(corrected)} after')


if __name__ == '__main__':
    main()
