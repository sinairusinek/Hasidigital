"""Link unlinked <placeName> elements to the place authority by exact name variant
(PIPELINE.md step 10), in stories and outside them alike (Sinai 2026-11-22).

Usage: python3 editions/scripts/link_places.py EDITION.xml [...] [--write]

Same matching as Authorities/scripts/batch_link_places.py (the variant index of
Authorities/authorities-matching-db.json; 'ישראל' is skipped), but with lxml, so the file is
otherwise untouched, and it neither changes the matching DB nor overwrites
editions/unmatched-places-report.tsv (the Kima Review decision file). Names left unmatched
are written to editions/kimatch/unmatched-after-link-{date}.tsv for the Kima pipeline.
"""
import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Authorities' / 'scripts'))
from batch_link_places import build_variant_index, SKIP_NAMES  # noqa: E402

T = '{http://www.tei-c.org/ns/1.0}'


def part(el):
    for a in el.iterancestors(T + 'div'):
        if a.get('type') == 'story':
            return 'story'
    for a in el.iterancestors(T + 'div'):
        if a.get('type'):
            return a.get('type')
    return 'other'


def main():
    files = [Path(a) for a in sys.argv[1:] if not a.startswith('--')]
    db = json.loads((ROOT / 'Authorities' / 'authorities-matching-db.json').read_text())
    vi = build_variant_index(db)
    unmatched = defaultdict(lambda: {'n': 0, 'editions': set(), 'parts': set()})
    for f in files:
        tree = etree.parse(str(f))
        txt = tree.getroot().find(T + 'text')
        before = ''.join(txt.itertext())
        added = defaultdict(int)
        for p in txt.iter(T + 'placeName'):
            t = (p.text or '').strip()
            if p.get('ref') or len(p) or not t or t in SKIP_NAMES:
                continue
            if t in vi:
                p.set('ref', '#' + vi[t]['id'])
                added['story' if part(p) == 'story' else 'non-story'] += 1
            else:
                u = unmatched[t]
                u['n'] += 1
                u['editions'].add(f.stem)
                u['parts'].add(part(p))
        assert ''.join(txt.itertext()) == before
        print(f'{f.name}: {dict(added)}')
        if '--write' in sys.argv and added:
            tree.write(str(f), xml_declaration=True, encoding='UTF-8')
    if '--write' in sys.argv:
        out = ROOT / 'editions' / 'kimatch' / f'unmatched-after-link-{date.today()}.tsv'
        with open(out, 'w', newline='') as fh:
            w = csv.writer(fh, delimiter='\t')
            w.writerow(['name', 'occurrences', 'editions', 'parts'])
            for t, u in sorted(unmatched.items(), key=lambda x: -x[1]['n']):
                w.writerow([t, u['n'], ', '.join(sorted(u['editions'])), ', '.join(sorted(u['parts']))])
        print('unmatched:', len(unmatched), 'names ->', out)


if __name__ == '__main__':
    main()
