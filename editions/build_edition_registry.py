#!/usr/bin/env python3
"""
Build editions/edition-registry.tsv: one row per WORK in the catalogue,
joining every place where edition work is tracked, so nothing is redone.

Sources
  1. Catalogue  — `Hasidic-editions-status - hasidic editions.tsv` (repo root).
     This local copy is a superset of the Google Sheet's "hasidic editions" tab
     (DBids, dates and Kima ids were filled in locally), so it is the source.
     Works are delimited by the `Nu. מספר.` column (set on each work's first row).
  2. Status tab — live Google Sheet tab "Status" (decisions, column H notes).
  3. Drive      — public listing of the `selected_editions` folder (NLI zips).
  4. Transkribus— collection 49371 via the TrpServer REST API
                  (TRANSKRIBUS_USER / TRANSKRIBUS_PASS env vars); doc→work roles
                  come from the curated editions/transkribus-collection-map.tsv,
                  whose page counts this script refreshes.
  5. Local      — editions/edition-metadata.json + editions/online + incoming.

Usage
    python editions/build_edition_registry.py            # live fetch
    python editions/build_edition_registry.py --offline  # skip Transkribus API
"""
from __future__ import annotations

import argparse
import collections
import csv
import html
import io
import json
import os
import re
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
CATALOGUE = REPO / "Hasidic-editions-status - hasidic editions.tsv"
METADATA = REPO / "editions" / "edition-metadata.json"
TRP_MAP = REPO / "editions" / "transkribus-collection-map.tsv"
OUT = REPO / "editions" / "edition-registry.tsv"

SHEET_ID = "1CdA3uSJaUy4A_HJfBZgY8DPNH_fN3GQlAw51umzDp-M"
STATUS_GID = "909971925"
DRIVE_FOLDER = ("0B1TlfouSwHTnfi1RSU1VQVFSS05NWHpHbHlHZ2NzeXRvUUJlQXVWY2hFNXhuRERFbmx5WWc",
                "0-2ytPkKz63YC59t3CN3yPAg")
TRP_COLLECTION = 49371
TRP_REST = "https://transkribus.eu/TrpServer/rest"

# Status-tab titles that do not match any catalogue title by spelling
STATUS_OVERRIDES = {"שערי האמונה": "61", "רמתיים צופים?": "29",
                    "מעשה נפלאה (יידיש!) זלמינא וייטפסקער": "7"}
# earlier XML drafts of works that never went online (editions/archived-editions)
ARCHIVED_DRAFTS = {"4": r"^(Shivhei-Haran|ShvheiHaran)", "39": r"^MeromHarim",
                   "104": r"^(Em-?Labina|emlabina)", "115": r"^(Ohel|ohel)"}
STATUS_FOOTER = {"do-sinai", "Shaya", "check!", "?", "no", "done", "other"}
# catalogue scan links (Drive zip / NLI / HebrewBooks) checked and found to be a different book
WRONG_SCANS = {"141": "Drive zip IE101483126 and NLI 001898821 are I.H. Weiss's דור דור ודורשיו",
               "60": "NLI 000400073 opens שערי האמונה"}
# only a later printing than the record has been found; waiting for Gadi to accept it
# works whose catalogue DB title names a different book (145: DBid 3620 is titled סיפורי צדיקים, bound with it)
WORK_NAMES = {"145": "שבחי הרב"}
LATER_EDITION_ONLY = {"123": "Warsaw 1924 Yiddish", "126": "Przemyśl 1927",
                      "131": "Warsaw 1930", "138": "Bilgoraj 1925"}


def norm(s: str) -> str:
    s = s.replace("ספורי", "סיפורי").replace("ספורים", "סיפורים")
    return re.sub(r"[^א-ת]", "", s)


def overlaps(a: set[str], b: set[str]) -> bool:
    return any(x in y or y in x for x in a for y in b)


