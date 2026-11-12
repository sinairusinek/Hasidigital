"""HTR test: can a vision model read our pages as well as the Transkribus HTR model 52805, and can its reading
also correct the region tags and find badly cut lines?

    python htr_test.py fetch PAGES.tsv                 the last HTR-52805 version of each page → xml/<doc>/<page>.htr.xml
    python htr_test.py read MODEL PAGES.tsv            the RA's own lines, cut into numbered strips → text per line
    python htr_test.py combined MODEL PAGES.tsv        our layout (numbered boxes + line strips) → text, box tags and
                                                       lines that look wrongly cut, in one call; tags → .<OURS>+htr-<MODEL>.xml
    python htr_test.py score PAGES.tsv                 → htr-scores.tsv, htr-lines.tsv and totals

Character error rate (CER) is edit distance over the RA's FINAL text, line by line. Each FINAL line is compared with
the line that holds most of its letters (by baseline), so splits, merges and missed lines count against a method.
Text is normalised first (״ = ", ׳ = ', no vowel points, one space, no space before : . ,); 'letters CER' also drops
spaces and punctuation. Answers are cached in ~/Documents/Hasidigital-data/htr/. Claude runs through `claude -p` on
the Max plan; Gemini through the google-genai SDK.
"""
import csv, json, re, sys, unicodedata, collections, subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np, cv2, requests
import xml.etree.ElementTree as ET
from rapidfuzz.distance import Levenshtein
from layout_qa import read_layout, letters
from line_score import assign_baseline, FW, OK
from vlm_relabel import ask, numbered, DEFS, TAGS

HERE = Path(__file__).parent
DATA = Path.home() / "Documents/Hasidigital-data"
IMG = DATA / "layout-test"
OUT = DATA / "htr"; (OUT / "strips").mkdir(parents=True, exist_ok=True)
FULLDOC = DATA / "layout-train" / "fulldoc"
OURS = "yolo+krakenfix-yolo-noext"
PER_STRIP = 10

RULES = """Transcribe exactly as printed:
- keep abbreviations as printed (הרה"ק, ז"ל, וכו') and never expand them;
- do not correct spelling or grammar and do not add letters that are not printed;
- keep the punctuation that is printed (: . , [ ] ( ) and the like); no vowel points;
- Rashi-script and Yiddish lines are transcribed in ordinary Hebrew letters, as printed;
- a line may be only a page number, a running head or a single catch-word: transcribe it too;
- if part of a line is cut off or unclear, give what you can read."""


# ---------- PAGE XML ----------
def page_lines(f):
    """Lines in reading order with their region number (1-based, as read_layout and numbered() count regions),
    region tag, outline, baseline and text."""
    root = ET.parse(f).getroot(); ns = root.tag.split("}")[0][1:]; q = lambda t: f"{{{ns}}}{t}"
    pts = lambda s: np.array([tuple(map(int, xy.split(","))) for xy in s.split()])
    out, k = [], 0
    for r in root.iter(q("TextRegion")):
        c = r.find(q("Coords"))
        if c is None or not c.get("points"): continue
        k += 1; m = re.search(r"type:([\w-]+)", r.get("custom", "")); lab = m.group(1) if m else "none"
        for l in r.iter(q("TextLine")):
            c = l.find(q("Coords"))
            if c is None or not c.get("points"): continue
            p = pts(c.get("points"))
            if len(p) < 2: continue
            b = l.find(q("Baseline")); bl = pts(b.get("points")) if b is not None and b.get("points") else None
            if bl is None:  # our outlines run 1.6 letter heights above the baseline and 0.5 below
                y0, y1 = p[:, 1].min(), p[:, 1].max(); y = int(y1 - (y1 - y0) * 0.5 / 2.1)
                bl = np.array([[p[:, 0].min(), y], [p[:, 0].max(), y]])
            u = l.find(f"{q('TextEquiv')}/{q('Unicode')}")
            out.append(dict(region=k, lab=lab, poly=p, bl=bl[np.argsort(bl[:, 0])], text=(u.text or "") if u is not None else "",
                            coords=c.get("points")))
    return out


