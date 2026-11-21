#!/bin/bash
# Rebuild the 8 Gemini-corrected incoming editions without the April 2026
# text-shuffling bug (see ner_pipeline/annotation_inserter.py _unwrap_element),
# then prepare them for the site. No API calls.
#
#   1. replay the logged Gemini corrections on the pre-correction file (2c7750c)
#   2. carry over the later tag edits (May 2026, up to acd3bbf)
#   3. drop empty tags and pipeline FLAGGED notes, site header, page breaks
#
# Usage: editions/scripts/repair_incoming.sh [EDITION ...]
set -euo pipefail
cd "$(dirname "$0")/../.."
W=$(mktemp -d)
EDS=("$@")
[ ${#EDS[@]} -eq 0 ] && EDS=(Maim-Rabim Derech-Haemuna Likutim-Hadashim Maasim-Tovim Peulat-Hatzadikim Seva-Ratzon Tiferet-Hayyim Toldot-Haniflaot)

for e in "${EDS[@]}"; do
  echo "== $e"
  git show 58f4166:editions/incoming/ready/$e.xml > "$W/$e.april.xml"
  git show acd3bbf:editions/incoming/ready/$e.xml > "$W/$e.may.xml"
  python3 editions/scripts/replay_gemini_correction.py "$e" "$W/$e.fixed.xml" 2>/dev/null | sed 's/^/  /'
  python3 editions/scripts/transplant_entity_edits.py "$W/$e.april.xml" "$W/$e.may.xml" "$W/$e.fixed.xml" "$W/$e.final.xml" 2>/dev/null \
    | grep -v '^    ' | sed 's/^/  /'
  python3 - "$W/$e.final.xml" "editions/incoming/ready/$e.xml" "$e" <<'EOF'
import sys, re
from lxml import etree
sys.path.insert(0, '.')
from ner_pipeline.annotation_inserter import _unwrap_element
src, out, name = sys.argv[1:4]
T = '{http://www.tei-c.org/ns/1.0}'
ENT = {T + t for t in ('persName', 'placeName', 'orgName', 'date', 'name')}
tree = etree.parse(src)
txt = tree.getroot().find(T + 'text')
before = ''.join(txt.itertext())
empty = [el for el in txt.iter() if el.tag in ENT and not ''.join(el.itertext()).strip() and not el.get('spanTo')]
for el in empty:
    _unwrap_element(el)
assert ''.join(txt.itertext()) == before
s = etree.tostring(tree, xml_declaration=True, encoding='UTF-8').decode()
if name == 'Maim-Rabim':
    # marginal item the author numbered 20: keep as non-story, keep its number
    a = ('<div type="unclear" ana="FLAGGED: rend=&quot;marginal&quot; with n=&quot;20&quot; '
         '— marginal note has story number; classify manually as story or non-story">')
    assert s.count(a) == 1
    s = s.replace(a, '<div type="non-story" ana="marginal" n="20">')
s = re.sub(r' ana="FLAGGED[^"]*"', '', s)
s = s.replace('</revisionDesc>', '<change when="2026-11-21">text repaired: Gemini correction pass '
              'replayed without the tag-stripping bug that shuffled text (58f4166); later tag edits carried over</change></revisionDesc>', 1)
open(out, 'w', encoding='utf-8').write(s)
print(f'  empty tags removed: {len(empty)}')
EOF
  python3 editions/scripts/site_header.py "editions/incoming/ready/$e.xml" --write > /dev/null
  tk=$(python3 -c "import json;d=json.load(open('editions/edition-metadata.json'));i=d if isinstance(d,list) else d['editions'];print(next(x for x in i if x['xml_filename']=='$e.xml')['identifiers']['Transkribus'])")
  python3 editions/scripts/restore_pb.py "$(ls editions/incoming/$tk/*.bak)" "editions/incoming/ready/$e.xml" --write | sed -n '2p;4,5p'
  xmllint --noout "editions/incoming/ready/$e.xml" && echo "  well-formed"
done
rm -rf "$W"
