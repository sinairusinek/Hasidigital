"""Apply editions/tag-audit/irregular-tags-mapping.tsv to the edition XMLs.

Collapses the ad-hoc tag families that predate the vocabulary (they are the RA's
earliest hand-tagging, visible since the 2026-11-24 inline-span sweep lifted them
into the story-level spans) down to the 13 families of editions/llm-tagging/vocab.tsv.

Only @ana ATTRIBUTE VALUES are touched. No element is added, removed or moved, and
no text changes: transcription, NER links, pb, headers and the women tiers are
untouched by construction.

Per row of the mapping:
  drop      -> remove the tag from the @ana it sits in
  replace   -> replace it with the proposed tag(s) (';'-separated), skipping any
               already present on the same story (so no duplicates appear)
  keep      -> leave it alone
  obsolete  -> expect 0 uses; report if any remain
Order inside each @ana is preserved; a replacement takes the position of the tag
it replaces. An @ana left empty would be a bug, so it is reported, not written.

Usage: python3 -I editions/tag-audit/apply_irregular_mapping.py [--write]
Without --write nothing is written.
"""
import csv
import glob
import re
import sys
from collections import Counter

from lxml import etree

T = '{http://www.tei-c.org/ns/1.0}'
X = '{http://www.w3.org/XML/1998/namespace}'
MAP = 'editions/tag-audit/irregular-tags-mapping.tsv'
VOCAB = 'editions/llm-tagging/vocab.tsv'


def load_mapping():
    rules = {}
    for r in csv.DictReader(open(MAP), delimiter='\t'):
        tag, act = r['current_tag'], (r['action'] or '').strip()
        act = act.split()[0].lower() if act else ''
        if act.startswith('drop'):
            rules[tag] = ('drop', [])
        elif act.startswith('replace') or act.startswith('split'):
            prop = re.sub(r'\(.*?\)', '', r['proposed'] or '')
            targets = [t.strip() for t in prop.split(';') if t.strip() and t.strip() != 'drop']
            rules[tag] = ('replace', targets) if targets else ('drop', [])
        elif act.startswith('keep'):
            rules[tag] = ('keep', [])
        elif act.startswith('obsolete'):
            rules[tag] = ('obsolete', [])
    # The 2026-11-24 label normalisation already split the bad-separator rows, leaving
    # 'practice:ritual_bathing,' with a dangling comma. Map the post-split form too.
    rules.setdefault('practice:ritual_bathing,', ('replace', ['practice:tvilah']))
    return rules


def main():
    write = '--write' in sys.argv
    rules = load_mapping()
    vocab = {l.split('\t')[0] for l in open(VOCAB) if l.strip()}
    stats, per_tag, problems, unmapped = Counter(), Counter(), [], Counter()

    for path in sorted(glob.glob('editions/online/*.xml')):
        tree = etree.parse(path)
        root = tree.getroot()
        before_text = ''.join(root.find(T + 'text').itertext())
        changed = False
        for sp in root.iter(T + 'span'):
            ana = sp.get('ana')
            if not ana:
                continue
            tags = [t.strip() for t in ana.split(';')]
            present = {t for t in tags if t}
            out, hit = [], False
            for t in tags:
                if not t:
                    continue
                rule = rules.get(t)
                if rule is None:
                    if t != 'TBD:Unknown' and t not in vocab:
                        unmapped[t] += 1
                    out.append(t)
                    continue
                act, targets = rule
                if act in ('keep',):
                    out.append(t)
                elif act == 'obsolete':
                    problems.append((path, 'obsolete tag still present', t))
                    out.append(t)
                elif act == 'drop':
                    hit = True
                    per_tag[f'{t} -> (dropped)'] += 1
                elif act == 'replace':
                    hit = True
                    added = [g for g in targets if g not in present and g not in out]
                    out.extend(added)
                    present.update(added)
                    per_tag[f'{t} -> {"; ".join(targets)}'
                            + ('' if added else ' [already present]')] += 1
            if not hit:
                continue
            if not out:
                # a leftover inline span whose only tag is dropped: remove the element, as
                # the 2026-11-24 sweep did for its siblings. Its text (if any) is kept in place.
                if (sp.text or '').strip():
                    problems.append((path, 'would empty an @ana but holds text', ana))
                    continue
                par = sp.getparent()
                prev = sp.getprevious()
                tail = (sp.text or '') + (sp.tail or '')
                if prev is not None:
                    prev.tail = (prev.tail or '') + tail
                else:
                    par.text = (par.text or '') + tail
                par.remove(sp)
                changed = True
                stats['empty spans removed'] += 1
                per_tag[f'{ana} -> (dropped, empty span removed)'] += 1
                continue
            new = '; '.join(out)
            if new != ana:
                sp.set('ana', new)
                changed = True
                stats['spans changed'] += 1
        if changed:
            after_text = ''.join(root.find(T + 'text').itertext())
            assert after_text == before_text, f'TEXT CHANGED in {path}'
            stats['files changed'] += 1
            if write:
                tree.write(path, xml_declaration=True, encoding='UTF-8')

    print('==', 'WRITTEN' if write else 'DRY RUN', '==')
    print(dict(stats))
    print('\nby rule:')
    for k, v in sorted(per_tag.items(), key=lambda x: -x[1]):
        print(f'  {v:4}  {k}')
    if unmapped:
        print('\nstill outside the vocabulary and NOT in the mapping:')
        for k, v in unmapped.most_common():
            print(f'  {v:4}  {k}')
    if problems:
        print('\nPROBLEMS:')
        for p in problems:
            print('  ', p)


if __name__ == '__main__':
    main()
