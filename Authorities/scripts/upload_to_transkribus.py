#!/usr/bin/env python3
"""
upload_to_transkribus.py  —  Pipeline Step 01a: scan → Transkribus
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Takes a work from editions/edition-registry.tsv, fetches its NLI scan zip from
the Drive `selected_editions` folder (or reads HebrewBooks PDFs from a local
folder, --from-dir: HebrewBooks blocks scripted downloads; name other scans
W{nu}_{source}.pdf), renames the images to the canonical
`{Slug}_{NNNN}.jpg` (the leading NLI page number is kept, as in step 01b), and
uploads them as a new document to Transkribus collection 49371.

The new document is appended to editions/transkribus-collection-map.tsv with
role "main", so the registry picks it up on its next build.

Slug = the catalogue's English title (`title-eng-Y`), hyphenated.
Doc title = `{Slug}_NLI_{IE}`; externalId = IE.

Needs TRANSKRIBUS_USER / TRANSKRIBUS_PASS in the environment.

Usage:
    python Authorities/scripts/upload_to_transkribus.py 51 107 119
    python Authorities/scripts/upload_to_transkribus.py --all-drive   # every work whose next step is a Drive upload
    python Authorities/scripts/upload_to_transkribus.py --from-dir ~/Downloads/hasidic-scans
    python Authorities/scripts/upload_to_transkribus.py 51 --dry-run
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "editions" / "edition-registry.tsv"
CATALOGUE = REPO / "Hasidic-editions-status - hasidic editions.tsv"
TRP_MAP = REPO / "editions" / "transkribus-collection-map.tsv"

DRIVE_FOLDER = ("0B1TlfouSwHTnfi1RSU1VQVFSS05NWHpHbHlHZ2NzeXRvUUJlQXVWY2hFNXhuRERFbmx5WWc",
                "0-2ytPkKz63YC59t3CN3yPAg")
TRP_REST = "https://transkribus.eu/TrpServer/rest"
COLLECTION = 49371
# catalogue English titles that are missing, wrong or too long (key = Nu., or row for unnumbered works)
SLUG_OVERRIDES = {"35.5": "Masaot-Hayam", "76": "Tzvi-Latzadik", "91": "Ilana-Dehayei",
                  "96": "Niflaot-Hayehudi", "102": "Sihat-Hulin", "124": "Daat-Zekenim",
                  "11": "Heichal-Habracha", "89": "Ahavat-Shalom-Tinyana", "90": "Rishfei-Esh",
                  "95": "Ateret-Tzvi-1908", "111": "Dover-Shalom", "114": "Harav-MiLadi",
                  "58": "Rabbi-Yisrael-Baal-Shem-Tov", "6": "Magid-Sichot", "238": "Niflaot-Beit-Levi"}
IMG_RE = re.compile(r"^(\d{4})_.*\.(jpe?g|tiff?|png)$", re.I)


def slugify(title: str) -> str:
    title = re.sub(r"[\"'’`]", "", title)
    return "-".join(w.capitalize() if w.islower() else w for w in re.findall(r"[A-Za-z0-9]+", title))


def drive_zips() -> dict[str, str]:
    """IE id → Drive file id for every zip in the selected_editions folder."""
    fid, rk = DRIVE_FOLDER
    page = requests.get(f"https://drive.google.com/embeddedfolderview?id={fid}&resourcekey={rk}", timeout=60).text
    out = {}
    for url, name in re.findall(r'<a href="([^"]+)"[^>]*>.*?<div class="flip-entry-title">(.*?)</div>', page, re.S):
        name = html.unescape(name).strip()
        m, ie = re.search(r"/file/d/([^/]+)", url), re.search(r"IE\d+", name)
        if name.endswith(".zip") and m and ie:
            out.setdefault(ie.group(), m.group(1))
    return out


def zip_images(drive_id: str, slug: str) -> list[tuple[str, bytes]]:
    """NLI zip from Drive → images renamed {slug}_{NNNN} (NLI page number kept)."""
    z = requests.get(f"https://drive.usercontent.google.com/download?id={drive_id}&export=download&confirm=t",
                     timeout=900).content
    zf = zipfile.ZipFile(io.BytesIO(z))
    out = []
    for n in sorted(zf.namelist()):
        m = IMG_RE.match(Path(n).name)
        if m:
            out.append((f"{slug}_{m.group(1)}.{m.group(2).lower().replace('jpeg', 'jpg')}", zf.read(n)))
    return out


def local_zip_images(path: Path, slug: str) -> list[tuple[str, bytes]]:
    """Locally downloaded NLI zip → images renamed {slug}_{NNNN}."""
    zf = zipfile.ZipFile(path)
    out = []
    for n in sorted(zf.namelist()):
        m = IMG_RE.match(Path(n).name)
        if m:
            out.append((f"{slug}_{m.group(1)}.{m.group(2).lower().replace('jpeg', 'jpg')}", zf.read(n)))
    return out


def pdf_images(pdf: Path, slug: str) -> list[tuple[str, bytes]]:
    """HebrewBooks PDF → one 300-dpi JPEG per page, named {slug}_{NNNN}."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "300", "-jpeg", "-jpegopt", "quality=90", str(pdf), f"{tmp}/p"],
                       check=True)
        pages = sorted(Path(tmp).glob("p-*.jpg"), key=lambda p: int(p.stem.split("-")[1]))
        return [(f"{slug}_{i:04d}.jpg", p.read_bytes()) for i, p in enumerate(pages, 1)]


