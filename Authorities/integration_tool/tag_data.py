"""
Generalized story-tag extraction from TEI XML editions.

Generalizes women_data.py from the `women:*` family to *all* `ana` tag families.
Parses every <span ana="..."> inside each <div type="story"> and returns per-story
the full set of category:subcategory tags, plus the plain story text (for lexical
search and embeddings).

Two edition scopes:
  - "core"   : the 9 fully human-annotated editions (the women/pidyon basis). Used for
               tag statistics, taxonomy, and the audit's human-tag ground truth.
  - "online" : all editions/online/*.xml. Used for the lexical untagged-mention search
               (the pidyon review spanned the full online corpus).

Run directly to (re)generate editions/tag-audit/taxonomy.tsv and tag-inventory.tsv.
"""
import os
import re
import csv
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from typing import List, Dict, Optional

from config import PROJECT_DIR

TEI = "http://www.tei-c.org/ns/1.0"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

ONLINE_DIR = os.path.join(PROJECT_DIR, "editions", "online")
AUDIT_DIR = os.path.join(PROJECT_DIR, "editions", "tag-audit")

# The 9 fully-annotated editions (names as they appear in
# topics/data/10HasidicEditionsTopics.tsv). Matched to files by normalized key,
# because filenames differ in case/hyphenation (e.g. maase-zadikim.xml,
# PeerMikdoshim.xml).
CORE_EDITION_NAMES = [
    "Adat-Zadikim", "Khal-Hasidim", "Khal-Kdoshim", "Maase-Zadikim",
    "Mifalot-HaZadikim", "Peer-MiKdoshim", "Shivhei-Habesht",
    "Shivhei-Harav", "Sipurei-Zadikim",
]


