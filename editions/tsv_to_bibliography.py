#!/usr/bin/env python3
"""
Convert Hasidic editions TSV to a TEI XML bibliography.

Input:  ../Hasidic-editions-status - hasidic editions.tsv
Output: bibliography.xml (in this directory)
Lookups: ../Authorities/authorities-matching-db.json  (Kima → H-LOC)

Structure:
  TEI/text/body/listBibl
    listBibl @xml:id="W-N"  (one per work, grouped by "Final Edition Title for the DB")
      biblStruct @xml:id="ed-{DBid}"  (one per edition)

Run: python3 editions/tsv_to_bibliography.py
"""

import csv
import json
import re
import unicodedata
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.dom import minidom

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO = Path(__file__).parent.parent
TSV_PATH    = REPO / "Hasidic-editions-status - hasidic editions.tsv"
MATCH_DB    = REPO / "Authorities" / "authorities-matching-db.json"
OUT_XML     = Path(__file__).parent / "bibliography.xml"

TEI_NS  = "http://www.tei-c.org/ns/1.0"
XML_NS  = "http://www.w3.org/XML/1998/namespace"
XLINK_NS = "http://www.w3.org/1999/xlink"

ET.register_namespace("",      TEI_NS)
ET.register_namespace("xml",   XML_NS)

# ── Helpers ────────────────────────────────────────────────────────────────────

def tei(tag):
    return f"{{{TEI_NS}}}{tag}"

def xml_attr(name):
    return f"{{{XML_NS}}}{name}"

HEBREW_RE = re.compile(r'[\u0590-\u05FF\uFB1D-\uFB4F]')

def is_hebrew(s):
    return bool(HEBREW_RE.search(s))

def parse_pub_place(raw):
    """Split 'קאפוסט,Kopys' into (hebrew_part, latin_part) or (None, raw)."""
    if not raw.strip():
        return None, None
    parts = [p.strip() for p in raw.split(',') if p.strip()]
    hebrew = [p for p in parts if is_hebrew(p)]
    latin  = [p for p in parts if not is_hebrew(p)]
    return (hebrew[0] if hebrew else None,
            latin[0]  if latin  else None)

def clean_kima_id(val):
    """Return a clean numeric Kima ID string or None."""
    v = val.strip()
    if not v or v.upper() in ('TBD', 'NULL', ''):
        return None
    # Remove question marks and non-digit/non-number junk
    clean = re.sub(r'[^\d]', '', v)
    return clean if clean else None

LANG_MAP = {
    'heb': 'he',
    'yid': 'yi',
    'jrb': 'jrb',   # Judeo-Arabic — no ISO 639-1, keep 3-letter
}

def norm_lang(raw):
    v = raw.strip()
    if not v:
        return None
    # Handle "כנראה בheb" / "כנראה heb"
    m = re.search(r'\b(heb|yid|jrb)\b', v)
    if m:
        code = m.group(1)
    else:
        code = v.lower()
    return LANG_MAP.get(code, code)

def build_kima_hloc_map(match_db):
    """Return {kima_number_str: 'H-LOC_N'} from the matching DB."""
    out = {}
    for p in match_db.get('places', []):
        kima_url = p.get('identifiers', {}).get('Kima', '')
        if kima_url:
            num = kima_url.rstrip('/').split('/')[-1]
            out[num] = p['id']
    return out

def sub(parent, tag, text=None, attrib=None):
    """Create a subelement, optionally with text and attributes."""
    attrib = attrib or {}
    el = ET.SubElement(parent, tei(tag), attrib)
    if text is not None:
        el.text = str(text).strip()
    return el

def add_if(parent, tag, value, attrib=None):
    """Add subelement only when value is non-empty."""
    v = (value or '').strip()
    if v and v.upper() not in ('TBD', 'NULL', 'NA', '()'):
        sub(parent, tag, v, attrib)

# ── Build biblStruct for one edition row ──────────────────────────────────────

_noid_counter = [0]  # mutable for use inside function

