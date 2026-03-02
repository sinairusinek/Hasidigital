"""
CSV Authority Integrator
A 4-step wizard for merging CSV/Excel data into the TEI authority XML.

Steps:
  1. Upload CSV/Excel + Map columns
  2. Run matching algorithm, review auto-results
  3. Resolve conflicts and assign IDs to new entities
  4. Save enriched XML and commit
"""
import copy
import sys
import os

import streamlit as st
import pandas as pd

# Allow imports from the parent integration_tool directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import AUTHORITY_XML_PATH, AUTH_DIR, PROJECT_DIR, TEI_NS, XML_NS
from data_models import MatchResult
from xml_parser import parse_xml
from csv_reader import (
    load_file, df_to_places, df_to_persons, df_to_bibls,
    PLACE_FIELDS, PERSON_FIELDS, BIBL_FIELDS, ENTITY_FIELDS, guess_mapping,
)
from matcher import match_places, match_persons, match_bibls, _distance_label
from xml_writer import apply_results, serialise_bytes, serialise
from utils import next_hloc_id, next_temph_id, next_hbibl_id

# ── Session state helpers ─────────────────────────────────────────────────────

def _init():
    defaults = {
        "ci_step": 1,
        "ci_xml_tree": None,
        "ci_xml_places": [],
        "ci_xml_persons": [],
        "ci_xml_bibls": [],
        "ci_xml_loaded": False,
        "ci_df": None,
        "ci_entity_type": "place",
        "ci_column_mapping": {},
        "ci_csv_records": [],
        "ci_match_results": [],
        "ci_csv_filename": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()
ss = st.session_state

# Auto-load the authority XML from the repository on first run
if not ss.get("ci_xml_loaded"):
    try:
        _path = os.path.abspath(AUTHORITY_XML_PATH)
        places, persons, bibls, tree = parse_xml(_path)
        ss.ci_xml_places = places
        ss.ci_xml_persons = persons
        ss.ci_xml_bibls = bibls
        ss.ci_xml_tree = tree
        ss.ci_xml_loaded = True
        ss.ci_xml_path = _path
    except Exception as _e:
        ss.ci_xml_loaded = False
        ss.ci_xml_error = str(_e)


def _go(step: int):
    ss.ci_step = step


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
    """Build a CSV of all skipped matches, with full details of both sides."""
    import io as _io
    import csv

    rows = []
    for r in results:
        if r.resolution != "skip":
            continue
        csv_rec = r.csv_record
        xml_rec = r.xml_record

        def _flat(rec, prefix):
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
    return buf.getvalue().encode("utf-8-sig")


# ── Sidebar progress ──────────────────────────────────────────────────────────

STEPS = ["1 \u00b7 Upload & Map", "2 \u00b7 Review Matches", "3 \u00b7 Resolve Issues", "4 \u00b7 Save & Commit"]

with st.sidebar:
    st.markdown("---")
    st.markdown("**CSV Integrator Progress**")
    for i, label in enumerate(STEPS, start=1):
        marker = "\u2705" if ss.ci_step > i else ("\u25b6\ufe0f" if ss.ci_step == i else "\u2b1c")
        st.markdown(f"{marker} {label}")
    st.markdown("---")
    if ss.ci_step > 1:
        if st.button("\u2190 Back", key="ci_back"):
            _go(ss.ci_step - 1)


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Upload & Map
# ═══════════════════════════════════════════════════════════════════════════════

if ss.ci_step == 1:
    st.header("Step 1 \u00b7 Upload data file and map columns")

    col_xml, col_csv = st.columns(2)

    with col_xml:
        st.subheader("TEI Authority XML")
        if ss.get("ci_xml_loaded"):
            st.success(
                f"Auto-loaded from repository:  \n"
                f"`{os.path.basename(ss.get('ci_xml_path', ''))}`  \n"
                f"{len(ss.ci_xml_places)} places \u00b7 {len(ss.ci_xml_persons)} persons \u00b7 {len(ss.ci_xml_bibls)} bibls"
            )
        else:
            st.error(f"Could not load XML: {ss.get('ci_xml_error', 'unknown error')}")
            st.info(f"Expected path: `{os.path.abspath(AUTHORITY_XML_PATH)}`")

    with col_csv:
        st.subheader("CSV / Excel data")
        csv_file = st.file_uploader(
            "Upload CSV, TSV, or Excel",
            type=["csv", "tsv", "tab", "xlsx", "xls"],
            key="ci_csv_upload",
        )
        if csv_file:
            try:
                df = load_file(csv_file)
                ss.ci_df = df
                ss.ci_csv_filename = csv_file.name
                st.success(f"Loaded: {len(df)} rows \u00d7 {len(df.columns)} columns")
                st.dataframe(df.head(5), use_container_width=True)
            except Exception as e:
                st.error(f"Failed to load file: {e}")

    if ss.get("ci_xml_loaded") and ss.ci_df is not None:
        st.markdown("---")
        st.subheader("Entity type and column mapping")

        entity_type = st.radio(
            "What kind of entities does this CSV contain?",
            options=["place", "person", "bibl"],
            format_func=lambda x: {"place": "Places", "person": "Persons", "bibl": "Bibliography"}[x],
            horizontal=True,
            key="ci_entity_type_radio",
        )
        ss.ci_entity_type = entity_type

        fields = ENTITY_FIELDS[entity_type]
        guessed = guess_mapping(list(ss.ci_df.columns), entity_type)
        col_options = ["(skip)"] + list(ss.ci_df.columns)

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
                        key=f"ci_map_{field_key}",
                    )
                    if chosen != "(skip)":
                        mapping[field_key] = chosen
        ss.ci_column_mapping = mapping

        if st.button("\u25b6 Run matching \u2192", type="primary", key="ci_run"):
            if not mapping:
                st.warning("Please map at least one column before continuing.")
            else:
                _go(2)
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Review matches
# ═══════════════════════════════════════════════════════════════════════════════

