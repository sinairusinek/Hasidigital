"""Checks that need the page text (so they run after HTR): the catch-word of page n should equal the first word
of page n+1, and printed page numbers should run in sequence.
    python text_checks.py SUFFIX     (text from xml/<doc>/<page>.<suffix>.xml; consecutive pages of test-set.tsv)
"""
import csv, re, sys
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).parent
VAL = dict(zip("אבגדהוזחטיכלמנסעפצקרשת", [1,2,3,4,5,6,7,8,9,10,20,30,40,50,60,70,80,90,100,200,300,400]))
VAL.update(dict(zip("ךםןףץ", [20, 40, 50, 80, 90])))


def texts(f):
    root = ET.parse(f).getroot(); ns = root.tag.split("}")[0][1:]; q = lambda t: f"{{{ns}}}{t}"
    out = {"_lines": []}
    for r in root.iter(q("TextRegion")):
        m = re.search(r"type:([\w-]+)", r.get("custom", "")); lab = m.group(1) if m else "none"
        ls = []
        for l in r.iter(q("TextLine")):
            u = l.find(f"{q('TextEquiv')}/{q('Unicode')}"); t = (u.text or "") if u is not None else ""
            ro = re.search(r"readingOrder \{index:(\d+)", r.get("custom", ""))
            ls.append(t); out["_lines"].append(((int(ro.group(1)) if ro else 999, len(ls)), lab, t))
        out.setdefault(lab, []).append(" ".join(ls))
    return out


def norm(w): return re.sub(r"[^א-ת]", "", w)


def hebnum(s):
    s = norm(s)
    return sum(VAL.get(c, 0) for c in s) if s else None


def first_word(t):
    """First word in reading order (page furniture excluded)."""
    for _, lab, line in sorted(t["_lines"]):
        if lab in ("running-head", "page-number", "catch-word"): continue
        ws = [norm(w) for w in line.split() if norm(w)]
        if ws: return ws[0]
    return None


def close(a, b):
    """Same word allowing one OCR slip, or one a prefix of the other (catch-words are sometimes cut)."""
    if a.startswith(b) or b.startswith(a): return True
    if abs(len(a) - len(b)) > 1: return False
    d = [[i + j if not i * j else 0 for j in range(len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i-1][j] + 1, d[i][j-1] + 1, d[i-1][j-1] + (a[i-1] != b[j-1]))
    return d[-1][-1] <= 1


def main():
    suffix = sys.argv[1] if len(sys.argv) > 1 else "final"
    rows = list(csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t"))
    T = {}
    for r in rows:
        f = HERE / "xml" / r["docId"] / f"{int(r['pageNr']):04d}.{suffix}.xml"
        if f.exists(): T[(r["docId"], int(r["pageNr"]))] = texts(f)
    n_cw = bad_cw = n_pn = bad_pn = 0; report = []
    for (d, n), t in T.items():
        nxt = T.get((d, n + 1))
        if not nxt: continue
        cws = [norm(c) for c in t.get("catch-word", []) if norm(c)]
        fw = first_word(nxt)
        if cws and fw:
            n_cw += 1
            if not close(cws[0], fw): bad_cw += 1; report.append(f"{d} p{n}: catch-word {cws[0]} / next page starts {fw}")
        a = [hebnum(x) for x in t.get("page-number", []) if hebnum(x)]; b = [hebnum(x) for x in nxt.get("page-number", []) if hebnum(x)]
        if a and b:
            n_pn += 1
            if b[0] - a[0] not in (1, 2): bad_pn += 1; report.append(f"{d} p{n}: page number {a[0]} then {b[0]}")
    print(f"{suffix}: catch-word pairs {n_cw}, mismatched {bad_cw}; page-number pairs {n_pn}, out of sequence {bad_pn}")
    for x in report: print("  " + x)


if __name__ == "__main__":
    main()
