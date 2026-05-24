#!/usr/bin/env python3
"""
build_kimatch_inventory.py — assemble ALL toponyms in the Hasidigital project and
emit (a) a full inventory table and (b) the Kima-unlinked subset ready for the
Kimatch engine.

Adapted from the Dybbuk / zibn-shtern workflow (assemble → match unlinked →
route → donate). Stage "assemble".

Sources
-------
1. Authority file (`Authorities/Authorities2026-01-14.xml`) — every <place>:
   xml:id, all <placeName> variants (Hebrew + romanized), Wikidata QID, Kima idno
   (= link status), geo coords.
2. Editions (`editions/online/*.xml` + `editions/incoming/ready/*.xml`) — every
   <placeName>: text, optional ref="#H-LOC_x", and the surrounding paragraph text
   used as matching/disambiguation context.

A toponym is keyed by:
  - its authority place id, when an edition <placeName> carries ref="#H-LOC_x"
    OR its normalized text equals an authority variant; else
  - its normalized edition text (an "edition-only" toponym, not yet in the
    authority file — typically from the freshly-NER'd incoming editions).

"Linked to Kima" == the resolved authority place has a <idno type="Kima">.

Outputs (under editions/kimatch/)
---------------------------------
  toponyms_all.tsv     full inventory (linked + unlinked, authority + edition-only)
  kimatch_input.tsv    Kima-UNLINKED subset, columns mapped for the Kimatch job

Run:
    python3 Authorities/scripts/build_kimatch_inventory.py
"""
from __future__ import annotations

import csv
import glob
import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict

# ── paths ─────────────────────────────────────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
AUTH_XML = os.path.join(PROJECT, "Authorities", "Authorities2026-01-14.xml")
EDITION_GLOBS = [
    os.path.join(PROJECT, "editions", "online", "*.xml"),
    os.path.join(PROJECT, "editions", "incoming", "ready", "*.xml"),
]
OUT_DIR = os.path.join(PROJECT, "editions", "kimatch")
INVENTORY_TSV = os.path.join(OUT_DIR, "toponyms_all.tsv")
INPUT_TSV = os.path.join(OUT_DIR, "kimatch_input.tsv")
MENTIONS_JSON = os.path.join(OUT_DIR, "mentions.json")  # {local_id: [{rid,edition,text,ctx}]}
# Names a reviewer rejected as not-a-place / homographs (spotcheck_grade_a.py apply).
# Dropped from the matcher INPUT so they don't re-enter matching, but still kept in
# the full inventory (marked) for transparency.
STOPLIST_TSV = os.path.join(OUT_DIR, "reject_stoplist.tsv")

