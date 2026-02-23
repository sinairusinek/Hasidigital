"""
Hasidigital Authority Integration Tool
A 4-step Streamlit wizard for merging CSV/Excel data into the TEI authority XML.

Steps:
  1. Upload XML + Upload CSV/Excel + Map columns
  2. Run matching algorithm, review auto-results
  3. Resolve conflicts and assign IDs to new entities
  4. Preview diff and download enriched XML
"""
import copy
import sys
import os

import streamlit as st
import pandas as pd

# Allow running from the project root as well as from this directory
sys.path.insert(0, os.path.dirname(__file__))

from data_models import MatchResult
from xml_parser import parse_xml
from csv_reader import (
    load_file, df_to_places, df_to_persons, df_to_bibls,
    PLACE_FIELDS, PERSON_FIELDS, BIBL_FIELDS, ENTITY_FIELDS, guess_mapping,
)
from matcher import match_places, match_persons, match_bibls, _distance_label
from xml_writer import apply_results, serialise_bytes
from utils import next_hloc_id, next_temph_id, next_hbibl_id

# ── Hardcoded XML path ────────────────────────────────────────────────────────

DEFAULT_XML_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "Authorities2026-01-14.xml"
)

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Hasidigital Authority Integration",
    page_icon="📜",
    layout="wide",
)

# ── Session state helpers ─────────────────────────────────────────────────────