def trp_session() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{TRP_REST}/auth/login", data={"user": os.environ["TRANSKRIBUS_USER"],
                                                "pw": os.environ["TRANSKRIBUS_PASS"]}, timeout=60)
    r.raise_for_status()
    s.cookies.set("JSESSIONID", re.search(r"<sessionId>(.*?)</sessionId>", r.text).group(1))
    return s


def upload(s: requests.Session, title: str, ie: str, desc: str, images: list[tuple[str, bytes]]) -> int:
    body = {"md": {"title": title, "externalId": ie, "desc": desc},
            "pageList": {"pages": [{"fileName": n, "pageNr": i + 1} for i, (n, _) in enumerate(images)]}}
    # the kept-alive connection goes stale while images are prepared (minutes); retry on a fresh one
    for attempt in range(5):
        try:
            r = s.post(f"{TRP_REST}/uploads?collId={COLLECTION}", json=body,
                       headers={"Accept": "application/json"}, timeout=120)
            break
        except requests.RequestException:
            if attempt == 4:
                raise
            time.sleep(10 * (attempt + 1))
    r.raise_for_status()
    uid = r.json()["uploadId"]
    for name, data in images:
        for attempt in range(5):
            try:
                rr = s.put(f"{TRP_REST}/uploads/{uid}", files={"img": (name, data, "image/jpeg")},
                           headers={"Accept": "application/json"}, timeout=300)
                if rr.status_code == 200:
                    break
            except requests.RequestException:   # connection reset mid-batch
                if attempt == 4:
                    raise
            time.sleep(10 * (attempt + 1))
        rr.raise_for_status()
    return uid


