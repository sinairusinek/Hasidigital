#!/usr/bin/env python3
"""Compare an annotated edition's text with its Transkribus export, line by line.
Reports lines whose letters are the same but in a different order ('shuffled')
and lines whose letters differ ('changed'). Usage: text_drift.py SOURCE.bak EDITION.xml [-v]"""
import re, sys, difflib
from collections import Counter
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from restore_pb import source_lines, edition_lines
s, _ = source_lines(open(sys.argv[1], encoding='utf-8').read())
e = edition_lines(open(sys.argv[2], encoding='utf-8').read())
a = [x[2] for x in s]; b = [x[1] for x in e]
# compare the whole text as one letter stream, then attribute differences
A = ''.join(a); B = ''.join(b)
sm = difflib.SequenceMatcher(None, A, B, autojunk=False)
ops = [o for o in sm.get_opcodes() if o[0] != 'equal']
moved = sum(1 for o in ops if o[0] in ('delete', 'insert') and len(A[o[1]:o[2]] or B[o[3]:o[4]]) >= 3)
print(f'{sys.argv[2].split("/")[-1]:24} letters src {len(A)} ed {len(B)}  same-order {sum(m.size for m in sm.get_matching_blocks())/max(len(A),1):.4f}  diff-ops {len(ops)} (>=3 letters: {moved})')
# line level: same letters, different order
sm2 = difflib.SequenceMatcher(None, a, b, autojunk=False)
shuffled = 0; ex = []
for tag, i1, i2, j1, j2 in sm2.get_opcodes():
    if tag == 'replace':
        sa, sb = ''.join(a[i1:i2]), ''.join(b[j1:j2])
        if Counter(sa) == Counter(sb) and sa != sb:
            shuffled += (j2 - j1); ex.append((sa[:60], sb[:60]))
print(f'  line groups with the same letters in a different order: {len(ex)} ({shuffled} lines)')
if '-v' in sys.argv:
    for x, y in ex[:8]: print('   src', x, '\n   ed ', y)
