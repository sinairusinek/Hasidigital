"""Additions-only write-back for the recall-only pass (curated editions).

Unlike writeback.py, which FILLS empty TBD:Unknown placeholders and skips any story
that already has real tags, this script ADDS tags to stories that are already curated.

Design, so the pass is reversible and auditable:
  * the curated <span ana="..."> is NEVER modified or reordered;
  * additions go in a SECOND span, right after the curated one:
        <span ana="family:tag; family:tag" resp="#llm-recall">תיוגים</span>
    so `resp` alone distinguishes every LLM-added tag from every human one, and the
    whole pass can be undone by deleting the spans with that resp;
  * a tag already present on the story (in any span) is never added again;
  * tags on DROP are never added; tags on CONF3 are added only at confidence 3;
  * a division the tagger read as SEVERAL stories is skipped by default: the curated span
    describes the division as a whole, and merging 2-4 stories' tags onto it would attach
    each story's tags to all of them. Pass --merge-multi to add them anyway.

Usage:
  python3 editions/llm-tagging/writeback_additions.py EDITION.xml [--min-conf 2] [--write]
Without --write it reports what it would do and changes nothing.
"""
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from lxml import etree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tag_edition import divisions  # noqa: E402

T = '{http://www.tei-c.org/ns/1.0}'
RESP_ID = 'llm-recall'

# Adjudicated on 233 sampled additions (editions/llm-tagging/adjudication.tsv, step 3
# 2026-11-24). Precision of additions overall 81%; these fell below it.
DROP = {
    'practice:storytelling',    # 1/10 judged present: fires on the שמעתי transmission formula
    'spaces:beth_midrash',      # 2/6
}
CONF3 = {
    'times:shabbat',            # 7/10
    'practice:protection',      # 6/8
    'practice:sermon',          # 7/9
    'supernatural:reincarnation',  # 1/3, too thin to judge: added only at full confidence
}

RESP = ('Topic tags marked resp="#llm-recall": ADDITIONS proposed by Claude Opus 5.5 to stories '
        'already tagged by hand, to raise recall (editions/llm-tagging; est. precision 0.81 of '
        'additions, model-judged, 2026-11-24). The hand-assigned tags are the unmarked span; '
        'these additions are not reviewed by hand.')


def story_tags(d):
    """Every topic tag already on this story division, from any span."""
    out = set()
    for s in d.iter(T + 'span'):
        for x in re.split(r'[;\s]+', s.get('ana') or ''):
            if x and x != 'TBD:Unknown':
                out.add(x)
    return out


def main():
    path = Path(sys.argv[1])
    min_conf = int(sys.argv[sys.argv.index('--min-conf') + 1]) if '--min-conf' in sys.argv else 2
    merge_multi = '--merge-multi' in sys.argv
    tree = etree.parse(str(path))
    root = tree.getroot()
    txt = root.find(T + 'text')
    before = ''.join(txt.itertext())
    runs = HERE / 'runs' / path.stem
    stats, added_count, examples = Counter(), Counter(), []

    for did, d in divisions(root):
        if d.get('type') != 'story':
            continue
        f = runs / f'{did}.json'
        if not f.exists():
            stats['no result'] += 1
            continue
        res = json.loads(f.read_text())
        if len(res.get('stories', [])) > 1 and not merge_multi:
            stats['skipped: several stories in one div'] += 1
            continue
        have = story_tags(d)
        if not have:
            # an untagged story: that is writeback.py's job (fill the placeholder), not ours
            stats['skipped: not curated'] += 1
            continue
        prop = {}
        for s in res.get('stories', []):
            for t in s.get('tags', []):
                c = int(t.get('confidence', 2))
                prop[t['tag']] = max(prop.get(t['tag'], 0), c)
        new = {}
        for tag, c in prop.items():
            if tag in have:
                continue
            if c < min_conf:
                stats['filtered: low confidence'] += 1
                continue
            if tag in DROP:
                stats['filtered: dropped tag'] += 1
                continue
            if tag in CONF3 and c < 3:
                stats['filtered: conf3-only tag'] += 1
                continue
            new[tag] = c
        if not new:
            stats['no additions'] += 1
            continue

        # reuse this story's existing additions span if the script ran before
        sp = next((s for s in d.iter(T + 'span') if s.get('resp') == '#' + RESP_ID), None)
        if sp is None:
            cur = next((s for s in d.iter(T + 'span')
                        if s.get('ana') and s.get('resp') != '#' + RESP_ID), None)
            if cur is None:
                stats['skipped: no curated span'] += 1
                continue
            sp = etree.Element(T + 'span')
            sp.set('resp', '#' + RESP_ID)
            sp.text = 'תיוגים'
            sp.tail = cur.tail
            cur.tail = None
            cur.addnext(sp)
        sp.set('ana', '; '.join(sorted(new, key=lambda k: (-new[k], k))))
        stats['stories with additions'] += 1
        stats['tags added'] += len(new)
        for t in new:
            added_count[t] += 1
        if len(examples) < 5:
            examples.append((did, sorted(have)[:3], sorted(new)))

    after = ''.join(txt.itertext())
    assert after.replace('תיוגים', '') == before.replace('תיוגים', ''), 'text changed beyond the tag markers'

    hdr = root.find(T + 'teiHeader')
    ts = hdr.find(f'{T}fileDesc/{T}titleStmt')
    q = f'{T}respStmt[@{{http://www.w3.org/XML/1998/namespace}}id="{RESP_ID}"]'
    if ts.find(q) is None and stats['stories with additions']:
        rs = etree.SubElement(ts, T + 'respStmt')
        rs.set('{http://www.w3.org/XML/1998/namespace}id', RESP_ID)
        etree.SubElement(rs, T + 'resp').text = RESP
        etree.SubElement(rs, T + 'name').text = 'Claude Opus 5.5 (Anthropic)'
        rd = hdr.find(T + 'revisionDesc')
        if rd is None:
            rd = etree.SubElement(hdr, T + 'revisionDesc')
        ch = etree.SubElement(rd, T + 'change')
        ch.set('when', str(date.today()))
        ch.text = (f'recall pass: {stats["tags added"]} topic tags added to '
                   f'{stats["stories with additions"]} already-curated stories, marked '
                   f'resp="#{RESP_ID}"; not reviewed by hand')

    print(dict(stats))
    print('\ntop added tags:')
    for t, n in added_count.most_common(15):
        print(f'   {n:4d}  {t}')
    print('\nexamples:')
    for did, had, new in examples:
        print(f'   {did}: had {had}... + ADDS {new}')
    if '--write' in sys.argv:
        tree.write(str(path), xml_declaration=True, encoding='UTF-8')
        print('\nwritten', path)
    else:
        print('\n(dry run: nothing written; pass --write to apply)')


if __name__ == '__main__':
    main()