def wait_for_doc(s: requests.Session, title: str, timeout: int = 900) -> dict | None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            docs = s.get(f"{TRP_REST}/collections/{COLLECTION}/list",
                         headers={"Accept": "application/json"}, timeout=120).json()
        except (requests.RequestException, ValueError):   # transient reset while polling
            time.sleep(20)
            continue
        hit = [d for d in docs if d["title"] == title]
        if hit:
            return hit[0]
        time.sleep(20)
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("works", nargs="*", help="catalogue work numbers (Nu.)")
    ap.add_argument("--all-drive", action="store_true")
    ap.add_argument("--from-dir", help="folder of Hebrewbooks_org_NNNN.pdf files to upload")
    ap.add_argument("--skip", nargs="*", default=[], help="work numbers to leave out")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    reg = list(csv.DictReader(open(REGISTRY, encoding="utf-8"), delimiter="\t"))
    cat = list(csv.DictReader(open(CATALOGUE, encoding="utf-8"), delimiter="\t"))
    rowkey = list(cat[0])[0]
    by_row = {r[rowkey].strip(): r for r in cat}
    trp_map = list(csv.DictReader(open(TRP_MAP, encoding="utf-8"), delimiter="\t"))
    in_trp = " ".join(m["transkribus_title"] for m in trp_map)
    s = None if args.dry_run else trp_session()

    def slug_for(r: dict) -> str:
        return SLUG_OVERRIDES.get(r["nu"] or r["edition_row"]) or slugify(by_row[r["edition_row"]]["title-eng-Y"])

    # jobs: (registry row, doc title, external id, source description, image loader)
    jobs = []
    if args.from_dir:
        hb_to_work = {}
        for r in reg:
            for x in re.findall(r"hebrewbooks\.org/(\d+)", r["hebrewbooks_link"] + " " + r["nli_link"]):
                hb_to_work.setdefault(x, r)
        by_nu = {r["nu"] or r["edition_row"]: r for r in reg}
        for pdf in sorted(Path(args.from_dir).expanduser().glob("*.*")):
            if pdf.suffix.lower() not in (".pdf", ".zip"):
                continue
            # W{nu}_{source}.pdf|zip ties a scan from any source to a work explicitly
            m = re.match(r"W([\d.]+)_(.+?)(?: \(\d+\))?\.(?:pdf|zip)$", pdf.name)
            if m:
                r, source = by_nu.get(m.group(1)), m.group(2)
            else:
                m = re.match(r"hebrewbooks_org_(\d+)(?: \(\d+\))?\.pdf$", pdf.name, re.I)
                if not m:
                    continue
                r, source = hb_to_work.get(m.group(1)), f"Hebrewbooks_org_{m.group(1)}"
            if not r:
                print(f"SKIP {pdf.name}: not a candidate edition in the registry")
                continue
            title = f"{slug_for(r)}_{source}"
            loader = local_zip_images if pdf.suffix.lower() == ".zip" else pdf_images
            jobs.append((r, title, source, source.replace("_", " "),
                         lambda pdf=pdf, slug=slug_for(r), loader=loader: loader(pdf, slug)))
    else:
        targets = [r for r in reg if (args.all_drive and r["next_step"].endswith("upload Drive scan to Transkribus"))
                   or r["nu"] in args.works]
        zips = drive_zips()
        for r in targets:
            ed = by_row[r["edition_row"]]
            ie = (re.findall(r"IE\d+", ed["downloaded filename"]) or [""])[0]
            if not ie or ie not in zips:
                print(f'SKIP work {r["nu"]} {r["work"]}: no Drive zip')
                continue
            jobs.append((r, f"{slug_for(r)}_NLI_{ie}", ie, f'NLI {ed["downloaded filename"]}',
                         lambda fid=zips[ie], slug=slug_for(r): zip_images(fid, slug)))

    # the live collection, not just the map: an upload whose client crashed can still be ingested
    live = {} if s is None else {d["title"]: d for d in s.get(
        f"{TRP_REST}/collections/{COLLECTION}/list", headers={"Accept": "application/json"}, timeout=120).json()}

    def record(doc: dict, title: str, r: dict, note: str) -> None:
        nonlocal in_trp
        trp_map.append({"docId": str(doc["docId"]), "transkribus_title": title, "pages": str(doc["nrOfPages"]),
                        "pages_final_or_done": "0", "pages_in_progress": "0", "pages_new": str(doc["nrOfPages"]),
                        "last_edit": "", "uploaded": time.strftime("%Y-%m-%d"),
                        "work_nu": r["nu"] or r["edition_row"], "work": r["work"], "role": "main", "note": note})
        in_trp += " " + title
        with open(TRP_MAP, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(trp_map[0]), delimiter="\t", lineterminator="\n")
            w.writeheader()
            w.writerows(trp_map)

    for r, title, ext, source, load in jobs:
        tag = f'work {r["nu"] or r["edition_row"]} {r["work"]} → {title}'
        if r["nu"] in args.skip:
            continue
        if ext in in_trp:
            print(f"SKIP {tag}: already in Transkribus")
            continue
        if title in live:
            record(live[title], title, r, "uploaded by upload_to_transkribus.py (found live, added to map)")
            print(f"MAP  {tag}: already in Transkribus as docId {live[title]['docId']}, added to map")
            continue
        if args.dry_run:
            print(f"DRY  {tag}")
            continue
        images = load()
        desc = f'{r["work"]} ({r["edition_year"]}), catalogue work {r["nu"]}, row {r["edition_row"]}; {source}'
        print(f"UP   {tag}: {len(images)} images", flush=True)
        upload(s, title, ext, desc, images)
        doc = wait_for_doc(s, title)
        if not doc:
            print(f"  ! {title}: upload sent but document not visible yet; rerun later to add it to the map")
            continue
        record(doc, title, r, "uploaded by upload_to_transkribus.py")
        print(f"  ✓ docId {doc['docId']} ({doc['nrOfPages']} pages)", flush=True)


if __name__ == "__main__":
    sys.exit(main())
