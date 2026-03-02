"""
Edition Place-Name Linker
A 4-step wizard for matching unlinked place names in editions
to the authorities matching database.

Steps:
  1. Select an edition from editions/incoming/, see linked vs unlinked summary
  2. Review auto-matches of unlinked names against the matching DB
  3. Resolve conflicts and assign IDs to new places
  4. Save updates to matching DB (+ Authorities.xml for new places) and commit
"""
import json
import sys
import os
import xml.etree.ElementTree as ET

import streamlit as st
import pandas as pd

# Allow imports from the parent integration_tool directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import (
    AUTH_DIR, PROJECT_DIR, EDITIONS_INCOMING,
    MATCHING_DB_PATH, DISPLAY_XML_PATH, SKIPPED_JSON_PATH,
    TEI_NS, XML_NS,
)
from utils import next_hloc_id

# ── Session state helpers ────────────────────────────────────────────────────

def _init():
    defaults = {
        "el_step": 1,
        "el_db": None,
        "el_db_loaded": False,
        "el_edition_file": None,
        "el_edition_name": "",
        "el_linked_places": [],
        "el_unlinked_places": [],
        "el_match_results": [],
        "el_skipped_json_path": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()
ss = st.session_state

# ── Auto-load the matching DB ────────────────────────────────────────────────

if not ss.get("el_db_loaded"):
    try:
        with open(MATCHING_DB_PATH, "r", encoding="utf-8") as f:
            ss.el_db = json.load(f)
        ss.el_db_loaded = True
    except Exception as _e:
        ss.el_db_loaded = False
        ss.el_db_error = str(_e)


def _go(step: int):
    ss.el_step = step


# ── Matching helpers ─────────────────────────────────────────────────────────

def _build_variant_index(db):
    """Build a lookup: variant_name -> place dict from the matching DB."""
    index = {}
    for place in db["places"]:
        for name in place.get("names_he", []) + place.get("names_en", []):
            if name and name not in index:
                index[name] = place
    return index


def _detect_lang(text: str) -> str:
    """Detect whether text is Hebrew or Latin."""
    hebrew_chars = sum(1 for c in text if '\u0590' <= c <= '\u05FF')
    return "he" if hebrew_chars > 0 else "en"


def _elem_full_text(elem):
    """Return the full text content of an element including all descendants."""
    return "".join(elem.itertext()).strip()


def _build_parent_map(root):
    """Build a child -> parent mapping for the entire XML tree."""
    return {child: parent for parent in root.iter() for child in parent}


def _find_parent_p(elem, parent_map):
    """Find the nearest ancestor <p> element for *elem* using a parent map."""
    current = elem
    while current is not None:
        current = parent_map.get(current)
        if current is not None and current.tag == f"{{{TEI_NS}}}p":
            return current
    return None


def _parse_edition_places(edition_path):
    """
    Parse an edition XML and extract all placeName tags.
    Returns (linked, unlinked) lists.
    Each unlinked entry includes a 'context' field with the full parent <p> text.
    """
    tree = ET.parse(edition_path)
    root = tree.getroot()
    parent_map = _build_parent_map(root)

    linked = []
    unlinked = []

    for idx, pn_elem in enumerate(root.findall(f".//{{{TEI_NS}}}placeName")):
        ref = pn_elem.get("ref", "")
        text = (pn_elem.text or "").strip()

        if not text:
            continue

        entry = {
            "text": text,
            "index": idx,
            "type": pn_elem.get("type", ""),
            "ana": pn_elem.get("ana", ""),
        }

        if ref:
            entry["ref_id"] = ref.lstrip("#")
            linked.append(entry)
        else:
            parent_p = _find_parent_p(pn_elem, parent_map)
            entry["context"] = _elem_full_text(parent_p) if parent_p else ""
            unlinked.append(entry)

    return linked, unlinked


def _match_unlinked(unlinked, variant_index):
    """
    Try to match each unlinked place name against the variant index.
    Returns list of result dicts.  Each result carries a 'contexts' list
    with the parent-paragraph text of every occurrence.
    """
    results = []

    seen_texts = {}
    for entry in unlinked:
        t = entry["text"]
        if t not in seen_texts:
            seen_texts[t] = {"indices": [], "contexts": []}
        seen_texts[t]["indices"].append(entry["index"])
        ctx = entry.get("context", "")
        if ctx and ctx not in seen_texts[t]["contexts"]:
            seen_texts[t]["contexts"].append(ctx)

    for text, info in seen_texts.items():
        result = {
            "text": text,
            "indices": info["indices"],
            "contexts": info["contexts"],
            "count": len(info["indices"]),
            "status": "new",
            "matched_place": None,
            "resolution": "",
            "assigned_id": None,
        }

        if text in variant_index:
            place = variant_index[text]
            result["status"] = "matched"
            result["matched_place"] = place
            result["resolution"] = "accept"

        results.append(result)

    results.sort(key=lambda r: (0 if r["status"] == "matched" else 1, r["text"]))
    return results


# ── Skipped places JSON ─────────────────────────────────────────────────────

def _load_skipped_json():
    """Load existing skipped_places.json or return empty list."""
    if os.path.exists(SKIPPED_JSON_PATH):
        with open(SKIPPED_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_skipped_json(skipped_list):
    """Write the full skipped places list to JSON."""
    with open(SKIPPED_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(skipped_list, f, ensure_ascii=False, indent=2)


def _append_skipped_places(results, edition_name):
    """
    Append newly skipped places to the persistent skipped_places.json.
    Each entry records the place name, source edition, paragraph context,
    and a timestamp.  Returns the path if anything was written, else None.
    """
    import datetime as _dt

    new_skips = []
    for r in results:
        if r["resolution"] != "skip":
            continue
        entry = {
            "name": r["text"],
            "source": edition_name,
            "contexts": r.get("contexts", []),
            "occurrences": r["count"],
            "skipped_at": _dt.datetime.now().isoformat(),
        }
        if r["matched_place"]:
            mp = r["matched_place"]
            entry["suggested_id"] = mp["id"]
            entry["suggested_name_en"] = mp.get("primary_name_en", "")
            entry["suggested_name_he"] = mp.get("primary_name_he", "")
        new_skips.append(entry)

    if not new_skips:
        return None

    existing = _load_skipped_json()
    existing.extend(new_skips)
    _save_skipped_json(existing)
    return SKIPPED_JSON_PATH


# ── Sidebar progress ────────────────────────────────────────────────────────

STEPS = ["1 \u00b7 Select Edition", "2 \u00b7 Review Matches", "3 \u00b7 Resolve Issues", "4 \u00b7 Save & Commit"]

with st.sidebar:
    st.markdown("---")
    st.markdown("**Edition Linker Progress**")
    for i, label in enumerate(STEPS, start=1):
        marker = "\u2705" if ss.el_step > i else ("\u25b6\ufe0f" if ss.el_step == i else "\u2b1c")
        st.markdown(f"{marker} {label}")
    st.markdown("---")
    if ss.el_step > 1:
        if st.button("\u2190 Back", key="el_back"):
            _go(ss.el_step - 1)


# ═════════════════════════════════════════════════════════════════════════════
# STEP 1 — Select edition
# ═════════════════════════════════════════════════════════════════════════════

if ss.el_step == 1:
    st.header("Step 1 \u00b7 Select an edition and review place names")

    if ss.el_db_loaded:
        db = ss.el_db
        place_count = len(db["places"])
        places_with_he = sum(1 for p in db["places"] if p.get("names_he"))
        st.success(
            f"Matching DB loaded: **{place_count}** places "
            f"({places_with_he} with Hebrew variants)"
        )
    else:
        st.error(f"Could not load matching DB: {ss.get('el_db_error', 'unknown error')}")
        st.info(f"Expected path: `{MATCHING_DB_PATH}`")
        st.stop()

    edition_files = sorted([
        f for f in os.listdir(EDITIONS_INCOMING)
        if f.endswith(".xml")
    ])

    if not edition_files:
        st.warning(f"No XML files found in `{EDITIONS_INCOMING}`")
        st.stop()

    selected = st.selectbox(
        "Select an edition file",
        options=edition_files,
        key="el_edition_selector",
    )

    if selected:
        edition_path = os.path.join(EDITIONS_INCOMING, selected)

        try:
            linked, unlinked = _parse_edition_places(edition_path)
            ss.el_edition_file = edition_path
            ss.el_edition_name = selected
            ss.el_linked_places = linked
            ss.el_unlinked_places = unlinked

            st.markdown("---")

            c1, c2, c3 = st.columns(3)
            c1.metric("Total place names", len(linked) + len(unlinked))
            c2.metric("\u2705 Already linked", len(linked))
            c3.metric("\u2753 Unlinked", len(unlinked))

            if linked:
                with st.expander(f"\u2705 Already linked ({len(linked)})", expanded=False):
                    rows = []
                    for entry in linked:
                        rows.append({
                            "Text": entry["text"],
                            "Ref ID": entry["ref_id"],
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)

            if unlinked:
                with st.expander(f"\u2753 Unlinked place names ({len(unlinked)})", expanded=True):
                    from collections import Counter
                    name_counts = Counter(e["text"] for e in unlinked)
                    rows = [{"Name": name, "Occurrences": count}
                            for name, count in name_counts.most_common()]
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)

                if st.button("\u25b6 Run matching \u2192", type="primary", key="el_run"):
                    _go(2)
                    st.rerun()
            else:
                st.info("All place names in this edition are already linked!")

        except Exception as e:
            st.error(f"Could not parse edition: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# STEP 2 — Review matches
# ═════════════════════════════════════════════════════════════════════════════

elif ss.el_step == 2:
    st.header("Step 2 \u00b7 Review matching results")

    if not ss.el_match_results:
        with st.spinner("Matching unlinked place names against DB..."):
            variant_index = _build_variant_index(ss.el_db)
            results = _match_unlinked(ss.el_unlinked_places, variant_index)
            ss.el_match_results = results

    results = ss.el_match_results
    matched = [r for r in results if r["status"] == "matched"]
    new_recs = [r for r in results if r["status"] == "new"]

    total_matched_occ = sum(r["count"] for r in matched)
    total_new_occ = sum(r["count"] for r in new_recs)

    m1, m2, m3 = st.columns(3)
    m1.metric("\u2705 Matched (unique names)", len(matched))
    m2.metric("\U0001f195 Unmatched (unique names)", len(new_recs))
    m3.metric("\U0001f4ca Coverage", f"{total_matched_occ}/{total_matched_occ + total_new_occ}")

    st.markdown("---")

    with st.expander(f"\u2705 Matched ({len(matched)} unique names, {total_matched_occ} occurrences)", expanded=False):
        rows = []
        for r in matched:
            mp = r["matched_place"]
            rows.append({
                "Edition name": r["text"],
                "Matched ID": mp["id"],
                "Authority name (en)": mp.get("primary_name_en", ""),
                "Authority name (he)": mp.get("primary_name_he", ""),
                "Occurrences": r["count"],
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

    with st.expander(f"\U0001f195 Unmatched ({len(new_recs)} unique names, {total_new_occ} occurrences)", expanded=True):
        rows = []
        for r in new_recs:
            rows.append({
                "Edition name": r["text"],
                "Occurrences": r["count"],
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

    col_l, col_r = st.columns(2)
    with col_l:
        if st.button("\u2190 Back to edition selection", key="el_back_2"):
            ss.el_match_results = []
            _go(1)
            st.rerun()
    with col_r:
        if st.button("\u25b6 Resolve issues \u2192", type="primary", key="el_resolve"):
            _go(3)
            st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# STEP 3 — Resolve conflicts and assign IDs
# ═════════════════════════════════════════════════════════════════════════════

elif ss.el_step == 3:
    st.header("Step 3 \u00b7 Resolve unmatched names and assign IDs")

    results = ss.el_match_results
    db = ss.el_db

    existing_ids = [p["id"] for p in db["places"]]
    for r in results:
        if r.get("assigned_id"):
            existing_ids.append(r["assigned_id"])

    new_recs = [r for r in results if r["status"] == "new"]
    if new_recs:
        st.subheader(f"\U0001f195 {len(new_recs)} unmatched place name(s)")
        st.markdown("For each, choose to **skip** or **create a new place** in the authority.")

        for i, r in enumerate(new_recs):
            with st.expander(f"**{r['text']}** ({r['count']}x)", expanded=True):
                action = st.radio(
                    "Action",
                    options=["skip", "new_entity"],
                    format_func=lambda x: {
                        "skip": "\u23ed Skip (don't add to authority)",
                        "new_entity": "\u2795 Create new place in authority",
                    }[x],
                    key=f"el_new_action_{i}",
                    index=0 if r["resolution"] != "new_entity" else 1,
                )
                r["resolution"] = action

                if action == "new_entity":
                    suggested = next_hloc_id(existing_ids)
                    assigned = st.text_input(
                        "New Place ID",
                        value=r.get("assigned_id") or suggested,
                        key=f"el_new_id_{i}",
                    )
                    r["assigned_id"] = assigned
                    if assigned and assigned not in existing_ids:
                        existing_ids.append(assigned)
    else:
        st.info("All unlinked names were matched \u2014 nothing to resolve.")

    matched = [r for r in results if r["status"] == "matched"]
    if matched:
        st.markdown("---")
        st.subheader(f"\u2705 {len(matched)} matched name(s) \u2014 will add refs to edition")
        st.markdown("These will add variant names to the matching DB and write `ref` attributes to the edition XML.")

        with st.expander("Review matched names", expanded=False):
            rows = []
            for r in matched:
                mp = r["matched_place"]
                rows.append({
                    "Edition name": r["text"],
                    "\u2192 Authority": f"{mp['id']} ({mp.get('primary_name_en', '')})",
                    "Occurrences": r["count"],
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

    st.markdown("---")
    if st.button("\u25b6 Save & commit \u2192", type="primary", key="el_save"):
        # Save skipped places now, before the git commit in Step 4
        ss.el_skipped_json_path = _append_skipped_places(ss.el_match_results, ss.el_edition_name)
        _go(4)
        st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# STEP 4 — Save and commit
# ═════════════════════════════════════════════════════════════════════════════

elif ss.el_step == 4:
    st.header("Step 4 \u00b7 Save and commit")

    import datetime
    import subprocess

    results = ss.el_match_results
    db = ss.el_db
    edition_name = ss.el_edition_name

    accepted_matches = [r for r in results if r["status"] == "matched" and r["resolution"] == "accept"]
    new_places = [r for r in results if r["resolution"] == "new_entity" and r.get("assigned_id")]
    skipped = [r for r in results if r["resolution"] == "skip"]

    c1, c2, c3 = st.columns(3)
    c1.metric("DB updates (variants)", len(accepted_matches))
    c2.metric("New places to add", len(new_places))
    c3.metric("Skipped", len(skipped))

    if not accepted_matches and not new_places:
        st.warning("Nothing to save \u2014 all names were skipped.")
    else:
        summary_rows = []
        for r in accepted_matches:
            mp = r["matched_place"]
            summary_rows.append({
                "Action": "Update DB",
                "Name": r["text"],
                "Place ID": mp["id"],
                "Occurrences": r["count"],
            })
        for r in new_places:
            summary_rows.append({
                "Action": "New place",
                "Name": r["text"],
                "Place ID": r["assigned_id"],
                "Occurrences": r["count"],
            })
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)

        st.markdown("---")

        default_msg = (
            f"Link places in {edition_name}: "
            f"{len(accepted_matches)} matched, {len(new_places)} new"
        )
        commit_msg = st.text_input("Commit message", value=default_msg, key="el_commit_msg")

        if st.button("\U0001f4be Save and commit", type="primary", key="el_commit"):
            with st.spinner("Updating matching DB and committing..."):
                # 1. Update JSON matching DB
                place_by_id = {p["id"]: p for p in db["places"]}

                for r in accepted_matches:
                    mp_id = r["matched_place"]["id"]
                    if mp_id in place_by_id:
                        place = place_by_id[mp_id]
                        variant = r["text"]
                        lang = _detect_lang(variant)

                        name_list = place["names_he"] if lang == "he" else place["names_en"]
                        if variant not in name_list:
                            name_list.append(variant)

                        if lang == "he" and place.get("primary_name_he") == "(to be updated)":
                            place["primary_name_he"] = variant

                for r in new_places:
                    variant = r["text"]
                    lang = _detect_lang(variant)
                    new_place = {
                        "id": r["assigned_id"],
                        "primary_name_he": variant if lang == "he" else "(to be updated)",
                        "primary_name_en": variant if lang == "en" else "Unknown",
                        "names_he": [variant] if lang == "he" else [],
                        "names_en": [variant] if lang == "en" else [],
                        "coordinates": None,
                        "identifiers": {},
                        "notes": f"First seen in {edition_name}",
                        "status": "unidentified",
                    }
                    db["places"].append(new_place)

                db["meta"]["generated"] = datetime.datetime.now().isoformat()

                with open(MATCHING_DB_PATH, "w", encoding="utf-8") as f:
                    json.dump(db, f, ensure_ascii=False, indent=2)

                # 2. Write ref attributes back to edition XML
                ET.register_namespace('', TEI_NS)
                ET.register_namespace('xml', XML_NS)
                edition_tree = ET.parse(ss.el_edition_file)
                edition_root = edition_tree.getroot()

                text_to_ref = {}
                for r in accepted_matches:
                    text_to_ref[r["text"]] = "#" + r["matched_place"]["id"]
                for r in new_places:
                    text_to_ref[r["text"]] = "#" + r["assigned_id"]

                refs_added = 0
                for pn_elem in edition_root.findall(f".//{{{TEI_NS}}}placeName"):
                    if pn_elem.get("ref"):
                        continue
                    text = (pn_elem.text or "").strip()
                    if text in text_to_ref:
                        pn_elem.set("ref", text_to_ref[text])
                        refs_added += 1

                if refs_added > 0:
                    edition_tree.write(ss.el_edition_file, encoding="utf-8",
                                       xml_declaration=True)

                # 3. Update Authorities.xml only for new places
                new_place_added = False
                if new_places:
                    try:
                        ET.register_namespace('', TEI_NS)
                        ET.register_namespace('xml', XML_NS)
                        auth_tree = ET.parse(DISPLAY_XML_PATH)
                        auth_root = auth_tree.getroot()
                        list_place = auth_root.find(f".//{{{TEI_NS}}}listPlace")

                        if list_place is not None:
                            for r in new_places:
                                place_elem = ET.SubElement(list_place, "place")
                                place_elem.set(f"{{{XML_NS}}}id", r["assigned_id"])

                                variant = r["text"]
                                lang = _detect_lang(variant)

                                pn_he = ET.SubElement(place_elem, "placeName")
                                pn_he.set(f"{{{XML_NS}}}lang", "he")
                                pn_he.set("type", "primary_he")
                                pn_he.text = variant if lang == "he" else "(to be updated)"

                                pn_en = ET.SubElement(place_elem, "placeName")
                                pn_en.set(f"{{{XML_NS}}}lang", "en")
                                pn_en.set("type", "primary_en")
                                pn_en.text = variant if lang == "en" else "Unknown"

                            auth_tree.write(DISPLAY_XML_PATH, encoding="utf-8",
                                            xml_declaration=True)
                            new_place_added = True
                    except Exception as xml_err:
                        st.warning(f"Could not update Authorities.xml: {xml_err}")

                # 4. Skipped places were already saved when leaving Step 3
                skipped_json_path = ss.el_skipped_json_path

                # 5. Git commit
                files_to_stage = [MATCHING_DB_PATH]
                if refs_added > 0:
                    files_to_stage.append(ss.el_edition_file)
                if new_place_added:
                    files_to_stage.append(DISPLAY_XML_PATH)
                if skipped_json_path:
                    files_to_stage.append(skipped_json_path)

                try:
                    subprocess.run(
                        ["git", "add"] + files_to_stage,
                        cwd=PROJECT_DIR, check=True, capture_output=True,
                    )
                    subprocess.run(
                        ["git", "commit", "-m", commit_msg],
                        cwd=PROJECT_DIR, check=True, capture_output=True,
                    )
                    commit_ok = True
                    commit_err = ""
                except subprocess.CalledProcessError as e:
                    commit_ok = False
                    commit_err = e.stderr.decode() if e.stderr else str(e)

            if commit_ok:
                st.success(
                    f"\u2705 Matching DB updated and committed.  \n"
                    f"**{len(accepted_matches)}** matches added, "
                    f"**{len(new_places)}** new places created."
                )
                if new_place_added:
                    st.info(f"Authorities.xml updated with {len(new_places)} new place(s).")
                if skipped_json_path:
                    st.info(
                        f"\U0001f4cb {len(skipped)} skipped name(s) appended to:  \n"
                        f"`Authorities/skipped_places.json`"
                    )
            else:
                st.error(f"Git commit failed:\n```\n{commit_err}\n```")
                st.info("The matching DB has been updated on disk \u2014 you can commit manually.")

    st.markdown("---")
    if st.button("\U0001f504 Start over", key="el_restart"):
        for key in list(st.session_state.keys()):
            if key.startswith("el_"):
                del st.session_state[key]
        st.rerun()
