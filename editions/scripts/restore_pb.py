#!/usr/bin/env python3
"""Put <pb facs="..."/> page breaks back into an annotated edition XML.

The Transkribus export (.xml.bak in editions/incoming/<docid>/) has one <pb>
per page, but the annotation pipeline dropped them. This script lines up the
<lb> lines of the export and of the annotated file by their letters, gives
every annotated line the page of its source line, and inserts each page's
<pb/> right before that page's first line.

Usage: restore_pb.py SOURCE.xml.bak EDITION.xml [--write]
Without --write it only reports.
"""
import re
import sys
import difflib

TAG = re.compile(r'<[^>]+>')
LETTERS = re.compile(r'[^א-תA-Za-z0-9]')
LB = re.compile(r'<lb\b[^>]*/>')
PB = re.compile(r'<pb\b[^>]*/>')
COMMENT = re.compile(r'<!--.*?-->', re.S)


def body_start(xml):
    m = re.search(r'<text\b', xml)
    return m.start() if m else 0


def norm(s):
    return LETTERS.sub('', TAG.sub('', s))


def source_lines(xml):
    """[(page_facs, n, normalized line text)] in document order."""
    xml = COMMENT.sub('', xml)
    xml = xml[body_start(xml):]
    events = sorted([(m.start(), 'pb', m) for m in PB.finditer(xml)] +
                    [(m.start(), 'lb', m) for m in LB.finditer(xml)])
    out, page, n = [], None, None
    for i, (pos, kind, m) in enumerate(events):
        if kind == 'pb':
            page = re.search(r'facs="([^"]+)"', m.group()).group(1)
            nm = re.search(r'\bn="([^"]+)"', m.group())
            n = nm.group(1) if nm else None
            continue
        end = events[i + 1][0] if i + 1 < len(events) else len(xml)
        out.append((page, n, norm(xml[m.end():end])))
    pages = [(re.search(r'facs="([^"]+)"', m.group()).group(1)) for m in PB.finditer(xml)]
    return out, pages


def edition_lines(xml):
    """[(offset of <lb>, normalized text)] in document order."""
    start = body_start(xml)
    ms = [m for m in LB.finditer(xml) if m.start() >= start]
    out = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(xml)
        seg = xml[m.end():end]
        seg = re.split(r'</(?:div|front|body|back)>', seg)[0]
        out.append((m.start(), norm(seg)))
    return out


def main():
    src_path, ed_path = sys.argv[1], sys.argv[2]
    write = '--write' in sys.argv
    src_xml = open(src_path, encoding='utf-8').read()
    ed_xml = open(ed_path, encoding='utf-8').read()
    if PB.search(ed_xml[body_start(ed_xml):]):
        sys.exit(f'{ed_path} already has <pb>; not touching it')

    src, pages = source_lines(src_xml)
    ed = edition_lines(ed_xml)
    a = [s[2] for s in src]
    b = [e[1] for e in ed]

    # exact matches first, then fuzzy for the gaps between them
    page_of = [None] * len(b)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    exact = fuzzy = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                page_of[j1 + k] = src[i1 + k][0]
                exact += 1
        elif tag in ('replace',):
            for j in range(j1, j2):
                best, bi = 0.0, None
                for i in range(i1, i2):
                    r = difflib.SequenceMatcher(None, a[i], b[j], autojunk=False).ratio()
                    if r > best:
                        best, bi = r, i
                if bi is not None and best >= 0.6:
                    page_of[j] = src[bi][0]
                    fuzzy += 1
    # unmatched lines inherit the previous line's page (or the next one's at the start)
    unmatched = sum(p is None for p in page_of)
    last = None
    for j in range(len(page_of)):
        if page_of[j] is None:
            page_of[j] = last
        last = page_of[j]
    nxt = None
    for j in range(len(page_of) - 1, -1, -1):
        if page_of[j] is None:
            page_of[j] = nxt
        nxt = page_of[j]

    # page order must never go backwards
    order = {p: i for i, p in enumerate(pages)}
    backwards = [j for j in range(1, len(page_of))
                 if order[page_of[j]] < order[page_of[j - 1]]]

    # first edition line of each page
    first = {}
    for j, p in enumerate(page_of):
        first.setdefault(p, j)
    # pages with no lines go right before the next page that has some
    inserts = {}  # line index -> [pb facs ...]
    pending = []
    for p in pages:
        if p in first:
            inserts.setdefault(first[p], []).extend(pending + [p])
            pending = []
        else:
            pending.append(p)
    tail = pending  # pages after the last line

    print(f'{ed_path}: {len(b)} lines, source {len(a)} lines, {len(pages)} pages')
    print(f'  matched exact {exact}, fuzzy {fuzzy}, unmatched {unmatched}')
    print(f'  pages with no text: {[p for p in pages if p not in first]}')
    print(f'  backwards steps: {len(backwards)}')
    if backwards:
        sys.exit('  page order goes backwards; not writing')

    if write:
        out, prev = [], 0
        for j, (off, _) in enumerate(ed):
            if j in inserts:
                out.append(ed_xml[prev:off])
                out.append(''.join(f'<pb facs="{p}" />' for p in inserts[j]))
                prev = off
        out.append(ed_xml[prev:])
        new = ''.join(out)
        if tail:
            new = new.replace('</body>', ''.join(f'<pb facs="{p}" />' for p in tail) + '</body>', 1)
        open(ed_path, 'w', encoding='utf-8').write(new)
        print(f'  wrote {len(PB.findall(new))} <pb/>')


if __name__ == '__main__':
    main()
