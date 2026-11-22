"""Bring a current Transkribus TEI export (2026 format) into the shape the
incoming pipeline (Authorities/scripts/story_structure.py, restore_pb.py) expects.

  - decode literal \\uXXXX escapes Transkribus leaves in tag text/attributes
    (rend="non\\u0020story", <corr>מו\\u0022ה</corr>)
  - <ab> text regions -> <p> (story_structure walks <p>)
  - paragraphs split at each <story> tag that is not at their start
  - <pb facs="#facs_N" n="N" xml:id=...> -> <pb facs="{slug}_{NNNN}.jpg" n="N"/>

  - <fw>/<head>/<note> regions -> <p type="fw:TYPE"> / <p type="head"> so the story
    step keeps them (it only collects <p>; it used to drop 118 lines of
    Torat-Haramal); run with --post on the story-step output to turn them back:
    fw (page-number -> pageNum, catch, running-head) <head> and <note>; type="main-text" dropped

Usage: prep_transkribus_export.py EXPORT.xml SLUG OUT.xml
       prep_transkribus_export.py --post EDITION.xml
Text content is unchanged apart from the decoded escapes (checked).
"""
import re, sys
from lxml import etree

T = '{http://www.tei-c.org/ns/1.0}'
if sys.argv[1] == '--post':
    path = sys.argv[2]
    tree = etree.parse(path); txt = tree.getroot().find(T + 'text'); before = ''.join(txt.itertext())
    FW = {'page-number': 'pageNum', 'catch': 'catch', 'catch-word': 'catch', 'running-head': 'running-head'}
    c = {}
    for p in list(txt.iter(T + 'p')):
        t = p.get('type') or ''
        kind = t[3:] if t.startswith('fw:') else t
        if kind in FW:
            p.tag = T + 'fw'; p.set('type', FW[kind])
        elif t in ('head', 'note'):
            p.tag = T + t; del p.attrib['type']
        elif t in ('main-text', 'main'):
            del p.attrib['type']
        else:
            continue
        c[t] = c.get(t, 0) + 1
    assert ''.join(txt.itertext()) == before
    tree.write(path, xml_declaration=True, encoding='UTF-8')
    print('post:', c); sys.exit()
src, slug, out = sys.argv[1:4]
raw = open(src, encoding='utf-8').read()
n_esc = len(re.findall(r'\\u[0-9a-fA-F]{4}', raw))
tree = etree.fromstring(re.sub(r'\\u0022', '&quot;', raw).replace('\\u0027', "'").encode())
# decode remaining escapes in text and attributes via the tree (safe for quotes)
def d(s): return re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s) if s else s
for el in tree.iter():
    if not isinstance(el.tag, str): continue
    el.text, el.tail = d(el.text), d(el.tail)
    for k, v in el.attrib.items(): el.set(k, d(v))
n_ab = 0
for ab in tree.iter(T + 'ab'):
    ab.tag = T + 'p'; n_ab += 1
    if ab.get('type') == '': del ab.attrib['type']
n_fw = 0
for el in list(tree.iter(T + 'fw', T + 'head', T + 'note')):
    par = el.getparent()
    if par is None or par.tag != T + 'div':   # only top-level regions
        continue
    el.set('type', 'fw:' + (el.get('type') or '') if el.tag == T + 'fw' else el.tag[len(T):])
    el.tag = T + 'p'; n_fw += 1
# split paragraphs at every <story> tag that is not at the paragraph start,
# so the story step (which assigns whole <p>s to units) cuts at the tag; an
# item number right before the tag ("ז)", "(יב)") goes with it
import copy
NUM = re.compile(r'(\(?[\u05d0-\u05ea]{1,3}[\)\]]\s*)$')
n_split = 0
for p in list(tree.iter(T + 'p')):
    while True:
        kids = list(p)
        cut = None
        for i, c in enumerate(kids):
            if c.tag != T + 'story' or i == 0 and not (p.text or '').strip():
                continue
            before = (p.text or '') + ''.join(''.join(k.itertext()) + (k.tail or '') for k in kids[:i])
            if before.strip() and not NUM.fullmatch(before.lstrip()):
                cut = i; break
        if cut is None:
            break
        tag = kids[cut]
        prev = kids[cut - 1] if cut > 0 else None
        node = prev.tail if prev is not None else p.text
        node = node or ''
        m = NUM.search(node)
        keep, carry = (node[:m.start()], m.group(1)) if m else (node, '')
        if prev is not None: prev.tail = keep
        else: p.text = keep
        newp = etree.Element(p.tag, dict(p.attrib)); newp.text = carry; newp.tail = p.tail
        for k in kids[cut:]:
            newp.append(k)
        p.tail = '\n'
        p.addnext(newp)
        n_split += 1
        p = newp
n_pb = 0
for pb in tree.iter(T + 'pb'):
    n = int(pb.get('n'))
    pb.set('facs', f'{slug}_{n:04d}.jpg')
    pb.attrib.pop('{http://www.w3.org/XML/1998/namespace}id', None)
    n_pb += 1
left = sum(len(re.findall(r'\\u[0-9a-fA-F]{4}', (e.text or '') + (e.tail or '') + ''.join(e.attrib.values())))
           for e in tree.iter() if isinstance(e.tag, str))
etree.ElementTree(tree).write(out, xml_declaration=True, encoding='UTF-8')
print(f'escapes decoded {n_esc} (left {left}), ab->p {n_ab}, fw/head->p {n_fw}, paragraphs split at story tags {n_split}, pb renamed {n_pb}')