def our_lines(doc, n):
    """Our layout's lines (in region order, as numbered for the model) with Kraken's true baselines, which the
    region file lacks; outlines are identical in both files."""
    d = HERE / "xml" / doc
    ls = page_lines(d / f"{n:04d}.{OURS}.xml")
    bl = {l["coords"]: l["bl"] for l in page_lines(d / f"{n:04d}.krakenfix-yolo-noext.xml")}
    for l in ls: l["bl"] = bl.get(l["coords"], l["bl"])
    return ls


# ---------- strips ----------
def strips(doc, n, lines, tag):
    """Numbered strips of line images, PER_STRIP lines each, cut from the full-resolution page around each baseline."""
    im = cv2.imread(str(IMG / doc / f"{n:04d}.jpg")); H, W = im.shape[:2]
    L = letters(IMG / doc / f"{n:04d}.jpg", W, H); h = float(np.median(L[:, 2])) if L is not None and len(L) else 30
    rows = []
    for i, l in enumerate(lines, 1):
        bl = l["bl"]; x0, x1 = int(max(0, bl[:, 0].min() - 0.6 * h)), int(min(W, bl[:, 0].max() + 0.6 * h))
        y0, y1 = int(max(0, bl[:, 1].min() - 1.5 * h)), int(min(H, bl[:, 1].max() + 0.6 * h))
        c = im[y0:y1, x0:x1]
        if c.size == 0: c = np.full((int(2 * h), int(4 * h), 3), 255, np.uint8)
        if c.shape[1] > 1700: c = cv2.resize(c, (1700, int(c.shape[0] * 1700 / c.shape[1])), interpolation=cv2.INTER_AREA)
        g = np.full((c.shape[0] + 14, 1800, 3), 255, np.uint8); g[7:7 + c.shape[0], 1800 - c.shape[1]:] = c
        cv2.putText(g, str(i), (6, min(g.shape[0] - 8, 40)), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 200), 2)
        cv2.line(g, (0, g.shape[0] - 1), (1800, g.shape[0] - 1), (180, 180, 180), 1)
        rows.append(g)
    files = []
    for k in range(0, len(rows), PER_STRIP):
        f = OUT / "strips" / f"{doc}_{n:04d}_{tag}_{k // PER_STRIP + 1}.jpg"
        cv2.imwrite(str(f), np.vstack(rows[k:k + PER_STRIP]), [cv2.IMWRITE_JPEG_QUALITY, 90]); files.append(f)
    return files


def numbered_lines(text, section=None):
    """'12<TAB>text' lines → {12: text}; with section, only the lines under that heading."""
    if section:
        m = re.search(rf"^{section}\s*:?\s*$(.*?)(?=^[A-Z]+\s*:?\s*$|\Z)", text, re.S | re.M)
        text = m.group(1) if m else ""
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\s*(\d+)\s*(?:\t|:|\.|\)|-|–| )\s*(.*?)\s*$", line)
        if m: out[int(m.group(1))] = m.group(2)
    return out


def claude_hint(model):
    return "" if model.startswith("gemini") else "Use the Read tool on every image listed at the end, in order.\n\n"


# ---------- runs ----------
def read_page(model, doc, n):
    f = OUT / f"read-{model}-{doc}_{n:04d}.txt"
    if f.exists(): return
    lines = page_lines(HERE / "xml" / doc / f"{n:04d}.final.xml")
    files = strips(doc, n, lines, "final")
    out = ask(claude_hint(model) + f"""The images are strips of numbered text lines cut from one page of a printed Hebrew book
(19th or early 20th century). There are {len(lines)} lines, numbered 1 to {len(lines)} in red on the left.

{RULES}

Answer with one row per line: the number, a tab, then the text. Nothing else.""", files, model)
    f.write_text(out)


