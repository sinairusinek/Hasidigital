#!/usr/bin/env python3
"""
Deduplicate place entries in the TEI authority XML.

Finds groups of <place> elements that share external identifiers (Kima,
Wikidata, Tsadikim, etc.), merges them into a single canonical entry
(lowest H-LOC ID), and rewrites edition ref attributes.

Usage:
    python dedup_places.py              # apply changes
    python dedup_places.py --dry-run    # report only, no file changes

Also importable:
    from dedup_places import find_duplicate_groups, merge_groups
"""

import math
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ── Paths & constants ────────────────────────────────────────────────────────

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("", TEI_NS)
ET.register_namespace("xml", XML_NS)

# False-duplicate auto-fix: remove the Kima from H-LOC_389 (Turňa) which
# incorrectly shares Kima 765 with H-LOC_161 (Tarnów).
FALSE_DUPE_FIX = {"H-LOC_389": "Kima"}

# Maximum distance (km) between coordinates before flagging as false duplicate
MAX_MERGE_DISTANCE_KM = 50.0


def _default_paths():
    script_dir = Path(__file__).parent
    auth_dir = script_dir.parent
    project_dir = auth_dir.parent
    authority_xml = auth_dir / "Authorities2026-01-14.xml"
    editions_dir = project_dir / "editions" / "online"
    return authority_xml, editions_dir


# ── Helpers ──────────────────────────────────────────────────────────────────

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _hloc_sort_key(place_id: str) -> int:
    """Extract numeric part from H-LOC_NNN for sorting."""
    m = re.match(r"H-LOC_(\d+)", place_id)
    return int(m.group(1)) if m else 999999


def _normalize_id_type(key: str) -> str:
    return key.strip().title()


def _get_place_coords(place_elem) -> Optional[Tuple[float, float]]:
    geo = place_elem.find(f"{{{TEI_NS}}}location/{{{TEI_NS}}}geo")
    if geo is not None and geo.text:
        try:
            lat, lon = geo.text.strip().split(",")
            return float(lat), float(lon)
        except (ValueError, IndexError):
            pass
    return None


def _get_place_names(place_elem) -> List[str]:
    names = []
    for pn in place_elem.findall(f"{{{TEI_NS}}}placeName"):
        text = (pn.text or "").strip()
        if text and text not in names:
            names.append(text)
    return names


def _get_place_idnos(place_elem) -> Dict[str, str]:
    """Return {normalized_type: value} for all <idno> children."""
    result = {}
    for idno in place_elem.findall(f"{{{TEI_NS}}}idno"):
        t = _normalize_id_type(idno.get("type", "unknown"))
        v = (idno.text or "").strip()
        if v:
            result[t] = v
    return result


# ── Union-Find for transitive grouping ───────────────────────────────────────

class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def groups(self) -> Dict:
        """Return {root: [members]}."""
        result = {}
        for item in self.parent:
            root = self.find(item)
            result.setdefault(root, []).append(item)
        return result


# ── Phase 1: Fix known false duplicates in-place ────────────────────────────

def _apply_false_dupe_fixes(root):
    """Remove specific <idno> entries that are known false duplicates."""
    fixes_applied = []
    for place_elem in root.findall(f".//{{{TEI_NS}}}place"):
        xml_id = place_elem.get(f"{{{XML_NS}}}id") or place_elem.get("id")
        if xml_id not in FALSE_DUPE_FIX:
            continue
        idno_type_to_remove = FALSE_DUPE_FIX[xml_id]
        for idno in list(place_elem.findall(f"{{{TEI_NS}}}idno")):
            t = _normalize_id_type(idno.get("type", ""))
            if t == idno_type_to_remove:
                place_elem.remove(idno)
                fixes_applied.append(
                    f"Removed {idno_type_to_remove} from {xml_id}"
                )
    return fixes_applied


# ── Phase 2: Find duplicate groups ──────────────────────────────────────────

