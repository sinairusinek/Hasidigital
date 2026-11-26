"""Align <fw> @type to the values the TEI-Publisher ODD actually acts on.

The server's ODD for <fw> is:

    <model predicate="@type='running-head' or @type='catch'" behaviour="omit"/>
    <model predicate="@type='pageNum'" behaviour="inline" cssClass="attrFW"/>

So only 'running-head' and 'catch' are suppressed. Anything else - 'catchword',
'catch-word', 'page-number', or no @type at all - falls through and is printed in
the reading text. That, not a renderer bug, is why page numbers and some running
heads appear mid-story on the site.

This script maps every <fw> onto the three values the ODD knows:

    catchword, catch-word  -> catch          (restores the suppression; the earlier
                                              normalisation to 'catchword' had silently
                                              turned suppressed catchwords into visible ones)
    page-number            -> pageNum        (one spelling, the one the ODD matches)
    running-head                             (unchanged)

Page numbers KEEP their own type: they are evidence of the printed book and Sinai
wants them retained in the XML. They are not retyped to a suppressed value, which
would be false encoding. Hiding them is the ODD's job - one line, changing
behaviour="inline" to "omit" (or to a margin rendering) for the pageNum model.

Only @type is written. No element, attribute or text is otherwise touched.

Usage: python3 -I editions/scripts/align_fw_to_odd.py [--write]
"""
import glob
import sys
from collections import Counter

from lxml import etree

T = '{http://www.tei-c.org/ns/1.0}'
MAP = {'catchword': 'catch', 'catch-word': 'catch', 'page-number': 'pageNum'}
ODD_KNOWS = {'running-head', 'catch', 'pageNum'}


def main():
    write = '--write' in sys.argv
    stats, files = Counter(), Counter()
    for path in sorted(glob.glob('editions/online/*.xml')):
        tree = etree.parse(path)
        root = tree.getroot()
        before = ''.join(root.find(T + 'text').itertext())
        changed = False
        for fw in root.iter(T + 'fw'):
            old = fw.get('type')
            new = MAP.get(old, old)
            if new != old:
                fw.set('type', new)
                stats[f'{old} -> {new}'] += 1
                files[path.split("/")[-1]] += 1
                changed = True
            if new not in ODD_KNOWS:
                stats[f'!! UNKNOWN TO THE ODD: {new!r}'] += 1
        if changed:
            assert ''.join(root.find(T + 'text').itertext()) == before, f'TEXT CHANGED {path}'
            if write:
                tree.write(path, xml_declaration=True, encoding='UTF-8')
    print('==', 'WRITTEN' if write else 'DRY RUN', '==')
    for k, v in stats.most_common():
        print(f'  {v:5}  {k}')
    print(f'\nfiles touched: {len(files)}')


if __name__ == '__main__':
    main()
