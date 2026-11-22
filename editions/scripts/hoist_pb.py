"""Move every <pb> out of a running head or heading to just before it.

Usage: python3 editions/scripts/hoist_pb.py EDITION.xml [...] [--write]

Found 2026-11-22 on the site: the edition view (/Edition/<name>) does not render <fw> (running
heads, page numbers), so a <pb> inside an <fw> is never output and the page's image never shows
(Shaarei-Haemuna: images stopped after page 3). restore_pb.py puts each <pb> before the page's
first <lb>, which is inside the running head when the page starts with one. The same holds for a
<pb> inside a <head> (the story heading is hidden too). The <pb> goes right before the outermost
such element, i.e. still at the top of its page; text and line breaks do not change.
"""
import sys

from lxml import etree

T = '{http://www.tei-c.org/ns/1.0}'
HIDDEN = (T + 'fw', T + 'head')


def hoist(root):
    moved = 0
    for pb in list(root.iter(T + 'pb')):
        anc = [a for a in pb.iterancestors() if a.tag in HIDDEN]
        if not anc:
            continue
        target = anc[-1]  # outermost
        # keep the text that followed the pb where it was
        tail, pb.tail = pb.tail, None
        if tail:
            prev = pb.getprevious()
            if prev is not None:
                prev.tail = (prev.tail or '') + tail
            else:
                par = pb.getparent()
                par.text = (par.text or '') + tail
        # the pb takes over the whitespace before the target, the target gets a fresh one
        target.addprevious(pb)
        moved += 1
    return moved


def main():
    for f in [a for a in sys.argv[1:] if not a.startswith('--')]:
        tree = etree.parse(f)
        tx = tree.getroot().find(T + 'text')
        before = (''.join(tx.itertext()), len(tx.findall(f'.//{T}lb')),
                  [pb.get('facs') for pb in tx.iter(T + 'pb')])
        n = hoist(tree.getroot())
        after = (''.join(tx.itertext()), len(tx.findall(f'.//{T}lb')),
                 [pb.get('facs') for pb in tx.iter(T + 'pb')])
        assert before == after, 'text, line breaks or page order changed'
        print(f'{f}: moved {n} <pb>')
        if n and '--write' in sys.argv:
            tree.write(f, xml_declaration=True, encoding='UTF-8')


if __name__ == '__main__':
    main()
