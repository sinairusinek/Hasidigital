"""Correct region tags with a vision model: Claude through `claude -p` on the Max plan (never the API), or Gemini.

Two steps per book, with no ground truth:
1. book note: the model looks at a few clean pages of the book and writes down its habits (what the running head
   says and where the page number sits, how headings and footnotes are set, whether there is a catch-word);
2. per page: the page with our boxes numbered on it, the current tags and the book note → corrected tags.
Boxes are kept as they are; only tags change ("none" drops a box that holds no text).

    python vlm_relabel.py SUFFIX PAGES.tsv [--model opus|gemini-…]   → .<SUFFIX>+vlm-<model>.xml next to each page's XML
PAGES.tsv needs docId and pageNr columns. Answers are cached in ~/Documents/Hasidigital-data/vlm/.
"""
import csv, json, os, re, subprocess, sys, collections
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import cv2
from layout_qa import read_layout

HERE = Path(__file__).parent
DATA = Path.home() / "Documents/Hasidigital-data"
IMG = DATA / "layout-test"
CACHE = DATA / "vlm"; (CACHE / "img").mkdir(parents=True, exist_ok=True)
CLAUDE = os.environ.get("CLAUDE_CLI_BIN", str(sorted(Path.home().glob(".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude"))[-1]))
TAGS = ["main-text", "heading", "running-head", "page-number", "catch-word", "footnote", "none"]

DEFS = """Region tags (Hebrew books, printed right to left):
- running-head: the title line at the very top of the page, repeated from page to page (book title, section or tsaddik's name).
- page-number: the page number at the top (Hebrew letters such as יב, or digits), usually in a corner; sometimes at the bottom.
- catch-word: a single word alone under the last line of the page, repeating the first word of the next page.
- heading: the title of a story, chapter or section, standing on its own line(s), often centred or in larger type.
  NOT a heading: large or bold opening words that begin a paragraph and run on in the same line.
- footnote: notes or commentary set in smaller type than the main text, usually at the bottom, often under a printed rule.
- main-text: the running text.
- none: no text at all (stamp, stain, ornament, library mark, the edge of the neighbouring page)."""


def ask(prompt, images, model):
    """Claude via `claude -p` (Max plan), or Gemini via the google-genai SDK when the model name starts with 'gemini'."""
    if model.startswith("gemini"):
        from google import genai
        from google.genai import types
        client = genai.Client()
        parts = [types.Part.from_bytes(data=Path(f).read_bytes(), mime_type="image/jpeg") for f in images]
        for _ in range(3):
            try: return client.models.generate_content(model=model, contents=parts + [prompt.replace("Read the image. ", "").replace("Read the images, then", "Then")]).text
            except Exception as ex: err = ex
        raise RuntimeError(str(err)[:300])
    cmd = [CLAUDE, "-p", "--model", model, "--allowedTools", "Read", "--output-format", "text"]
    for _ in range(3):
        r = subprocess.run(cmd, input=prompt + "\n\nImages:\n" + "\n".join(map(str, images)), capture_output=True, text=True, timeout=600)
        if r.returncode == 0: return r.stdout
    raise RuntimeError(r.stderr[:300])


