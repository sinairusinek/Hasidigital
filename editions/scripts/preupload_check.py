"""Pre-upload gate: an edition may be offered for upload to hasidic-stories.org
only when this check passes (editions/PIPELINE.md, step 14).

Usage: preupload_check.py EDITION.xml [EDITION.xml ...] [--images]

Fails (exit 1) on any of:
  - not well-formed / root not <TEI xmlns="http://www.tei-c.org/ns/1.0">
  - header fields the site reads: titleStmt/title[@type=main],
    sourceDesc/bibl/pubPlace and sourceDesc//bibl/date (no <imprint> wrapper),
    editionStmt/edition/@n, revisionDesc/change/@when
  - no <pb> (image names not in the {Slug}_{NNNN}.jpg form are only noted)
  - a story <div> without xml:id or without <head type="storyHead">
  - duplicate xml:id; a leftover ana="FLAGGED..."
  - no NER tags at all
  - TOPIC TAGS: a story with no topic tag (only TBD:Unknown or nothing), or a
    topic tag outside family:tag form (the step skipped for the April 2026 batch)
  - with --images: a page image missing from /db/apps/HasidicImages on the server
"""
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

from lxml import etree

T = '{http://www.tei-c.org/ns/1.0}'
XID = '{http://www.w3.org/XML/1998/namespace}id'
TAG = re.compile(r'^[a-z-]+:[a-z0-9_]+$')
IMG = 'https://teipub9.dh-dev.com/exist/rest/db/apps/HasidicImages/'


def check(path, images=False):
    errs, notes = [], []
    p = Path(path)
    try:
        root = etree.parse(str(p)).getroot()
    except etree.XMLSyntaxError as e:
        return [f'not well-formed: {e}'], notes
    if root.tag != T + 'TEI' or root.prefix is not None:
        errs.append('root is not <TEI xmlns="http://www.tei-c.org/ns/1.0">')
    h = root.find(T + 'teiHeader')
    need = {
        'title[@type=main]': f'{T}fileDesc/{T}titleStmt/{T}title[@type="main"]',
        'sourceDesc/bibl/pubPlace': f'{T}fileDesc/{T}sourceDesc/{T}bibl/{T}pubPlace',
        'sourceDesc//bibl/date': f'{T}fileDesc/{T}sourceDesc//{T}bibl/{T}date',
        'editionStmt/edition/@n': f'{T}fileDesc/{T}editionStmt/{T}edition[@n]',
        'revisionDesc/change/@when': f'{T}revisionDesc/{T}change[@when]',
    }
    for k, xp in need.items():
        if h is None or h.find(xp) is None:
            errs.append(f'header lacks {k}')
    if h is not None and h.find(f'.//{T}imprint') is not None:
        errs.append('header has <imprint> (the site then cannot find pubPlace/date)')
    txt = root.find(T + 'text')
    slug = p.stem
    pbs = txt.findall(f'.//{T}pb')
    if not pbs:
        errs.append('no <pb>')
    bad_facs = [pb.get('facs') for pb in pbs if not re.fullmatch(re.escape(slug) + r'_\d{4}\.jpg', pb.get('facs') or '')]
    if bad_facs:  # legacy names (e.g. MifalotZadikim-0001.jpg) work on the site; --images checks they exist
        notes.append(f'{len(bad_facs)} pb/@facs not in the {slug}_NNNN.jpg form, e.g. {bad_facs[0]}')
    ids = Counter(e.get(XID) for e in root.iter() if isinstance(e.tag, str) and e.get(XID))
    dup = [i for i, c in ids.items() if c > 1]
    if dup:
        errs.append(f'{len(dup)} duplicate xml:id, e.g. {dup[0]}')
    if 'ana="FLAGGED' in etree.tostring(root, encoding='unicode'):
        errs.append('leftover ana="FLAGGED..."')
    if not txt.findall(f'.//{T}persName') and not txt.findall(f'.//{T}placeName'):
        errs.append('no NER tags')
    stories = [d for d in txt.iter(T + 'div') if d.get('type') == 'story']
    no_id = [d for d in stories if not d.get(XID)]
    no_head = [d for d in stories if not any(x.get('type') == 'storyHead' for x in d.findall(T + 'head'))]
    if no_id:
        errs.append(f'{len(no_id)} story divs without xml:id')
    if no_head:
        errs.append(f'{len(no_head)} story divs without <head type="storyHead">')
    untagged, malformed = [], Counter()
    for d in stories:
        toks = [t for s in d.iter(T + 'span') for t in re.split(r'[;\s]+', s.get('ana') or '') if t]
        topic = [t for t in toks if t != 'TBD:Unknown']
        for t in topic:
            if not TAG.match(t):
                malformed[t] += 1
        if not topic:
            untagged.append(d.get(XID))
    if untagged:
        errs.append(f'TOPIC TAGGING NOT DONE: {len(untagged)} of {len(stories)} stories have no topic tag '
                    f'(e.g. {untagged[0]}); run editions/llm-tagging (PIPELINE.md step 12)')
    if malformed:
        errs.append(f'{sum(malformed.values())} malformed topic tags, e.g. {malformed.most_common(1)[0][0]!r} '
                    f'(see editions/tag-audit/irregular-tags-mapping.tsv)')
    if images:
        missing = []
        for f in sorted({pb.get('facs') for pb in pbs if pb.get('facs')}):
            try:
                urllib.request.urlopen(urllib.request.Request(IMG + f, method='HEAD'), timeout=30)
            except Exception:
                missing.append(f)
        if missing:
            errs.append(f'{len(missing)} page images not on the server, e.g. {missing[0]}')
    notes.append(f'{len(stories)} stories, {len(pbs)} pages')
    return errs, notes


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    images = '--images' in sys.argv
    bad = 0
    for a in args:
        errs, notes = check(a, images)
        print(('FAIL ' if errs else 'PASS ') + Path(a).name + '  (' + '; '.join(notes) + ')')
        for e in errs:
            print('   - ' + e)
        bad += bool(errs)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
