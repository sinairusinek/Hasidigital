"""
NER Annotator
A 4-step wizard for running Hebrew NER annotation on TEI XML editions.

Steps:
  1. Select an edition and configure pipeline settings
  2. Run the NER pipeline (DictaBERT + optional Gemini correction)
  3. Review detected entities and correction statistics
  4. Save annotated XML and optionally git-commit
"""

import os
import sys
import time
from pathlib import Path
from collections import Counter

import streamlit as st

# Allow imports from the parent integration_tool directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import EDITIONS_INCOMING, PROJECT_DIR

# ── Session state ────────────────────────────────────────────────────────────

def _init():
    defaults = {
        "na_step": 1,
        "na_edition_file": None,
        "na_edition_name": "",
        "na_use_gemini": True,
        "na_do_preprocess": True,
        "na_force_reannotate": False,
        "na_result": None,
        "na_entities": None,
        "na_error": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()
ss = st.session_state


def _go(step):
    ss.na_step = step


def _reset():
    for k in list(ss.keys()):
        if k.startswith("na_"):
            del ss[k]
    _init()


# ── Page header ──────────────────────────────────────────────────────────────

st.header("NER Annotator")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: Select & Configure
# ═══════════════════════════════════════════════════════════════════════════════

if ss.na_step == 1:
    st.subheader("Step 1: Select Edition & Configure")

    # List XML files in editions/online
    xml_files = sorted(Path(EDITIONS_INCOMING).glob("*.xml"))
    if not xml_files:
        st.warning("No XML files found in editions/online/")
        st.stop()

    file_names = [f.name for f in xml_files]
    selected = st.selectbox("Edition XML", file_names)

    if selected:
        xml_path = Path(EDITIONS_INCOMING) / selected

        # Show file info
        from lxml import etree
        tree = etree.parse(str(xml_path))

        # Check for zones and existing annotations
        ns = {"tei": "http://www.tei-c.org/ns/1.0"}
        zones = tree.xpath("//tei:facsimile//tei:zone", namespaces=ns)
        has_pers = len(tree.xpath("//tei:text//tei:persName", namespaces=ns))
        has_place = len(tree.xpath("//tei:text//tei:placeName", namespaces=ns))

        c1, c2, c3 = st.columns(3)
        c1.metric("Facsimile zones", len(zones))
        c2.metric("Existing persName", has_pers)
        c3.metric("Existing placeName", has_place)

        st.divider()

        # Configuration
        st.markdown("**Pipeline Configuration**")

        do_preprocess = st.checkbox(
            "Run structural preprocessing (facsimile zones)",
            value=len(zones) > 0,
            help="Auto-checked if facsimile zones detected.",
        )

        use_gemini = st.checkbox(
            "Use Gemini correction",
            value=True,
            help="Post-correct DictaBERT entities using Gemini 3.0 Flash.",
        )

        gemini_key_status = ""
        if use_gemini:
            env_key = os.environ.get("GEMINI_API_KEY")
            if env_key:
                gemini_key_status = f"GEMINI_API_KEY found in environment ({env_key[:8]}...)"
                st.success(gemini_key_status)
            else:
                st.warning("GEMINI_API_KEY not set in environment.")

        force = False
        if has_pers > 0 or has_place > 0:
            force = st.checkbox(
                "Re-annotate (strip existing annotations first)",
                value=False,
            )

        if st.button("Start NER Pipeline", type="primary"):
            if use_gemini and not os.environ.get("GEMINI_API_KEY"):
                st.error("Gemini API key required. Set GEMINI_API_KEY environment variable.")
            else:
                ss.na_edition_file = str(xml_path)
                ss.na_edition_name = selected
                ss.na_use_gemini = use_gemini
                ss.na_do_preprocess = do_preprocess
                ss.na_force_reannotate = force
                _go(2)
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: Processing
# ═══════════════════════════════════════════════════════════════════════════════

elif ss.na_step == 2:
    st.subheader(f"Step 2: Processing {ss.na_edition_name}")

    # Try importing the pipeline
    pipeline_dir = os.path.join(PROJECT_DIR, "ner_pipeline")
    if pipeline_dir not in sys.path:
        sys.path.insert(0, PROJECT_DIR)

    try:
        from ner_pipeline.pipeline import run_pipeline
    except ImportError as e:
        st.error(f"NER pipeline dependencies not installed: {e}")
        st.info("Install with: `pip install -r ner_pipeline/requirements.txt`")
        if st.button("Back"):
            _go(1)
            st.rerun()
        st.stop()

    # Run the pipeline with progress display
    progress_bar = st.progress(0)
    status_text = st.empty()
    log_container = st.container()

    stages = ["parse", "strip", "preprocess", "standoff", "ner", "gemini", "insert", "cleanup", "save", "done"]
    stage_labels = {
        "parse": "Parsing XML...",
        "strip": "Stripping existing annotations...",
        "preprocess": "Structural preprocessing...",
        "standoff": "Creating standoff view...",
        "ner": "Running DictaBERT NER...",
        "gemini": "Running Gemini correction...",
        "insert": "Inserting annotations...",
        "cleanup": "Cleaning up...",
        "save": "Saving output...",
        "done": "Complete!",
        "skip": "Skipped.",
    }

    def _progress_cb(stage, detail=""):
        label = stage_labels.get(stage, stage)
        if detail:
            label = f"{label} {detail}"
        status_text.text(label)
        if stage in stages:
            idx = stages.index(stage)
            progress_bar.progress((idx + 1) / len(stages))

    try:
        # Determine output path (annotated suffix for safety)
        input_path = ss.na_edition_file
        stem = Path(input_path).stem
        output_path = str(Path(input_path).parent / f"{stem}_ner_annotated.xml")

        result = run_pipeline(
            input_path=input_path,
            output_path=output_path,
            use_gemini=ss.na_use_gemini,
            preprocess=ss.na_do_preprocess,
            force=ss.na_force_reannotate,
            progress_cb=_progress_cb,
        )

        ss.na_result = result
        ss.na_error = None
        progress_bar.progress(1.0)
        status_text.text("Pipeline complete!")

    except Exception as e:
        ss.na_error = str(e)
        st.error(f"Pipeline error: {e}")
        import traceback
        with st.expander("Traceback"):
            st.code(traceback.format_exc())

    if ss.na_error:
        if st.button("Back to configuration"):
            _go(1)
            st.rerun()
    else:
        if st.button("Review results", type="primary"):
            _go(3)
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: Review
# ═══════════════════════════════════════════════════════════════════════════════

elif ss.na_step == 3:
    st.subheader(f"Step 3: Review — {ss.na_edition_name}")

    result = ss.na_result
    if result is None:
        st.warning("No results to review.")
        if st.button("Start over"):
            _reset()
            st.rerun()
        st.stop()

    # Summary metrics
    st.markdown("**Entity Summary**")
    if result.entities_by_type:
        cols = st.columns(len(result.entities_by_type))
        for col, (label, count) in zip(cols, sorted(result.entities_by_type.items())):
            col.metric(label, count)
    else:
        st.info("No entities detected.")

    st.metric("Total entities", result.entity_count)

    # Preprocessing info
    if result.was_preprocessed:
        st.info("Structural preprocessing was applied (facsimile zones).")
    if result.stripped_existing:
        st.info("Existing annotations were stripped before re-annotation.")

    # Gemini correction stats
    if result.gemini_stats:
        st.markdown("**Gemini Correction Statistics**")
        gs = result.gemini_stats
        g1, g2, g3 = st.columns(3)
        g1.metric("Added", f"+{gs['added']}")
        g2.metric("Removed", f"-{gs['removed']}")
        g3.metric("Reclassified", f"~{gs['reclassified']}")

    st.markdown(f"**Output file:** `{result.output_path}`")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Save & Finish", type="primary"):
            _go(4)
            st.rerun()
    with col2:
        if st.button("Start over"):
            _reset()
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: Done
# ═══════════════════════════════════════════════════════════════════════════════

elif ss.na_step == 4:
    st.subheader("Step 4: Complete")

    result = ss.na_result
    st.success(
        f"Annotated XML saved to `{Path(result.output_path).name}` "
        f"with {result.entity_count} entities."
    )

    # Optional git commit
    st.markdown("**Optional: Git commit**")
    default_msg = (
        f"NER annotation: {ss.na_edition_name}: "
        f"{result.entity_count} entities "
        f"({', '.join(f'{k}={v}' for k, v in sorted(result.entities_by_type.items()))})"
    )
    commit_msg = st.text_area("Commit message", value=default_msg)

    if st.button("Commit"):
        import subprocess
        try:
            subprocess.run(
                ["git", "add", result.output_path],
                cwd=PROJECT_DIR, check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=PROJECT_DIR, check=True, capture_output=True,
            )
            st.success("Committed!")
        except subprocess.CalledProcessError as e:
            st.error(f"Git error: {e.stderr.decode()}")

    st.divider()
    if st.button("Process another edition"):
        _reset()
        st.rerun()
