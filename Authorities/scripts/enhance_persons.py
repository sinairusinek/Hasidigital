#!/usr/bin/env python3
"""
Enhance person authority entries in Authorities2026-01-14.xml:

1. Add Hebrew name variants (abbreviations/titles) to existing persons
2. Add tsadikim IDs to tempH entries identified by RA
3. Add Hebrew names to Tsadik_ entries (from RA data + manual mappings)
4. Add biblical and major rabbinical figures as new person entries
5. Add curated prominent tsadikim as new person entries

Run:
    python3 Authorities/scripts/enhance_persons.py
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
AUTH_XML = REPO / "Authorities" / "Authorities2026-01-14.xml"

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
T = f"{{{TEI_NS}}}"
X = f"{{{XML_NS}}}"

# ── Step 1: Name variant mappings (abbreviations → existing person IDs) ──────

# Map: person xml:id → list of Hebrew name variants to add
NAME_VARIANTS = {
    # Besht (Israel ben Eliezer) — Tsadik_001.001
    "Tsadik_001.001": [
        "ישראל בעל שם טוב",
        "ישראל בן אליעזר",
        "בעש״ט",
        "הבעש״ט",
        'הבעש"ט',
        "הבע״ש",
        "בעהש״ט",
        "הבעש״ט זי״ע",
        "הבעש״ט ז״ל",
    ],
    # Dov Ber of Mezeritch (the Maggid) — need to identify correct Tsadik entry
    # Tsadik_002.001 is Dov Ber (Sadagura dynasty ancestor)
    # But the Maggid of Mezeritch = 001.015 in tsadikim numbering
    # For now, we'll use tempH-105 if it matches, or create the mapping
}

# ── Step 2: Tsadikim IDs to add to tempH entries (from RA's db2zadikim) ──────

# Map: tempH xml:id → tsadikim URL to add
TSADIKIM_IDS = {
    "tempH-39":  "https://tsadikim.uwr.edu.pl/record/012.688",  # אברהם בן נחמן ישראל חזן
    "tempH-78":  "https://tsadikim.uwr.edu.pl/record/128.001",  # אהרן בן שמואל יעקב ראטה
    "tempH-105": "https://tsadikim.uwr.edu.pl/record/027.021",  # דב בר בן שמואל
    "tempH-102": "https://tsadikim.uwr.edu.pl/record/047.009",  # יהודה יחיאל בן פנחס חיים טויב
    "tempH-116": "https://tsadikim.uwr.edu.pl/record/059.001",  # יעקב יצחק בן אשר
    "tempH-126": "https://tsadikim.uwr.edu.pl/record/047.001",  # יצחק אייזיק בן שמואל שמעלקה טויבש
    "tempH-115": "https://tsadikim.uwr.edu.pl/record/005.005",  # מאיר בן אהרן אריה
    "tempH-49":  "https://tsadikim.uwr.edu.pl/record/036.001",  # מרדכי בן דב
    "tempH-50":  "https://tsadikim.uwr.edu.pl/record/037.001",  # משה יהודה ליב בן יעקב
    "tempH-9":   "https://tsadikim.uwr.edu.pl/record/001.022",  # נחמן בן שמחה
    "tempH-106": "https://tsadikim.uwr.edu.pl/record/055.006",  # נפתלי צבי בן מנחם מנדל הורוויץ
    "tempH-107": "https://tsadikim.uwr.edu.pl/record/003.002",  # פינחס בן אברהם אבא שפירא
    "tempH-68":  "https://tsadikim.uwr.edu.pl/record/017.004",  # צבי יהושע בן שמואל שמלקה הורביץ
    "tempH-75":  "https://tsadikim.uwr.edu.pl/record/073.001",  # שמחה בונם בן צבי הירש
}

# ── Step 2b: Hebrew names to add to Tsadik_ entries (for those with duplicates) ──

# For the 5 duplicates: add Hebrew names from the tempH entries to their Tsadik counterparts
TSADIK_HEBREW_NAMES = {
    "Tsadik_005.005": ["מאיר בן אהרן אריה"],           # = tempH-115
    "Tsadik_036.001": ["מרדכי בן דב"],                  # = tempH-49
    "Tsadik_037.001": ["משה יהודה ליב בן יעקב"],        # = tempH-50
    "Tsadik_055.006": ["נפתלי צבי בן מנחם מנדל הורוויץ"], # = tempH-106
    "Tsadik_003.002": ["פינחס בן אברהם אבא שפירא"],     # = tempH-107
    # Key Tsadik entries with known Hebrew equivalents
    "Tsadik_001.001": [],  # handled by NAME_VARIANTS above
}

# ── Step 3: Biblical and rabbinical figures to add ────────────────────────────

BIBLICAL_FIGURES = [
    {
        "id": "Biblical_Moses",
        "names_he": ["משה רבינו", "משה רבנו", "משה"],
        "names_en": ["Moses"],
        "wikidata": "https://www.wikidata.org/wiki/Q9077",
    },
    {
        "id": "Biblical_Abraham",
        "names_he": ["אברהם אבינו", "אברהם"],
        "names_en": ["Abraham"],
        "wikidata": "https://www.wikidata.org/wiki/Q9181",
    },
    {
        "id": "Biblical_Elijah",
        "names_he": ["אליהו הנביא", "אליהו"],
        "names_en": ["Elijah"],
        "wikidata": "https://www.wikidata.org/wiki/Q133507",
    },
    {
        "id": "Biblical_David",
        "names_he": ["דוד המלך", "דוד"],
        "names_en": ["King David", "David"],
        "wikidata": "https://www.wikidata.org/wiki/Q41370",
    },
    {
        "id": "Biblical_Solomon",
        "names_he": ["שלמה המלך", "שלמה"],
        "names_en": ["King Solomon", "Solomon"],
        "wikidata": "https://www.wikidata.org/wiki/Q41386",
    },
    {
        "id": "Biblical_Jacob",
        "names_he": ["יעקב אבינו", "יעקב"],
        "names_en": ["Jacob", "Israel"],
        "wikidata": "https://www.wikidata.org/wiki/Q58078",
    },
    {
        "id": "Biblical_Isaac",
        "names_he": ["יצחק אבינו", "יצחק"],
        "names_en": ["Isaac"],
        "wikidata": "https://www.wikidata.org/wiki/Q178149",
    },
    {
        "id": "Biblical_Joseph",
        "names_he": ["יוסף הצדיק", "יוסף"],
        "names_en": ["Joseph"],
        "wikidata": "https://www.wikidata.org/wiki/Q40662",
    },
    {
        "id": "Biblical_ShimonBarYochai",
        "names_he": ["רשב״י", "שמעון בר יוחאי", "רבי שמעון בר יוחאי"],
        "names_en": ["Shimon bar Yochai", "Rashbi"],
        "wikidata": "https://www.wikidata.org/wiki/Q298684",
    },
    {
        "id": "Rabbinic_Rema",
        "names_he": ["רמ״א", "משה איסרליש", "בעל המפה", "משה בעל המפה"],
        "names_en": ["Moses Isserles", "Rema"],
        "wikidata": "https://www.wikidata.org/wiki/Q1949189",
    },
    {
        "id": "Rabbinic_AriZal",
        "names_he": ["האר״י", "האריז״ל", "יצחק לוריא", "רבי יצחק לוריא"],
        "names_en": ["Isaac Luria", "Ari", "Arizal"],
        "wikidata": "https://www.wikidata.org/wiki/Q318428",
    },
    {
        "id": "Rabbinic_Rambam",
        "names_he": ["רמב״ם", "משה בן מימון"],
        "names_en": ["Maimonides", "Rambam", "Moses ben Maimon"],
        "wikidata": "https://www.wikidata.org/wiki/Q81012",
    },
]


# ── Step 4: Curated prominent tsadikim to add ─────────────────────────────────

PROMINENT_TSADIKIM = [
    {
        "id": "Tsadik_065.001",
        "names_he": [
            "צבי אלימלך שפירא",
            "צבי אלימלך מדינוב",
            "רבי צבי אלימלך מדינוב",
            "בני יששכר",
        ],
        "names_en": ["Tsvi Elimelekh Shapira", "Zvi Elimelech of Dynow"],
        "tsadikim": "https://tsadikim.uwr.edu.pl/record/065.001",
    },
    {
        "id": "Tsadik_043.001",
        "names_he": [
            "יצחק מאיר השיל",
            "יצחק מאיר העשיל",
            "יצחק מאיר מאפטא",
            "רבי יצחק מאיר מאפטא",
        ],
        "names_en": ["Yitzhak Meir Heshel", "Yitzhak Meir of Apt"],
        "tsadikim": "https://tsadikim.uwr.edu.pl/record/043.001",
    },
    {
        "id": "Tsadik_087.001",
        "names_he": [
            "מנחם מנדל מורגנשטרן",
            "מנחם מנדל קוצק",
            "רבי מנחם מנדל קוצק",
            "השרף קוצק",
        ],
        "names_en": ["Menahem Mendel Morgenstern", "Menachem Mendel of Kock"],
        "tsadikim": "https://tsadikim.uwr.edu.pl/record/087.001",
    },
    {
        "id": "Tsadik_092.001",
        "names_he": [
            "חיים הלברשטאם",
            "חיים הלברשטם",
            "חיים מצאנז",
            "רבי חיים מצאנז",
            "דברי חיים",
        ],
        "names_en": ["Hayim Halberstam", "Hayim of Sanz"],
        "tsadikim": "https://tsadikim.uwr.edu.pl/record/092.001",
    },
    {
        "id": "Tsadik_102.001",
        "names_he": [
            "יצחק מאיר אלתר",
            "יצחק מאיר מגור",
            "רבי יצחק מאיר מגור",
            "חידושי הרי״ם",
            "חידושי הרי\"ם",
            "הרי״ם",
            "הרי\"ם",
        ],
        "names_en": ["Yitzhak Meir Alter", "Yitzhak Meir of Ger"],
        "tsadikim": "https://tsadikim.uwr.edu.pl/record/102.001",
    },
    {
        "id": "Tsadik_100.001",
        "names_he": [
            "שרגא פייבל דנציגר",
            "שרגא פייבל מאלכסנדר",
            "רבי שרגא פייבל מאלכסנדר",
        ],
        "names_en": ["Shraga Faivel Danziger", "Shraga Faivel of Alexander"],
        "tsadikim": "https://tsadikim.uwr.edu.pl/record/100.001",
    },
    {
        "id": "Tsadik_086.001",
        "names_he": [
            "ישראל יצחק קאליש",
            "ישראל יצחק מוורקא",
            "ישראל יצחק מווארקא",
            "רבי ישראל יצחק מוורקא",
        ],
        "names_en": ["Israel Yitzhak Kalish", "Israel Yitzhak of Warka"],
        "tsadikim": "https://tsadikim.uwr.edu.pl/record/086.001",
    },
    {
        "id": "Tsadik_066.001",
        "names_he": ["משה טייטלבוים", "רבי משה טייטלבוים מאוהעל", "ישמח משה"],
        "names_en": ["Moshe Teitelbaum", "Moshe of Ujhely"],
        "tsadikim": "https://tsadikim.uwr.edu.pl/record/066.001",
    },
    {
        "id": "Tsadik_058.001",
        "names_he": [
            "יצחק אייזיק אייכנשטיין",
            "יצחק אייזיק אייכנשטין",
            "יצחק אייזיק מזידיטשוב",
            "רבי יצחק אייזיק מזידיטשוב",
        ],
        "names_en": ["Yitzhak Aizyk Eichenstein", "Yitzhak Aizyk of Zhydachiv"],
        "tsadikim": "https://tsadikim.uwr.edu.pl/record/058.001",
    },
    {
        "id": "Tsadik_039.001",
        "names_he": [
            "חיים טירר",
            "חיים מצ׳רנוביץ",
            "רבי חיים מצ׳רנוביץ",
            "באר מים חיים",
        ],
        "names_en": ["Hayim Tirer", "Hayim of Czernowitz"],
        "tsadikim": "https://tsadikim.uwr.edu.pl/record/039.001",
    },
]


def _find_person(root, xml_id):
    """Find a <person> element by xml:id."""
    for person in root.iter(f"{T}person"):
        if person.get(f"{X}id") == xml_id:
            return person
    return None


def _has_name(person, text, lang="he"):
    """Check if person already has a <name> with given text and lang."""
    for nm in person.findall(f"{T}name"):
        if nm.get(f"{X}lang") == lang and (nm.text or "").strip() == text:
            return True
    # Also check <persName>
    for pn in person.findall(f"{T}persName"):
        if pn.get(f"{X}lang") == lang and "".join(pn.itertext()).strip() == text:
            return True
    return False


def _has_idno(person, id_type):
    """Check if person already has an <idno> of given type."""
    for idno in person.findall(f"{T}idno"):
        if idno.get("type") == id_type:
            return True
    return False


def _add_name(person, text, lang="he"):
    """Add a <name xml:lang=lang> element to person."""
    name_el = ET.SubElement(person, f"{T}name")
    name_el.set(f"{X}lang", lang)
    name_el.text = text
    name_el.tail = "\n                              "


def _add_idno(person, id_type, value):
    """Add an <idno type=type> element to person."""
    idno_el = ET.SubElement(person, f"{T}idno")
    idno_el.set("type", id_type)
    idno_el.text = value
    idno_el.tail = "\n                              "


def _create_person_element(fig):
    """Create a new <person> element from a figure dict."""
    person = ET.Element(f"{T}person")
    person.set(f"{X}id", fig["id"])
    person.text = "\n                                    "
    person.tail = "\n                              "

    for he_name in fig["names_he"]:
        nm = ET.SubElement(person, f"{T}name")
        nm.set(f"{X}lang", "he")
        nm.text = he_name
        nm.tail = "\n                                    "

    for en_name in fig["names_en"]:
        nm = ET.SubElement(person, f"{T}name")
        nm.set(f"{X}lang", "en")
        nm.text = en_name
        nm.tail = "\n                                    "

    if fig.get("wikidata"):
        idno = ET.SubElement(person, f"{T}idno")
        idno.set("type", "Wikidata")
        idno.text = fig["wikidata"]
        idno.tail = "\n                              "

    if fig.get("tsadikim"):
        idno = ET.SubElement(person, f"{T}idno")
        idno.set("type", "tsadikim")
        idno.text = fig["tsadikim"]
        idno.tail = "\n                              "

    return person


def enhance(xml_path=AUTH_XML):
    ET.register_namespace("", TEI_NS)
    ET.register_namespace("xml", XML_NS)
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    stats = {"variants_added": 0, "tsadikim_ids_added": 0,
             "hebrew_names_added": 0, "persons_created": 0,
             "prominent_created": 0, "prominent_names_added": 0,
             "prominent_ids_added": 0,
             "skipped": 0}

    # ── Step 1: Add name variants ──
    print("Step 1: Adding name variants...")
    for xml_id, variants in NAME_VARIANTS.items():
        person = _find_person(root, xml_id)
        if person is None:
            print(f"  WARNING: {xml_id} not found in XML")
            continue
        for variant in variants:
            if not _has_name(person, variant, "he"):
                _add_name(person, variant, "he")
                stats["variants_added"] += 1
                print(f"  + {xml_id}: {variant}")
            else:
                stats["skipped"] += 1

    # ── Step 2: Add tsadikim IDs to tempH entries ──
    print("\nStep 2: Adding tsadikim IDs to tempH entries...")
    for xml_id, url in TSADIKIM_IDS.items():
        person = _find_person(root, xml_id)
        if person is None:
            print(f"  WARNING: {xml_id} not found in XML")
            continue
        if not _has_idno(person, "tsadikim"):
            _add_idno(person, "tsadikim", url)
            stats["tsadikim_ids_added"] += 1
            print(f"  + {xml_id}: {url}")
        else:
            print(f"  SKIP {xml_id}: already has tsadikim idno")
            stats["skipped"] += 1

    # ── Step 2b: Add Hebrew names to Tsadik entries ──
    print("\nStep 2b: Adding Hebrew names to Tsadik entries...")
    for xml_id, he_names in TSADIK_HEBREW_NAMES.items():
        person = _find_person(root, xml_id)
        if person is None:
            print(f"  WARNING: {xml_id} not found in XML")
            continue
        for he_name in he_names:
            if not _has_name(person, he_name, "he"):
                _add_name(person, he_name, "he")
                stats["hebrew_names_added"] += 1
                print(f"  + {xml_id}: {he_name}")
            else:
                stats["skipped"] += 1

    # ── Step 3: Add biblical/rabbinical figures ──
    print("\nStep 3: Adding biblical and rabbinical figures...")
    # Find the <listPerson type="contents"> to append to
    list_person = None
    for lp in root.iter(f"{T}listPerson"):
        if lp.get("type") == "contents":
            list_person = lp
            break

    if list_person is None:
        print("  ERROR: No <listPerson type='contents'> found!")
        return

    for fig in BIBLICAL_FIGURES:
        existing = _find_person(root, fig["id"])
        if existing is not None:
            print(f"  SKIP {fig['id']}: already exists")
            stats["skipped"] += 1
            continue

        person_el = _create_person_element(fig)
        list_person.append(person_el)
        stats["persons_created"] += 1
        print(f"  + {fig['id']}: {fig['names_he'][0]} / {fig['names_en'][0]}")

    # ── Step 4: Add curated prominent tsadikim ──
    print("\nStep 4: Adding curated prominent tsadikim...")
    for fig in PROMINENT_TSADIKIM:
        existing = _find_person(root, fig["id"])
        if existing is not None:
            changed = 0
            for he_name in fig.get("names_he", []):
                if not _has_name(existing, he_name, "he"):
                    _add_name(existing, he_name, "he")
                    stats["prominent_names_added"] += 1
                    changed += 1
            for en_name in fig.get("names_en", []):
                if not _has_name(existing, en_name, "en"):
                    _add_name(existing, en_name, "en")
                    stats["prominent_names_added"] += 1
                    changed += 1
            tsadikim_url = fig.get("tsadikim")
            if tsadikim_url and not _has_idno(existing, "tsadikim"):
                _add_idno(existing, "tsadikim", tsadikim_url)
                stats["prominent_ids_added"] += 1
                changed += 1
            if changed:
                print(f"  ~ {fig['id']}: synced {changed} missing fields")
            else:
                print(f"  SKIP {fig['id']}: already exists")
                stats["skipped"] += 1
            continue

        person_el = _create_person_element(fig)
        list_person.append(person_el)
        stats["prominent_created"] += 1
        print(f"  + {fig['id']}: {fig['names_he'][0]} / {fig['names_en'][0]}")

    # ── Write output ──
    tree.write(str(xml_path), encoding="unicode", xml_declaration=True)

    print(f"\n{'='*60}")
    print(f"Enhancement complete:")
    print(f"  Name variants added:     {stats['variants_added']}")
    print(f"  Tsadikim IDs added:      {stats['tsadikim_ids_added']}")
    print(f"  Hebrew names added:      {stats['hebrew_names_added']}")
    print(f"  New persons created:     {stats['persons_created']}")
    print(f"  Prominent tsadikim add:  {stats['prominent_created']}")
    print(f"  Prominent names synced:  {stats['prominent_names_added']}")
    print(f"  Prominent ids synced:    {stats['prominent_ids_added']}")
    print(f"  Skipped (already exist): {stats['skipped']}")
    print(f"Written to: {xml_path}")


if __name__ == "__main__":
    enhance()
