"""Put back the DictaBERT tags OUTSIDE stories, which earlier --correct runs displaced.

Usage: python3 editions/scripts/restore_non_story_tags.py EDITION.xml BASE_COMMIT [--write]

Found 2026-11-22: ner_pipeline's extract_existing_entities_simple located tags by string search
(first occurrence in the whole book, one tag type at a time), so a story-only --correct run
re-inserted the untouched non-story tags on other occurrences of the same name, or cut short at a
line break (about 15% of non-story tags in the 12 DictaBERT editions). The function is fixed; this
restores those tags from the DictaBERT commit (BASE_COMMIT, whose text must be identical).
Tags inside story divs (the corrected ones) are kept: the story divs of the current file are put
back unchanged. A story div split out of paratext (subtype="in-...") counts as non-story here,
since its tags were never corrected.
"""
import copy
import subprocess
import sys
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ner_pipeline.annotation_inserter import (  # noqa: E402
    extract_existing_entities_simple, strip_existing_annotations, insert_annotations,
    strip_annotations_from_heads)
from ner_pipeline.text_extraction import create_standoff_view  # noqa: E402
from ner_pipeline.nisba_fixer import fix_nisba_nesting  # noqa: E402

T = '{http://www.tei-c.org/ns/1.0}'


def corrected_stories(root):
    return [d for d in root.iter(T + 'div') if d.get('type') == 'story'
            and not (d.get('subtype') or '').startswith('in-')
            and not any(a.get('type') == 'story' for a in d.iterancestors(T + 'div'))]


def story_ranges(root):
    tx = root.find(T + 'text')
    keep = corrected_stories(root)  # held alive: lxml proxy ids are only stable while referenced
    want = set(map(id, keep))
    out, pos = [], [0]

    def walk(el):
        st = pos[0]
        if el.text:
            pos[0] += len(el.text)
        for c in el:
            walk(c)
            if c.tail:
                pos[0] += len(c.tail)
        if id(el) in want:
            out.append((st, pos[0]))
    walk(tx)
    return out


def main():
    path, base = Path(sys.argv[1]), sys.argv[2]
    rel = path.resolve().relative_to(ROOT)
    tree = etree.parse(str(path))
    orig = copy.deepcopy(tree)
    try:
        bxml = subprocess.check_output(['git', 'show', f'{base}:{rel}'], cwd=ROOT)
    except subprocess.CalledProcessError:
        bxml = subprocess.check_output(['git', 'show', f'{base}:editions/incoming/ready/{path.name}'], cwd=ROOT)
    btree = etree.ElementTree(etree.fromstring(bxml))
    cur, pt = extract_existing_entities_simple(tree)
    bas, pb = extract_existing_entities_simple(btree)
    assert pt == pb, 'base text differs'
    rng = story_ranges(tree.getroot())
    inside = lambda e: any(e['start'] >= a and e['end'] <= b for a, b in rng)
    overl = lambda e: any(e['start'] < b and e['end'] > a for a, b in rng)
    final = [e for e in cur if inside(e)] + [e for e in bas if not overl(e)]
    out_before = sum(1 for e in cur if not inside(e))
    strip_existing_annotations(tree)
    so, view, _ = create_standoff_view(tree)
    insert_annotations(so, view, sorted(final, key=lambda e: (e['start'], e['end'])))
    # standoffconverter makes the new elements without a namespace; they become TEI elements
    # once serialized under the default xmlns, so round-trip before working on them
    tree = etree.ElementTree(etree.fromstring(etree.tostring(tree)))
    fix_nisba_nesting(tree)
    strip_annotations_from_heads(tree)
    # story divs: exactly as they were
    o_st, n_st = corrected_stories(orig.getroot()), corrected_stories(tree.getroot())
    assert len(o_st) == len(n_st)
    for o, n in zip(o_st, n_st):
        c = copy.deepcopy(o)
        c.tail = n.tail
        n.getparent().replace(n, c)
    ot, nt = orig.getroot().find(T + 'text'), tree.getroot().find(T + 'text')
    assert ''.join(ot.itertext()) == ''.join(nt.itertext()), 'text changed'
    for tag in ('lb', 'pb', 'fw', 'div', 'p'):
        assert len(ot.findall(f'.//{T}{tag}')) == len(nt.findall(f'.//{T}{tag}')), f'{tag} count changed'
    now, _ = extract_existing_entities_simple(tree)
    bset = {(e['start'], e['end'], e['label']) for e in bas if not overl(e)}
    nset = {(e['start'], e['end'], e['label']) for e in now if not inside(e)}
    print(f'{path.name}: non-story tags {out_before} -> {len(nset)} '
          f'(DictaBERT base: {len(bset)}; at the base position: {len(bset & nset)})')
    if '--write' in sys.argv:
        tree.write(str(path), xml_declaration=True, encoding='UTF-8')


if __name__ == '__main__':
    main()
