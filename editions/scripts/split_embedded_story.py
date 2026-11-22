"""Nest the stories the topic tagger found inside non-story divisions (introductions,
approbations, sayings...) as their own <div type="story">, so the site lists and shows them.

Usage: python3 editions/scripts/split_embedded_story.py EDITION.xml [--write]

Sinai, 2026-11-22: stories found within non-story text are to be split out and tagged.
The story div is nested INSIDE its paratext div (the site lists nested story divs, e.g.
Maasiot-veSihot-Zadikim), so the paratext stays one division and the XML records where the
story was found:  <div type="story" xml:id="{Slug}_{parent}_s{k}" subtype="in-{parent type}">.
Boundaries are the tagger's verbatim start/end quotes (editions/llm-tagging/runs/{slug}/*.json).
A paragraph cut at a boundary becomes two <p>; the text and the lb/pb count do not change
apart from the new storyHead. A run JSON is written for each new story so writeback.py tags it.
"""
import copy
import json
import re
import sys
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'editions' / 'llm-tagging'))
from tag_edition import divisions  # noqa: E402

T = '{http://www.tei-c.org/ns/1.0}'
XID = '{http://www.w3.org/XML/1998/namespace}id'
BLOCK = {T + x for x in ('p', 'ab', 'div', 'head', 'note', 'l', 'lg', 'list', 'item', 'quote', 'cit', 'body',
                         'front', 'back', 'text', 'floatingText')}
MARK = 'MARK'


def skipped(el, d):
    return el is not d and (el.tag == T + 'fw' or (el.tag == T + 'head' and el.get('type') == 'storyHead')
                            or (el.tag == T + 'div' and el.get('type') == 'story')
                            or (el.tag == T + 'span' and ''.join(el.itertext()).strip() in ('תיוגים', 'תיוגים*')))


def stream(d):
    """Normalized text of d (as the tagger saw it) and, per char, its (el, 'text'|'tail', offset)."""
    segs = []

    def walk(el):
        if not isinstance(el.tag, str):
            if el.tail:
                segs.append((el, 'tail'))
            return
        if skipped(el, d):
            if el.tail:
                segs.append((el, 'tail'))
            return
        if el.text:
            segs.append((el, 'text'))
        for c in el:
            walk(c)
        if el.tail and el is not d:
            segs.append((el, 'tail'))
    walk(d)
    out, pos = [], []
    for el, kind in segs:
        s = el.text if kind == 'text' else el.tail
        for i, ch in enumerate(s):
            ch = {'״': '"', '׳': "'"}.get(ch, ch)
            if ch.isspace():
                if out and out[-1] == ' ':
                    continue
                ch = ' '
            out.append(ch)
            pos.append((el, kind, i))
    return ''.join(out), pos


def norm(s):
    return re.sub(r'\s+', ' ', s.replace('״', '"').replace('׳', "'")).strip()


def outer_inline(el, kind):
    """The outermost inline element (below a block) that holds this text position, or None."""
    host = el if kind == 'text' else el.getparent()
    top = None
    while host is not None and host.tag not in BLOCK:
        top = host
        host = host.getparent()
    return top


def put_mark(el, kind, off, end):
    m = etree.Element(MARK)
    il = outer_inline(el, kind)
    if il is not None:  # never cut inside a name: move the boundary to the edge of the inline element
        if end:
            m.tail, il.tail = il.tail, None
            il.addnext(m)
        else:
            il.addprevious(m)
        return
    if kind == 'text':
        m.tail, el.text = el.text[off:], el.text[:off]
        el.insert(0, m)
    else:
        m.tail, el.tail = el.tail[off:], el.tail[:off]
        el.addnext(m)


def drop_mark(m):
    par, prev = m.getparent(), m.getprevious()
    if prev is not None:
        prev.tail = (prev.tail or '') + (m.tail or '')
    else:
        par.text = (par.text or '') + (m.tail or '')
    par.remove(m)


def keep_before(root, m):
    node = m
    m.tail = None
    while node is not root:
        par = node.getparent()
        for s in list(node.itersiblings()):
            par.remove(s)
        if node is not m:
            node.tail = None
        node = par
    drop_mark(m)


