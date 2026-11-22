"""NER correction of the text OUTSIDE stories (introductions, approbations, sayings, commentary,
title pages), Sinai 2026-11-22: "do tag paratexts and non story materials, correct and link them".

Usage: python3 editions/scripts/correct_non_story.py EDITION.xml OUT.xml [--engine gemini|claude-cli]

Runs `ner_pipeline.cli --correct --story-id @non-story` (pieces of ~3000 characters; a piece with
no tags yet is annotated from scratch by the same prompt) on a scratch copy, then puts every story
div of the ORIGINAL back unchanged, so curated story markup can never be touched. Checks that the
text and the lb/pb count are unchanged. Log: gemini-correction-log-{slug}-non-story.tsv.
"""
import copy
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from lxml import etree

T = '{http://www.tei-c.org/ns/1.0}'
ROOT = Path(__file__).resolve().parents[2]


def outer_stories(root):
    return [d for d in root.iter(T + 'div') if d.get('type') == 'story'
            and not any(a.get('type') == 'story' for a in d.iterancestors(T + 'div'))]


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    env = dict(os.environ)
    # --story-id A,B: correct those story divs instead of the non-story text (split stories)
    sid = sys.argv[sys.argv.index('--story-id') + 1] if '--story-id' in sys.argv else '@non-story'
    keep_new = set(sid.split(',')) if sid != '@non-story' else set()
    if '--engine' in sys.argv and sys.argv[sys.argv.index('--engine') + 1] == 'claude-cli':
        env['NER_CORRECTOR'] = 'claude-cli'
    if '--from-corrected' in sys.argv:  # finish a run whose Gemini part already ran
        tmp = Path(sys.argv[sys.argv.index('--from-corrected') + 1])
        tmpd = tmp.parent
    else:
        tmpd = Path(tempfile.mkdtemp())
        tmp = tmpd / src.name
        shutil.copy(src, tmp)
        print('scratch copy:', tmp, flush=True)
        subprocess.run([sys.executable, '-m', 'ner_pipeline.cli', '--input', str(tmp), '--correct',
                        '--story-id', sid, '--max-removal-pct', '60', '--output-suffix', ''],
                       cwd=ROOT, env=env, check=True)
    log = tmpd / 'gemini-correction-log.tsv'
    if log.exists():
        d = ROOT / 'editions' / 'ner-logs'
        d.mkdir(exist_ok=True)
        shutil.copy(log, d / f'gemini-correction-log-{src.stem}-{"split-stories" if keep_new else "non-story"}.tsv')
    orig = etree.parse(str(src))
    # the inserter can write the same <anchor xml:id=X/> twice (a tag ending at a <supplied>
    # boundary); drop the repeats, as finish_corrected.py does
    raw, seen = tmp.read_bytes().decode('utf-8'), set()

    def _dedupe(m):
        if m.group(1) in seen:
            return ''
        seen.add(m.group(1))
        return m.group(0)
    raw = re.sub(r'<anchor xml:id="([^"]+)"\s*/>', _dedupe, raw)
    corr = etree.ElementTree(etree.fromstring(raw.encode('utf-8')))
    o_st, c_st = outer_stories(orig.getroot()), outer_stories(corr.getroot())
    assert len(o_st) == len(c_st), 'story count differs'
    for o, c in zip(o_st, c_st):
        if o.get('{http://www.w3.org/XML/1998/namespace}id') in keep_new:
            continue
        n = copy.deepcopy(o)
        n.tail = c.tail
        c.getparent().replace(c, n)
    ot, ct = orig.getroot().find(T + 'text'), corr.getroot().find(T + 'text')
    assert ''.join(ot.itertext()) == ''.join(ct.itertext()), 'text changed'
    for tag in ('lb', 'pb'):
        assert len(ot.findall(f'.//{T}{tag}')) == len(ct.findall(f'.//{T}{tag}')), f'{tag} count changed'
    # the header is the original's (the pipeline may touch it)
    corr.getroot().replace(corr.getroot().find(T + 'teiHeader'), copy.deepcopy(orig.getroot().find(T + 'teiHeader')))
    if keep_new:  # the rest of the file exactly as it was: put the corrected stories into the original
        new = {d.get('{http://www.w3.org/XML/1998/namespace}id'): d for d in c_st}
        for o in o_st:
            i = o.get('{http://www.w3.org/XML/1998/namespace}id')
            if i in keep_new:
                n = copy.deepcopy(new[i])
                n.tail = o.tail
                o.getparent().replace(o, n)
        corr = orig
        ct = corr.getroot().find(T + 'text')
        assert ''.join(ot.itertext()) == ''.join(ct.itertext()), 'text changed'
    corr.write(str(out), xml_declaration=True, encoding='UTF-8')
    cnt = lambda t: {k: len(t.findall(f'.//{T}{k}')) for k in ('placeName', 'persName', 'name', 'date')}
    print('before', cnt(ot), '\nafter ', cnt(ct))


if __name__ == '__main__':
    main()
