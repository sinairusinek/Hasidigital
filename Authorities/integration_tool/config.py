"""
Shared path constants and XML namespaces for the Hasidigital integration tool.
"""
import os

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_DIR = os.path.abspath(os.path.join(TOOL_DIR, ".."))
PROJECT_DIR = os.path.abspath(os.path.join(AUTH_DIR, ".."))
EDITIONS_INCOMING = os.path.join(PROJECT_DIR, "editions", "incoming")

# Authority files
AUTHORITY_XML_PATH = os.path.join(AUTH_DIR, "Authorities2026-01-14.xml")
DISPLAY_XML_PATH = os.path.join(AUTH_DIR, "Authorities.xml")
MATCHING_DB_PATH = os.path.join(AUTH_DIR, "authorities-matching-db.json")
SKIPPED_JSON_PATH = os.path.join(AUTH_DIR, "skipped_places.json")
GEN_SCRIPT = os.path.join(AUTH_DIR, "scripts", "generate_matching_db.py")

# Kimatch / unmatched-place review files
UNMATCHED_TSV = os.path.join(PROJECT_DIR, "editions", "unmatched-places-report.tsv")
UNMATCHED_CSV = os.path.join(PROJECT_DIR, "editions", "unmatched-kima-results.csv")

# Shidduch / unmatched-person review files
UNMATCHED_PERSONS_TSV = os.path.join(
    PROJECT_DIR, "editions", "unmatched-persons-report.tsv"
)
UNMATCHED_PERSONS_CSV = os.path.join(
    PROJECT_DIR, "editions", "unmatched-shidduch-results.csv"
)

# Full Kima CSV (local dev, git-ignored) — falls back to trimmed version on Streamlit Cloud
_KIMA_FULL = os.path.join(
    os.path.expanduser("~"), "Documents", "GitHub", "Kimatch",
    "20250126KimaPlacesCSVx.csv",
)
_KIMA_TRIMMED = os.path.join(PROJECT_DIR, "editions", "kima-candidates-trimmed.csv")
KIMA_PLACES_CSV = _KIMA_FULL if os.path.exists(_KIMA_FULL) else _KIMA_TRIMMED

# XML namespaces
TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
