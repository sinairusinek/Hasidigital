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

# XML namespaces
TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