def build_bibl_struct(row, kima_hloc):
    dbid = row['DBid'].strip()
    if dbid:
        # Sanitise: "3572|3573" → "3572-3573"
        safe_dbid = re.sub(r'[^\w-]', '-', dbid)
        xml_id = f"ed-{safe_dbid}"
    else:
        _noid_counter[0] += 1
        xml_id = f"ed-noid-{_noid_counter[0]}"

    struct = ET.Element(tei('biblStruct'), {
        xml_attr('id'): xml_id,
    })
    if row.get('edition', '').strip():
        struct.set('n', row['edition'].strip())

    monogr = sub(struct, 'monogr')

    # Titles
    title_he = (row.get('Final Edition Title for the DB') or '').strip()
    title_en = (row.get('title-eng-Y') or '').strip()
    kitsis_title = (row.get('KitsisTitle') or '').strip()
    subtitle = (row.get('fabio:hasSubtitle(2)') or '').strip()

    if title_he:
        sub(monogr, 'title', title_he, {xml_attr('lang'): 'he', 'type': 'main'})
    if title_en:
        sub(monogr, 'title', title_en, {xml_attr('lang'): 'en', 'type': 'main'})
    if kitsis_title and kitsis_title not in (title_he, title_en):
        sub(monogr, 'title', kitsis_title, {'type': 'alt'})
    if subtitle:
        sub(monogr, 'title', subtitle, {'type': 'sub'})

    # Author
    author_he  = (row.get('Author-heb-Y') or '').strip()
    author_en  = (row.get('Author-eng-Y') or '').strip()
    entity_id  = (row.get('AuthorEntityID') or '').strip()
    person_kitsis = (row.get('PersonKitsis') or '').strip()

    if author_he or author_en or entity_id:
        author_el = sub(monogr, 'author')
        if author_he:
            sub(author_el, 'name', author_he, {xml_attr('lang'): 'he'})
        if author_en:
            sub(author_el, 'name', author_en, {xml_attr('lang'): 'en'})
        if not author_he and not author_en and person_kitsis:
            sub(author_el, 'name', person_kitsis)
        if entity_id:
            sub(author_el, 'idno', entity_id, {'type': 'AuthorEntity'})

    # Editor
    editor = (row.get('Editor') or '').strip()
    if editor and editor.upper() not in ('TBD', 'NA', 'NULL'):
        sub(monogr, 'editor', editor)

    # Printer as respStmt
    printer  = (row.get('dijest:printer') or '').strip()
    printer2 = (row.get('dijest:printer(2)') or '').strip()
    used_printer = printer or printer2
    if used_printer and used_printer.upper() not in ('TBD', 'NULL', 'NA'):
        resp_el = sub(monogr, 'respStmt')
        sub(resp_el, 'resp', 'printer')
        sub(resp_el, 'name', used_printer)

    # Imprint
    imprint = sub(monogr, 'imprint')

    # Publication place
    # Note: 'BHBpublicationDate' column is misnamed — it actually contains place names.
    # 'KitsispubPlace' is nearly empty; the real place data is in BHBpublicationDate.
    pub_place_raw = (row.get('BHBpublicationDate') or '').strip()
    if not pub_place_raw:
        pub_place_raw = (row.get('KitsispubPlace') or row.get('מקום הדפסה (כששונה מהוצאה)') or '').strip()

    kima_raw = (row.get('dijest:kimaID') or '').strip()
    kima_id  = clean_kima_id(kima_raw)
    # Fallback to (2) column
    if not kima_id:
        kima_id = clean_kima_id(row.get('dijest:kimaID(2)') or '')

    hloc_ref = kima_hloc.get(kima_id) if kima_id else None

    if pub_place_raw:
        he_place, lat_place = parse_pub_place(pub_place_raw)
        pp_attrib = {}
        if hloc_ref:
            pp_attrib['ref'] = f'#{hloc_ref}'
        if he_place:
            sub(imprint, 'pubPlace', he_place, {**pp_attrib, xml_attr('lang'): 'he'})
        if lat_place and lat_place != he_place:
            sub(imprint, 'pubPlace', lat_place, {**pp_attrib, xml_attr('lang'): 'en'})
        if not he_place and not lat_place and pub_place_raw:
            sub(imprint, 'pubPlace', pub_place_raw, pp_attrib)

    # Publisher
    publisher  = (row.get('dcterms:publisher') or '').strip()
    publisher2 = (row.get('dcterms:publisher(2)') or '').strip()
    used_pub = publisher or publisher2
    if used_pub and used_pub.upper() not in ('TBD', 'NULL', 'NA'):
        sub(imprint, 'publisher', used_pub)

    # Date  — use BHB-date (Gregorian year) as @when; Hebrew date as text
    # Note: BHBpublicationDate column actually contains place data (mislabeled).
    greg_year  = (row.get('BHB-date') or '').strip()
    heb_date   = (row.get('BHBHebrewDate') or row.get('Kitsisdate') or '').strip()
    date_attrib = {}
    if greg_year and re.match(r'^\d{4}$', greg_year):
        date_attrib['when'] = greg_year
    date_text = heb_date or greg_year
    if date_attrib or date_text:
        sub(imprint, 'date', date_text or None, date_attrib or None)

    # Extent
    pages = (row.get('Number of Pages') or '').strip()
    if pages and pages not in ('NULL', ''):
        sub(monogr, 'extent', f'{pages} עמ\'')

    # Format
    fmt = (row.get('Format (2/4/8)') or '').strip()
    if fmt:
        sub(monogr, 'biblScope', fmt, {'unit': 'format'})

    # Language
    lang_code = norm_lang(row.get('Language') or row.get('dcterms:lanugage') or '')
    if lang_code:
        sub(monogr, 'textLang', None, {'mainLang': lang_code})

    # Identifiers inside monogr
    add_if(monogr, 'idno', row.get('Bibliography of the Hebrew Book'), {'type': 'BHB'})
    add_if(monogr, 'idno', row.get('ALMA ID'), {'type': 'ALMA'})
    if kima_id:
        sub(monogr, 'idno', kima_id, {'type': 'Kima'})
    add_if(monogr, 'idno', dbid, {'type': 'DBid'})
    add_if(monogr, 'idno', row.get('KitsisID'), {'type': 'Kitsis'})

    # External links as <ref> on biblStruct
    nli_link    = (row.get('download link') or '').strip()
    hb_link     = (row.get('HebrewBooksLink') or '').strip()
    otzar_link  = (row.get('OtzarHachochmaLink') or '').strip()

    if nli_link:
        sub(struct, 'ref', None, {'type': 'NLI', 'target': nli_link})
    if hb_link:
        sub(struct, 'ref', None, {'type': 'HebrewBooks', 'target': hb_link})
    if otzar_link:
        sub(struct, 'ref', None, {'type': 'OtzarHachochma', 'target': otzar_link})

    # Notes
    description = (row.get('Kitzisdescription') or '').strip()
    if description:
        sub(struct, 'note', description, {'type': 'description'})

    haskama = (row.get('dijest:Haskama(2)') or '').strip()
    if haskama and haskama.upper() not in ('TBD', 'NULL'):
        sub(struct, 'note', haskama, {'type': 'haskama'})

    general_note = (row.get('bf:note(2)') or '').strip()
    if general_note and general_note.upper() not in ('TBD', 'NULL'):
        sub(struct, 'note', general_note, {'type': 'general'})

    accuracy = (row.get('accuracy') or '').strip()
    if accuracy:
        sub(struct, 'note', accuracy, {'type': 'dateAccuracy'})

    genre = (row.get('Kitsis Genre and tradition') or '').strip()
    if genre:
        sub(struct, 'note', genre, {'type': 'genre'})

    n_stories = (row.get('Number of Stories') or row.get('Nu. מספר.') or '').strip()
    if n_stories and n_stories not in ('NULL', ''):
        sub(struct, 'note', n_stories, {'type': 'storyCount'})

    return struct


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    # Load data
    with open(TSV_PATH, encoding='utf-8') as f:
        rows = list(csv.DictReader(f, delimiter='\t'))

    with open(MATCH_DB, encoding='utf-8') as f:
        db = json.load(f)

    kima_hloc = build_kima_hloc_map(db)

    # Group editions by work (preserving order of first appearance)
    title_col = 'Final Edition Title for the DB'
    works = {}   # title_he → [row, ...]
    work_order = []
    for row in rows:
        t = row[title_col].strip()
        if t not in works:
            works[t] = []
            work_order.append(t)
        works[t].append(row)

    # Build TEI tree
    root = ET.Element(tei('TEI'))

    # teiHeader
    header = sub(root, 'teiHeader')
    file_desc = sub(header, 'fileDesc')
    title_stmt = sub(file_desc, 'titleStmt')
    sub(title_stmt, 'title', 'Bibliography of Hasidic Story Editions')
    pub_stmt = sub(file_desc, 'publicationStmt')
    sub(pub_stmt, 'p',
        'Generated automatically from Hasidic-editions-status - hasidic editions.tsv '
        'as part of the project "Historical Digital Analysis of Hasidic Stories Until 1914".')
    source_desc = sub(file_desc, 'sourceDesc')
    sub(source_desc, 'p', f'Converted from {TSV_PATH.name}. '
        f'{len(rows)} editions, {len(work_order)} distinct works.')

    # text / body
    text_el = sub(root, 'text')
    body    = sub(text_el, 'body')

    outer_list = ET.SubElement(body, tei('listBibl'), {
        xml_attr('id'): 'hasidic-editions-bibliography',
    })
    sub(outer_list, 'head', 'Bibliography of Hasidic Story Editions')

    # One inner listBibl per work
    for w_idx, work_title in enumerate(work_order, start=1):
        work_rows = works[work_title]
        w_id = f'W-{w_idx}'

        work_list = ET.SubElement(outer_list, tei('listBibl'), {
            xml_attr('id'): w_id,
        })
        if work_title:
            sub(work_list, 'head', work_title, {xml_attr('lang'): 'he'})

        # English work title from first row that has one
        eng_titles = [r.get('title-eng-Y', '').strip() for r in work_rows
                      if r.get('title-eng-Y', '').strip()]
        if eng_titles:
            sub(work_list, 'head', eng_titles[0], {xml_attr('lang'): 'en'})

        for row in work_rows:
            struct = build_bibl_struct(row, kima_hloc)
            work_list.append(struct)

    # ── Serialise with pretty-printing ────────────────────────────────────────
    raw = ET.tostring(root, encoding='unicode', xml_declaration=False)
    dom = minidom.parseString(f'<?xml version="1.0" encoding="UTF-8"?>\n{raw}')
    pretty = dom.toprettyxml(indent='  ', encoding=None)
    # minidom adds its own xml declaration; strip the duplicate
    lines = pretty.split('\n')
    if lines[0].startswith('<?xml'):
        lines = lines[1:]
    result = '<?xml version="1.0" encoding="UTF-8"?>\n' + '\n'.join(lines)

    OUT_XML.write_text(result, encoding='utf-8')
    print(f'Written: {OUT_XML}')
    print(f'  {len(rows)} editions in {len(work_order)} works')

    # ── Quick integrity report ─────────────────────────────────────────────────
    print('\n── Integrity report ──────────────────────────────────────────────')

    no_dbid     = [r for r in rows if not r['DBid'].strip()]
    no_title    = [r for r in rows if not r[title_col].strip()]
    no_date     = [r for r in rows if not r['BHB-date'].strip() and not r['Kitsisdate'].strip()]
    no_place    = [r for r in rows if not (r.get('BHBpublicationDate') or r.get('KitsispubPlace') or '').strip()]
    no_lang     = [r for r in rows if not norm_lang(r.get('Language', ''))]
    no_bhb      = [r for r in rows if not r['Bibliography of the Hebrew Book'].strip()]
    no_kima     = [r for r in rows if not clean_kima_id(r.get('dijest:kimaID', ''))]

    # Place linking stats
    linkable = [r for r in rows if clean_kima_id(r.get('dijest:kimaID', ''))]
    linked   = [r for r in linkable if kima_hloc.get(clean_kima_id(r['dijest:kimaID']))]

    lang_vals = {}
    for r in rows:
        lv = (r.get('Language') or '').strip()
        lang_vals[lv] = lang_vals.get(lv, 0) + 1

    print(f'  Total rows:           {len(rows)}')
    print(f'  Missing DBid:         {len(no_dbid)}')
    print(f'  Missing work title:   {len(no_title)}')
    print(f'  Missing date:         {len(no_date)}')
    print(f'  Missing pub place:    {len(no_place)}')
    print(f'  Missing language:     {len(no_lang)}')
    print(f'  Missing BHB ID:       {len(no_bhb)}')
    print(f'  Missing Kima ID:      {len(no_kima)}')
    print(f'  pubPlace linked to H-LOC: {len(linked)}/{len(linkable)} '
          f'({100*len(linked)//len(linkable) if linkable else 0}%)')
    print(f'  Language raw values:  {dict(sorted(lang_vals.items()))}')

    if no_dbid:
        print(f'\n  Rows with no DBid (title | date):')
        for r in no_dbid:
            print(f'    "{r[title_col]}" | {r["BHB-date"]}')

    unlinked_kimas = set()
    for r in rows:
        kid = clean_kima_id(r.get('dijest:kimaID', ''))
        if kid and kid not in kima_hloc:
            unlinked_kimas.add(kid)
    if unlinked_kimas:
        print(f'\n  Kima IDs in TSV not found in authority DB ({len(unlinked_kimas)}):')
        for k in sorted(unlinked_kimas, key=lambda x: int(x)):
            print(f'    {k}')


if __name__ == '__main__':
    main()