NS = {"t": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
TEI = "{http://www.tei-c.org/ns/1.0}"

MAX_CONTEXTS = 5          # sample contexts kept per toponym (for context_sample)
MAX_MENTIONS = 60         # per-occurrence mentions kept per toponym (per-mention review)
CONTEXT_WINDOW = 220      # chars kept around the mention inside its paragraph

_HEB = re.compile(r"[֐-׿]")
_WS = re.compile(r"\s+")


def is_hebrew(s: str) -> bool:
    return bool(_HEB.search(s or ""))


def norm(s: str) -> str:
    """Normalize a place string for keying: collapse ws, strip TEI gershayim/quotes."""
    s = _WS.sub(" ", (s or "").strip())
    return s.strip(" ׳״\"'.,")


def qid_from_url(url: str) -> str:
    m = re.search(r"(Q\d+)", url or "")
    return m.group(1) if m else ""


def kima_id_from_url(url: str) -> str:
    m = re.search(r"/Details/(\d+)", url or "")
    return m.group(1) if m else ""


# ── 1. load authority places ────────────────────────────────────────────────
class Place:
    __slots__ = ("id", "names_heb", "names_rom", "wikidata", "kima_id", "lat",
                 "lon", "occ", "editions", "contexts", "mentions", "_ed_idx")

    def __init__(self, pid):
        self.id = pid
        self.names_heb: list[str] = []
        self.names_rom: list[str] = []
        self.wikidata = ""
        self.kima_id = ""
        self.lat = ""
        self.lon = ""
        self.occ = 0
        self.editions: set[str] = set()
        self.contexts: list[str] = []
        # per-occurrence mentions for per-mention review (capped); rid locates the
        # nth occurrence of this toponym in an edition (used later for apply-back).
        self.mentions: list[dict] = []
        self._ed_idx: dict[str, int] = {}

    @property
    def linked(self) -> bool:
        return bool(self.kima_id)

    def add_context(self, ed: str, ctx: str, surface: str = ""):
        self.occ += 1
        self.editions.add(ed)
        if ctx and len(self.contexts) < MAX_CONTEXTS and ctx not in self.contexts:
            self.contexts.append(ctx)
        if len(self.mentions) < MAX_MENTIONS:
            idx = self._ed_idx.get(ed, 0) + 1
            self._ed_idx[ed] = idx
            self.mentions.append({
                "rid": f"{ed}#{idx}", "edition": ed,
                "text": surface, "ctx": ctx,
            })


def load_authority() -> tuple[dict[str, Place], dict[str, str]]:
    """Return (places_by_id, variant_norm -> place_id)."""
    root = ET.parse(AUTH_XML).getroot()
    places: dict[str, Place] = {}
    variant_to_id: dict[str, str] = {}
    for el in root.findall(".//t:place", NS):
        pid = el.get(XML_ID)
        if not pid:
            continue
        p = Place(pid)
        for nm in el.findall("t:placeName", NS):
            txt = norm(nm.text or "")
            if not txt:
                continue
            (p.names_heb if is_hebrew(txt) else p.names_rom).append(txt)
            variant_to_id.setdefault(txt, pid)
        for idno in el.findall(".//t:idno", NS):
            typ = (idno.get("type") or "").lower()
            val = (idno.text or "").strip()
            if typ == "wikidata":
                p.wikidata = qid_from_url(val) or p.wikidata
            elif typ == "kima":
                p.kima_id = kima_id_from_url(val) or p.kima_id
        geo = el.find(".//t:geo", NS)
        if geo is not None and geo.text and "," in geo.text:
            lat, lon = geo.text.split(",", 1)
            p.lat, p.lon = lat.strip(), lon.strip()
        places[pid] = p
    return places, variant_to_id


# ── 2. scan editions ──────────────────────────────────────────────────────────
def paragraph_context(parent_map, el, mention: str) -> str:
    """Containing-paragraph text, windowed around the mention."""
    node = el
    container = None
    while node is not None:
        tag = node.tag
        if tag in (TEI + "p", TEI + "ab", TEI + "head", TEI + "l"):
            container = node
            break
        node = parent_map.get(node)
    if container is None:
        container = parent_map.get(el)
    if container is None:
        return ""
    txt = _WS.sub(" ", "".join(container.itertext())).strip()
    if not txt:
        return ""
    i = txt.find(mention)
    if i < 0:
        return txt[:CONTEXT_WINDOW]
    start = max(0, i - CONTEXT_WINDOW // 2)
    end = min(len(txt), i + len(mention) + CONTEXT_WINDOW // 2)
    snippet = txt[start:end]
    return ("…" if start else "") + snippet + ("…" if end < len(txt) else "")


def scan_editions(places, variant_to_id):
    """Mutate authority Place objects with occurrences; collect edition-only toponyms."""
    edition_only: dict[str, Place] = {}
    files = []
    for g in EDITION_GLOBS:
        files.extend(sorted(glob.glob(g)))

    for fp in files:
        ed = os.path.splitext(os.path.basename(fp))[0]
        try:
            tree = ET.parse(fp)
        except ET.ParseError as e:
            print(f"  ! parse error {ed}: {e}")
            continue
        root = tree.getroot()
        parent_map = {c: p for p in root.iter() for c in p}
        for nm in root.iter(TEI + "placeName"):
            text = norm("".join(nm.itertext()))
            if not text:
                continue
            ref = (nm.get("ref") or "").lstrip("#").strip()
            ctx = paragraph_context(parent_map, nm, text)

            target = None
            if ref and ref in places:
                target = places[ref]
            elif text in variant_to_id:
                target = places[variant_to_id[text]]

            if target is not None:
                target.add_context(ed, ctx, text)
            else:
                key = text
                p = edition_only.get(key)
                if p is None:
                    p = Place(f"ED::{key}")
                    (p.names_heb if is_hebrew(key) else p.names_rom).append(key)
                    edition_only[key] = p
                p.add_context(ed, ctx, text)
    return edition_only, files


# ── 3. emit ────────────────────────────────────────────────────────────────────
INV_FIELDS = ["key", "kind", "kima_linked", "stoplisted", "kima_id", "wikidata",
              "lat", "lon", "name_heb", "name_rom", "names_all", "occurrences",
              "n_editions", "editions", "context_sample"]

INPUT_FIELDS = ["local_id", "name_heb", "name_rom", "wikidata_qid", "lat", "lon",
                "occurrences", "n_editions", "editions", "context", "kind"]


def primary(names: list[str]) -> str:
    return names[0] if names else ""


def load_stoplist() -> set[str]:
    if not os.path.exists(STOPLIST_TSV):
        return set()
    with open(STOPLIST_TSV, encoding="utf-8") as fh:
        return {norm(r["name"]) for r in csv.DictReader(fh, delimiter="\t")
                if r.get("name")}


def write_outputs(places: dict[str, Place], edition_only: dict[str, Place]):
    import json
    os.makedirs(OUT_DIR, exist_ok=True)
    all_places = list(places.values()) + list(edition_only.values())
    stoplist = load_stoplist()

    # per-occurrence mentions sidecar (keyed by local_id) for per-mention review
    with open(MENTIONS_JSON, "w", encoding="utf-8") as fh:
        json.dump({p.id: p.mentions for p in all_places if p.mentions},
                  fh, ensure_ascii=False)

    def is_stoplisted(p: "Place") -> bool:
        return any(norm(n) in stoplist for n in (p.names_heb + p.names_rom))

    # full inventory
    with open(INVENTORY_TSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=INV_FIELDS, delimiter="\t")
        w.writeheader()
        for p in sorted(all_places, key=lambda x: (-x.occ, x.id)):
            kind = "edition_only" if p.id.startswith("ED::") else "authority"
            names_all = " | ".join(p.names_heb + p.names_rom)
            w.writerow({
                "key": p.id,
                "kind": kind,
                "kima_linked": "yes" if p.linked else "no",
                "stoplisted": "yes" if is_stoplisted(p) else "no",
                "kima_id": p.kima_id,
                "wikidata": p.wikidata,
                "lat": p.lat, "lon": p.lon,
                "name_heb": primary(p.names_heb),
                "name_rom": primary(p.names_rom),
                "names_all": names_all,
                "occurrences": p.occ,
                "n_editions": len(p.editions),
                "editions": "; ".join(sorted(p.editions)),
                "context_sample": " ⟦SEP⟧ ".join(p.contexts),
            })

    # unlinked subset → matcher input
    n_in = 0
    with open(INPUT_TSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=INPUT_FIELDS, delimiter="\t")
        w.writeheader()
        for p in sorted(all_places, key=lambda x: -x.occ):
            if p.linked or is_stoplisted(p):
                continue
            kind = "edition_only" if p.id.startswith("ED::") else "authority"
            w.writerow({
                "local_id": p.id,
                "name_heb": primary(p.names_heb),
                "name_rom": primary(p.names_rom),
                "wikidata_qid": p.wikidata,
                "lat": p.lat, "lon": p.lon,
                "occurrences": p.occ,
                "n_editions": len(p.editions),
                "editions": "; ".join(sorted(p.editions)),
                # join name variants into context too, so phonetic recall sees them
                "context": (" ⟦SEP⟧ ".join(p.contexts)) or "",
                "kind": kind,
            })
            n_in += 1
    return all_places, n_in


def main():
    print("Loading authority places …")
    places, variant_to_id = load_authority()
    linked = sum(1 for p in places.values() if p.linked)
    print(f"  {len(places)} authority places ({linked} Kima-linked, "
          f"{len(places) - linked} unlinked)")

    print("Scanning editions …")
    edition_only, files = scan_editions(places, variant_to_id)
    print(f"  {len(files)} edition files scanned")
    print(f"  {len(edition_only)} edition-only toponyms (not in authority)")

    all_places, n_in = write_outputs(places, edition_only)
    total_occ = sum(p.occ for p in all_places)
    print(f"\nInventory: {len(all_places)} distinct toponyms, {total_occ} occurrences")
    print(f"  → {INVENTORY_TSV}")
    print(f"Unlinked input for Kimatch: {n_in} toponyms")
    print(f"  → {INPUT_TSV}")


if __name__ == "__main__":
    main()
