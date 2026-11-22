"""Write the tagger's results (runs/{slug}/*.json from tag_edition.py) into the edition XML.

Usage: python3 editions/llm-tagging/writeback.py EDITION.xml [--min-conf 2] [--write]

For each <div type="story">: the tags (confidence >= --min-conf, the calibrated threshold)
of every story the tagger found in it go into one story-level span right after the
storyHead, in the form the curated editions use:
    <span ana="family:tag; family:tag" resp="#llm-tagging">תיוגים</span>
Existing TBD:Unknown placeholder spans in the div are removed; a div that already has
real topic tags is left alone (curated tags are never overwritten).
The header gets <respStmt xml:id="llm-tagging"> and a revisionDesc change, so the XML
records that these tags are LLM-assigned and not reviewed by hand.
The verbatim quotes stay in the JSON (standoff), not in the XML.

Reported, not changed: story divs where the tagger found no story (e.g. a teaching),
divs where it found several stories, and non-story divs that contain a story.
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
RESP = ('Topic tags: assigned by Claude Opus 5.5 with the project\'s topic scheme '
        '(editions/llm-tagging; calibrated 2026-11-16, est. precision 0.89 / recall 0.90, model-judged); '
        'not reviewed by hand')


def main():
    path = Path(sys.argv[1])
    min_conf = int(sys.argv[sys.argv.index('--min-conf') + 1]) if '--min-conf' in sys.argv else 2
    tree = etree.parse(str(path))
    root = tree.getroot()
    txt = root.find(T + 'text')
    before = ''.join(txt.itertext())
    runs = HERE / 'runs' / path.stem
    stats, report = Counter(), []
    # genre.json: {div_id: "not-a-hasidic-story:TAG"} for story divs the tagger judged not to be a
    # Hasidic story (Sinai 2026-11-22: keep the author's division, mark its genre with a tag)
    gf = runs / 'genre.json'
    genre = json.loads(gf.read_text()) if gf.exists() else {}
    for did, d in divisions(root):
        f = runs / f'{did}.json'
        if not f.exists():
            if d.get('type') == 'story':
                report.append((did, 'story', 'NOT TAGGED (no result)', ''))
            continue
        res = json.loads(f.read_text())
        kind = res['unit']['kind']
        stories = res.get('stories', [])
        if d.get('type') != 'story':
            split = [x for x in d.iter(T + 'div') if x.get('type') == 'story']
            if stories and len(split) < len(stories):
                report.append((did, d.get('type'), f'{kind}: contains {len(stories)} story(ies) — not tagged in XML',
                               '; '.join(s.get('summary_en', '')[:90] for s in stories)))
            continue
        tags = {}
        for s in stories:
            for t in s['tags']:
                c = int(t.get('confidence', 2))
                if c >= min_conf:
                    tags[t['tag']] = max(tags.get(t['tag'], 0), c)
        if did in genre:
            tags[genre[did]] = 3
        elif not tags and kind == 'saying_or_teaching':
            # option (b), Sinai 2026-11-22: keep the author's story division, mark its genre
            why = res['unit'].get('why', '').lower()
            tags['not-a-hasidic-story:halakhah' if any(w in why for w in ('halakh', 'custom', 'law'))
                 else 'not-a-hasidic-story:sermon'] = 2
            stats['genre tag'] += 1
        if kind != 'hasidic_story' or len(stories) != 1:
            report.append((did, 'story', f'{kind}, {len(stories)} stories', res['unit'].get('why', '')))
        spans = [s for s in d.iter(T + 'span')]
        real = [s for s in spans if any(x and x != 'TBD:Unknown' for x in re.split(r'[;\s]+', s.get('ana') or ''))]
        if real:
            stats['kept curated'] += 1
            continue
        if not tags:
            stats['no tags'] += 1
            continue
        for s in spans:  # placeholders only
            par = s.getparent()
            prev = s.getprevious()
            tail = (s.tail or '')
            if prev is not None:
                prev.tail = (prev.tail or '') + tail
            else:
                par.text = (par.text or '') + tail
            par.remove(s)
        sp = etree.Element(T + 'span')
        sp.set('ana', '; '.join(sorted(tags, key=lambda k: (-tags[k], k))))
        sp.set('resp', '#llm-tagging')
        sp.text = 'תיוגים'
        head = next((h for h in d.findall(T + 'head') if h.get('type') == 'storyHead'), None)
        if head is not None:
            sp.tail = head.tail
            head.tail = None
            head.addnext(sp)
        else:
            sp.tail = d.text
            d.text = None
            d.insert(0, sp)
        stats['tagged'] += 1
        stats['tags'] += len(tags)
    # text may only gain the marker word 'תיוגים'
    after = ''.join(txt.itertext())
    assert after.replace('תיוגים', '') == before.replace('תיוגים', ''), 'text changed beyond the tag markers'
    hdr = root.find(T + 'teiHeader')
    ts = hdr.find(f'{T}fileDesc/{T}titleStmt')
    if ts.find(f'{T}respStmt[@{{http://www.w3.org/XML/1998/namespace}}id="llm-tagging"]') is None and stats['tagged']:
        rs = etree.SubElement(ts, T + 'respStmt')
        rs.set('{http://www.w3.org/XML/1998/namespace}id', 'llm-tagging')
        etree.SubElement(rs, T + 'resp').text = RESP
        etree.SubElement(rs, T + 'name').text = 'Claude Opus 5.5 (Anthropic)'
        rd = hdr.find(T + 'revisionDesc')
        if rd is None:
            rd = etree.SubElement(hdr, T + 'revisionDesc')
        ch = etree.SubElement(rd, T + 'change')
        ch.set('when', str(date.today()))
        ch.text = f'topic tags (LLM, confidence >= {min_conf}) written for {stats["tagged"]} stories; not reviewed by hand'
    print(dict(stats))
    for r in report:
        print('  REPORT', ' | '.join(str(x) for x in r))
    if '--write' in sys.argv:
        tree.write(str(path), xml_declaration=True, encoding='UTF-8')
        print('written', path)


if __name__ == '__main__':
    main()
