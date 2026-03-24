#!/usr/bin/env python3
"""Match XML edition files in editions/incoming/ to bibliography rows in the TSV.

Matching strategy (in priority order):
1. dedupmrg ID in XML sourceDesc ↔ 'downloaded filename' column in TSV
2. HebrewBooks ID in XML ↔ HebrewBooksLink column in TSV
3. Manual mapping table for remaining editions

Output: a TSV report with columns:
  xml_filename | work_number | DBid | eng_title | heb_title | date | match_method | notes
"""

from __future__ import annotations
import csv
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INCOMING = REPO / "editions" / "incoming"
TSV_PATH = REPO / "Hasidic-editions-status - hasidic editions.tsv"
OUTPUT = REPO / "editions" / "edition-bibliography-match.tsv"

# ── Manual mapping: XML basename → work number in bibliography ──────────────
# Built from title comparison between XML <title> and TSV English/Hebrew titles.
# Each entry also notes which specific edition (row) we matched, by DBid.
MANUAL_MAP = {
    # work 10: Adat Tzadikim 1864 — XML has dedupmrg285545615 in sourceDesc
    # work 13: Kehal Chasidim — XML title "Khal Hasidim 1866 קהל חסידים"
    "Khal-Hasidim": (13, "3621", "title match: Kehal Chasidim = Khal Hasidim"),
    # work 16: Ke'hal Kedoshim — XML title "Khal Kdoshim 1865 קהל קדושים"
    "Khal-Kdoshim": (16, "3629", "title match: Ke'hal Kedoshim = Khal Kdoshim"),
    # work 18: Mifalot Hatzadikim — XML title has "מפעלות הצדיקים"; TSV row for 1866 Lemberg
    # Note: work 18 first row is 1856, but we may have the 1866 edition
    "Mifalot-HaZadikim": (18, "3635", "title match: Mifalot HaZadikim; verify edition year"),
    # work 19: Sipurei Kedoshim 1866
    "Sipurei-Kdoshim": (19, "3641", "title match: Sipurei Kedoshim"),
    # work 20: Tmimei Derech 1871
    "tmimei_derech": (20, "3644", "title match: Tmimei Derech"),
    # work 22: Shlosha Edrei Tzon
    "Shlosha-edrei-zon": (22, "3646", "title match: Shlosha Edrei Tzon"),
    # work 27: Morayim Gedolim
    "Sefer-Moraim-Gdolim": (27, "3653", "title match: Morayim Gedolim = Moraim Gdolim"),
    # work 28: Butzina Denehora
    "Buzina_Denehora": (28, "3654", "title match: Butzina Denehora = Buzina Denehora"),
    # work 30: Shivchei Tzadikim — XML "Shivhei-Zadikim"
    "shivheiZadikim": (30, "3664", "title match: Shivchei Tzadikim = shivheiZadikim"),
    # work 35: Semichat Moshe — HebrewBooks 34276
    "Smichat-Moshe": (35, "3673", "title match: Semichat Moshe; HebrewBooks 34276"),
    # work 40: Maasiot VeSichot Tzadikim
    "Maasiot-veSihot-Zadikim": (40, "3678", "title match: Maasiot VeSichot Tzadikim"),
    # work 42: Maasiot Pliot
    "Maasiot-Pliot": (42, "3669|3683", "title match: Maasiot Pliot"),
    # work 45: Kochavei Or
    "Kokhvei-Or": (45, "3688", "title match: Kochavei Or = Kokhvei Or"),
    # work 68: Maasiot UMaamarim Yekarim
    "MaasiyotUmaamarimYekarim": (68, "3714", "title match: Maasiot UMaamarim Yekarim"),
    # work 69: Sipurim UMaamarim Yekarim — HebrewBooks 3804
    "SipurimUmaamarimYekarim_Hebrewbooks_org_3804": (69, "3715", "title match: Sipurim UMaamarim Yekarim; HebrewBooks 3804"),
    # work 70: Sipurim Nechmadim — HebrewBooks 3802
    "Sipurim-Nehmadim": (70, "3716", "title match: Sipurim Nechmadim; HebrewBooks 3802"),
    # work 71: Maasiot MeTzadikei Yesodei Olam
    "MaasyiotMzadikeiYesodeiOlam": (71, "3717", "title match: Maasiot MeTzadikei Yesodei Olam"),
    # work 72: Sipurei Anshei Shem
    "SipureiAnsheiShem": (72, "3718", "title match: Sipurei Anshei Shem"),
    # work 81: Hitgalut Hatzadikim
    "Hitgalut-HaZadikim": (81, "3727.0||3728.0", "title match: Hitgalut HaZadikim"),
    # work 83: Devarim Yekarim — XML "דברים יקרים"
    "Dvarim-Yekarim": (83, "3731", "title match: Devarim Yekarim = Dvarim Yekarim"),
    # work 84: Shemen Hatov
    "Shemen-Hatov": (84, "3732", "title match: Shemen Hatov"),
    # Sipurei Zadikim: could be work 12 or 14 (both "ספורי צדיקים")
    # XML has dedupmrg285038807 which matches both 12 and 14 (same dedup ID!)
    # Work 12 = Chut Hameshulash edition, work 14 = Arbaa Meitivei Lechet
    # The file has "Sipurei Zadikim 1864" → work 14 is dated 1864
    "Sipurei-Zadikim": (14, "3624", "dedupmrg match + date 1864 → work 14 (Arbaa Meitivei Lechet)"),
    # Shivhei-Harav: dedupmrg329404700_IE128045948 — same IE as DBid 3620 (different dedup prefix)
    # TSV row 59 = "שבחי הרב וסיפורי צדיקים" bound together, no work number assigned
    # The BHBTitle is "שבחי הרב וסיפורי צדיקים" — Shivhei Harav is a distinct work by Frumkin
    "Shivhei-Harav": (0, "3620", "NO WORK NUMBER in TSV; BHBTitle='שבחי הרב וסיפורי צדיקים'; same IE as DBid 3620; needs work number assignment"),
    # maase-zadikim: dedupmrg478887820_IE50112763 — not in TSV, but title = מעשה צדיקים = work 9
    # XML date 1864 Lemberg matches DBid 3603 (work 9, 1864 Lemberg)
    "maase-zadikim": (9, "3603", "title+date match: Maase Tzadikim 1864 Lemberg; XML dedupmrg differs from TSV"),
}


