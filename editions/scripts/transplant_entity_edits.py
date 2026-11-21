#!/usr/bin/env python3
"""Carry entity-tag edits made after the April Gemini pass onto the repaired file.

The April pass (58f4166) shuffled text but placed each entity tag at the
character offset it has in the *correct* text. Later commits only changed
entity tags (removed some, added refs/ana), never the text. So an entity's
(start, end) offset in the text is the same in the damaged April file, the
damaged current file and the repaired replay. This script:

  1. reads the entity tags of APRIL (damaged, 58f4166), CURRENT (damaged, with
     the later edits) and REPAIRED (replay with fixed strip),
  2. checks APRIL and REPAIRED have the same entities at the same offsets,
  3. applies CURRENT-vs-APRIL differences to REPAIRED: unwraps removed tags,
     copies changed attributes, and wraps the few added tags,
  4. writes OUT.

Usage: transplant_entity_edits.py APRIL.xml CURRENT.xml REPAIRED.xml OUT.xml
"""
import sys
from lxml import etree

sys.path.insert(0, __file__.rsplit('/', 3)[0])
from ner_pipeline.annotation_inserter import _unwrap_element  # noqa: E402

T = '{http://www.tei-c.org/ns/1.0}'
ENT = {T + 'persName', T + 'placeName', T + 'orgName', T + 'date', T + 'name'}


def text_el(tree):
    return tree.getroot().find(T + 'text')


def entities(tree):
    """{(tag, start, end, occurrence): element} with offsets in itertext space."""
    out, pos, seen = {}, [0], {}

    def walk(el):
        is_ent = el.tag in ENT
        start = pos[0]
        if el.text:
            pos[0] += len(el.text)
        for ch in el:
            if isinstance(ch.tag, str):
                walk(ch)
            elif ch.tail:  # comments / PIs
                pos[0] += len(ch.tail)
        if is_ent:
            k = (el.tag, start, pos[0])
            n = seen.get(k, 0)
            seen[k] = n + 1
            out[k + (n,)] = el
        if el.tail and el is not root:
            pos[0] += len(el.tail)

    root = text_el(tree)
    walk(root)
    return out


def attrs(el):
    return dict(el.attrib)


def main():
    april, current, repaired = (etree.parse(p) for p in sys.argv[1:4])
    out = sys.argv[4]
    ta = ''.join(text_el(april).itertext())
    tc = ''.join(text_el(current).itertext())
    tr = ''.join(text_el(repaired).itertext())
    assert ta == tc, 'APRIL and CURRENT text differ; later commits changed text'
    assert len(ta) == len(tr), 'repaired text has a different length'

    ea, ec, er = entities(april), entities(current), entities(repaired)
    sa, sr = set(ea), set(er)
    same = sa == sr
    print(f'entities: april {len(ea)}, current {len(ec)}, repaired {len(er)}; '
          f'april==repaired offsets: {same} (only april {len(sa - sr)}, only repaired {len(sr - sa)})')
    if not same:
        for k in sorted(sa ^ sr, key=lambda k: k[1])[:10]:
            print('   ', 'A' if k in sa else 'R', k[0].replace(T, ''), k[1:], repr(tr[k[1]:k[2]]))

    removed = [k for k in ea if k not in ec]
    added = [k for k in ec if k not in ea]
    changed = [k for k in ea if k in ec and attrs(ea[k]) != attrs(ec[k])]
    print(f'later edits: removed {len(removed)}, added {len(added)}, attributes changed {len(changed)}')

    # attributes first (elements still in place), then removals
    miss = 0
    for k in changed:
        if k in er:
            el = er[k]
            for a in list(el.attrib):
                del el.attrib[a]
            for a, v in ec[k].attrib.items():
                el.set(a, v)
        else:
            miss += 1
    for k in sorted(removed, key=lambda k: -(k[2] - k[1])):
        if k in er:
            _unwrap_element(er[k])
        else:
            miss += 1
    unadded = []
    for k in added:
        unadded.append((k[0].replace(T, ''), dict(ec[k].attrib), repr(tr[k[1]:k[2]])))
    print(f'edits that found no matching tag in the repaired file: {miss}')
    if unadded:
        print(f'{len(unadded)} tags added after April are NOT carried over:')
        for u in unadded[:20]:
            print('   ', u)
    repaired.write(out, xml_declaration=True, encoding='UTF-8')


if __name__ == '__main__':
    main()
