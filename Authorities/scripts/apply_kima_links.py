#!/usr/bin/env python3
"""
Apply confirmed Kima toponym decisions back into the sources.

This is TODO 4 of the Kima toponym pipeline (see editions/kimatch/NEXT-SESSION.md
section B): write confirmed Kima links into

  1. the **authority file** — add ``<idno type="Kima">`` to existing places and
     create new ``<place>`` entries for edition-only toponyms; and
  2. the **edition XML** — add ``ref="#H-LOC_x"`` to bare ``<placeName>`` tags.

Decision sources (combined):
  * ``kima_decisions.json`` (Kimatch repo ``data`` branch) — human-confirmed,
    either GLOBAL (``{action, kima_id}`` keyed by toponym) or PER-MENTION
    (``{mentions: {rid: {kima_id}}}``).  Per-mention decisions are written to
    *exactly* the decided ``rid`` occurrences; undecided occurrences stay bare.
  * ``editions/kimatch/auto_confirmed.tsv`` — grade-A auto-links (GLOBAL).
  * ``editions/kimatch/confirmed_priors.tsv`` — name→kima_id keeps (GLOBAL).

The ``rid`` locator (``<edition>#<n>``) is reproduced by re-walking the same
edition glob as ``build_kimatch_inventory.py`` and counting the n-th occurrence
of each normalized ``<placeName>`` text per edition (document order).

Usage::

    python3 Authorities/scripts/apply_kima_links.py --dry-run
    python3 Authorities/scripts/apply_kima_links.py --apply [--skip-commit]
"""

from __future__ import annotations

import argparse
import collections
import csv
import glob
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_AUTH_DIR = _SCRIPT_DIR.parent
_PROJECT = _AUTH_DIR.parent
sys.path.insert(0, str(_AUTH_DIR / "integration_tool"))

from config import (  # noqa: E402
    AUTHORITY_XML_PATH,
    GEN_SCRIPT,
    TEI_NS,
    XML_NS,
)

# Reuse the battle-tested helpers from the older apply script.
from apply_kima_decisions import (  # noqa: E402
    _find_list_place,
    _highest_hloc_num,
    _load_kima_lookup,
    _strip_hebrew_prefix,
)

T = f"{{{TEI_NS}}}"
X = f"{{{XML_NS}}}"

# Same edition glob the inventory builder scans, in the same order.
EDITION_GLOBS = [
    str(_PROJECT / "editions" / "online" / "*.xml"),
    str(_PROJECT / "editions" / "incoming" / "ready" / "*.xml"),
]
KIMATCH_DIR = _PROJECT / "editions" / "kimatch"
AUTO_CONFIRMED_TSV = KIMATCH_DIR / "auto_confirmed.tsv"
PRIORS_TSV = KIMATCH_DIR / "confirmed_priors.tsv"
DECISIONS_LOCAL = KIMATCH_DIR / "kima_decisions.json"
KIMATCH_REPO = Path(os.environ.get("KIMATCH_REPO", str(_PROJECT.parent / "Kimatch")))
DATA_BRANCH_PATH = "data/hasidigital/kima_decisions.json"

_WS = re.compile(r"\s+")
_HEB = re.compile(r"[֐-׿]")

# Galicia duplicate: H-LOC_683 (wrong Wikidata Q485018 = Spanish Galicia) is a
# dup of H-LOC_218 (Q180086 + Kima 1473). No edition references 683.
GALICIA_DUP = ("H-LOC_683", "H-LOC_218")


def norm(s: str) -> str:
    """Match build_kimatch_inventory.norm() exactly (for rid reproduction)."""
    s = _WS.sub(" ", (s or "").strip())
    return s.strip(" ׳״\"'.,")


def kima_num(text: str) -> str:
    """Extract the Kima place number from either URL form the corpus uses:
    ``/Places/Details/961`` (path) or ``/Places/Details?id=961`` (query)."""
    m = re.search(r"Details(?:/|\?id=)(\d+)", text or "")
    return m.group(1) if m else ""