# ---------------------------------------------------------------- catalogue
def load_works() -> list[dict]:
    rows = list(csv.reader(open(CATALOGUE, encoding="utf-8"), delimiter="\t"))
    ix = {c: i for i, c in enumerate(rows[0])}
    g = lambda r, c: r[ix[c]].strip()

    def titles(r):
        cols = ["Final Edition Title for the DB", "BHBTitle", "KitsisTitle", "title(notBHB)"]
        return {norm(g(r, c)) for c in cols if norm(g(r, c))}

    works: list[dict] = []
    for r in rows[1:]:
        rec = {c: g(r, c) for c in ix}
        rec["_row"] = r[0].strip()
        rec["_titles"] = titles(r)
        m = re.search(r"1[789]\d\d", rec["BHB-date"] + " " + rec["Kitsisdate"])
        rec["_year"] = int(m.group()) if m else None
        # a new work starts at a Nu. value, or at a Kitsis head whose title is new
        new = bool(rec["Nu. מספר."]) or (bool(rec["Kitsis-head"]) and works
                                         and not overlaps(rec["_titles"], works[-1]["titles"]))
        if new or not works:
            works.append({"nu": rec["Nu. מספר."], "rows": [], "titles": set()})
        works[-1]["rows"].append(rec)
        works[-1]["titles"] |= rec["_titles"]

    # rows listed above their own work's Nu. row belong to the next work
    for k in range(len(works) - 1):
        w, nx = works[k], works[k + 1]
        first = w["rows"][0]["_titles"]
        for r in [r for r in w["rows"][1:] if r["_titles"] and not overlaps(r["_titles"], first)
                  and overlaps(r["_titles"], nx["rows"][0]["_titles"])]:
            w["rows"].remove(r)
            nx["rows"].insert(0, r)
    # row 136 (Kitsis head of דרך האמונה ומעשה רב) sits apart from its Nu. 48 row
    lone = next(k for k, w in enumerate(works) if w["rows"][0]["_row"] == "136")
    works[lone + 1]["rows"].insert(0, works[lone]["rows"][0])
    del works[lone]
    # דברים ערבים part B (Nu. 80) is part of work 75
    w75 = next(w for w in works if w["nu"] == "75")
    w80 = next(w for w in works if w["nu"] == "80")
    w75["rows"] += w80["rows"]
    works.remove(w80)

    for w in works:
        w["titles"] = set().union(*[r["_titles"] for r in w["rows"]])
        w["name"] = WORK_NAMES.get(w["nu"]) or next((r[c] for r in w["rows"] for c in
                          ["Final Edition Title for the DB", "BHBTitle", "KitsisTitle"] if r[c]), "?")
        w["key"] = w["nu"] or w["rows"][0]["_row"]
        w["status"] = []
    return works


# ---------------------------------------------------------------- status tab
def load_status(works: list[dict]) -> None:
    text = requests.get(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export"
                        f"?format=csv&gid={STATUS_GID}", timeout=60).content.decode("utf-8")
    rowpos = {r["_row"]: i for i, w in enumerate(works) for r in w["rows"] if r["_row"]}
    bhbpos: dict[str, int] = {}
    for i, w in enumerate(works):
        for r in w["rows"]:
            if r["Bibliography of the Hebrew Book"]:
                bhbpos.setdefault(r["Bibliography of the Hebrew Book"], i)
    prev = 0
    for s in list(csv.reader(io.StringIO(text)))[1:]:
        title = s[4].strip()
        if not title or title in STATUS_FOOTER:
            continue
        rec = {"row": s[0].strip(), "bhb": s[2].strip(), "title": title, "t": norm(title),
               "where": s[5].strip(), "inc": s[6].strip(), "H": s[7].strip()}
        if title in STATUS_OVERRIDES:
            i = next(j for j, w in enumerate(works) if w["nu"] == STATUS_OVERRIDES[title])
        elif rec["row"] in rowpos:
            i = rowpos[rec["row"]]
        elif rec["bhb"] in bhbpos:
            i = bhbpos[rec["bhb"]]
        else:
            exact = [j for j, w in enumerate(works) if rec["t"] in w["titles"]]
            cand = exact or [j for j, w in enumerate(works) if len(rec["t"]) > 5 and any(
                rec["t"] in t or t in rec["t"] for t in w["titles"])]
            # generic titles recur; take the candidate nearest the previous match
            i = min(cand, key=lambda j: (abs(j - prev), -j)) if cand else None
        if i is None:
            print("  ! Status row not matched:", title)
            continue
        works[i]["status"].append(rec)
        if rec["row"] != "212":  # אם לבינה sits out of order in the Status tab
            prev = i


# ---------------------------------------------------------------- drive
def drive_ies() -> set[str]:
    fid, rk = DRIVE_FOLDER
    page = requests.get(f"https://drive.google.com/embeddedfolderview?id={fid}&resourcekey={rk}",
                        timeout=60).text
    names = [html.unescape(t) for t in re.findall(r'<div class="flip-entry-title">(.*?)</div>', page, re.S)]
    return set(re.findall(r"IE\d+", " ".join(names)))