def combined_page(model, doc, n):
    f = OUT / f"comb-{model}-{doc}_{n:04d}.txt"
    src = HERE / "xml" / doc / f"{n:04d}.{OURS}.xml"
    regs, W, H = read_layout(src); lines = page_lines(src)
    if not f.exists():
        note = (DATA / "vlm" / f"note-{doc}-{'opus' if not model.startswith('gemini') else model}.txt")
        note = note.read_text() if note.exists() else "(no note)"
        files = [numbered(doc, n, regs)] + strips(doc, n, lines, "ours")
        boxes = "\n".join(f"box {i}: now '{r['lab']}'" for i, r in enumerate(regs, 1))
        owner = "\n".join(f"line {i}: in box {l['region']}" for i, l in enumerate(lines, 1))
        out = ask(claude_hint(model) + f"""The first image is a page of a printed Hebrew book with numbered red boxes drawn by an automatic
layout tool. The other images are strips of the text lines the tool found on that page, numbered 1 to {len(lines)} in red on the left.
Do three things.

1. Transcribe every numbered line.
{RULES}

2. Give the right tag for every box. The tool's tags are often wrong; use what the text says as well as how it looks
(a running head repeats the book or section title, a catch-word is one word under the last line, a heading names a story or
chapter, footnotes are notes in smaller type).
{DEFS}
What we know about this book:
{note}

3. Name the lines that the tool cut wrongly: a strip that holds two lines or two columns side by side, a strip that is only part of
a line (the line goes on beyond the strip), or a strip with no text.

Boxes:
{boxes}

Lines and their boxes:
{owner}

Answer in exactly this form and nothing else:
LINES
1<TAB>text
...
TAGS
1<TAB>tag
...
PROBLEMS
<line number><TAB>two lines | two columns | part of a line | no text
(write PROBLEMS and leave it empty if there are none)""", files, model)
        f.write_text(out)
    # write the re-tagged layout
    tags = numbered_lines(f.read_text(), "TAGS")
    x = src.read_text(); ids = [m.group(1) for m in re.finditer(r'<TextRegion id="([^"]+)"[^>]*>\s*<Coords points="[^"]+"', x)]
    for i, rid in enumerate(ids, 1):
        t = tags.get(i, "").strip().strip("'\"").lower()
        if t not in TAGS or t == regs[i - 1]["lab"]: continue
        if t == "none": x = re.sub(rf'<TextRegion id="{rid}".*?</TextRegion>\n?', "", x, flags=re.S)
        else: x = re.sub(rf'(<TextRegion id="{rid}" custom="structure {{type:)[\w-]+', rf"\g<1>{t}", x)
    (src.parent / f"{n:04d}.{OURS}+htr-{model}.xml").write_text(x)


def fetch(pages):
    for doc, n in pages:
        out = HERE / "xml" / doc / f"{n:04d}.htr.xml"
        if out.exists(): continue
        p = next(p for p in json.loads((FULLDOC / f"{doc}.json").read_text())["pageList"]["pages"] if p["pageNr"] == n)
        v = sorted([t for t in p["tsList"]["transcripts"] if "52805" in (t.get("toolName") or "")], key=lambda t: t["timestamp"])
        if v: out.write_bytes(requests.get(v[-1]["url"], timeout=180).content)


# ---------- scoring ----------
def norm(s):
    s = unicodedata.normalize("NFC", s or "")
    s = s.replace("״", '"').replace("׳", "'").replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'").replace("־", "-")
    s = re.sub(r"[֑-ֽֿ-ׇ]", "", s)
    s = re.sub(r"\s+", " ", s).strip(); return re.sub(r" ([:.,;])", r"\1", s)


def bare(s):
    return re.sub(r"[^א-ת0-9]", "", norm(s))


