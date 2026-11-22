#!/usr/bin/env python3
"""Give an incoming edition the teiHeader shape the live editions have
(respStmts, editionStmt, project publicationStmt, digital + original bibl),
filled from editions/edition-metadata.json.

Usage: site_header.py EDITION.xml [--write]
"""
import json
import re
import sys
import datetime
from html import escape
from pathlib import Path

META = Path(__file__).resolve().parent.parent / 'edition-metadata.json'

DIGITAL = {
    'HebrewBooks': ('Digital scan from HebrewBooks.org', 'HebrewBooks.org',
                    'https://hebrewbooks.org/{}'),
    'NLI': ('Digital scan from National Library of Israel', 'National Library of Israel',
            'https://www.nli.org.il/he/books/{}'),
}


def e(s):
    return escape(s or '', quote=True)


def build(m, fname, old_changes):
    ids = m.get('identifiers', {})
    src = 'NLI' if 'NLI' in ids else 'HebrewBooks' if 'HebrewBooks' in ids else None
    digi = ''
    if src:
        title, pub, url = DIGITAL[src]
        tk = f'<idno type="Transkribus">{e(ids["Transkribus"])}</idno>' if 'Transkribus' in ids else ''
        digi = (f'<bibl type="digital"><title>{title}</title><publisher>{pub}</publisher>'
                f'<ptr target="{url.format(ids[src])}" /><idno type="{src}">{e(ids[src])}</idno>{tk}'
                f'<note>Source for transcription</note></bibl>')
    idnos = ''.join(f'<idno type="{k}">{e(v)}</idno>' for k, v in ids.items())
    idnos += f'<idno type="DBid">{e(m["DBid"])}</idno>' if m.get('DBid') else ''
    idnos += f'<idno type="work">{m["work_number"]}</idno>' if m.get('work_number') else ''
    orig = (f'<bibl type="original"><title type="main" xml:lang="he">{e(m["title_he"])}</title>'
            f'<title type="main" xml:lang="en">{e(m["title_en"])}</title>'
            f'<author><persName xml:lang="he">{e(m["author_he"])}</persName>'
            f'<persName xml:lang="en">{e(m["author_en"])}</persName></author>'
            f'<pubPlace xml:lang="he">{e(m["pub_place_he"])}</pubPlace>'
            f'<pubPlace xml:lang="en">{e(m["pub_place_en"])}</pubPlace>'
            f'<date when="{e(m["date_ce"])}">{e(m["date_he"])}</date>'
            f'<textLang mainLang="{e(m.get("language", "heb"))}" />{idnos}</bibl>')
    digitizer = DIGITAL[src][1] if src else 'unknown'
    today = datetime.date.today().isoformat()
    return f'''<teiHeader>
		<fileDesc>
			<titleStmt>
				<title type="main">{e(m["title_en"])} {e(m["date_ce"])} {e(m["title_he"])}</title>
				<respStmt>
					<resp>Digitization</resp>
					<orgName>{digitizer}</orgName>
				</respStmt>
				<respStmt>
					<resp>Transcription</resp>
					<name>Transkribus</name>
					<note>Transcribed using Transkribus; story divisions marked in Transkribus</note>
				</respStmt>
				<respStmt>
					<resp>Named Entity Tagging</resp>
					<name>DictaBert</name>
					<note>automatic tagging, corrected with Gemini; not yet reviewed by hand</note>
				</respStmt>
			</titleStmt><editionStmt><edition n="1.0.0">Working edition</edition></editionStmt>
			<publicationStmt>
				<p>This edition was created in the framework of the the project "Historical Digital
					Analysis of Hasidic Stories Until 1914", PI: Gadi Sagiv; Supervising
					Editor: Sinai Rusinek. This edition was prepared using an implementation of
					TEI-Publisher Annotator and the XML-Planter, developed by DH-dev.com (Gil
					Shalit).</p>
			</publicationStmt>
			<sourceDesc>{digi}{orig}</sourceDesc>
		</fileDesc>
	<revisionDesc>{old_changes}<change when="{today}">header in the shape of the online editions; page breaks restored from the Transkribus export</change></revisionDesc></teiHeader>'''


def main():
    path = Path(sys.argv[1])
    meta = json.load(open(META, encoding='utf-8'))
    items = meta if isinstance(meta, list) else meta['editions']
    m = next(x for x in items if x['xml_filename'] == path.name)
    xml = path.read_text(encoding='utf-8')
    hdr = re.search(r'<teiHeader\b[^>]*>.*?</teiHeader>', xml, re.S)
    old = re.search(r'<revisionDesc>(.*?)</revisionDesc>', hdr.group(), re.S)
    new = build(m, path.name, old.group(1) if old else '')
    print(new)
    if '--write' in sys.argv:
        path.write_text(xml[:hdr.start()] + new + xml[hdr.end():], encoding='utf-8')
        print('written', path)


if __name__ == '__main__':
    main()