elif ss.ci_step == 2:
    st.header("Step 2 \u00b7 Review matching results")

    if not ss.ci_match_results:
        with st.spinner("Running matching algorithm\u2026"):
            et = ss.ci_entity_type
            mapping = ss.ci_column_mapping
            df = ss.ci_df

            if et == "place":
                csv_recs = df_to_places(df, mapping)
                results = match_places(csv_recs, ss.ci_xml_places)
            elif et == "person":
                csv_recs = df_to_persons(df, mapping)
                results = match_persons(csv_recs, ss.ci_xml_persons)
            else:
                csv_recs = df_to_bibls(df, mapping)
                results = match_bibls(csv_recs, ss.ci_xml_bibls)

            for r in results:
                if r.status == MatchResult.MATCHED:
                    r.resolution = "accept"

            ss.ci_csv_records = csv_recs
            ss.ci_match_results = results

    results = ss.ci_match_results
    matched = [r for r in results if r.status == MatchResult.MATCHED]
    conflicts = [r for r in results if r.status == MatchResult.CONFLICT]
    new_recs = [r for r in results if r.status == MatchResult.NEW]

    m1, m2, m3 = st.columns(3)
    m1.metric("\u2705 Matched", len(matched))
    m2.metric("\u26a0\ufe0f Conflicts / Low confidence", len(conflicts))
    m3.metric("\U0001f195 New entities", len(new_recs))

    st.markdown("---")

    with st.expander(f"\u2705 Matched records ({len(matched)})", expanded=False):
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

    with st.expander(f"\u26a0\ufe0f Conflicts ({len(conflicts)})", expanded=True):
        for r in conflicts:
            dist_str = f" \u00b7 distance: {_distance_label(r.distance_km)}" if r.distance_km is not None else ""
            st.warning(
                f"**{r.csv_record.primary_name}** \u2192 "
                f"XML `{r.xml_record.xml_id if r.xml_record else '?'}` | "
                f"{r.conflict_details}{dist_str}"
            )

    with st.expander(f"\U0001f195 New records ({len(new_recs)})", expanded=False):
        rows = [{"CSV name": r.csv_record.primary_name} for r in new_recs]
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

    col_l, col_r = st.columns(2)
    with col_l:
        if st.button("\u2190 Re-upload / change mapping", key="ci_back_2"):
            ss.ci_match_results = []
            _go(1)
            st.rerun()
    with col_r:
        if st.button("\u25b6 Resolve issues \u2192", type="primary", key="ci_resolve"):
            _go(3)
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Resolve conflicts and assign IDs
# ═══════════════════════════════════════════════════════════════════════════════

