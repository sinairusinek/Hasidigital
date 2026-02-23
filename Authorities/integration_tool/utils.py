"""
Utility functions: normalization, Haversine distance, ID generation.
"""
import math
import re
import unicodedata
from typing import Optional


# ── ID normalisation ────────────────────────────────────────────────────────

def normalize_id_type(raw: str) -> str:
    """
    Canonicalize idno @type values to title-case.
    E.g. 'wikidata' -> 'Wikidata', 'tsadikim' -> 'Tsadikim'.
    """
    mapping = {
        "wikidata": "Wikidata",
        "kima": "Kima",
        "tsadikim": "Tsadikim",
        "jewishgen": "JewishGen",
        "dijestdb": "DiJeStDB",
        "disjestdb": "DiJeStDB",
        "dijestdb": "DiJeStDB",
    }
    return mapping.get(raw.lower(), raw)


def normalize_wikidata_url(value: str) -> Optional[str]:
    """
    Accept a bare Q-number ('Q997343') or a full URL and return the
    canonical full URL https://www.wikidata.org/wiki/QXXXXXXX.
    Returns None if value is empty/None.
    """
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    # Already a full URL
    if value.startswith("http"):
        # Normalise to www.wikidata.org/wiki/
        m = re.search(r'(Q\d+)', value)
        if m:
            return f"https://www.wikidata.org/wiki/{m.group(1)}"
        return value
    # Bare Q-number
    if re.match(r'^Q\d+$', value):
        return f"https://www.wikidata.org/wiki/{value}"
    return None


def normalize_kima_url(value: str) -> Optional[str]:
    """
    Normalise Kima URLs to the /Places/Details/N form.
    Handles /Details?id=N as well.  Also handles pipe-separated lists —
    returns just the first one.
    """
    if not value:
        return None
    value = str(value).strip().split("|")[0].strip()
    if not value:
        return None
    # Already canonical
    if "Places/Details/" in value:
        return value
    # ?id=N variant
    m = re.search(r'[?&]id=(\d+)', value)
    if m:
        return f"https://data.geo-kima.org/Places/Details/{m.group(1)}"
    # Bare numeric ID
    if re.match(r'^\d+(\.\d+)?$', value):
        numeric = str(int(float(value)))
        return f"https://data.geo-kima.org/Places/Details/{numeric}"
    return value


def extract_kima_id(url: str) -> Optional[str]:
    """Return the numeric Kima ID from a URL, or None."""
    if not url:
        return None
    m = re.search(r'/Details/(\d+)', url)
    if m:
        return m.group(1)
    m = re.search(r'[?&]id=(\d+)', url)
    if m:
        return m.group(1)
    return None


def extract_wikidata_qid(url: str) -> Optional[str]:
    """Return the Q-number from a Wikidata URL, or None."""
    if not url:
        return None
    m = re.search(r'(Q\d+)', url)
    return m.group(1) if m else None


# ── String normalisation ────────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    """Lowercase, strip diacritics, collapse whitespace."""
    if not name:
        return ""
    # NFD decomposition strips combining characters
    nfd = unicodedata.normalize("NFD", name)
    stripped = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return re.sub(r'\s+', ' ', stripped).strip().lower()


def name_similarity(a: str, b: str) -> float:
    """
    Simple Jaccard similarity on character trigrams.
    Returns 0.0–1.0.
    """
    a, b = normalize_name(a), normalize_name(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    def trigrams(s):
        return set(s[i:i+3] for i in range(len(s) - 2))
    ta, tb = trigrams(a), trigrams(b)
    if not ta or not tb:
        # fall back to token overlap for very short strings
        wa, wb = set(a.split()), set(b.split())
        if not wa or not wb:
            return 0.0
        return len(wa & wb) / len(wa | wb)
    return len(ta & tb) / len(ta | tb)


# ── Geographic ──────────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── ID generation ───────────────────────────────────────────────────────────

def next_hloc_id(existing_ids: list[str]) -> str:
    """Return the next H-LOC_N id not already in existing_ids."""
    used = set()
    for id_ in existing_ids:
        m = re.match(r'^H-LOC_(\d+)$', id_)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return f"H-LOC_{n}"


def next_temph_id(existing_ids: list[str]) -> str:
    """Return the next tempH-N id not already in existing_ids."""
    used = set()
    for id_ in existing_ids:
        m = re.match(r'^tempH-(\d+)$', id_)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return f"tempH-{n}"


def next_hbibl_id(existing_ids: list[str]) -> str:
    """Return the next H-BIBL_N id not already in existing_ids."""
    used = set()
    for id_ in existing_ids:
        m = re.match(r'^H-BIBL_(\d+)$', id_)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return f"H-BIBL_{n}"