def find_duplicate_groups(xml_path: str) -> Tuple[List[Dict], List[str]]:
    """
    Scan the authority XML for place entries sharing external identifiers.

    Returns:
        (groups, false_dupe_fixes)

        groups: list of dicts, each with:
            canonical_id: str          — lowest H-LOC ID in group
            merge_ids: list[str]       — IDs to merge into canonical
            shared_identifiers: dict   — {source: uri} that linked them
            all_names: list[str]       — union of all placeName texts
            flag: None | str           — "coordinates_differ" if flagged

        false_dupe_fixes: list of str  — descriptions of auto-fixes applied
    """
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    # Apply known false-dupe fixes before scanning
    false_dupe_fixes = _apply_false_dupe_fixes(root)

    # Collect place data
    place_elems = {}  # id -> ET element
    place_coords = {}  # id -> (lat, lon) or None
    place_idnos = {}   # id -> {norm_type: value}
    place_names = {}   # id -> [name texts]

    for pe in root.findall(f".//{{{TEI_NS}}}place"):
        pid = pe.get(f"{{{XML_NS}}}id") or pe.get("id")
        if not pid or not pid.startswith("H-LOC_"):
            continue
        place_elems[pid] = pe
        place_coords[pid] = _get_place_coords(pe)
        place_idnos[pid] = _get_place_idnos(pe)
        place_names[pid] = _get_place_names(pe)

    # Build URI -> [place_ids] index
    uri_to_ids = {}  # (source, uri) -> [ids]
    for pid, idnos in place_idnos.items():
        for source, uri in idnos.items():
            uri_to_ids.setdefault((source, uri), []).append(pid)

    # Union-Find: transitively group places sharing any URI
    uf = UnionFind()
    for (source, uri), ids in uri_to_ids.items():
        if len(ids) < 2:
            continue
        for i in range(1, len(ids)):
            uf.union(ids[0], ids[i])

    # Build group dicts
    groups = []
    for _root_id, members in uf.groups().items():
        if len(members) < 2:
            continue

        # Sort by H-LOC number, pick lowest as canonical
        members.sort(key=_hloc_sort_key)
        canonical = members[0]
        merge_ids = members[1:]

        # Collect shared identifiers that caused the grouping
        shared = {}
        for source, uri in uri_to_ids:
            ids_for_uri = uri_to_ids[(source, uri)]
            if any(m in ids_for_uri for m in members) and len(ids_for_uri) > 1:
                shared[source] = uri

        # Collect all names
        all_names = []
        for m in members:
            for n in place_names.get(m, []):
                if n not in all_names:
                    all_names.append(n)

        # Check coordinate distance — flag if coords differ significantly
        flag = None
        coords_list = [
            place_coords[m] for m in members if place_coords.get(m)
        ]
        if len(coords_list) >= 2:
            max_dist = 0.0
            for i in range(len(coords_list)):
                for j in range(i + 1, len(coords_list)):
                    d = _haversine_km(
                        coords_list[i][0], coords_list[i][1],
                        coords_list[j][0], coords_list[j][1],
                    )
                    max_dist = max(max_dist, d)
            if max_dist > MAX_MERGE_DISTANCE_KM:
                flag = f"coordinates_differ ({max_dist:.0f} km apart)"

        groups.append({
            "canonical_id": canonical,
            "merge_ids": merge_ids,
            "shared_identifiers": shared,
            "all_names": all_names,
            "all_ids": members,
            "flag": flag,
        })

    groups.sort(key=lambda g: _hloc_sort_key(g["canonical_id"]))
    return groups, false_dupe_fixes


# ── Phase 3: Merge groups ───────────────────────────────────────────────────