def _norm_key(name: str) -> str:
    """Normalize an edition name/filename for matching across naming conventions."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


CORE_KEYS = {_norm_key(n) for n in CORE_EDITION_NAMES}


def _edition_name(xml_path: str) -> str:
    return os.path.splitext(os.path.basename(xml_path))[0]


def _parse_ana(ana_value: str) -> List[str]:
    """Split a semicolon-delimited ana= string into individual tag tokens."""
    return [t.strip() for t in ana_value.split(";") if t.strip()]


def _story_text(div_elem) -> str:
    """Plain text of a story div, tags stripped, whitespace collapsed."""
    raw = " ".join(div_elem.itertext())
    return re.sub(r"\s+", " ", raw).strip()


# ── Tag classification ─────────────────────────────────────────────────────────

_HEB = re.compile(r"[֐-׿יִ-פֿ]")


def classify_tag(tag: str) -> str:
    """
    Classify a raw ana token's well-formedness:
      ok        - exactly one 'top:sub' pair, ascii
      tbd       - TBD:* placeholder
      bad-sep   - uses ',' instead of ';' (multiple tags glued together)
      hebrew    - contains Hebrew characters
      no-colon  - bare value, no 'top:sub' structure
    """
    if tag.startswith("TBD"):
        return "tbd"
    if _HEB.search(tag):
        return "hebrew"
    if "," in tag:
        return "bad-sep"
    if ":" not in tag:
        return "no-colon"
    return "ok"


def split_tag(tag: str):
    """Return (top, sub) for an ok tag, else (tag, '')."""
    if ":" in tag and classify_tag(tag) == "ok":
        top, sub = tag.split(":", 1)
        return top, sub
    return tag, ""


# ── Extraction ───────────────────────────────────────────────────────────────

def load_stories(scope: str = "core") -> List[dict]:
    """
    Return story dicts for the requested scope.
    Each dict: story_id, edition, tags (raw ok tags), raw_tokens (all tokens
    incl. anomalous), top_tags (set), text, xml_path, in_core (bool).
    """
    stories = []
    for fname in sorted(os.listdir(ONLINE_DIR)):
        if not fname.endswith(".xml"):
            continue
        xml_path = os.path.join(ONLINE_DIR, fname)
        edition = _edition_name(xml_path)
        in_core = _norm_key(edition) in CORE_KEYS
        if scope == "core" and not in_core:
            continue
        try:
            root = ET.parse(xml_path).getroot()
        except ET.ParseError:
            continue
        for div in root.iter(f"{{{TEI}}}div"):
            if div.get("type") != "story":
                continue
            raw_tokens = []
            for span in div.iter(f"{{{TEI}}}span"):
                raw_tokens.extend(_parse_ana(span.get("ana", "")))
            ok_tags = [t for t in raw_tokens if classify_tag(t) == "ok"]
            stories.append({
                "story_id": div.get(XML_ID, ""),
                "edition": edition,
                "tags": ok_tags,
                "raw_tokens": raw_tokens,
                "top_tags": {split_tag(t)[0] for t in ok_tags},
                "text": _story_text(div),
                "xml_path": xml_path,
                "in_core": in_core,
            })
    return stories


def stories_with_tag(tag: str, stories: List[dict]) -> List[dict]:
    return [s for s in stories if tag in s["tags"]]


# ── Taxonomy + inventory generation ────────────────────────────────────────────

def build_taxonomy(stories: List[dict]) -> List[dict]:
    """One row per distinct raw token: top, sub, full, status, freq."""
    freq = Counter()
    for s in stories:
        freq.update(set(s["raw_tokens"]))  # count once per story
    rows = []
    for token, n in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0])):
        status = classify_tag(token)
        top, sub = split_tag(token)
        rows.append({
            "full_tag": token,
            "top_tag": top,
            "sub_tag": sub,
            "status": status,
            "detectability": "",   # to be set per tag: lexical-strong | semantic | interpretive
            "n_stories": n,
            "proposed_canonical": "",
        })
    return rows


def build_inventory(stories: List[dict], top_k_cooc: int = 5) -> List[dict]:
    """One row per ok full_tag with freq, #editions, top co-occurring tags, examples."""
    by_tag_editions = defaultdict(set)
    by_tag_examples = defaultdict(list)
    cooc = defaultdict(Counter)
    freq = Counter()
    for s in stories:
        tags = set(s["tags"])
        for t in tags:
            freq[t] += 1
            by_tag_editions[t].add(s["edition"])
            if len(by_tag_examples[t]) < 3:
                by_tag_examples[t].append(s["story_id"])
            for o in tags:
                if o != t:
                    cooc[t][o] += 1
    rows = []
    for t, n in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0])):
        top, sub = split_tag(t)
        top_cooc = "; ".join(f"{k}({v})" for k, v in cooc[t].most_common(top_k_cooc))
        rows.append({
            "full_tag": t,
            "top_tag": top,
            "sub_tag": sub,
            "n_stories": n,
            "n_editions": len(by_tag_editions[t]),
            "top_cooccurring": top_cooc,
            "examples": "; ".join(by_tag_examples[t]),
        })
    return rows


def _write_tsv(path: str, rows: List[dict]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(rows)


def main():
    stories = load_stories(scope="core")
    print(f"Core editions: {sorted({s['edition'] for s in stories})}")
    print(f"Core stories: {len(stories)}")

    tax = build_taxonomy(stories)
    inv = build_inventory(stories)
    _write_tsv(os.path.join(AUDIT_DIR, "taxonomy.tsv"), tax)
    _write_tsv(os.path.join(AUDIT_DIR, "tag-inventory.tsv"), inv)

    status_counts = Counter(r["status"] for r in tax)
    print(f"Distinct raw tokens: {len(tax)}  ->  status {dict(status_counts)}")
    print(f"Distinct ok full-tags: {len(inv)}")
    print(f"Wrote taxonomy.tsv and tag-inventory.tsv to {AUDIT_DIR}")


if __name__ == "__main__":
    main()