# ──────────────────────────────────────────────────────────────────────────────
# Load decisions
# ──────────────────────────────────────────────────────────────────────────────

def fetch_decisions(path: str | None) -> dict:
    """Load kima_decisions.json. Prefer an explicit path, then the Kimatch
    `data` branch (origin/data), then a local cached copy."""
    import json
    if path:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    if KIMATCH_REPO.is_dir():
        try:
            out = subprocess.check_output(
                ["git", "-C", str(KIMATCH_REPO), "show",
                 f"origin/data:{DATA_BRANCH_PATH}"],
                stderr=subprocess.DEVNULL, text=True)
            print(f"  decisions: origin/data:{DATA_BRANCH_PATH} ({KIMATCH_REPO})")
            return json.loads(out)
        except subprocess.CalledProcessError:
            pass
    if DECISIONS_LOCAL.exists():
        print(f"  decisions: {DECISIONS_LOCAL} (local fallback)")
        with open(DECISIONS_LOCAL, encoding="utf-8") as fh:
            return json.load(fh)
    print("  ! no kima_decisions.json found — proceeding with auto_confirmed only")
    return {}


class Link:
    """A resolved link target: a kima_id plus enrichment, applied to a name.

    ``hloc`` is set when the source already names an existing authority place
    (auto_confirmed ``kind=authority`` rows) — that id is trusted as-is."""
    __slots__ = ("name", "kima_id", "wikidata", "rom", "heb_name", "source", "hloc")

    def __init__(self, name, kima_id, wikidata="", rom="", heb_name="",
                 source="", hloc=""):
        self.name = name
        self.kima_id = str(kima_id)
        self.wikidata = wikidata
        self.rom = rom
        self.heb_name = heb_name
        self.source = source
        self.hloc = hloc


def collect_global_links(decisions: dict) -> list[Link]:
    """GLOBAL links from auto_confirmed.tsv, confirmed_priors.tsv, and global
    (non-per-mention) entries in kima_decisions.json."""
    links: list[Link] = []
    seen: set[tuple[str, str]] = set()

    def add(name, kima_id, **kw):
        name = norm(name)
        if not name or not kima_id:
            return
        key = (name, str(kima_id))
        if key in seen:
            return
        seen.add(key)
        links.append(Link(name, kima_id, **kw))

    if AUTO_CONFIRMED_TSV.exists():
        for r in csv.DictReader(open(AUTO_CONFIRMED_TSV, encoding="utf-8"),
                                delimiter="\t"):
            nm = r.get("name_heb") or r.get("name_rom") or ""
            # kind=authority → local_id is an existing H-LOC we trust as-is.
            hloc = r["local_id"] if r.get("kind") == "authority" else ""
            add(nm, r.get("kima_id", ""), wikidata=(r.get("wikidata_qid") or ""),
                rom=(r.get("kima_name_rom") or ""),
                heb_name=(r.get("kima_name_heb") or ""),
                source="auto_confirmed", hloc=hloc)
    if PRIORS_TSV.exists():
        for r in csv.DictReader(open(PRIORS_TSV, encoding="utf-8"),
                                delimiter="\t"):
            add(r.get("name", ""), r.get("kima_id", ""), source="priors")
    for name, v in decisions.items():
        if "mentions" in v:
            continue
        add(name, v.get("kima_id", ""), source="decision_global")
    return links


def collect_per_mention(decisions: dict) -> dict[str, dict]:
    """{norm(name): {rid: kima_id}} for per-mention decisions, plus the set of
    target kima_ids (so the authority place still gets created)."""
    out: dict[str, dict] = {}
    for name, v in decisions.items():
        if "mentions" not in v:
            continue
        rid_map = {rid: m.get("kima_id") for rid, m in v["mentions"].items()
                   if m.get("kima_id")}
        if rid_map:
            out[norm(name)] = rid_map
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Phase A — authority file
# ──────────────────────────────────────────────────────────────────────────────

