"""Run the topic tagger (tagger.py) on every division of one edition (PIPELINE.md step 12).

Usage: python3 editions/llm-tagging/tag_edition.py EDITION.xml [--max-chars 30000] [--non-story-only] [--only DIV_ID ...]

One `claude -p` call per division (Max plan, Opus 5.5, as in the calibration). Results are
cached as JSON in editions/llm-tagging/runs/{slug}/{division}.json, so a run can be resumed
and the verbatim quotes are kept (standoff). Divisions longer than --max-chars are not sent
(listed as skipped): e.g. Torat-Haramal's 32-page Torah commentary.
Then write the tags into the XML with writeback.py.
"""
import json
import sys
import time
from pathlib import Path

from lxml import etree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tagger import tag_unit, clean_text  # noqa: E402

T = '{http://www.tei-c.org/ns/1.0}'
XID = '{http://www.w3.org/XML/1998/namespace}id'
SKIP = {T + 'fw'}  # running heads, page numbers, catchwords


def div_text(d):
    out = []

    def walk(el):
        if el.tag in SKIP or (el.tag == T + 'head' and el.get('type') == 'storyHead') or \
           (el is not d and el.tag == T + 'div' and el.get('type') == 'story') or \
           (el.tag == T + 'span' and (''.join(el.itertext()).strip() in ('תיוגים', 'תיוגים*'))):
            if el.tail:
                out.append(el.tail)
            return
        if el.text:
            out.append(el.text)
        for c in el:
            walk(c)
        if el.tail and el is not d:
            out.append(el.tail)
    walk(d)
    return clean_text(''.join(out))


def divisions(root):
    """Top-level text divisions in reading order, with a stable id."""
    txt = root.find(T + 'text')
    # a story div nested in a paratext div (split_embedded_story.py) is its own division;
    # the paratext's text then excludes it (div_text)
    divs = [d for d in txt.iter(T + 'div')
            if (d.get('type') == 'story' and not any(a.get('type') == 'story' for a in d.iterancestors(T + 'div')))
            or (d.get('type') in ('non-story', 'front-matter', 'unclear')
                and not any(a.get('type') in ('story', 'non-story') for a in d.iterancestors(T + 'div')))]
    out, i = [], 0
    for d in divs:
        nested = any(a.tag == T + 'div' for a in d.iterancestors()) and d.get('type') == 'story' and \
            any(a.get('type') in ('non-story', 'front-matter', 'unclear') for a in d.iterancestors(T + 'div'))
        if not nested:  # nested stories don't shift the fallback ids (= run cache names) of the rest
            i += 1
        did = d.get(XID) or f"{d.get('type')}-{i:03d}"
        out.append((did, d))
    return out


def main():
    path = Path(sys.argv[1])
    max_chars = int(sys.argv[sys.argv.index('--max-chars') + 1]) if '--max-chars' in sys.argv else 30000
    only = set(sys.argv[sys.argv.index('--only') + 1:]) if '--only' in sys.argv else None
    slug = path.stem
    root = etree.parse(str(path)).getroot()
    edition = root.findtext(f'.//{T}titleStmt/{T}title[@type="main"]') or slug
    runs = HERE / 'runs' / slug
    runs.mkdir(parents=True, exist_ok=True)
    divs = divisions(root)
    texts = [div_text(d) for _, d in divs]
    t0, done, skipped = time.time(), 0, []
    for i, (did, d) in enumerate(divs):
        if only and did not in only:
            continue
        if '--non-story-only' in sys.argv and d.get('type') == 'story':
            continue  # curated editions: look only for stories hidden in paratext
        f = runs / f'{did}.json'
        if f.exists():
            continue
        text = texts[i]
        if len(text) > max_chars:
            skipped.append((did, d.get('type'), len(text)))
            continue
        if not text.strip():
            continue
        label = d.get('type') + (f" ({d.get('ana')})" if d.get('ana') else '')
        unit = {'id': did, 'edition': edition, 'label': label, 'text': text,
                'prev_tail': texts[i - 1][-200:] if i else '', 'next_head': texts[i + 1][:200] if i + 1 < len(texts) else ''}
        t1 = time.time()
        res = tag_unit(unit)
        res['chars'] = len(text)
        res['seconds'] = round(time.time() - t1)
        f.write_text(json.dumps(res, ensure_ascii=False, indent=1))
        done += 1
        print(f"{did}: {res['unit']['kind']}, {len(res.get('stories', []))} stories, "
              f"{sum(len(s['tags']) for s in res.get('stories', []))} tags, {res['seconds']} s", flush=True)
    (runs / 'skipped.json').write_text(json.dumps(skipped, ensure_ascii=False))
    print(f'{done} divisions tagged in {round(time.time() - t0)} s; skipped (too long): {skipped}')


if __name__ == '__main__':
    main()