def numbered(doc, n, regs):
    """Page image with each box outlined and numbered; long side 1800 px."""
    im = cv2.imread(str(IMG / doc / f"{n:04d}.jpg")); s = 1800 / max(im.shape[:2]); im = cv2.resize(im, None, fx=s, fy=s)
    for i, r in enumerate(regs, 1):
        x0, y0, x1, y1 = [int(v * s) for v in r["box"]]
        cv2.rectangle(im, (x0, y0), (x1, y1), (0, 0, 230), 3)
        cv2.rectangle(im, (x0, y0), (x0 + 46, y0 + 34), (0, 0, 230), -1)
        cv2.putText(im, str(i), (x0 + 4, y0 + 27), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    f = CACHE / "img" / f"{doc}_{n:04d}.jpg"; cv2.imwrite(str(f), im, [cv2.IMWRITE_JPEG_QUALITY, 85]); return f


def book_note(doc, pages, model):
    f = CACHE / f"note-{doc}-{model}.txt"
    if f.exists(): return f.read_text()
    imgs = [IMG / doc / f"{n:04d}.jpg" for n in pages[:3]]
    note = ask(f"""These are pages from one printed Hebrew book. Read the images, then describe this book's page layout
habits in at most 120 words, as notes for someone tagging its regions: what the running head says and where it is, where the
page number is and how it is written, whether pages end with a catch-word, how story or section headings look, whether there
are footnotes and how they look, and anything else unusual (columns, large opening words, rules). Facts only, no preamble.

{DEFS}""", imgs, model).strip()
    f.write_text(note); return note


def relabel(doc, n, suffix, note, model):
    f = CACHE / f"{doc}_{n:04d}-{suffix}-{model}.json"
    src = HERE / "xml" / doc / f"{n:04d}.{suffix}.xml"
    regs, W, H = read_layout(src)
    if not f.exists():
        boxes = "\n".join(f"{i}: now '{r['lab']}', box {100*r['box'][0]/W:.0f}-{100*r['box'][2]/W:.0f}% across, "
                          f"{100*r['box'][1]/H:.0f}-{100*r['box'][3]/H:.0f}% down, {len(r['lines'])} lines" for i, r in enumerate(regs, 1))
        out = ask(f"""Read the image. It is a page of a printed Hebrew book with numbered red boxes drawn by an automatic layout tool.
Each box has a tag, often wrong. Give the right tag for every box.

{DEFS}

What we know about this book:
{note}

Boxes:
{boxes}

If a box holds more than one kind of text, give the tag of most of its text. Answer with JSON only, e.g. {{"1": "main-text", "2": "heading"}}.""",
                     [numbered(doc, n, regs)], model)
        m = re.search(r"\{.*\}", out, re.S); f.write_text(m.group(0) if m else "{}")
    new = json.loads(f.read_text())
    # write the same XML with the tags changed; region order matches read_layout's
    x = src.read_text(); ids = [m.group(1) for m in re.finditer(r'<TextRegion id="([^"]+)"[^>]*>\s*<Coords points="[^"]+"', x)]
    changed = 0
    for i, rid in enumerate(ids, 1):
        t = new.get(str(i))
        if t not in TAGS or t == regs[i - 1]["lab"]: continue
        changed += 1
        if t == "none":
            x = re.sub(rf'<TextRegion id="{rid}".*?</TextRegion>\n?', "", x, flags=re.S)
        else:
            x = re.sub(rf'(<TextRegion id="{rid}" custom="structure {{type:)[\w-]+', rf"\g<1>{t}", x)
    (src.parent / f"{n:04d}.{suffix}+vlm-{model}.xml").write_text(x)
    return changed


def main():
    suffix, pages_f = sys.argv[1], sys.argv[2]
    model = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "opus"
    pages = [(r["docId"], int(r["pageNr"])) for r in csv.DictReader(open(pages_f), delimiter="\t")]
    by = collections.defaultdict(list)
    for d, n in pages: by[d].append(n)
    with ThreadPoolExecutor(4) as ex:
        book = collections.defaultdict(list)  # the note comes from the book's own test pages, not only the ones relabelled
        for r in csv.DictReader(open(HERE / "test-set.tsv"), delimiter="\t"): book[r["docId"]].append(int(r["pageNr"]))
        notes = dict(zip(by, ex.map(lambda d: book_note(d, sorted(book[d] or by[d]), model), by)))
        ch = list(ex.map(lambda p: relabel(p[0], p[1], suffix, notes[p[0]], model), pages))
    print(f"{len(pages)} pages, {sum(ch)} tags changed")


if __name__ == "__main__":
    main()