def keep_after(root, m):
    node = m
    while node is not root:
        par = node.getparent()
        for s in list(node.itersiblings(preceding=True)):
            par.remove(s)
        par.text = None
        node = par
    drop_mark(m)


def nest(d, s_off, e_off, pos, new_id, ptype):
    # end first: inserting it does not move the start's offset, even in the same text node
    el, kind, off = pos[e_off - 1]
    put_mark(el, kind, off + 1, end=True)
    el, kind, off = pos[s_off]
    put_mark(el, kind, off, end=False)
    left, mid, right = copy.deepcopy(d), copy.deepcopy(d), copy.deepcopy(d)
    a, b = list(left.iter(MARK))
    keep_before(left, a)
    a, b = list(mid.iter(MARK))
    keep_after(mid, a)
    keep_before(mid, b)
    a, b = list(right.iter(MARK))
    drop_mark(a)
    keep_after(right, b)
    # ids of split containers would now occur twice: keep them on the left copy only
    seen = {e.get(XID) for e in left.iter() if isinstance(e.tag, str) and e.get(XID)}
    for part in (mid, right):
        for e in part.iter():
            if isinstance(e.tag, str) and e.get(XID) in seen and e is not part:
                del e.attrib[XID]
        seen |= {e.get(XID) for e in part.iter() if isinstance(e.tag, str) and e.get(XID)}
    st = etree.Element(T + 'div')
    st.set('type', 'story')
    st.set(XID, new_id)
    st.set('subtype', f'in-{ptype}')
    h = etree.SubElement(st, T + 'head')
    h.set('type', 'storyHead')
    h.text = new_id
    h.tail = mid.text
    for c in list(mid):
        st.append(c)
    for c in list(d):
        d.remove(c)
    d.text = left.text
    for c in list(left):
        d.append(c)
    st.tail = right.text
    d.append(st)
    for c in list(right):
        d.append(c)


def main():
    path = Path(sys.argv[1])
    slug = path.stem
    runs = ROOT / 'editions' / 'llm-tagging' / 'runs' / slug
    tree = etree.parse(str(path))
    root = tree.getroot()
    txt = root.find(T + 'text')
    before = ''.join(txt.itertext())
    lbs = len(txt.findall(f'.//{T}lb')) + len(txt.findall(f'.//{T}pb'))
    made = []
    for did, d in divisions(root):
        if d.get('type') == 'story':
            continue
        f = runs / f'{did}.json'
        if not f.exists():
            continue
        res = json.loads(f.read_text())
        for s in res.get('stories', []):
            new_id = f'{slug}_{did}_s{s.get("k", 1)}'
            if root.find(f'.//*[@{XID}="{new_id}"]') is not None:
                continue  # already split
            text, pos = stream(d)
            i = text.find(norm(s.get('start_quote') or '\0'))
            j = text.find(norm(s.get('end_quote') or '\0'), max(i, 0))
            if i < 0 or j < 0:
                print(f'  SKIP {did} story {s.get("k")}: quotes not found')
                continue
            j += len(norm(s['end_quote']))
            while j < len(text) and text[j] in '.:,;!?)]':  # closing punctuation goes with the story
                j += 1
            nest(d, i, j, pos, new_id, d.get('type') or 'div')
            (runs / f'{new_id}.json').write_text(json.dumps(
                {'unit': {'kind': 'hasidic_story', 'why': f'split out of {did} ({d.get("type")})'},
                 'stories': [s], 'id': new_id, 'split_from': did}, ensure_ascii=False, indent=1))
            made.append((new_id, s.get('summary_en', '')[:100]))
    after = ''.join(txt.itertext())
    for nid, _ in made:
        after = after.replace(nid, '', 1)
    assert after == before, 'text changed'
    assert lbs == len(txt.findall(f'.//{T}lb')) + len(txt.findall(f'.//{T}pb')), 'lb/pb count changed'
    for m in made:
        print('  NEW STORY', *m)
    if made and '--write' in sys.argv:
        tree.write(str(path), xml_declaration=True, encoding='UTF-8')
        print('written', path)


if __name__ == '__main__':
    main()
