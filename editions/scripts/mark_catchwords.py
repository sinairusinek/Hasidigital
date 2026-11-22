"""Wrap printer's catchwords left at the end of a division in <fw type="catch">.

Usage: mark_catchwords.py EDITION.xml BOUNDARIES.tsv [--write]
Takes the rows of BOUNDARIES.tsv (from check/boundary_check.py) whose signals
include 'catchword': the division BEFORE story_id ends with a word equal to the
first word of story_id. Text is unchanged; only the wrapper is added.
"""
import csv, sys
from lxml import etree

T = '{http://www.tei-c.org/ns/1.0}'
XID = '{http://www.w3.org/XML/1998/namespace}id'
path, tsv = sys.argv[1:3]
tree = etree.parse(path)
text_el = tree.getroot().find(T + 'text')
before = ''.join(text_el.itertext())
divs = [d for d in text_el.iter(T + 'div') if d.get('type') in ('story', 'non-story')]
pos = {d.get(XID): i for i, d in enumerate(divs) if d.get(XID)}
rows = [r for r in csv.DictReader(open(tsv, encoding='utf-8'), delimiter='\t') if 'catchword' in r['signals']]
done = 0
for r in rows:
    i = pos[r['story_id']]
    prev, cur = divs[i - 1], divs[i]
    first = ''.join(cur.itertext()).split()
    first = [w for w in first if w != r['story_id']]
    word = first[1] if first[0].startswith('(') else first[0]   # skip the item number "(ח)"
    # last non-empty text node of prev
    nodes = []
    for el in prev.iter():
        if el is not prev and el.tail and el.tail.strip(): nodes.append((el, 'tail'))
        if el.text and el.text.strip(): nodes.append((el, 'text'))
    order = {id(e): k for k, e in enumerate(prev.iter())}
    el, attr = max(nodes, key=lambda n: (order[id(n[0])] + (0.5 if n[1] == 'tail' else 0)) if n[1] == 'text' else order[id(n[0])] + 0.9)
    s = getattr(el, attr)
    stripped = s.rstrip()
    if not stripped.endswith(word):
        print('SKIP', r['story_id'], 'prev ends', repr(stripped[-30:]), 'word', word); continue
    head, trail = stripped[:-len(word)], s[len(stripped):]
    fw = etree.Element(T + 'fw', type='catch'); fw.text = word; fw.tail = trail
    if attr == 'text':
        el.text = head; el.insert(0, fw)
    else:
        el.tail = head; p = el.getparent(); p.insert(p.index(el) + 1, fw)
    done += 1
    print('OK', prev.get(XID) or prev.get('type'), '->', word)
assert ''.join(text_el.itertext()) == before
print(f'{done}/{len(rows)} catchwords wrapped')
if '--write' in sys.argv:
    tree.write(path, xml_declaration=True, encoding='UTF-8')
