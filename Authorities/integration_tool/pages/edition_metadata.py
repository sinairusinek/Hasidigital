"""
Edition Metadata Editor — view and edit edition bibliographic metadata.

Single source of truth: editions/edition-metadata.json
On save, syncs to:
  - Each edition XML's <sourceDesc>
  - authorities-matching-db.json ("editions" key)
"""
from __future__ import annotations
import json
import os
import subprocess
import sys

import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import EDITION_METADATA_JSON, SYNC_EDITION_SCRIPT, EDITIONS_INCOMING

PREFIX = "em_"

# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_metadata() -> list[dict]:
    if not os.path.exists(EDITION_METADATA_JSON):
        st.error(f"edition-metadata.json not found at {EDITION_METADATA_JSON}")
        return []
    with open(EDITION_METADATA_JSON, encoding="utf-8") as f:
        return json.load(f)["editions"]


def _save_metadata(editions: list[dict]):
    data = {
        "editions": editions,
        "meta": {
            "description": "Single source of truth for edition metadata. Edit here, then sync to XML headers and authorities-matching-db.json.",
            "edition_count": len(editions),
        }
    }
    with open(EDITION_METADATA_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _run_sync() -> tuple[bool, str]:
    """Run sync_edition_metadata.py and return (success, output)."""
    try:
        result = subprocess.run(
            [sys.executable, SYNC_EDITION_SCRIPT],
            capture_output=True, text=True, timeout=60,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except Exception as e:
        return False, str(e)


# ── Page ─────────────────────────────────────────────────────────────────────

st.header("📚 Edition Metadata")

# Load data
if f"{PREFIX}editions" not in st.session_state:
    st.session_state[f"{PREFIX}editions"] = _load_metadata()
    st.session_state[f"{PREFIX}dirty"] = False

editions = st.session_state[f"{PREFIX}editions"]

if not editions:
    st.stop()

# ── Sidebar: overview table + sync ──────────────────────────────────────────

with st.sidebar:
    st.subheader("📚 Editions")
    st.metric("Total", len(editions))

    missing_work = sum(1 for e in editions if not e.get("work_number"))
    missing_title = sum(1 for e in editions if not e.get("title_he") and not e.get("title_en"))
    if missing_work:
        st.warning(f"{missing_work} edition(s) missing work number")
    if missing_title:
        st.warning(f"{missing_title} edition(s) missing title")

    st.divider()

    if st.button("🔄 Reload from disk", use_container_width=True):
        st.session_state[f"{PREFIX}editions"] = _load_metadata()
        st.session_state[f"{PREFIX}dirty"] = False
        st.rerun()

    if st.session_state[f"{PREFIX}dirty"]:
        st.info("You have unsaved changes.")
        if st.button("💾 Save & Sync", type="primary", use_container_width=True):
            _save_metadata(editions)
            ok, output = _run_sync()
            if ok:
                st.success("Saved and synced!")
                st.session_state[f"{PREFIX}dirty"] = False
            else:
                st.error("Sync failed:")
                st.code(output)
            st.rerun()

# ── Edition selector ────────────────────────────────────────────────────────

# Build display labels
labels = []
for e in editions:
    w = f"W-{e['work_number']}" if e.get("work_number") else "W-?"
    title = e.get("title_he") or e.get("title_en") or "(no title)"
    labels.append(f"{w}  {e['xml_filename']}  —  {title}")

col_sel, col_nav = st.columns([5, 1])
with col_sel:
    selected_idx = st.selectbox(
        "Select edition",
        range(len(editions)),
        format_func=lambda i: labels[i],
        key=f"{PREFIX}selector",
    )
with col_nav:
    st.write("")  # spacing
    c1, c2 = st.columns(2)
    if c1.button("◀", key=f"{PREFIX}prev", disabled=selected_idx == 0):
        st.session_state[f"{PREFIX}selector"] = selected_idx - 1
        st.rerun()
    if c2.button("▶", key=f"{PREFIX}next", disabled=selected_idx == len(editions) - 1):
        st.session_state[f"{PREFIX}selector"] = selected_idx + 1
        st.rerun()

entry = editions[selected_idx]

st.divider()

# ── Editor form ─────────────────────────────────────────────────────────────

st.subheader(f"Editing: {entry['xml_filename']}")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**Identification**")
    new_work = st.number_input(
        "Work number",
        value=entry.get("work_number") or 0,
        min_value=0, step=1,
        key=f"{PREFIX}work_{selected_idx}",
        help="Bibliography work number (W-N). 0 = unassigned.",
    )
    new_dbid = st.text_input(
        "DBid",
        value=entry.get("DBid") or "",
        key=f"{PREFIX}dbid_{selected_idx}",
    )

    st.markdown("**Titles**")
    new_title_he = st.text_input(
        "Title (Hebrew)",
        value=entry.get("title_he", ""),
        key=f"{PREFIX}title_he_{selected_idx}",
    )
    new_title_en = st.text_input(
        "Title (English)",
        value=entry.get("title_en", ""),
        key=f"{PREFIX}title_en_{selected_idx}",
    )

    st.markdown("**Authors**")
    new_author_he = st.text_input(
        "Author (Hebrew)",
        value=entry.get("author_he", ""),
        key=f"{PREFIX}author_he_{selected_idx}",
    )
    new_author_en = st.text_input(
        "Author (English)",
        value=entry.get("author_en", ""),
        key=f"{PREFIX}author_en_{selected_idx}",
    )

with col2:
    st.markdown("**Publication**")
    new_date_ce = st.text_input(
        "Date (CE)",
        value=entry.get("date_ce", ""),
        key=f"{PREFIX}date_ce_{selected_idx}",
    )
    new_date_he = st.text_input(
        "Date (Hebrew)",
        value=entry.get("date_he", ""),
        key=f"{PREFIX}date_he_{selected_idx}",
    )
    new_place_ref = st.text_input(
        "Place ref (e.g. #H-LOC_40)",
        value=entry.get("pub_place_ref", ""),
        key=f"{PREFIX}place_ref_{selected_idx}",
    )
    new_place_he = st.text_input(
        "Place (Hebrew)",
        value=entry.get("pub_place_he", ""),
        key=f"{PREFIX}place_he_{selected_idx}",
    )
    new_place_en = st.text_input(
        "Place (English)",
        value=entry.get("pub_place_en", ""),
        key=f"{PREFIX}place_en_{selected_idx}",
    )
    new_language = st.selectbox(
        "Language",
        options=["heb", "yid", "jrb", "ara", ""],
        index=["heb", "yid", "jrb", "ara", ""].index(entry.get("language", "") or ""),
        key=f"{PREFIX}lang_{selected_idx}",
    )

# ── Identifiers ─────────────────────────────────────────────────────────────

st.markdown("**Identifiers**")
ids = entry.get("identifiers", {})
id_types = ["BHB", "ALMA", "Kima", "Kitsis", "Transkribus", "HebrewBooks", "NLI"]
new_ids = {}
cols = st.columns(4)
for i, id_type in enumerate(id_types):
    with cols[i % 4]:
        val = st.text_input(
            id_type,
            value=ids.get(id_type, ""),
            key=f"{PREFIX}id_{id_type}_{selected_idx}",
        )
        if val.strip():
            new_ids[id_type] = val.strip()
# Preserve any extra identifiers not in the standard list
for k, v in ids.items():
    if k not in id_types and v:
        new_ids[k] = v

# ── Match info (read-only) ──────────────────────────────────────────────────

with st.expander("Match info (read-only)"):
    st.text(f"Method: {entry.get('match_method', '')}")
    st.text(f"Notes: {entry.get('match_notes', '')}")

# ── Apply changes ───────────────────────────────────────────────────────────

# Collect new values
new_vals = {
    "work_number": new_work if new_work > 0 else None,
    "DBid": new_dbid.strip() or None,
    "title_he": new_title_he.strip(),
    "title_en": new_title_en.strip(),
    "date_ce": new_date_ce.strip(),
    "date_he": new_date_he.strip(),
    "pub_place_ref": new_place_ref.strip(),
    "pub_place_he": new_place_he.strip(),
    "pub_place_en": new_place_en.strip(),
    "author_he": new_author_he.strip(),
    "author_en": new_author_en.strip(),
    "language": new_language,
    "identifiers": new_ids,
}

# Detect changes
changed = False
for k, v in new_vals.items():
    if entry.get(k) != v:
        changed = True
        break

if changed:
    # Auto-apply to in-memory state
    for k, v in new_vals.items():
        entry[k] = v
    st.session_state[f"{PREFIX}dirty"] = True

# ── Overview table ──────────────────────────────────────────────────────────

st.divider()
st.subheader("All editions")

table_data = []
for e in editions:
    table_data.append({
        "W#": e.get("work_number") or "",
        "File": e["xml_filename"],
        "Title (he)": e.get("title_he", ""),
        "Title (en)": e.get("title_en", ""),
        "Date": e.get("date_ce", ""),
        "Place": e.get("pub_place_he", ""),
        "Lang": e.get("language", ""),
        "DBid": e.get("DBid") or "",
    })

df = pd.DataFrame(table_data)
st.dataframe(df, use_container_width=True, height=400)
