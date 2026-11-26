"""Normalise @type on <fw> (forme work: page numbers, running heads, catchwords).

Seven spellings were in use for three distinctions, so a renderer keyed on @type
cannot reliably suppress or margin-place forme work. Target vocabulary, the TEI-usual
spellings and the majority forms already in the corpus:

    pageNum       (was: page-number)
    running-head
    catchword     (was: catch, catch-word)

72 <fw> had no @type at all. They are classified by content:
    pure digits (incl. Hebrew-numeral + digit, e.g. "ב 2")  -> pageNum
    a multi-word Hebrew string matching the edition's title -> running-head
    anything else (a short word or a single letter)         -> catchword
A single Hebrew letter is usually a signature mark rather than a true catchword;
both sit in the forme, and the renderer treats them alike, so they go to catchword.
Every inferred value is listed in the report for checking.

Only @type is written. No element, attribute or text is otherwise touched.

Usage: python3 -I editions/scripts/normalise_fw_types.py [--write]
"""
import glob
import re
import sys
from collections import Counter

from lxml import etree

T = '{http://www.tei-c.org/ns/1.0}'
RENAME = {'page-number': 'pageNum', 'catch': 'catchword', 'catch-word': 'catchword'}
KEEP = {'pageNum', 'running-head', 'catchword'}


def infer(text, title_words):
    s = (text or '').strip()
    if not s:
        return 'catchword'
    if re.fullmatch(r'[א-תװ-״\'"״׳]*\s*\d+\s*', s):
        return 'pageNum'          # "12", "ב 2"
    words = s.split()
    if len(words) >= 2:
        # a catchword is a single word by definition, so any multi-word forme-work
        # string that shares its first word with the title is a running head, however
        # badly OCR mangled the rest ('התגלות הבך' for 'התגלות הצדיקים')
        def near_title(w):
            return any(w == tw or (len(w) >= 4 and (tw.startswith(w[:4]) or w.startswith(tw[:4])
                                                    or tw[1:].startswith(w[:4]) or w.startswith(tw[1:5])))
                       for tw in title_words)
        if near_title(words[0]):
            return 'running-head'
        # the book's title in the forme, often OCR-truncated at the edge of the page
        # ('התגלות הצד' for 'התגלות הצדיקים'), so match on prefixes both ways
        def near(w):
            return any(w == tw or (len(w) >= 3 and (tw.startswith(w[:-1]) or w.startswith(tw[:3])))
                       for tw in title_words)
        if sum(near(w) for w in words) >= 2:
            return 'running-head'
    return 'catchword'


def main():
    write = '--write' in sys.argv
    stats, inferred, per_file = Counter(), [], Counter()
    for path in sorted(glob.glob('editions/online/*.xml')):
        tree = etree.parse(path)
        root = tree.getroot()
        before = ''.join(root.find(T + 'text').itertext())
        t = root.find(f'{T}teiHeader/{T}fileDesc/{T}titleStmt/{T}title')
        title_words = set((''.join(t.itertext()) if t is not None else '').split())
        changed = False
        for fw in root.iter(T + 'fw'):
            old = fw.get('type')
            if old in KEEP:
                continue
            if old in RENAME:
                new = RENAME[old]
            elif old is None:
                new = infer(''.join(fw.itertext()), title_words)
                inferred.append((path.split('/')[-1], ''.join(fw.itertext()).strip()[:40], new))
            else:
                new = RENAME.get(old, 'catchword')
            fw.set('type', new)
            stats[f'{old!r} -> {new}'] += 1
            per_file[path.split('/')[-1]] += 1
            changed = True
        if changed:
            assert ''.join(root.find(T + 'text').itertext()) == before, f'TEXT CHANGED {path}'
            if write:
                tree.write(path, xml_declaration=True, encoding='UTF-8')

    print('==', 'WRITTEN' if write else 'DRY RUN', '==')
    for k, v in stats.most_common():
        print(f'  {v:5}  {k}')
    print(f'\nfiles touched: {len(per_file)}')
    if inferred:
        print(f'\ninferred for the {len(inferred)} untyped <fw>:')
        for f, txt, new in inferred:
            print(f'  {f:32} {txt!r:44} -> {new}')


if __name__ == '__main__':
    main()
