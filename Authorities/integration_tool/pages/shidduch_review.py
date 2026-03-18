"""
Person Review -- step-through GUI for reviewing Shidduch person name matches.

Thin wrapper around the generic review module, configured with
the Hasidigital-specific person backend (CSV results + TSV decisions + authority DB).

Session state prefix: pr_
"""
from __future__ import annotations

import os
import sys

# Ensure the integration_tool directory is on the path for config imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from kimatch.review import render_review_page, ReviewConfig
except ImportError:
    from kimatch_review import render_review_page, ReviewConfig

import streamlit as st
from shidduch_adapter import HasidigitalPersonBackend

# Cache backend instance in session state so its loaded data survives reruns.
if "pr_backend" not in st.session_state:
    st.session_state.pr_backend = HasidigitalPersonBackend()
backend = st.session_state.pr_backend

config = ReviewConfig(
    entity_label="Person",
    sidebar_title="Person Review",
    page_title="Person Name Review",
    session_prefix="pr_",
    context_window=200,
    filters={
        "has_candidates": "Matched (has candidates)",
        "unset": "Unset -- no match",
        "ambiguous": "Ambiguous",
        "auto": "Decided",
        "all": "All",
    },
)

render_review_page(backend, config)