# ---------------------------------------------------------------- transkribus
def refresh_trp_map(offline: bool) -> list[dict]:
    rows = list(csv.DictReader(open(TRP_MAP, encoding="utf-8"), delimiter="\t"))
    if offline or not os.environ.get("TRANSKRIBUS_USER"):
        return rows
    s = requests.Session()
    r = s.post(f"{TRP_REST}/auth/login", data={"user": os.environ["TRANSKRIBUS_USER"],
                                                "pw": os.environ["TRANSKRIBUS_PASS"]}, timeout=60)
    s.cookies.set("JSESSIONID", re.search(r"<sessionId>(.*?)</sessionId>", r.text).group(1))
    docs = s.get(f"{TRP_REST}/collections/{TRP_COLLECTION}/list",
                 headers={"Accept": "application/json"}, timeout=120).json()
    known = {r["docId"] for r in rows}
    for d in docs:
        if str(d["docId"]) not in known:
            print(f"  ! new Transkribus doc, add it to the map: {d['docId']} {d['title']}")
    for row in rows:
        try:
            j = s.get(f"{TRP_REST}/collections/{TRP_COLLECTION}/{row['docId']}/fulldoc",
                      headers={"Accept": "application/json"}, timeout=180).json()
        except Exception as e:  # deleted doc or network error: keep the old counts
            print("  ! could not refresh", row["docId"], e)
            continue
        st = collections.Counter()
        last = 0
        for p in j["pageList"]["pages"]:
            ts = p["tsList"]["transcripts"]
            if ts:
                st[ts[0]["status"]] += 1
                last = max(last, ts[0].get("timestamp", 0))
        row["pages"] = str(len(j["pageList"]["pages"]))
        row["pages_final_or_done"] = str(st["FINAL"] + st["DONE"] + st["GT"])
        row["pages_in_progress"] = str(st["IN_PROGRESS"])
        row["pages_new"] = str(st["NEW"])
        if last:
            import datetime
            row["last_edit"] = datetime.datetime.fromtimestamp(last / 1000).strftime("%Y-%m-%d")
    with open(TRP_MAP, "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)
    return rows


# ---------------------------------------------------------------- build
def scan_source(r: dict) -> str:
    a = r["Access-comments"]
    if r["downloaded filename"]:
        return "NLI downloaded"
    if "hebrewbooks" in (a + r["HebrewBooksLink"] + r["download link"]).lower():
        return "HebrewBooks"
    if any(k in a for k in ["זכויות", "לבקש", "ליובאוויטש"]):
        return "library request"
    if a.startswith("אין") or "לא מצאתי" in a:
        return "no scan found"
    return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="do not query Transkribus")
    args = ap.parse_args()

    works = load_works()
    load_status(works)
    ies = drive_ies()
    trp = refresh_trp_map(args.offline)
    meta = json.load(open(METADATA, encoding="utf-8"))["editions"]
    online = {p.name for p in (REPO / "editions" / "online").glob("*.xml")}
    incoming = {p.name for p in (REPO / "editions" / "incoming" / "ready").rglob("*.xml")}

    # join editions to works by work_number; fall back to DBid for editions without one
    wn2meta = collections.defaultdict(dict)
    db2meta = {}
    for m in meta:
        if m.get("work_number"):
            wn2meta[str(m["work_number"])][m["xml_filename"]] = m
        for x in re.split(r"\|+", m["DBid"].replace(".0", "")):
            if x:
                db2meta[x] = m
    trp_by_work = collections.defaultdict(list)
    for t in trp:
        if t["role"] not in ("training", "other-project"):
            trp_by_work[t["work_nu"]].append(t)

    archived = sorted(p.name for p in (REPO / "editions" / "archived-editions").iterdir())
    out = []
    for w in works:
        metas = dict(wn2meta.get(w["nu"], {}))
        for r in w["rows"]:
            ids = [x for x in r["DBid"].split("|") if x]
            if len(ids) <= 2:  # longer cells are junk (e.g. row 25)
                metas.update({m["xml_filename"]: m for m in map(db2meta.get, ids)
                              if m and not m.get("work_number") or m and m["xml_filename"] == "Maasiot-Pliot.xml"})
        incs = " ".join((s["inc"] + " " + s["where"]).lower() for s in w["status"])
        if metas or "done" in incs or "incoming" in incs or re.search(r"\bdo\b", incs):
            decision = "included"
        elif w["status"] and all(s["inc"].lower() == "no" for s in w["status"]):
            decision = "no"
        elif w["status"]:
            decision = "pending"
        else:
            decision = "not assessed"

        dated = sorted(w["rows"], key=lambda r: r["_year"] or 9999)
        ed = next((r for r in dated if r["DBid"] and len(r["DBid"].split("|")) <= 2
                   and any(x in db2meta for x in r["DBid"].split("|"))), None)
        ed = ed or next((r for r in dated if (r["_year"] or 0) <= 1914), dated[0])
        ie = set(re.findall(r"IE\d+", ed["downloaded filename"]))
        docs = trp_by_work.get(w["key"], [])
        main_docs = [d for d in docs if d["role"] == "main"]
        pages = sum(int(d["pages"]) for d in main_docs)
        fin = sum(int(d["pages_final_or_done"]) for d in main_docs)
        prog = sum(int(d["pages_in_progress"]) for d in main_docs)
        xmls = sorted(metas)
        stem = lambda x: x.split("_Hebrewbooks")[0].removesuffix(".xml") + ".xml"
        where = ["online" if stem(x) in online else "incoming" if stem(x) in incoming
                 else "registered, no XML" for x in xmls]

        if decision == "no":
            step = ""
        elif "online" in where:
            step = "online"
        elif "incoming" in where:
            step = "incoming pipeline"
        elif "registered, no XML" in where:
            step = "re-export from Transkribus (without 'force valid TEI') → pipeline"
        elif main_docs and fin >= 0.9 * pages:
            step = "export from Transkribus → pipeline"
        elif main_docs and fin + prog > 0:
            step = "finish transcription in Transkribus"
        elif main_docs:
            step = "run layout + HTR in Transkribus"
        elif w["key"] in LATER_EDITION_ONLY:
            step = f'confirm later edition with Gadi ({LATER_EDITION_ONLY[w["key"]]})'
        elif w["key"] in WRONG_SCANS:
            step = "find a scan"
        elif ie & ies:
            step = "upload Drive scan to Transkribus"
        elif scan_source(ed) in ("NLI downloaded", "HebrewBooks"):
            step = "download scan"
        else:
            step = "find a scan"
        if decision in ("pending", "not assessed") and step not in ("online", "incoming pipeline"):
            step = "decide → " + step

        out.append({
            "nu": w["nu"], "work": w["name"], "first_year": min((r["_year"] for r in w["rows"] if r["_year"]), default=""),
            "n_editions": len(w["rows"]), "decision": decision,
            "status_tab_note": " / ".join(f'{s["inc"]}: {s["H"]}'.strip(": ") for s in w["status"]),
            "layout_flag": "yes" if any("layout" in s["H"].lower() for s in w["status"]) else "",
            "edition_row": ed["_row"], "edition_DBid": ed["DBid"], "edition_year": ed["_year"] or "",
            "RA_marked_A": "yes" if ed["edition"].startswith("A") else "",
            "scan_source": scan_source(ed),
            "drive_zip": ("yes" if ie & ies else "missing") if ie else "",
            "nli_link": ed["download link"], "hebrewbooks_link": ed["HebrewBooksLink"],
            "trp_main_docs": " ".join(d["docId"] for d in main_docs),
            "trp_pages": pages or "", "trp_pages_final": fin if main_docs else "",
            "trp_last_edit": max((d["last_edit"] for d in main_docs), default=""),
            "trp_other_docs": " ".join(f'{d["docId"]}({d["role"]})' for d in docs if d["role"] != "main"),
            "xml": " ".join(xmls), "xml_location": " ".join(where),
            "archived_drafts": "; ".join(a for a in archived if w["nu"] in ARCHIVED_DRAFTS
                                         and re.match(ARCHIVED_DRAFTS[w["nu"]], a, re.I)),
            "next_step": step,
        })

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(out[0]), delimiter="\t", lineterminator="\n")
        wr.writeheader()
        wr.writerows(out)
    print(f"{len(out)} works → {OUT.relative_to(REPO)}")
    for k, v in collections.Counter(r["decision"] for r in out).most_common():
        print(f"  {v:4d} {k}")
    print("next steps:")
    for k, v in collections.Counter(r["next_step"] for r in out if r["next_step"]).most_common():
        print(f"  {v:4d} {k}")


if __name__ == "__main__":
    main()
    import build_status_page          # keep editions/edition-status.html in step with the registry
    build_status_page.main()