elif ss.ci_step == 3:
    st.header("Step 3 \u00b7 Resolve conflicts and assign IDs to new entities")

    results = ss.ci_match_results
    et = ss.ci_entity_type

    if et == "place":
        existing_ids = [r.xml_id for r in ss.ci_xml_places if r.xml_id]
    elif et == "person":
        existing_ids = [r.xml_id for r in ss.ci_xml_persons if r.xml_id]
    else:
        existing_ids = [r.xml_id for r in ss.ci_xml_bibls if r.xml_id]

    for r in results:
        if r.assigned_id:
            existing_ids.append(r.assigned_id)

    # ── Conflicts ────────────────────────────────────────────────────────────
    conflicts = [r for r in results if r.status == MatchResult.CONFLICT]
    if conflicts:
        st.subheader(f"\u26a0\ufe0f {len(conflicts)} conflict(s) to resolve")
        for i, r in enumerate(conflicts):
            csv_name = r.csv_record.primary_name
            xml_id = r.xml_record.xml_id if r.xml_record else "?"
            xml_name = r.xml_record.primary_name if r.xml_record else "?"
            with st.expander(f"{csv_name} \u2194 {xml_id} ({xml_name})", expanded=True):
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
                    key=f"ci_conflict_res_{i}",
                    index=["accept", "skip", "new_entity"].index(r.resolution) if r.resolution in ["accept", "skip", "new_entity"] else 1,
                )
                r.resolution = choice

                if choice == "new_entity":
                    new_id = _suggest_id(et, existing_ids)
                    assigned = st.text_input(
                        "New ID",
                        value=new_id,
                        key=f"ci_conflict_newid_{i}",
                    )
                    r.assigned_id = assigned
                    if assigned and assigned not in existing_ids:
                        existing_ids.append(assigned)
    else:
        st.info("No conflicts \u2014 all matches were high-confidence.")

    st.markdown("---")

    # ── New entities ─────────────────────────────────────────────────────────
    new_recs = [r for r in results if r.status == MatchResult.NEW]
    if new_recs:
        st.subheader(f"\U0001f195 {len(new_recs)} new entit{'ies' if len(new_recs) != 1 else 'y'} to assign IDs")
        st.markdown("Each new entity will be appended to the XML. Assign an ID or skip it.")

        for i, r in enumerate(new_recs):
            col_name, col_action, col_id = st.columns([3, 2, 3])
            with col_name:
                st.markdown(f"**{r.csv_record.primary_name or '(unnamed)'}**")
            with col_action:
                action = st.radio(
                    "Action",
                    options=["add", "skip"],
                    format_func=lambda x: {"add": "\u2795 Add to XML", "skip": "\u23ed Skip"}[x],
                    key=f"ci_new_action_{i}",
                    horizontal=True,
                )
                r.resolution = "new_entity" if action == "add" else "skip"
            with col_id:
                if action == "add":
                    suggested = _suggest_id(et, existing_ids)
                    assigned = st.text_input(
                        "ID",
                        value=r.assigned_id or suggested,
                        key=f"ci_new_id_{i}",
                        label_visibility="collapsed",
                    )
                    r.assigned_id = assigned
                    if assigned and assigned not in existing_ids:
                        existing_ids.append(assigned)
    else:
        st.info("No new entities to add.")

    st.markdown("---")
    if st.button("\u25b6 Generate enriched XML \u2192", type="primary", key="ci_generate"):
        _go(4)
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Save and commit
# ═══════════════════════════════════════════════════════════════════════════════

elif ss.ci_step == 4:
    st.header("Step 4 \u00b7 Save and commit to repository")

    import datetime
    import subprocess

    results = ss.ci_match_results
    et = ss.ci_entity_type

    to_enrich = [r for r in results if r.status == MatchResult.MATCHED and r.resolution in ("accept", "")]
    to_add = [r for r in results if r.resolution == "new_entity" and r.assigned_id]
    skipped = [r for r in results if r.resolution == "skip"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Records to enrich", len(to_enrich))
    c2.metric("New records to add", len(to_add))
    c3.metric("Skipped / issues", len(skipped))

    if not to_enrich and not to_add:
        st.warning("Nothing to write \u2014 all records were skipped or unresolved.")
    else:
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

        src = f" from {ss.ci_csv_filename}" if ss.get("ci_csv_filename") else ""
        default_msg = (
            f"Integrate {et} data{src}: enrich {len(to_enrich)}, add {len(to_add)} new"
        )
        commit_msg = st.text_input(
            "Commit message",
            value=default_msg,
            key="ci_commit_msg",
        )

        if st.button("\U0001f4be Save and commit", type="primary", key="ci_commit"):
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            xml_path = os.path.abspath(ss.ci_xml_path)

            with st.spinner("Applying changes and committing\u2026"):
                # 1. Apply results to a fresh copy of the tree
                fresh_tree = copy.deepcopy(ss.ci_xml_tree)
                apply_results(fresh_tree, results, et)

                # 2. Write enriched XML back to the repository file
                serialise(fresh_tree, xml_path)

                # 3. Save issues CSV if there are skipped matches
                issues_path = None
                issues_csv = _build_issues_csv(results)
                if issues_csv:
                    issues_dir = os.path.join(AUTH_DIR, "matching_issues")
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

                # 5. Regenerate matching database
                if commit_ok:
                    try:
                        from config import GEN_SCRIPT
                        subprocess.run(
                            ["python3", GEN_SCRIPT],
                            cwd=PROJECT_DIR, check=True, capture_output=True, timeout=60,
                        )
                        st.info("\u2713 Matching database regenerated")
                    except Exception as db_err:
                        st.warning(f"\u26a0\ufe0f Could not regenerate matching DB: {db_err}")

            if commit_ok:
                st.success(
                    f"\u2705 Authority file updated and committed.  \n"
                    f"`{os.path.basename(xml_path)}` \u2014 "
                    f"{len(to_enrich)} enriched, {len(to_add)} added."
                )
                if issues_path:
                    st.info(
                        f"\U0001f4cb {len(skipped)} skipped match(es) saved to:  \n"
                        f"`Authorities/matching_issues/skipped_{et}_{timestamp}.csv`"
                    )
            else:
                st.error(f"Git commit failed:\n```\n{commit_err}\n```")
                st.info("The XML file has been updated on disk \u2014 you can commit manually.")

            with st.expander("Preview committed XML (first 3000 chars)"):
                with open(xml_path, "rb") as _f:
                    st.code(_f.read(3000).decode("utf-8", errors="replace"), language="xml")

    st.markdown("---")
    if st.button("\U0001f504 Start over", key="ci_restart"):
        for key in list(st.session_state.keys()):
            if key.startswith("ci_"):
                del st.session_state[key]
        st.rerun()
