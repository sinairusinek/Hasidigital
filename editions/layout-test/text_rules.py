"""Correct region tags from the text a model read on our lines, using what only consecutive pages show:
- running head: a piece of a page's top line whose text recurs at the top of other pages of the book;
- page number: a short top-line piece that reads as a Hebrew numeral or as digits;
- catch-word: a single word alone on the bottom line that matches the first word of the next page.
A box is re-tagged only when every line in it is that piece. Reading comes from htr_test.py's combined run.

    python text_rules.py MODEL BASE PAGES.tsv   tags of .<BASE>.xml → .<BASE>+text.xml; prints what changed
"""
import csv, re, sys, collections
from pathlib import Path
import numpy as np
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein
from htr_test import our_lines, numbered_lines, bare, OUT, HERE, IMG
from layout_qa import read_layout, letters

HEB_NUM = re.compile(r"^(ת{0,4}(ק|ר|ש|ת)?(י|כ|ל|מ|נ|ס|ע|פ|צ)?(א|ב|ג|ד|ה|ו|ז|ח|ט)?|טו|טז)$")


def rows(lines, h):
    """Top and bottom rows: line indexes whose baseline lies within one letter height of the first / last."""
    y = np.array([np.median(l["bl"][:, 1]) for l in lines])
    return set(np.where(y < y.min() + h)[0]), set(np.where(y > y.max() - h)[0]), y


def main():
    model, base, pages_f = sys.argv[1], sys.argv[2], sys.argv[3]
    pages = sorted((r["docId"], int(r["pageNr"])) for r in csv.DictReader(open(pages_f), delimiter="\t"))
    info = {}
    for doc, n in pages:
        f = OUT / f"comb-{model}-{doc}_{n:04d}.txt"
        if not f.exists(): continue
        ls = our_lines(doc, n); t = numbered_lines(f.read_text(), "LINES")
        for i, l in enumerate(ls): l["read"] = t.get(i + 1, "")
        im = IMG / doc / f"{n:04d}.jpg"; _, W, H = read_layout(HERE / "xml" / doc / f"{n:04d}.{base}.xml")
        h = float(np.median(letters(im, W, H)[:, 2])); top, bottom, y = rows(ls, h)
        body = sorted((i for i in range(len(ls)) if i not in top), key=lambda i: (y[i] // h, -ls[i]["bl"][:, 0].max()))
        first = ls[body[0]]["read"].split()[0] if body and ls[body[0]]["read"].split() else ""
        info[(doc, n)] = dict(lines=ls, top=top, bottom=bottom, first=first)
    changes = collections.Counter()
    for (doc, n), p in info.items():
        ls = p["lines"]; want = {}
        others = [bare(ls2[i]["read"]) for (d2, n2), q in info.items() if d2 == doc and n2 != n for ls2 in [q["lines"]] for i in q["top"]]
        for i in p["top"]:
            b = bare(ls[i]["read"])
            if not b: continue
            if len(b) <= 4 and (b.isdigit() or HEB_NUM.match(b)): want[i] = "page-number"
            elif len(b) >= 5 and any(fuzz.partial_ratio(b, o) >= 80 for o in others if len(o) >= 5): want[i] = "running-head"
        nxt = info.get((doc, n + 1))
        if nxt and nxt["first"]:
            for i in p["bottom"]:
                w = ls[i]["read"].split()
                if len(w) == 1 and Levenshtein.distance(bare(w[0]), bare(nxt["first"])) <= 1 and bare(w[0]): want[i] = "catch-word"
        src = HERE / "xml" / doc / f"{n:04d}.{base}.xml"; x = src.read_text()
        # boxes are numbered as in our layout file; the base file may have dropped some, so match them by id
        ours = (HERE / "xml" / doc / f"{n:04d}.yolo+krakenfix-yolo-noext.xml").read_text()
        ids = [m.group(1) for m in re.finditer(r'<TextRegion id="([^"]+)"[^>]*>\s*<Coords points="[^"]+"', ours)]
        now = dict(re.findall(r'<TextRegion id="([^"]+)" custom="structure \{type:([\w-]+);', x))
        by_box = collections.defaultdict(list)
        for i, l in enumerate(ls): by_box[l["region"]].append(i)
        for k, members in by_box.items():
            tags = {want.get(i) for i in members}
            if len(tags) != 1 or None in tags: continue
            t = tags.pop()
            rid = ids[k - 1] if k - 1 < len(ids) else None
            if rid in now and now[rid] != t:
                x = re.sub(rf'(<TextRegion id="{rid}" custom="structure {{type:)[\w-]+', rf"\g<1>{t}", x)
                changes[f"{now[rid]}→{t}"] += 1
        (src.parent / f"{n:04d}.{base}+text.xml").write_text(x)
    print(len(info), "pages;", dict(changes))


if __name__ == "__main__":
    main()
