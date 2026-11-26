"""Wrap bare running heads in <fw type="running-head"> so the ODD can suppress them.

About half the running heads in the corpus were never wrapped. They sit as bare text
after an <lb/> inside an ordinary <p>:

    <p><lb/>שבחי צדיקים</p>          <- printed on the site
    <fw type="running-head">שבחי צדיקים</fw>   <- suppressed by the ODD

Nothing marks the first as forme work, so no ODD rule reaches it.

STRICT conditions, all required, so that real text is never touched:
  * the string is the whole of a text node (ignoring whitespace), 2+ words, <= 30 chars;
  * it matches the edition's own Hebrew title, allowing the OCR damage these strings
    take at the page edge (a prefix either way, >= 4 chars);
  * it is inside <body>, in a <div type="story"> or a non-story div - never in <front>,
    never inside <head>, <name>, <title>, <bibl> or an existing <fw>;
  * the <p> it sits in contains nothing else but <lb/> elements. A running head shares
    its paragraph with no narrative, so this is the test that keeps real prose safe.

The last condition is the important one: 'ספר שבחי צדיקים' in a story <head> is the
book's title, and 'שבחי הבעש״ט' inside Tmimei_Derech is a genuine citation of another
work. Both sit in paragraphs with other content, so both are left alone.

Unlike the @type work, this CHANGES THE TEXT LAYER: the string moves from a tail into
an element. The check is therefore that the flattened text is unchanged, not that the
bytes are.

Usage: python3 -I editions/scripts/wrap_bare_running_heads.py [--write] [--limit N]
"""
import glob
import sys
from collections import Counter

from lxml import etree

T = '{http://www.tei-c.org/ns/1.0}'
SKIP_ANCESTORS = {'head', 'name', 'title', 'bibl', 'fw', 'front', 'teiHeader'}


def title_words(root):
    t = root.find(f'{T}teiHeader/{T}fileDesc/{T}titleStmt/{T}title')
    s = ''.join(t.itertext()) if t is not None else ''
    return [w for w in s.split() if any('א' <= c <= 'ת' for c in w)]


def matches_title(s, words):
    """The string must be the title and NOTHING ELSE.

    A running head is the book's title reprinted at the top of the page, so every
    token in the string has to be a title word (allowing OCR damage at the page
    edge). An earlier, looser rule that merely required *most* tokens to match
    swallowed real prose - 'ח) האמונה שלימה הוא בלי חקירות' in Shaarei-Haemuna is
    a sentence, not a running head - so the test is now all-or-nothing.
    """
    toks = s.split()
    if not (2 <= len(toks) <= len(words) + 1):
        return False
    if any(c.isdigit() or c in '()[]:.,;' for c in s):
        return False          # section numbers and punctuation: not a running head

    def near(a, b):
        if a == b:
            return True
        # OCR truncates or mangles the head at the page edge, but the stem survives
        return len(a) >= 3 and len(b) >= 3 and (b.startswith(a[:3]) or a.startswith(b[:3]))
    return all(any(near(tok, w) for w in words) for tok in toks)


def main():
    write = '--write' in sys.argv
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else None
    stats, shown = Counter(), 0
    for path in sorted(glob.glob('editions/online/*.xml')):
        tree = etree.parse(path)
        root = tree.getroot()
        body = root.find(f'{T}text/{T}body')
        if body is None:
            continue
        before = ' '.join(''.join(root.find(T + 'text').itertext()).split())
        words = title_words(root)
        if not words:
            continue
        todo = []
        for el in body.iter():
            if etree.QName(el).localname in SKIP_ANCESTORS:
                continue
            if any(etree.QName(a).localname in SKIP_ANCESTORS for a in el.iterancestors()):
                continue
            s = (el.tail or '')
            st = ' '.join(s.split())
            if not st or len(st) > 30 or not matches_title(st, words):
                continue
            p = el.getparent()
            if p is None or etree.QName(p).localname != 'p':
                continue
            # the <p> must hold nothing but this string and <lb/> elements
            if (p.text or '').strip():
                continue
            if any(etree.QName(c).localname != 'lb' for c in p):
                continue
            others = ''.join((c.tail or '') for c in p if c is not el)
            if others.strip():
                continue
            todo.append((el, st))
        for el, st in todo:
            fw = etree.Element(T + 'fw')
            fw.set('type', 'running-head')
            fw.text = st
            el.tail = None
            el.addnext(fw)
            stats[path.split('/')[-1]] += 1
            if limit is None or shown < limit:
                print(f'  {path.split("/")[-1]:32} {st!r}')
                shown += 1
        if todo:
            after = ' '.join(''.join(root.find(T + 'text').itertext()).split())
            assert after == before, f'TEXT CHANGED beyond whitespace in {path}'
            if write:
                tree.write(path, xml_declaration=True, encoding='UTF-8')
    print('\n==', 'WRITTEN' if write else 'DRY RUN', '==')
    for k, v in stats.most_common():
        print(f'  {v:5}  {k}')
    print(f'  TOTAL {sum(stats.values())} in {len(stats)} editions')


if __name__ == '__main__':
    main()