def joined(final, hyp, texts, L):
    """For each FINAL line, the text of every hyp line whose letters lie mostly in it, right to left: a line cut in
    pieces is read whole, so this measures the reading; the strict mapping below also charges the cutting."""
    tup = lambda ls: [(l["poly"], l["lab"], l["bl"]) for l in ls]
    fa, ha = assign_baseline(tup(final), L), assign_baseline(tup(hyp), L)
    parts = collections.defaultdict(list)
    for j in range(len(hyp)):
        m = fa[(ha == j) & (fa >= 0)]
        if len(m): parts[collections.Counter(m.tolist()).most_common(1)[0][0]].append(j)
    return [" ".join(texts[j] for j in sorted(parts[i], key=lambda j: -hyp[j]["bl"][:, 0].max())) for i in range(len(final))]


def mapped(final, hyp, L):
    """For each FINAL line, the hyp line holding most of its letters (None if none)."""
    tup = lambda ls: [(l["poly"], l["lab"], l["bl"]) for l in ls]
    fa, ha = assign_baseline(tup(final), L), assign_baseline(tup(hyp), L)
    out = []
    for i in range(len(final)):
        mine = ha[fa == i]
        if len(mine) == 0: out.append(None); continue
        j, k = collections.Counter(mine.tolist()).most_common(1)[0]
        out.append(j if j >= 0 else None)
    return out, fa, ha