def merge_groups(
    xml_path: str,
    editions_dir: str,
    groups: List[Dict],
    dry_run: bool = False,
) -> Dict:
    """
    Merge duplicate place groups in the authority XML and update edition refs.

    Only processes groups where flag is None (not flagged for manual review).

    Returns a report dict.
    """
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    # Re-apply false-dupe fixes (idempotent); capture what was fixed
    false_dupe_fixes = _apply_false_dupe_fixes(root)
    fixes_applied = bool(false_dupe_fixes)

    # Index place elements by ID
    list_place = root.find(f".//{{{TEI_NS}}}listPlace")
    place_by_id = {}
    for pe in root.findall(f".//{{{TEI_NS}}}place"):
        pid = pe.get(f"{{{XML_NS}}}id") or pe.get("id")
        if pid:
            place_by_id[pid] = pe

    # Build merge map: old_id -> canonical_id (skip flagged groups)
    merge_map = {}  # old_id -> canonical_id
    groups_merged = 0
    places_removed = 0

    for g in groups:
        if g.get("flag"):
            continue  # skip flagged groups

        canonical_id = g["canonical_id"]
        canonical_elem = place_by_id.get(canonical_id)
        if canonical_elem is None:
            continue

        for old_id in g["merge_ids"]:
            old_elem = place_by_id.get(old_id)
            if old_elem is None:
                continue

            merge_map[old_id] = canonical_id

            # Merge names: add unique placeName elements to canonical
            existing_names = set()
            for pn in canonical_elem.findall(f"{{{TEI_NS}}}placeName"):
                existing_names.add((pn.text or "").strip())

            for pn in old_elem.findall(f"{{{TEI_NS}}}placeName"):
                text = (pn.text or "").strip()
                if text and text not in existing_names:
                    new_pn = ET.SubElement(canonical_elem, f"{{{TEI_NS}}}placeName")
                    # Copy attributes
                    for k, v in pn.attrib.items():
                        new_pn.set(k, v)
                    new_pn.text = pn.text
                    new_pn.tail = pn.tail
                    existing_names.add(text)

            # Merge coordinates: take from old if canonical lacks them
            if _get_place_coords(canonical_elem) is None:
                old_loc = old_elem.find(f"{{{TEI_NS}}}location")
                if old_loc is not None:
                    canonical_elem.append(old_loc)

            # Merge idno: add any missing identifier types
            existing_idno_keys = set()
            for idno in canonical_elem.findall(f"{{{TEI_NS}}}idno"):
                key = _normalize_id_type(idno.get("type", ""))
                val = (idno.text or "").strip()
                existing_idno_keys.add((key, val))

            for idno in old_elem.findall(f"{{{TEI_NS}}}idno"):
                key = _normalize_id_type(idno.get("type", ""))
                val = (idno.text or "").strip()
                if val and (key, val) not in existing_idno_keys:
                    new_idno = ET.SubElement(canonical_elem, f"{{{TEI_NS}}}idno")
                    new_idno.set("type", idno.get("type", "unknown"))
                    new_idno.text = idno.text
                    existing_idno_keys.add((key, val))

            # Remove old place element
            if list_place is not None:
                try:
                    list_place.remove(old_elem)
                except ValueError:
                    pass  # might be nested differently
            places_removed += 1

        groups_merged += 1

    # ── Rewrite edition refs ─────────────────────────────────────────────
    refs_rewritten = {}  # filename -> count

    if merge_map:
        editions_path = Path(str(editions_dir))
        if editions_path.is_dir():
            for xml_file in sorted(editions_path.glob("*.xml")):
                ed_tree = ET.parse(str(xml_file))
                ed_root = ed_tree.getroot()
                count = 0

                for pn in ed_root.findall(f".//{{{TEI_NS}}}placeName"):
                    ref = pn.get("ref", "")
                    if not ref:
                        continue
                    old_id = ref.lstrip("#")
                    if old_id in merge_map:
                        pn.set("ref", "#" + merge_map[old_id])
                        count += 1

                if count > 0:
                    refs_rewritten[xml_file.name] = count
                    if not dry_run:
                        ed_tree.write(str(xml_file), encoding="utf-8",
                                      xml_declaration=True)

    # ── Write authority XML ──────────────────────────────────────────────
    # Write if any merges happened OR if false-dupe fixes were applied
    # (fixes permanently remove bad <idno> elements even with nothing to merge)
    xml_changed = groups_merged > 0 or fixes_applied
    if not dry_run and xml_changed:
        tree.write(str(xml_path), encoding="utf-8", xml_declaration=True)

    flagged = [g for g in groups if g.get("flag")]

    return {
        "groups_merged": groups_merged,
        "places_removed": places_removed,
        "refs_rewritten": refs_rewritten,
        "total_refs_rewritten": sum(refs_rewritten.values()),
        "flagged": flagged,
        "merge_map": merge_map,
        "false_dupe_fixes_applied": false_dupe_fixes,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    dry_run = "--dry-run" in sys.argv

    xml_path, editions_dir = _default_paths()

    if not xml_path.exists():
        print(f"ERROR: Authority XML not found: {xml_path}")
        sys.exit(1)

    print(f"{'DRY RUN — ' if dry_run else ''}Deduplicating places in {xml_path.name}")
    print()

    # Phase 1: Find groups
    groups, fixes = find_duplicate_groups(str(xml_path))

    if fixes:
        print("False-duplicate auto-fixes:")
        for f in fixes:
            print(f"  {f}")
        print()

    print(f"Found {len(groups)} duplicate group(s)")
    mergeable = [g for g in groups if not g.get("flag")]
    flagged = [g for g in groups if g.get("flag")]
    print(f"  Mergeable: {len(mergeable)}")
    print(f"  Flagged for review: {len(flagged)}")
    print()

    # Show groups
    for i, g in enumerate(groups, 1):
        flag_str = f"  ⚠ {g['flag']}" if g["flag"] else ""
        ids = ", ".join(g["all_ids"])
        names_preview = ", ".join(g["all_names"][:5])
        if len(g["all_names"]) > 5:
            names_preview += f" (+{len(g['all_names']) - 5} more)"
        print(f"  Group {i}: canonical={g['canonical_id']}  "
              f"merge={g['merge_ids']}{flag_str}")
        print(f"    Names: {names_preview}")
        shared = ", ".join(f"{k}={v}" for k, v in g["shared_identifiers"].items())
        print(f"    Shared: {shared}")
        print()

    if not mergeable:
        print("Nothing to merge.")
        return

    # Phase 2: Merge
    report = merge_groups(str(xml_path), str(editions_dir), groups, dry_run=dry_run)

    print("=" * 60)
    print(f"{'DRY RUN ' if dry_run else ''}Results:")
    print(f"  Groups merged: {report['groups_merged']}")
    print(f"  Places removed: {report['places_removed']}")
    print(f"  Edition refs rewritten: {report['total_refs_rewritten']}")
    if report["refs_rewritten"]:
        for fname, cnt in sorted(report["refs_rewritten"].items()):
            print(f"    {fname}: {cnt} ref(s)")
    if report["flagged"]:
        print(f"\n  ⚠ {len(report['flagged'])} group(s) flagged — need manual review:")
        for g in report["flagged"]:
            print(f"    {g['all_ids']}: {g['flag']}")

    if not dry_run and (report["groups_merged"] > 0 or report["false_dupe_fixes_applied"]):
        print(f"\nAuthority XML updated: {xml_path}")
        if report["false_dupe_fixes_applied"]:
            print("  (false-dupe identifier fixes persisted to XML)")
        print("Run generate_matching_db.py to regenerate the matching database.")


if __name__ == "__main__":
    main()