def _init():
    defaults = {
        "step": 1,
        "xml_tree": None,
        "xml_places": [],
        "xml_persons": [],
        "xml_bibls": [],
        "xml_loaded": False,
        "df": None,
        "entity_type": "place",
        "column_mapping": {},
        "csv_records": [],
        "match_results": [],
        "csv_filename": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()
ss = st.session_state

# Auto-load the authority XML from the repository on first run
if not ss.get("xml_loaded"):
    try:
        _path = os.path.abspath(DEFAULT_XML_PATH)
        places, persons, bibls, tree = parse_xml(_path)
        ss.xml_places = places
        ss.xml_persons = persons
        ss.xml_bibls = bibls
        ss.xml_tree = tree
        ss.xml_loaded = True
        ss.xml_path = _path
    except Exception as _e:
        ss.xml_loaded = False
        ss.xml_error = str(_e)


def _go(step: int):
    ss.step = step


def _suggest_id(entity_type: str, existing_ids: list) -> str:
    if entity_type == "place":
        return next_hloc_id(existing_ids)
    elif entity_type == "person":
        return next_temph_id(existing_ids)
    else:
        return next_hbibl_id(existing_ids)


def _record_to_dict(rec) -> dict:
    if rec is None:
        return {}
    if hasattr(rec, "__dataclass_fields__"):
        return {k: getattr(rec, k) for k in rec.__dataclass_fields__ if k != "extra"}
    return {}


def _build_issues_csv(results: list) -> bytes:
    """
    Build a CSV of all skipped matches, with full details of both sides.
    """
    import io as _io
    import csv

    rows = []
    for r in results:
        if r.resolution != "skip":
            continue
        csv_rec = r.csv_record
        xml_rec = r.xml_record

        def _flat(rec, prefix):
            """Flatten a record's fields into prefixed dict entries."""
            if rec is None:
                return {}
            out = {}
            if hasattr(rec, "__dataclass_fields__"):
                for k in rec.__dataclass_fields__:
                    if k == "extra":
                        continue
                    val = getattr(rec, k)
                    if isinstance(val, list):
                        val = " | ".join(str(v) for v in val)
                    out[f"{prefix}_{k}"] = val if val is not None else ""
            return out

        row = {
            "match_method": r.match_method,
            "confidence": f"{r.confidence:.0%}" if r.confidence else "",
            "conflict_details": r.conflict_details,
        }
        row.update(_flat(csv_rec, "csv"))
        row.update(_flat(xml_rec, "xml"))
        rows.append(row)

    if not rows:
        return b""

    buf = _io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility


# ── Sidebar progress ──────────────────────────────────────────────────────────

STEPS = ["1 · Upload & Map", "2 · Review Matches", "3 · Resolve Issues", "4 · Save & Commit"]

with st.sidebar:
    st.title("📜 Authority Integrator")
    st.markdown("---")
    for i, label in enumerate(STEPS, start=1):
        marker = "✅" if ss.step > i else ("▶️" if ss.step == i else "⬜")
        st.markdown(f"{marker} {label}")
    st.markdown("---")
    if ss.step > 1:
        if st.button("← Back"):
            _go(ss.step - 1)


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Upload & Map
# ═══════════════════════════════════════════════════════════════════════════════

if ss.step == 1:
    st.header("Step 1 · Upload data file and map columns")

    col_xml, col_csv = st.columns(2)

    with col_xml:
        st.subheader("TEI Authority XML")
        if ss.get("xml_loaded"):
            st.success(
                f"Auto-loaded from repository:  \n"
                f"`{os.path.basename(ss.get('xml_path', ''))}`  \n"
                f"{len(ss.xml_places)} places · {len(ss.xml_persons)} persons · {len(ss.xml_bibls)} bibls"
            )
        else:
            st.error(f"Could not load XML: {ss.get('xml_error', 'unknown error')}")
            st.info(f"Expected path: `{os.path.abspath(DEFAULT_XML_PATH)}`")

    with col_csv:
        st.subheader("CSV / Excel data")
        csv_file = st.file_uploader("Upload CSV, TSV, or Excel", type=["csv", "tsv", "tab", "xlsx", "xls"], key="csv_upload")
        if csv_file:
            try:
                df = load_file(csv_file)
                ss.df = df
                ss.csv_filename = csv_file.name
                st.success(f"Loaded: {len(df)} rows × {len(df.columns)} columns")
                st.dataframe(df.head(5), use_container_width=True)
            except Exception as e:
                st.error(f"Failed to load file: {e}")

    if ss.get("xml_loaded") and ss.df is not None:
        st.markdown("---")
        st.subheader("Entity type and column mapping")

        entity_type = st.radio(
            "What kind of entities does this CSV contain?",
            options=["place", "person", "bibl"],
            format_func=lambda x: {"place": "Places", "person": "Persons", "bibl": "Bibliography"}[x],
            horizontal=True,
            key="entity_type_radio",
        )
        ss.entity_type = entity_type

        fields = ENTITY_FIELDS[entity_type]
        guessed = guess_mapping(list(ss.df.columns), entity_type)
        col_options = ["(skip)"] + list(ss.df.columns)

        st.markdown("Map each TEI field to a column in your file. Unneeded fields can be skipped.")

        mapping = {}
        cols_per_row = 3
        field_items = list(fields.items())
        for row_start in range(0, len(field_items), cols_per_row):
            row_fields = field_items[row_start: row_start + cols_per_row]
            cols = st.columns(len(row_fields))
            for col_ui, (field_key, field_label) in zip(cols, row_fields):
                with col_ui:
                    default_col = guessed.get(field_key, "(skip)")
                    default_idx = col_options.index(default_col) if default_col in col_options else 0
                    chosen = st.selectbox(
                        field_label,
                        options=col_options,
                        index=default_idx,
                        key=f"map_{field_key}",
                    )
                    if chosen != "(skip)":
                        mapping[field_key] = chosen
        ss.column_mapping = mapping

        if st.button("▶ Run matching →", type="primary"):
            if not mapping:
                st.warning("Please map at least one column before continuing.")
            else:
                _go(2)
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Review matches
# ═══════════════════════════════════════════════════════════════════════════════

elif ss.step == 2:
    st.header("Step 2 · Review matching results")

    if not ss.match_results:
        with st.spinner("Running matching algorithm…"):
            et = ss.entity_type
            mapping = ss.column_mapping
            df = ss.df

            if et == "place":
                csv_recs = df_to_places(df, mapping)
                results = match_places(csv_recs, ss.xml_places)
            elif et == "person":
                csv_recs = df_to_persons(df, mapping)
                results = match_persons(csv_recs, ss.xml_persons)
            else:
                csv_recs = df_to_bibls(df, mapping)
                results = match_bibls(csv_recs, ss.xml_bibls)

            # Default resolution for clean matches
            for r in results:
                if r.status == MatchResult.MATCHED:
                    r.resolution = "accept"

            ss.csv_records = csv_recs
            ss.match_results = results

    results = ss.match_results
    matched = [r for r in results if r.status == MatchResult.MATCHED]
    conflicts = [r for r in results if r.status == MatchResult.CONFLICT]
    new_recs = [r for r in results if r.status == MatchResult.NEW]

    m1, m2, m3 = st.columns(3)
    m1.metric("✅ Matched", len(matched))
    m2.metric("⚠️ Conflicts / Low confidence", len(conflicts))
    m3.metric("🆕 New entities", len(new_recs))

    st.markdown("---")

    # Matched table
    with st.expander(f"✅ Matched records ({len(matched)})", expanded=False):
        rows = []
        for r in matched:
            row = {
                "CSV name": r.csv_record.primary_name,
                "XML id": r.xml_record.xml_id if r.xml_record else "",
                "Method": r.match_method,
                "Confidence": f"{r.confidence:.0%}",
            }
            if r.distance_km is not None:
                row["Distance"] = _distance_label(r.distance_km)
            rows.append(row)
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

    # Conflicts table
    with st.expander(f"⚠️ Conflicts ({len(conflicts)})", expanded=True):
        for r in conflicts:
            dist_str = f" · distance: {_distance_label(r.distance_km)}" if r.distance_km is not None else ""
            st.warning(
                f"**{r.csv_record.primary_name}** → "
                f"XML `{r.xml_record.xml_id if r.xml_record else '?'}` | "
                f"{r.conflict_details}{dist_str}"
            )

    # New records table
    with st.expander(f"🆕 New records ({len(new_recs)})", expanded=False):
        rows = [{"CSV name": r.csv_record.primary_name} for r in new_recs]
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

    col_l, col_r = st.columns(2)
    with col_l:
        if st.button("← Re-upload / change mapping"):
            ss.match_results = []
            _go(1)
            st.rerun()
    with col_r:
        if st.button("▶ Resolve issues →", type="primary"):
            _go(3)
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Resolve conflicts and assign IDs
# ═══════════════════════════════════════════════════════════════════════════════

elif ss.step == 3:
    st.header("Step 3 · Resolve conflicts and assign IDs to new entities")

    results = ss.match_results
    et = ss.entity_type

    # Collect existing IDs from XML for next-ID generation
    if et == "place":
        existing_ids = [r.xml_id for r in ss.xml_places if r.xml_id]
    elif et == "person":
        existing_ids = [r.xml_id for r in ss.xml_persons if r.xml_id]
    else:
        existing_ids = [r.xml_id for r in ss.xml_bibls if r.xml_id]

    # Also include any already-assigned IDs in this session
    for r in results:
        if r.assigned_id:
            existing_ids.append(r.assigned_id)

    # ── Conflicts ────────────────────────────────────────────────────────────
    conflicts = [r for r in results if r.status == MatchResult.CONFLICT]
    if conflicts:
        st.subheader(f"⚠️ {len(conflicts)} conflict(s) to resolve")
        for i, r in enumerate(conflicts):
            csv_name = r.csv_record.primary_name
            xml_id = r.xml_record.xml_id if r.xml_record else "?"
            xml_name = r.xml_record.primary_name if r.xml_record else "?"
            with st.expander(f"{csv_name} ↔ {xml_id} ({xml_name})", expanded=True):
                st.markdown(f"**Match method:** {r.match_method}  ")
                st.markdown(f"**Confidence:** {r.confidence:.0%}  ")
                if r.distance_km is not None:
                    st.markdown(f"**Geographic distance:** {_distance_label(r.distance_km)}  ")
                if r.conflict_details:
                    st.markdown(f"**Details:** {r.conflict_details}")

                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("**CSV record:**")
                    st.json(_record_to_dict(r.csv_record), expanded=False)
                with col_b:
                    st.markdown("**XML record:**")
                    st.json(_record_to_dict(r.xml_record) if r.xml_record else {}, expanded=False)

                choice = st.radio(
                    "Resolution",
                    options=["accept", "skip", "new_entity"],
                    format_func=lambda x: {
                        "accept": "Accept match (merge CSV data into this XML record)",
                        "skip": "Skip (don't change anything)",
                        "new_entity": "Treat as new entity (add to XML as separate record)",
                    }[x],
                    key=f"conflict_res_{i}",
                    index=["accept", "skip", "new_entity"].index(r.resolution) if r.resolution in ["accept", "skip", "new_entity"] else 1,
                )
                r.resolution = choice

                if choice == "new_entity":
                    new_id = _suggest_id(et, existing_ids)
                    assigned = st.text_input(
                        "New ID",
                        value=new_id,
                        key=f"conflict_newid_{i}",
                    )
                    r.assigned_id = assigned
                    if assigned and assigned not in existing_ids:
                        existing_ids.append(assigned)
    else:
        st.info("No conflicts — all matches were high-confidence.")

    st.markdown("---")

    # ── New entities ─────────────────────────────────────────────────────────
    new_recs = [r for r in results if r.status == MatchResult.NEW]
    if new_recs:
        st.subheader(f"🆕 {len(new_recs)} new entit{'ies' if len(new_recs) != 1 else 'y'} to assign IDs")
        st.markdown("Each new entity will be appended to the XML. Assign an ID or skip it.")

        for i, r in enumerate(new_recs):
            col_name, col_action, col_id = st.columns([3, 2, 3])
            with col_name:
                st.markdown(f"**{r.csv_record.primary_name or '(unnamed)'}**")
            with col_action:
                action = st.radio(
                    "Action",
                    options=["add", "skip"],
                    format_func=lambda x: {"add": "➕ Add to XML", "skip": "⏭ Skip"}[x],
                    key=f"new_action_{i}",
                    horizontal=True,
                )
                r.resolution = "new_entity" if action == "add" else "skip"
            with col_id:
                if action == "add":
                    suggested = _suggest_id(et, existing_ids)
                    assigned = st.text_input(
                        "ID",
                        value=r.assigned_id or suggested,
                        key=f"new_id_{i}",
                        label_visibility="collapsed",
                    )
                    r.assigned_id = assigned
                    if assigned and assigned not in existing_ids:
                        existing_ids.append(assigned)
    else:
        st.info("No new entities to add.")

    st.markdown("---")
    if st.button("▶ Generate enriched XML →", type="primary"):
        _go(4)
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Save and commit
# ═══════════════════════════════════════════════════════════════════════════════

elif ss.step == 4:
    st.header("Step 4 · Save and commit to repository")

    import datetime
    import subprocess

    results = ss.match_results
    et = ss.entity_type

    # Count what will change
    to_enrich = [r for r in results if r.status == MatchResult.MATCHED and r.resolution in ("accept", "")]
    to_add = [r for r in results if r.resolution == "new_entity" and r.assigned_id]
    skipped = [r for r in results if r.resolution == "skip"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Records to enrich", len(to_enrich))
    c2.metric("New records to add", len(to_add))
    c3.metric("Skipped / issues", len(skipped))

    if not to_enrich and not to_add:
        st.warning("Nothing to write — all records were skipped or unresolved.")
    else:
        # Summary table
        summary_rows = []
        for r in to_enrich:
            summary_rows.append({
                "Action": "Enrich",
                "XML id": r.xml_record.xml_id,
                "Name": r.csv_record.primary_name,
                "Method": r.match_method,
            })
        for r in to_add:
            summary_rows.append({
                "Action": "Add new",
                "XML id": r.assigned_id,
                "Name": r.csv_record.primary_name,
                "Method": "new entity",
            })
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)

        st.markdown("---")

        # Commit message input
        src = f" from {ss.csv_filename}" if ss.get("csv_filename") else ""
        default_msg = (
            f"Integrate {et} data{src}: enrich {len(to_enrich)}, add {len(to_add)} new"
        )
        commit_msg = st.text_input(
            "Commit message",
            value=default_msg,
            key="commit_msg",
        )

        if st.button("💾 Save and commit", type="primary"):
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            xml_path = os.path.abspath(ss.xml_path)
            repo_dir = os.path.dirname(xml_path)

            with st.spinner("Applying changes and committing…"):
                # 1. Apply results to a fresh copy of the tree
                fresh_tree = copy.deepcopy(ss.xml_tree)
                apply_results(fresh_tree, results, et)

                # 2. Write enriched XML back to the repository file
                from xml_writer import serialise
                serialise(fresh_tree, xml_path)

                # 3. Save issues CSV if there are skipped matches
                issues_path = None
                issues_csv = _build_issues_csv(results)
                if issues_csv:
                    issues_dir = os.path.join(
                        os.path.dirname(__file__), "..", "matching_issues"
                    )
                    os.makedirs(issues_dir, exist_ok=True)
                    issues_path = os.path.abspath(
                        os.path.join(issues_dir, f"skipped_{et}_{timestamp}.csv")
                    )
                    with open(issues_path, "wb") as _f:
                        _f.write(issues_csv)

                # 4. Stage files and commit
                files_to_stage = [xml_path]
                if issues_path:
                    files_to_stage.append(issues_path)

                try:
                    subprocess.run(
                        ["git", "add"] + files_to_stage,
                        cwd=repo_dir, check=True, capture_output=True,
                    )
                    subprocess.run(
                        ["git", "commit", "-m", commit_msg],
                        cwd=repo_dir, check=True, capture_output=True,
                    )
                    commit_ok = True
                    commit_err = ""
                except subprocess.CalledProcessError as e:
                    commit_ok = False
                    commit_err = e.stderr.decode() if e.stderr else str(e)

                # 5. Regenerate matching database
                if commit_ok:
                    try:
                        script_path = os.path.join(
                            os.path.dirname(__file__), "..", "scripts", "generate_matching_db.py"
                        )
                        subprocess.run(
                            ["python3", script_path],
                            cwd=repo_dir, check=True, capture_output=True, timeout=60
                        )
                        st.info("✓ Matching database regenerated")
                    except Exception as db_err:
                        st.warning(f"⚠️ Could not regenerate matching DB: {db_err}")

            if commit_ok:
                st.success(
                    f"✅ Authority file updated and committed.  \n"
                    f"`{os.path.basename(xml_path)}` — "
                    f"{len(to_enrich)} enriched, {len(to_add)} added."
                )
                if issues_path:
                    st.info(
                        f"📋 {len(skipped)} skipped match(es) saved to:  \n"
                        f"`Authorities/matching_issues/skipped_{et}_{timestamp}.csv`"
                    )
            else:
                st.error(f"Git commit failed:\n```\n{commit_err}\n```")
                st.info("The XML file has been updated on disk — you can commit manually.")

            with st.expander("Preview committed XML (first 3000 chars)"):
                with open(xml_path, "rb") as _f:
                    st.code(_f.read(3000).decode("utf-8", errors="replace"), language="xml")

    st.markdown("---")
    if st.button("🔄 Start over"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
