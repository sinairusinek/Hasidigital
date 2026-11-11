#!/usr/bin/env python3
"""
Book-level text overlap across the whole corpus — finished XMLs and raw
Transkribus transcriptions alike — to catch duplicate or derivative books
before they are processed.

For every pair of books A, B:  containment(A in B) = |shingles(A) ∩ shingles(B)| / |shingles(A)|
Shingles are 7-character windows over Hebrew letters only (spaces, niqqud and
punctuation removed, final letters folded), which survive HTR errors better
than word n-grams or embeddings.

Books
  - editions/online/*.xml and editions/incoming/ready/**/*.xml (TEI <body> text)
  - every Transkribus doc in editions/transkribus-collection-map.tsv whose role is
    main / alt-scan / supplement / duplicate and whose work has no XML yet
    (page text from the latest PAGE XML transcript; cached in editions/.cache/trp-text/)

Output: editions/book-overlap.tsv — one row per pair where either containment ≥ 0.10,
with the shared-shingle count and both directions.

Usage:
    python editions/find_book_overlap.py            # fetch missing Transkribus text, then compare
    python editions/find_book_overlap.py --no-fetch # use the cache only
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from lxml import etree

REPO = Path(__file__).resolve().parent.parent
TRP_MAP = REPO / "editions" / "transkribus-collection-map.tsv"
REGISTRY = REPO / "editions" / "edition-registry.tsv"
CACHE = REPO / "editions" / ".cache" / "trp-text"
OUT = REPO / "editions" / "book-overlap.tsv"
TRP_REST = "https://transkribus.eu/TrpServer/rest"
COLLECTION = 49371
K = 7
MIN_SHINGLES = 2000          # ignore books with almost no text
REPORT_AT = 0.10

FINALS = str.maketrans("ךםןףץ", "כמנפצ")


def shingles(text: str) -> set[int]:
    t = re.sub(r"[^א-ת]", "", text).translate(FINALS)
    return {hash(t[i:i + K]) for i in range(len(t) - K + 1)}


def tei_text(path: Path) -> str:
    tree = etree.parse(str(path))
    body = tree.find(".//{http://www.tei-c.org/ns/1.0}body")
    return " ".join((body if body is not None else tree.getroot()).itertext())


def trp_session() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{TRP_REST}/auth/login", data={"user": os.environ["TRANSKRIBUS_USER"],
                                                "pw": os.environ["TRANSKRIBUS_PASS"]}, timeout=60)
    s.cookies.set("JSESSIONID", re.search(r"<sessionId>(.*?)</sessionId>", r.text).group(1))
    return s


def fetch_doc_text(s: requests.Session, doc_id: str) -> str:
    """Concatenated line text of every page's latest transcript, cached per doc."""
    cache = CACHE / f"{doc_id}.json"
    j = s.get(f"{TRP_REST}/collections/{COLLECTION}/{doc_id}/fulldoc",
              headers={"Accept": "application/json"}, timeout=180).json()
    pages = j["pageList"]["pages"]
    stamp = max((p["tsList"]["transcripts"][0].get("timestamp", 0) for p in pages if p["tsList"]["transcripts"]),
                default=0)
    if cache.exists():
        old = json.loads(cache.read_text())
        if old.get("stamp") == stamp:
            return old["text"]

    def page_text(p):
        ts = p["tsList"]["transcripts"]
        if not ts:
            return ""
        x = s.get(ts[0]["url"], timeout=120).content
        root = etree.fromstring(x)
        lines = root.findall(".//{*}TextLine/{*}TextEquiv/{*}Unicode")
        return "\n".join(l.text or "" for l in lines)

    with ThreadPoolExecutor(8) as ex:
        text = "\n".join(ex.map(page_text, pages))
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"stamp": stamp, "text": text}, ensure_ascii=False))
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args()

    reg = {r["nu"] or r["edition_row"]: r for r in csv.DictReader(open(REGISTRY, encoding="utf-8"), delimiter="\t")}
    books: dict[str, tuple[str, str, set[int]]] = {}   # label -> (work, kind, shingles)

    xml_works = {}
    for r in reg.values():
        for x in r["xml"].split():
            xml_works[x.split("_Hebrewbooks")[0].removesuffix(".xml") + ".xml"] = r["nu"] or r["edition_row"]
    for p in sorted((REPO / "editions" / "online").glob("*.xml")) + \
            sorted((REPO / "editions" / "incoming" / "ready").rglob("*.xml")):
        sh = shingles(tei_text(p))
        if len(sh) >= MIN_SHINGLES:
            books[f"xml:{p.stem}"] = (xml_works.get(p.name, "?"), "xml", sh)
    print(f"{len(books)} XML editions")

    roles = {"main", "alt-scan", "supplement", "duplicate"}
    docs = [d for d in csv.DictReader(open(TRP_MAP, encoding="utf-8"), delimiter="\t")
            if d["role"] in roles and not reg.get(d["work_nu"] or "59", {}).get("xml")]
    s = None if args.no_fetch else trp_session()
    for d in docs:
        cache = CACHE / f"{d['docId']}.json"
        if s is not None:
            try:
                text = fetch_doc_text(s, d["docId"])
            except Exception as e:
                print("  ! could not fetch", d["docId"], e)
                continue
        elif cache.exists():
            text = json.loads(cache.read_text())["text"]
        else:
            continue
        sh = shingles(text)
        if len(sh) >= MIN_SHINGLES:
            books[f"trp:{d['docId']}:{d['transkribus_title'][:40]}"] = (d["work_nu"] or "59", d["role"], sh)
        print(f"  {d['docId']} {d['transkribus_title'][:40]}: {len(sh)} shingles", flush=True)
    print(f"{len(books)} books with text")

    labels = sorted(books)
    rows = []
    for i, a in enumerate(labels):
        wa, _, sa = books[a]
        for b in labels[i + 1:]:
            wb, _, sb = books[b]
            inter = len(sa & sb)
            ca, cb = inter / len(sa), inter / len(sb)
            if max(ca, cb) >= REPORT_AT:
                rows.append({"book_a": a, "work_a": wa, "work_a_name": reg.get(wa, {}).get("work", ""),
                             "book_b": b, "work_b": wb, "work_b_name": reg.get(wb, {}).get("work", ""),
                             "a_in_b": f"{ca:.3f}", "b_in_a": f"{cb:.3f}", "shared": inter,
                             "size_a": len(sa), "size_b": len(sb), "same_work": "yes" if wa == wb else ""})
    rows.sort(key=lambda r: -max(float(r["a_in_b"]), float(r["b_in_a"])))
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["book_a"], delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} pairs ≥ {REPORT_AT} → {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
