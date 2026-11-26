"""Move block-level <fw type="pageNum"> into the adjacent paragraph, so it renders inline.

469 of the 708 page numbers are siblings of <p> inside a <div>, not inside any
paragraph. The ODD renders pageNum with behaviour="inline", but an element that sits
BETWEEN two block-level paragraphs still lays out on its own line - which is why
Shivhei-Tsadikim_0004 shows "6" and "7" stacked above the text. Stripping the
whitespace inside the element does not help: the position, not the whitespace, is
what breaks the line.

Where does the number belong? A printed page number names the page it stands on, and
<pb/> marks where that page begins, so a number following a <pb/> belongs to the text
AFTER it. 369 of the 469 sit directly after a <pb/>, and the rest follow other forme
work (a catchword) that itself follows one. So:

    <pb/> <fw pageNum>6</fw> <p>text...</p>   ->   <pb/> <p><fw pageNum>6</fw> text...</p>

The <fw> is inserted as the first child of the following <p>, its internal whitespace
collapsed to the bare number, with a single space after it (and the <p>'s own leading
whitespace dropped) so the rendered line reads "6 text..." with one space either side.

Only moved when the following sibling (skipping other forme work and milestones) is a
<p>. A number with no following paragraph in the same parent is left where it is and
reported - there is nothing to attach it to.

This CHANGES THE TEXT LAYER (an element moves), so the check is that the flattened
text is unchanged apart from whitespace, not that the bytes are.

Usage: python3 -I editions/scripts/inline_block_pagenums.py [--write]
"""
import glob
import sys
from collections import Counter

from lxml import etree

T = '{http://www.tei-c.org/ns/1.0}'
SKIPPABLE = {'fw', 'pb', 'milestone', 'lb'}


def main():
    write = '--write' in sys.argv
    moved, left, per = Counter(), Counter(), Counter()
    for path in sorted(glob.glob('editions/online/*.xml')):
        tree = etree.parse(path)
        root = tree.getroot()
        # A move reorders words by design: the number hops over any running head or
        # catchword between it and the paragraph. So the invariant is that the SAME
        # words are present, not that they are in the same order - nothing may be
        # added, lost or altered.
        from collections import Counter as _C
        words = lambda: _C(''.join(root.find(T + 'text').itertext()).split())
        before = words()
        changed = False
        # collect first: the tree is modified as we go
        targets = []
        for fw in root.iter(T + 'fw'):
            if fw.get('type') != 'pageNum':
                continue
            par = fw.getparent()
            if par is None or etree.QName(par).localname == 'p':
                continue
            targets.append((fw, par))
        for fw, par in reversed(targets):
            kids = list(par)
            i = kids.index(fw)
            dest = None
            for c in kids[i + 1:]:
                ln = etree.QName(c).localname
                if ln == 'p':
                    # skip a <p> that holds no narrative - one that is itself only
                    # forme work (a wrapped running head) is not a destination, or the
                    # number lands in a paragraph that still renders on its own line
                    if ''.join(t for t in c.itertext()).strip() and any(
                            (e.tail or '').strip() or (e.text or '').strip()
                            for e in [c] + [k for k in c if etree.QName(k).localname != 'fw']):
                        dest = c
                        break
                    continue
                if ln not in SKIPPABLE:
                    break
            if dest is None:
                left[path.split('/')[-1]] += 1
                continue
            num = ' '.join(''.join(fw.itertext()).split())
            tail = fw.tail or ''
            prv = fw.getprevious()
            if prv is not None:
                prv.tail = (prv.tail or '') + tail
            else:
                par.text = (par.text or '') + tail
            par.remove(fw)
            # some page numbers wrap the digits after an <lb/>; drop the children but
            # keep every character they held (num is the flattened text)
            for child in list(fw):
                fw.remove(child)
            fw.text = num
            dtxt = dest.text or ''
            # Only leading WHITESPACE may be dropped. An earlier version used
            # .lstrip(), which ate a real letter when a paragraph began mid-word
            # ('בתורה' -> 'תורה', with the ב fusing onto the number).
            stripped = dtxt[len(dtxt) - len(dtxt.lstrip()):] if not dtxt.strip() else dtxt.lstrip(' \t\r\n')
            fw.tail = ' ' + stripped
            dest.text = None
            # Always position 0. Inserting after existing children would place the
            # number in the middle of their text and split a word. Several numbers
            # going to the same <p> are processed in reverse so they end up in
            # printed order.
            dest.insert(0, fw)
            moved[path.split('/')[-1]] += 1
            per[num] += 1
            changed = True
        if changed:
            after = words()
            if after != before:
                lost = before - after
                gained = after - before
                raise AssertionError(f'TEXT CHANGED in {path}: lost={dict(lost)} gained={dict(gained)}')
            if write:
                tree.write(path, xml_declaration=True, encoding='UTF-8')
    print('==', 'WRITTEN' if write else 'DRY RUN', '==')
    print(f'moved into the following <p>: {sum(moved.values())} in {len(moved)} editions')
    for k, v in moved.most_common():
        print(f'  {v:5}  {k}')
    if left:
        print(f'\nleft in place (no following <p>): {sum(left.values())}')
        for k, v in left.most_common():
            print(f'  {v:5}  {k}')


if __name__ == '__main__':
    main()