def score(pages):
    methods = {}
    for f in sorted(OUT.glob("read-*.txt")): methods.setdefault("read " + f.name[5:].rsplit("-", 1)[0], None)
    for f in sorted(OUT.glob("comb-*.txt")): methods.setdefault("combined " + f.name[5:].rsplit("-", 1)[0], None)
    rows, flagrows = [], []
    for doc, n in pages:
        d = HERE / "xml" / doc; final = page_lines(d / f"{n:04d}.final.xml")
        _, W, H = read_layout(d / f"{n:04d}.final.xml"); L = letters(IMG / doc / f"{n:04d}.jpg", W, H)
        hyps = {}
        if (d / f"{n:04d}.htr.xml").exists():
            hl = page_lines(d / f"{n:04d}.htr.xml"); m, _, _ = mapped(final, hl, L)
            hyps["Transkribus HTR 52805"] = [hl[j]["text"] if j is not None else "" for j in m]
        for meth in methods:
            kind, model = meth.split(" ", 1)
            f = OUT / f"{'read' if kind == 'read' else 'comb'}-{model}-{doc}_{n:04d}.txt"
            if not f.exists(): continue
            if kind == "read":
                t = numbered_lines(f.read_text()); hyps[meth] = [t.get(i, "") for i in range(1, len(final) + 1)]
            else:
                ours = our_lines(doc, n); t = numbered_lines(f.read_text(), "LINES")
                m, fa, ha = mapped(final, ours, L)
                hyps[meth] = joined(final, ours, [t.get(j + 1, "") for j in range(len(ours))], L)
                hyps[meth + " (strict)"] = [t.get(j + 1, "") if j is not None else "" for j in m]
                # which of our lines are really wrong: they hold part of a FINAL line they do not hold cleanly
                bad = set()
                for i, l in enumerate(final):
                    mine = ha[fa == i]
                    if len(mine) < 3: continue
                    j, k = collections.Counter(mine.tolist()).most_common(1)[0]
                    if not (j >= 0 and k / len(mine) >= OK and k / max(1, (ha == j).sum()) >= OK):
                        bad |= {x for x in set(mine.tolist()) if x >= 0}
                said = {i - 1: v for i, v in numbered_lines(f.read_text(), "PROBLEMS").items()}
                for j in range(len(ours)):
                    flagrows.append(dict(method=meth, docId=doc, pageNr=n, line=j + 1, wrong=int(j in bad), flagged=said.get(j, "")))
        for meth, hyp in hyps.items():
            for i, l in enumerate(final):
                ref = norm(l["text"])
                if not ref: continue
                rows.append(dict(method=meth, docId=doc, pageNr=n, line=i + 1, tag=l["lab"], ref=ref, hyp=norm(hyp[i]),
                                 chars=len(ref), errors=Levenshtein.distance(ref, norm(hyp[i])),
                                 lchars=len(bare(ref)), lerrors=Levenshtein.distance(bare(ref), bare(hyp[i]))))
    w = csv.DictWriter(open(HERE / "htr-lines.tsv", "w"), rows[0].keys(), delimiter="\t"); w.writeheader(); w.writerows(rows)
    # each method is scored on its own pages, next to Transkribus on the same pages
    pages_of = lambda m: {(r["docId"], r["pageNr"]) for r in rows if r["method"] == m}
    tr = pages_of("Transkribus HTR 52805")
    def stats(meth, pages):
        xs = [r for r in rows if r["method"] == meth and (r["docId"], r["pageNr"]) in pages]
        body = [r for r in xs if r["tag"] not in FW]
        pg = collections.defaultdict(lambda: [0, 0])
        for r in body: pg[(r["docId"], r["pageNr"])][0] += r["errors"]; pg[(r["docId"], r["pageNr"])][1] += r["chars"]
        return dict(cer=round(sum(r["errors"] for r in body) / max(1, sum(r["chars"] for r in body)), 4),
                    letters_cer=round(sum(r["lerrors"] for r in body) / max(1, sum(r["lchars"] for r in body)), 4),
                    pages_over_5pct=sum(e / max(1, c) > 0.05 for e, c in pg.values()), lines=len(body),
                    fw_cer=round(sum(r["errors"] for r in xs if r["tag"] in FW) / max(1, sum(r["chars"] for r in xs if r["tag"] in FW)), 4))
    summary = []
    for meth in sorted({r["method"] for r in rows}):
        common = pages_of(meth) & tr; s = stats(meth, common); t = stats("Transkribus HTR 52805", common)
        summary.append(dict(method=meth, pages=len(common), **s, transkribus_cer=t["cer"], transkribus_letters_cer=t["letters_cer"],
                            transkribus_pages_over_5pct=t["pages_over_5pct"]))
    w = csv.DictWriter(open(HERE / "htr-scores.tsv", "w"), summary[0].keys(), delimiter="\t"); w.writeheader(); w.writerows(summary)
    for s in summary: print(s)
    if flagrows:
        w = csv.DictWriter(open(HERE / "htr-lineflags.tsv", "w"), flagrows[0].keys(), delimiter="\t"); w.writeheader(); w.writerows(flagrows)
        for meth in sorted({r["method"] for r in flagrows}):
            xs = [r for r in flagrows if r["method"] == meth]; wr = [r for r in xs if r["wrong"]]; fl = [r for r in xs if r["flagged"]]
            hit = sum(1 for r in fl if r["wrong"])
            print(f"{meth}: our lines {len(xs)}, really wrong {len(wr)}, flagged {len(fl)}, flagged and wrong {hit} "
                  f"(catches {hit/max(1,len(wr)):.0%} of wrong lines; {hit/max(1,len(fl)):.0%} of flags are right)")


def main():
    cmd = sys.argv[1]
    pages_f = sys.argv[-1]
    pages = [(r["docId"], int(r["pageNr"])) for r in csv.DictReader(open(pages_f), delimiter="\t")]
    if cmd == "fetch": fetch(pages); print("fetched")
    elif cmd == "score": score(pages)
    else:
        model = sys.argv[2]; fn = read_page if cmd == "read" else combined_page
        def safe(p):
            try: fn(model, *p)
            except Exception as ex: print("FAIL", p, str(ex)[:200], flush=True)
        with ThreadPoolExecutor(4) as ex: list(ex.map(safe, pages))
        print(cmd, model, "done", flush=True)


if __name__ == "__main__":
    main()
