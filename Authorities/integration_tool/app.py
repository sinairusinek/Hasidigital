"""
Hasidigital Authority Integration Tool — Edition Place-Name Linker
A 4-step Streamlit wizard for matching unlinked place names in editions
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

# Allow running from the project root as well as from this directory
sys.path.insert(0, os.path.dirname(__file__))

from utils import next_hloc_id

# ── Paths ────────────────────────────────────────────────────────────────────

TOOL_DIR = os.path.dirname(__file__)
AUTH_DIR = os.path.abspath(os.path.join(TOOL_DIR, ".."))
PROJECT_DIR = os.path.abspath(os.path.join(AUTH_DIR, ".."))
EDITIONS_INCOMING = os.path.join(PROJECT_DIR, "editions", "incoming")
MATCHING_DB_PATH = os.path.join(AUTH_DIR, "authorities-matching-db.json")
DISPLAY_XML_PATH = os.path.join(AUTH_DIR, "Authorities.xml")
GEN_SCRIPT = os.path.join(AUTH_DIR, "scripts", "generate_matching_db.py")

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Hasidigital Edition Linker",
    page_icon="📜",
    layout="wide",
)

# ── Session state helpers ────────────────────────────────────────────────────

def _init():
    defaults = {
        "step": 1,
        "db": None,
        "db_loaded": False,
        "edition_file": None,
        "edition_name": "",
        "linked_places": [],      # [{text, ref_id, ...}]
        "unlinked_places": [],    # [{text, index, ...}]
        "match_results": [],      # list of dicts with resolution info
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()
ss = st.session_state

# ── Auto-load the matching DB ────────────────────────────────────────────────

if not ss.get("db_loaded"):
    try:
        with open(MATCHING_DB_PATH, "r", encoding="utf-8") as f:
            ss.db = json.load(f)
        ss.db_loaded = True
    except Exception as _e:
        ss.db_loaded = False
        ss.db_error = str(_e)


def _go(step: int):
    ss.step = step


# ── Matching helpers ─────────────────────────────────────────────────────────

def _build_variant_index(db):
    """Build a lookup: variant_name → place dict from the matching DB."""
    index = {}  # name → place dict
    for place in db["places"]:
        for name in place.get("names_he", []) + place.get("names_en", []):
            if name and name not in index:
                index[name] = place
    return index


def _detect_lang(text: str) -> str:
    """Detect whether text is Hebrew or Latin."""
    hebrew_chars = sum(1 for c in text if '\u0590' <= c <= '\u05FF')
    return "he" if hebrew_chars > 0 else "en"


def _parse_edition_places(edition_path):
    """
    Parse an edition XML and extract all placeName tags.
    Returns (linked, unlinked) lists.
    """
    tree = ET.parse(edition_path)
    root = tree.getroot()

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
            unlinked.append(entry)

    return linked, unlinked


def _match_unlinked(unlinked, variant_index):
    """
    Try to match each unlinked place name against the variant index.
    Returns list of result dicts.
    """
    results = []

    # Deduplicate: group by unique text
    seen_texts = {}  # text → list of indices
    for entry in unlinked:
        t = entry["text"]
        if t not in seen_texts:
            seen_texts[t] = []
        seen_texts[t].append(entry["index"])

    for text, indices in seen_texts.items():
        result = {
            "text": text,
            "indices": indices,
            "count": len(indices),
            "status": "new",       # matched / new
            "matched_place": None,  # place dict if matched
            "resolution": "",       # accept / skip / new_entity
            "assigned_id": None,
        }

        if text in variant_index:
            place = variant_index[text]
            result["status"] = "matched"
            result["matched_place"] = place
            result["resolution"] = "accept"

        results.append(result)

    # Sort: matched first, then new
    results.sort(key=lambda r: (0 if r["status"] == "matched" else 1, r["text"]))

    return results


def _build_issues_csv(results):
    """Build a CSV of skipped matches for the issues folder."""
    import io as _io
    import csv

    rows = []
    for r in results:
        if r["resolution"] != "skip":
            continue
        row = {
            "edition_text": r["text"],
            "occurrences": r["count"],
            "status": r["status"],
        }
        if r["matched_place"]:
            mp = r["matched_place"]
            row["suggested_id"] = mp["id"]
            row["suggested_name_en"] = mp.get("primary_name_en", "")
            row["suggested_name_he"] = mp.get("primary_name_he", "")
        rows.append(row)

    if not rows:
        return b""

    buf = _io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


# ── Sidebar progress ────────────────────────────────────────────────────────

STEPS = ["1 · Select Edition", "2 · Review Matches", "3 · Resolve Issues", "4 · Save & Commit"]

with st.sidebar:
    st.title("📜 Edition Linker")
    st.markdown("---")
    for i, label in enumerate(STEPS, start=1):
        marker = "✅" if ss.step > i else ("▶️" if ss.step == i else "⬜")
        st.markdown(f"{marker} {label}")
    st.markdown("---")
    if ss.step > 1:
        if st.button("← Back"):
            _go(ss.step - 1)


# ═════════════════════════════════════════════════════════════════════════════
# STEP 1 — Select edition
# ═════════════════════════════════════════════════════════════════════════════

if ss.step == 1:
    st.header("Step 1 · Select an edition and review place names")

    # Show DB status
    if ss.db_loaded:
        db = ss.db
        place_count = len(db["places"])
        places_with_he = sum(1 for p in db["places"] if p.get("names_he"))
        st.success(
            f"Matching DB loaded: **{place_count}** places "
            f"({places_with_he} with Hebrew variants)"
        )
    else:
        st.error(f"Could not load matching DB: {ss.get('db_error', 'unknown error')}")
        st.info(f"Expected path: `{MATCHING_DB_PATH}`")
        st.stop()

    # List edition files
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
        key="edition_selector",
    )

    if selected:
        edition_path = os.path.join(EDITIONS_INCOMING, selected)

        try:
            linked, unlinked = _parse_edition_places(edition_path)
            ss.edition_file = edition_path
            ss.edition_name = selected
            ss.linked_places = linked
            ss.unlinked_places = unlinked

            st.markdown("---")

            c1, c2, c3 = st.columns(3)
            c1.metric("Total place names", len(linked) + len(unlinked))
            c2.metric("✅ Already linked", len(linked))
            c3.metric("❓ Unlinked", len(unlinked))

            # Show linked places summary
            if linked:
                with st.expander(f"✅ Already linked ({len(linked)})", expanded=False):
                    rows = []
                    for entry in linked:
                        rows.append({
                            "Text": entry["text"],
                            "Ref ID": entry["ref_id"],
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)

            # Show unlinked places preview
            if unlinked:
                with st.expander(f"❓ Unlinked place names ({len(unlinked)})", expanded=True):
                    # Deduplicate for display
                    from collections import Counter
                    name_counts = Counter(e["text"] for e in unlinked)
                    rows = [{"Name": name, "Occurrences": count}
                            for name, count in name_counts.most_common()]
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)

                if st.button("▶ Run matching →", type="primary"):
                    _go(2)
                    st.rerun()
            else:
                st.info("All place names in this edition are already linked!")

        except Exception as e:
            st.error(f"Could not parse edition: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# STEP 2 — Review matches
# ═════════════════════════════════════════════════════════════════════════════

elif ss.step == 2:
    st.header("Step 2 · Review matching results")

    if not ss.match_results:
        with st.spinner("Matching unlinked place names against DB..."):
            variant_index = _build_variant_index(ss.db)
            results = _match_unlinked(ss.unlinked_places, variant_index)
            ss.match_results = results

    results = ss.match_results
    matched = [r for r in results if r["status"] == "matched"]
    new_recs = [r for r in results if r["status"] == "new"]

    total_matched_occ = sum(r["count"] for r in matched)
    total_new_occ = sum(r["count"] for r in new_recs)

    m1, m2, m3 = st.columns(3)
    m1.metric("✅ Matched (unique names)", len(matched))
    m2.metric("🆕 Unmatched (unique names)", len(new_recs))
    m3.metric("📊 Coverage", f"{total_matched_occ}/{total_matched_occ + total_new_occ}")

    st.markdown("---")

    # Matched table
    with st.expander(f"✅ Matched ({len(matched)} unique names, {total_matched_occ} occurrences)", expanded=False):
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

    # Unmatched table
    with st.expander(f"🆕 Unmatched ({len(new_recs)} unique names, {total_new_occ} occurrences)", expanded=True):
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
        if st.button("← Back to edition selection"):
            ss.match_results = []
            _go(1)
            st.rerun()
    with col_r:
        if st.button("▶ Resolve issues →", type="primary"):
            _go(3)
            st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# STEP 3 — Resolve conflicts and assign IDs
# ═════════════════════════════════════════════════════════════════════════════

elif ss.step == 3:
    st.header("Step 3 · Resolve unmatched names and assign IDs")

    results = ss.match_results
    db = ss.db

    # Existing IDs for next-ID suggestions
    existing_ids = [p["id"] for p in db["places"]]
    for r in results:
        if r.get("assigned_id"):
            existing_ids.append(r["assigned_id"])

    # ── Unmatched names ──────────────────────────────────────────────────────
    new_recs = [r for r in results if r["status"] == "new"]
    if new_recs:
        st.subheader(f"🆕 {len(new_recs)} unmatched place name(s)")
        st.markdown("For each, choose to **skip** or **create a new place** in the authority.")

        for i, r in enumerate(new_recs):
            with st.expander(f"**{r['text']}** ({r['count']}x)", expanded=True):
                action = st.radio(
                    "Action",
                    options=["skip", "new_entity"],
                    format_func=lambda x: {
                        "skip": "⏭ Skip (don't add to authority)",
                        "new_entity": "➕ Create new place in authority",
                    }[x],
                    key=f"new_action_{i}",
                    index=0 if r["resolution"] != "new_entity" else 1,
                )
                r["resolution"] = action

                if action == "new_entity":
                    suggested = next_hloc_id(existing_ids)
                    assigned = st.text_input(
                        "New Place ID",
                        value=r.get("assigned_id") or suggested,
                        key=f"new_id_{i}",
                    )
                    r["assigned_id"] = assigned
                    if assigned and assigned not in existing_ids:
                        existing_ids.append(assigned)
    else:
        st.info("All unlinked names were matched — nothing to resolve.")

    # ── Matched names (confirm) ──────────────────────────────────────────────
    matched = [r for r in results if r["status"] == "matched"]
    if matched:
        st.markdown("---")
        st.subheader(f"✅ {len(matched)} matched name(s) — will update DB counts")
        st.markdown("These will add variant names and increment occurrence counts in the matching DB.")

        with st.expander("Review matched names", expanded=False):
            rows = []
            for r in matched:
                mp = r["matched_place"]
                rows.append({
                    "Edition name": r["text"],
                    "→ Authority": f"{mp['id']} ({mp.get('primary_name_en', '')})",
                    "Occurrences": r["count"],
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

    st.markdown("---")
    if st.button("▶ Save & commit →", type="primary"):
        _go(4)
        st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# STEP 4 — Save and commit
# ═════════════════════════════════════════════════════════════════════════════

elif ss.step == 4:
    st.header("Step 4 · Save and commit")

    import datetime
    import subprocess

    results = ss.match_results
    db = ss.db
    edition_name = ss.edition_name

    # Categorize
    accepted_matches = [r for r in results if r["status"] == "matched" and r["resolution"] == "accept"]
    new_places = [r for r in results if r["resolution"] == "new_entity" and r.get("assigned_id")]
    skipped = [r for r in results if r["resolution"] == "skip"]

    c1, c2, c3 = st.columns(3)
    c1.metric("DB updates (variants+counts)", len(accepted_matches))
    c2.metric("New places to add", len(new_places))
    c3.metric("Skipped", len(skipped))

    if not accepted_matches and not new_places:
        st.warning("Nothing to save — all names were skipped.")
    else:
        # Summary table
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

        # Commit message
        default_msg = (
            f"Link places in {edition_name}: "
            f"{len(accepted_matches)} matched, {len(new_places)} new"
        )
        commit_msg = st.text_input("Commit message", value=default_msg, key="commit_msg")

        if st.button("💾 Save and commit", type="primary"):
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

            with st.spinner("Updating matching DB and committing..."):
                # ── 1. Update JSON matching DB ────────────────────────────
                place_by_id = {p["id"]: p for p in db["places"]}

                # 1a. Accepted matches: add variant + update counts
                for r in accepted_matches:
                    mp_id = r["matched_place"]["id"]
                    if mp_id in place_by_id:
                        place = place_by_id[mp_id]
                        variant = r["text"]
                        lang = _detect_lang(variant)

                        # Add variant if new
                        name_list = place["names_he"] if lang == "he" else place["names_en"]
                        if variant not in name_list:
                            name_list.append(variant)

                        # Update primary Hebrew if placeholder
                        if lang == "he" and place.get("primary_name_he") == "(to be updated)":
                            place["primary_name_he"] = variant

                        # Update occurrences
                        if "occurrences" not in place:
                            place["occurrences"] = {}
                        if edition_name not in place["occurrences"]:
                            place["occurrences"][edition_name] = {}
                        if variant not in place["occurrences"][edition_name]:
                            place["occurrences"][edition_name][variant] = 0
                        place["occurrences"][edition_name][variant] += r["count"]

                        # Recompute total
                        total = 0
                        for file_dict in place["occurrences"].values():
                            for cnt in file_dict.values():
                                total += cnt
                        place["total_occurrences"] = total

                # 1b. New places
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
                        "occurrences": {
                            edition_name: {variant: r["count"]}
                        },
                        "total_occurrences": r["count"],
                    }
                    db["places"].append(new_place)

                # Update generation timestamp
                db["meta"]["generated"] = datetime.datetime.now().isoformat()

                # Write JSON
                with open(MATCHING_DB_PATH, "w", encoding="utf-8") as f:
                    json.dump(db, f, ensure_ascii=False, indent=2)

                # ── 2. Update Authorities.xml only for new places ─────────
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

                # ── 3. Save issues CSV ────────────────────────────────────
                issues_path = None
                issues_csv = _build_issues_csv(results)
                if issues_csv:
                    issues_dir = os.path.join(AUTH_DIR, "matching_issues")
                    os.makedirs(issues_dir, exist_ok=True)
                    issues_path = os.path.abspath(
                        os.path.join(issues_dir, f"skipped_places_{timestamp}.csv")
                    )
                    with open(issues_path, "wb") as _f:
                        _f.write(issues_csv)

                # ── 4. Git commit ─────────────────────────────────────────
                files_to_stage = [MATCHING_DB_PATH]
                if new_place_added:
                    files_to_stage.append(DISPLAY_XML_PATH)
                if issues_path:
                    files_to_stage.append(issues_path)

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
                    f"✅ Matching DB updated and committed.  \n"
                    f"**{len(accepted_matches)}** matches added, "
                    f"**{len(new_places)}** new places created."
                )
                if new_place_added:
                    st.info(f"Authorities.xml updated with {len(new_places)} new place(s).")
                if issues_path:
                    st.info(
                        f"📋 {len(skipped)} skipped name(s) saved to:  \n"
                        f"`Authorities/matching_issues/skipped_places_{timestamp}.csv`"
                    )
            else:
                st.error(f"Git commit failed:\n```\n{commit_err}\n```")
                st.info("The matching DB has been updated on disk — you can commit manually.")

    st.markdown("---")
    if st.button("🔄 Start over"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
