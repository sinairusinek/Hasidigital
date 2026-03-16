"""
Kima Review — step-through GUI for reviewing Kimatch candidate matches.

Thin wrapper around Kimatch's generic review module, configured with
the Hasidigital-specific backend (CSV results + TSV decisions + authority DB).

Session state prefix: kr_
"""
from __future__ import annotations

import os
import sys

# Ensure the integration_tool directory is on the path for config imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from kimatch.review import render_review_page, ReviewConfig  # local dev (kimatch installed)
except ImportError:
    from kimatch_review import render_review_page, ReviewConfig  # Streamlit Cloud (vendored)

from kimatch_adapter import HasidigitalPlaceBackend  # noqa: E402

backend = HasidigitalPlaceBackend()
config = ReviewConfig(
    entity_label="Place",
    sidebar_title="🗺️ Kima Review",
    page_title="🗺️ Kima Place Review",
    session_prefix="kr_",
    context_window=200,
    filters={
        "ambiguous": "🟠 Ambiguous",
        "unset": "❓ Unset — has Kima data",
        "auto": "✅ Auto-decided",
        "all": "📋 All with Kima data",
    },
)

render_review_page(backend, config)