def kima_url(kid: str) -> str:
    # Match the query-string form already used throughout the authority file.
    return f"https://data.geo-kima.org/Places/Details?id={kid}"


def wikidata_url(qid: str) -> str:
    return f"https://www.wikidata.org/wiki/{qid}"


def _has_idno(place: ET.Element, typ: str) -> bool:
    for idno in place.findall(f"{T}idno"):
        if (idno.get("type") or "").lower() == typ.lower():
            return True
    return False


def kima_num_in(place: ET.Element) -> str:
    """Return the Kima place number already on *place*, or ''."""
    for idno in place.findall(f"{T}idno"):
        if (idno.get("type") or "").lower() == "kima":
            kn = kima_num(idno.text or "")
            if kn:
                return kn
    return ""


def _add_idno(place: ET.Element, typ: str, text: str) -> None:
    el = ET.SubElement(place, f"{T}idno")
    el.set("type", typ)
    el.text = text


def apply_authority(root: ET.Element, links: list[Link],
                    per_mention_kima: dict[str, list[str]],
                    kima_lookup: dict, log: list[str]) -> dict[str, str]:
    """Ensure an authority place exists for every distinct kima_id.

    Returns ``{kima_id: H-LOC}``. Mutates *root*.
    """
    list_place = _find_list_place(root)
    next_num = _highest_hloc_num(root) + 1
    kima_to_hloc: dict[str, str] = {}
    created = added_idno = 0

    # Index existing places by id, by kima-number (robust to both URL forms),
    # and by name.
    by_id: dict[str, ET.Element] = {}
    kima_to_existing: dict[str, str] = {}
    name_to_place: dict[str, ET.Element] = {}
    for pl in root.iter(f"{T}place"):
        pid = pl.get(f"{X}id")
        by_id[pid] = pl
        for pn in pl.findall(f"{T}placeName"):
            name_to_place.setdefault(norm(pn.text or ""), pl)
        for idno in pl.findall(f"{T}idno"):
            if (idno.get("type") or "").lower() == "kima":
                kn = kima_num(idno.text or "")
                if kn:
                    kima_to_existing.setdefault(kn, pid)

    # All distinct kima_id -> representative Link (prefer one carrying an hloc).
    targets: dict[str, Link] = {}
    for lk in links:
        cur = targets.get(lk.kima_id)
        if cur is None or (lk.hloc and not cur.hloc):
            targets[lk.kima_id] = lk
    for name, kids in per_mention_kima.items():
        for kid in kids:
            targets.setdefault(str(kid), Link(name, kid, source="per_mention"))

    for kid, lk in targets.items():
        # 1. trusted explicit H-LOC (auto_confirmed authority rows)
        if lk.hloc and lk.hloc in by_id:
            kima_to_hloc[kid] = lk.hloc
            pl = by_id[lk.hloc]
            if kima_num_in(pl) != kid:
                _add_idno(pl, "Kima", kima_url(kid))
                added_idno += 1
                log.append(f"  +Kima idno {kid} → trusted {lk.hloc} ({lk.name})")
            continue
        # 2. an existing place already carries this kima number
        if kid in kima_to_existing:
            kima_to_hloc[kid] = kima_to_existing[kid]
            continue
        # 3. a same-name place exists; attach kima idno if it has none
        existing = name_to_place.get(norm(lk.name))
        if existing is not None and not _has_idno(existing, "Kima"):
            _add_idno(existing, "Kima", kima_url(kid))
            added_idno += 1
            hloc = existing.get(f"{X}id")
            kima_to_hloc[kid] = hloc
            log.append(f"  +Kima idno {kid} → existing {hloc} ({lk.name})")
            continue
        if existing is not None:  # name match but it already has a *different* kima
            log.append(f"  ! name '{lk.name}' matches {existing.get(f'{X}id')} which "
                       f"has a different Kima id — creating new place for {kid}")
        # 4. Create a new place.
        hloc = f"H-LOC_{next_num}"
        next_num += 1
        place = ET.SubElement(list_place, f"{T}place")
        place.set(f"{X}id", hloc)
        ET.SubElement(place, f"{T}placeName").text = lk.name
        # English/romanized name from kima
        rom = lk.rom or (kima_lookup.get(kid, {}).get("name_rom", "") if kima_lookup else "")
        if rom and norm(rom) != norm(lk.name):
            ET.SubElement(place, f"{T}placeName").text = rom
        _add_idno(place, "Kima", kima_url(kid))
        qid = lk.wikidata or (kima_lookup.get(kid, {}).get("wikidata", "") if kima_lookup else "")
        if qid:
            m = re.search(r"(Q\d+)", qid)
            if m:
                _add_idno(place, "Wikidata", wikidata_url(m.group(1)))
        kima_to_hloc[kid] = hloc
        created += 1
        log.append(f"  +new place {hloc} ← Kima {kid} ({lk.name}{' / '+rom if rom else ''})")

    log.append(f"  authority: {created} new places, {added_idno} idno additions, "
               f"{len(kima_to_hloc)} kima_ids resolved")
    return kima_to_hloc


