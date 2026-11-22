"""Finish an incoming edition after the NER correction pass, for the site.

Usage: finish_corrected.py CORRECTED.xml OUT.xml TRANSKRIBUS.bak "ENGINE NOTE"

  - drop empty entity tags (text unchanged, checked)
  - drop pipeline ana="FLAGGED..." notes
  - root in the default TEI namespace (<TEI xmlns=...>), as on the live editions
  - fw type="catchword" -> "catch" (the form most live editions use)
  - site header (site_header.py) + a revisionDesc change naming the engine
  - page breaks from the Transkribus export (restore_pb.py)
Same steps as Eser-Kedushot on 2026-11-22 (commit 7602996).
"""
import re, subprocess, sys
from datetime import date
from lxml import etree

sys.path.insert(0, '.')
from ner_pipeline.annotation_inserter import _unwrap_element

src, out, bak, note = sys.argv[1:5]
T = '{http://www.tei-c.org/ns/1.0}'
ENT = {T + t for t in ('persName', 'placeName', 'orgName', 'date', 'name')}
raw = open(src, encoding='utf-8').read()
# the inserter can write the same <anchor xml:id=X/> twice (an entity whose span
# crosses a break); keep the first, as replay_gemini_correction.py does
_seen = set()
def _dedupe(m):
    if m.group(1) in _seen:
        return ''
    _seen.add(m.group(1)); return m.group(0)
raw2 = re.sub(r'<anchor xml:id="([^"]+)"\s*/>', _dedupe, raw)
if raw2 != raw:
    print('duplicate anchors dropped:', raw.count('<anchor') - raw2.count('<anchor'))
tree = etree.ElementTree(etree.fromstring(raw2.encode('utf-8')))
txt = tree.getroot().find(T + 'text')
before = ''.join(txt.itertext())
lbs = len(txt.findall('.//' + T + 'lb'))
empty = [el for el in txt.iter() if el.tag in ENT and not ''.join(el.itertext()).strip() and not el.get('spanTo')]
for el in empty:
    _unwrap_element(el)
for fw in txt.iter(T + 'fw'):
    if fw.get('type') == 'catchword':
        fw.set('type', 'catch')
assert ''.join(txt.itertext()) == before
s = etree.tostring(tree, xml_declaration=True, encoding='UTF-8').decode()
n_flag = len(re.findall(r' ana="FLAGGED[^"]*"', s))
s = re.sub(r' ana="FLAGGED[^"]*"', '', s)
s = s.replace('<tei:TEI xmlns:tei="http://www.tei-c.org/ns/1.0">', '<TEI xmlns="http://www.tei-c.org/ns/1.0">', 1).replace('</tei:TEI>', '</TEI>', 1)
s = s.replace('<teiHeader xmlns="http://www.tei-c.org/ns/1.0">', '<teiHeader>', 1).replace('<text xmlns="http://www.tei-c.org/ns/1.0">', '<text>', 1)
open(out, 'w', encoding='utf-8').write(s)
print(f'empty tags removed {len(empty)}, FLAGGED removed {n_flag}')
subprocess.run([sys.executable, 'editions/scripts/site_header.py', out, '--write'], check=True, stdout=subprocess.DEVNULL)
s = open(out, encoding='utf-8').read()
s = s.replace('</revisionDesc>', f'<change when="{date.today()}">{note}</change></revisionDesc>', 1)
open(out, 'w', encoding='utf-8').write(s)
r = subprocess.run([sys.executable, 'editions/scripts/restore_pb.py', bak, out, '--write'], check=True, capture_output=True, text=True)
print(r.stdout.strip())
t2 = etree.parse(out).getroot().find(T + 'text')
assert ''.join(t2.itertext()) == before and len(t2.findall('.//' + T + 'lb')) == lbs
print('text and', lbs, 'line breaks unchanged; root', etree.parse(out).getroot().tag)