def extract_dedupmrg_ids(xml_path: str) -> list[str]:
    """Extract dedupmrg IDs from an XML file's sourceDesc/bibl section."""
    ids = []
    with open(xml_path, encoding="utf-8") as f:
        text = f.read()
    for m in re.finditer(r'(dedupmrg\d+_IE\d+)', text):
        ids.append(m.group(1))
    return ids


def extract_hebrewbooks_id(xml_path: str) -> str | None:
    """Extract HebrewBooks ID from XML."""
    with open(xml_path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r'[Hh]ebrewbooks?[_ ]org[_ ](\d+)', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def load_bibliography(tsv_path: str) -> list[dict]:
    """Load the bibliography TSV."""
    rows = []
    with open(tsv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows.append(row)
    return rows


def build_dedupmrg_index(bib_rows: list[dict]) -> dict:
    """Map dedupmrg IDs → (work_number, DBid, eng_title, heb_title, date)."""
    idx = {}
    for row in bib_rows:
        work_num = row.get("Nu. מספר.", "").strip()
        dbid = row.get("DBid", "").strip()
        eng = row.get("title-eng-Y", "").strip()
        heb = row.get("Final Edition Title for the DB", "").strip()
        date = row.get("BHB-date", "").strip()
        downloaded = row.get("downloaded filename", "").strip()
        if downloaded:
            # Extract the dedupmrg ID from the downloaded filename
            m = re.match(r'(dedupmrg\d+_IE\d+)', downloaded)
            if m:
                dedup_id = m.group(1)
                # Prefer the row that has a work number
                if dedup_id not in idx or work_num:
                    idx[dedup_id] = (work_num, dbid, eng, heb, date)
    return idx


def build_hebrewbooks_index(bib_rows: list[dict]) -> dict:
    """Map HebrewBooks IDs → (work_number, DBid, eng_title, heb_title, date)."""
    idx = {}
    for row in bib_rows:
        work_num = row.get("Nu. מספר.", "").strip()
        dbid = row.get("DBid", "").strip()
        eng = row.get("title-eng-Y", "").strip()
        heb = row.get("Final Edition Title for the DB", "").strip()
        date = row.get("BHB-date", "").strip()
        hb_link = row.get("HebrewBooksLink", "").strip()
        if hb_link:
            m = re.search(r'(\d+)', hb_link)
            if m:
                hb_id = m.group(1)
                if hb_id not in idx or work_num:
                    idx[hb_id] = (work_num, dbid, eng, heb, date)
    return idx


def main():
    bib_rows = load_bibliography(str(TSV_PATH))
    dedup_idx = build_dedupmrg_index(bib_rows)
    hb_idx = build_hebrewbooks_index(bib_rows)

    xml_files = sorted(INCOMING.glob("*.xml"))
    results = []

    for xml_path in xml_files:
        basename = xml_path.stem
        matched = False

        # Strategy 1: dedupmrg ID match
        dedup_ids = extract_dedupmrg_ids(str(xml_path))
        for did in dedup_ids:
            if did in dedup_idx:
                work_num, dbid, eng, heb, date = dedup_idx[did]
                results.append({
                    "xml_filename": xml_path.name,
                    "work_number": work_num,
                    "DBid": dbid,
                    "eng_title": eng,
                    "heb_title": heb,
                    "date": date,
                    "match_method": "dedupmrg",
                    "notes": f"matched via {did}",
                })
                matched = True
                break

        if matched:
            # Check if manual map has a better/corrected entry
            if basename in MANUAL_MAP:
                manual = MANUAL_MAP[basename]
                if str(manual[0]) != results[-1]["work_number"]:
                    results[-1]["notes"] += f" | MANUAL OVERRIDE to work {manual[0]}: {manual[2]}"
                    results[-1]["work_number"] = str(manual[0])
                    results[-1]["DBid"] = manual[1]
            continue

        # Strategy 2: HebrewBooks ID match
        hb_id = extract_hebrewbooks_id(str(xml_path))
        if hb_id and hb_id in hb_idx:
            work_num, dbid, eng, heb, date = hb_idx[hb_id]
            results.append({
                "xml_filename": xml_path.name,
                "work_number": work_num,
                "DBid": dbid,
                "eng_title": eng,
                "heb_title": heb,
                "date": date,
                "match_method": "hebrewbooks",
                "notes": f"HebrewBooks ID {hb_id}",
            })
            matched = True

        if matched:
            continue

        # Strategy 3: Manual mapping
        if basename in MANUAL_MAP:
            work_num, dbid, notes = MANUAL_MAP[basename]
            # Look up the rest from the bibliography
            eng = heb = date = ""
            for row in bib_rows:
                rw = row.get("Nu. מספר.", "").strip()
                if rw == str(work_num):
                    eng = row.get("title-eng-Y", "").strip()
                    heb = row.get("Final Edition Title for the DB", "").strip()
                    date = row.get("BHB-date", "").strip()
                    break
            results.append({
                "xml_filename": xml_path.name,
                "work_number": str(work_num),
                "DBid": dbid,
                "eng_title": eng,
                "heb_title": heb,
                "date": date,
                "match_method": "manual",
                "notes": notes,
            })
            matched = True

        if not matched:
            results.append({
                "xml_filename": xml_path.name,
                "work_number": "",
                "DBid": "",
                "eng_title": "",
                "heb_title": "",
                "date": "",
                "match_method": "UNMATCHED",
                "notes": f"dedupmrg IDs found: {dedup_ids}; HB ID: {hb_id}",
            })

    # Write output
    fieldnames = ["xml_filename", "work_number", "DBid", "eng_title", "heb_title", "date", "match_method", "notes"]
    with open(str(OUTPUT), "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    # Print summary
    methods = {}
    for r in results:
        m = r["match_method"]
        methods[m] = methods.get(m, 0) + 1

    print(f"\nMatched {len(results)} edition files:")
    for m, count in sorted(methods.items()):
        print(f"  {m}: {count}")
    print(f"\nOutput: {OUTPUT}")

    # Print details
    print(f"\n{'XML File':<55} {'Work#':>5}  {'Method':<12} {'Title'}")
    print("-" * 120)
    for r in results:
        print(f"{r['xml_filename']:<55} {r['work_number']:>5}  {r['match_method']:<12} {r['eng_title'] or r['heb_title']}")


if __name__ == "__main__":
    main()