def remove_galicia_dup(root: ET.Element, log: list[str]) -> None:
    dup, keep = GALICIA_DUP
    list_place = _find_list_place(root)
    for pl in list(list_place.findall(f"{T}place")):
        if pl.get(f"{X}id") == dup:
            list_place.remove(pl)
            log.append(f"  removed duplicate {dup} (Galicia, wrong Q485018) — "
                       f"kept {keep}")
            return


# ──────────────────────────────────────────────────────────────────────────────
# Phase B — edition XML
# ──────────────────────────────────────────────────────────────────────────────

def _parent_map(root):
    return {c: p for p in root.iter() for c in p}


def apply_editions(global_map: dict[str, str],
                   per_mention: dict[str, dict[str, str]],
                   kima_to_hloc: dict[str, str],
                   dry_run: bool, log: list[str]) -> int:
    """Write ref="#H-LOC" into edition placeNames. Returns count written."""
    files = []
    for g in EDITION_GLOBS:
        files += sorted(glob.glob(g))
    total = 0
    conflicts: list[str] = []
    dup, keep = GALICIA_DUP

    for path in files:
        edition = Path(path).stem
        try:
            tree = ET.parse(path)
        except ET.ParseError as e:
            log.append(f"  ! parse error {edition}: {e}")
            continue
        root = tree.getroot()
        counter: dict[str, int] = collections.defaultdict(int)
        changed = 0

        for pn in root.iter(f"{T}placeName"):
            raw = pn.text or ""
            ntext = norm(raw)
            if not ntext:
                continue
            counter[ntext] += 1
            idx = counter[ntext]
            rid = f"{edition}#{idx}"

            # Repoint any stale ref at the removed Galicia dup.
            if pn.get("ref", "").lstrip("#") == dup:
                if not dry_run:
                    pn.set("ref", f"#{keep}")
                changed += 1
                continue

            target_hloc = None
            # 1. per-mention decision (precise)
            pm = per_mention.get(ntext)
            if pm and rid in pm:
                target_hloc = kima_to_hloc.get(str(pm[rid]))
            # 2. global name decision
            if target_hloc is None and ntext in global_map:
                target_hloc = global_map[ntext]
            # 3. prefix-stripped global
            if target_hloc is None:
                pfx, bare = _strip_hebrew_prefix(ntext)
                if pfx and bare in global_map:
                    target_hloc = global_map[bare]

            if not target_hloc:
                continue
            cur = pn.get("ref", "").lstrip("#")
            if cur == target_hloc:
                continue  # already linked correctly
            if cur and cur != target_hloc:
                # Never override prior curation — surface as a conflict instead.
                conflicts.append(f"{edition}\t{rid}\t{raw}\t{cur}\t{target_hloc}")
                continue
            if not dry_run:
                pn.set("ref", f"#{target_hloc}")
            changed += 1

        if changed:
            log.append(f"  {'[dry] ' if dry_run else ''}{edition}: {changed} placeName ref(s)")
            total += changed
            if not dry_run:
                ET.register_namespace("", TEI_NS)
                ET.register_namespace("xml", XML_NS)
                tree.write(path, encoding="unicode", xml_declaration=True)

    if conflicts:
        out = KIMATCH_DIR / "apply_conflicts.tsv"
        log.append(f"  ! {len(conflicts)} ref conflicts (existing≠decision) — "
                   f"left untouched, logged to {out.name}")
        if not dry_run:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write("edition\trid\tsurface\tcurrent_ref\tdecision_ref\n")
                fh.write("\n".join(conflicts) + "\n")
        else:
            for c in conflicts[:8]:
                log.append("    conflict: " + c.replace("\t", " | "))
            if len(conflicts) > 8:
                log.append(f"    … and {len(conflicts) - 8} more")
    return total


# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True)
    g.add_argument("--apply", dest="dry_run", action="store_false")
    ap.add_argument("--decisions", help="path to kima_decisions.json override")
    ap.add_argument("--skip-commit", action="store_true")
    ap.add_argument("--skip-db", action="store_true",
                    help="don't regenerate the matching DB")
    args = ap.parse_args()
    dry = args.dry_run

    print("═" * 70)
    print(f"apply_kima_links — {'DRY RUN' if dry else 'APPLY'}")
    print("═" * 70)

    decisions = fetch_decisions(args.decisions)
    global_links = collect_global_links(decisions)
    per_mention = collect_per_mention(decisions)
    per_mention_kima = {n: list({v for v in m.values()})
                        for n, m in per_mention.items()}
    print(f"  {len(global_links)} global links, "
          f"{len(per_mention)} per-mention names "
          f"({sum(len(m) for m in per_mention.values())} mentions)")

    tree = ET.parse(AUTHORITY_XML_PATH)
    root = tree.getroot()
    kima_lookup = _load_kima_lookup()

    log: list[str] = []
    print("\n── Phase A: authority ──")
    kima_to_hloc = apply_authority(root, global_links, per_mention_kima,
                                   kima_lookup, log)
    remove_galicia_dup(root, log)

    global_map = {lk.name: kima_to_hloc[lk.kima_id]
                  for lk in global_links if lk.kima_id in kima_to_hloc}

    if not dry:
        ET.register_namespace("", TEI_NS)
        ET.register_namespace("xml", XML_NS)
        tree.write(AUTHORITY_XML_PATH, encoding="unicode", xml_declaration=True)
        print(f"  ✓ wrote {AUTHORITY_XML_PATH}")

    print("\n── Phase B: editions ──")
    n_edits = apply_editions(global_map, per_mention, kima_to_hloc, dry, log)

    print("\n".join(log))
    print(f"\n  total edition refs: {n_edits}")

    if not dry and not args.skip_db:
        print(f"\n  regenerating matching DB ({Path(GEN_SCRIPT).name}) …")
        subprocess.check_call([sys.executable, GEN_SCRIPT])

    if not dry and not args.skip_commit:
        msg = ("feat: apply confirmed Kima links back to editions + authority\n\n"
               f"{n_edits} placeName refs; "
               f"{len(kima_to_hloc)} kima ids resolved; Galicia dup removed.\n\n"
               "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>")
        subprocess.check_call(["git", "-C", str(_PROJECT), "add", "-A"])
        subprocess.check_call(["git", "-C", str(_PROJECT), "commit", "-m", msg])
        print("  ✓ committed")

    print("\nDone." + ("  (dry run — nothing written)" if dry else ""))


if __name__ == "__main__":
    main()
