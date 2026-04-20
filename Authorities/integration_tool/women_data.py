"""
Women-in-story data extraction from TEI XML editions.

Parses all editions/online/*.xml and derives per-story:
  - story_id, edition name
  - all topic tags (from all <span ana="..."> within the story div)
  - Women-in-story category: no / minor / major / major+minor
  - plain text of the story (for LLM input)

Also provides update_women_tag() to write back a decision to the XML.
"""
import os
import re
import xml.etree.ElementTree as ET
from typing import List, Optional, Dict

from config import EDITIONS_INCOMING, PROJECT_DIR

EDITIONS_DIR = os.path.join(PROJECT_DIR, "editions", "online")

TEI = "http://www.tei-c.org/ns/1.0"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def _edition_name(xml_path: str) -> str:
    return os.path.splitext(os.path.basename(xml_path))[0]


def _parse_ana(ana_value: str) -> List[str]:
    """Split a semicolon-delimited ana= string into individual topic tokens."""
    return [t.strip() for t in ana_value.split(";") if t.strip()]


def _derive_category(topics: List[str]) -> str:
    has_major = any(t == "women:major_character" for t in topics)
    has_minor = any(t == "women:minor_character" for t in topics)
    if has_major and has_minor:
        return "major+minor"
    if has_major:
        return "major"
    if has_minor:
        return "minor"
    return "no"


def _story_text(div_elem) -> str:
    """Extract plain text from a story div, stripping XML tags."""
    parts = []
    for text in div_elem.itertext():
        parts.append(text)
    raw = " ".join(parts)
    # collapse whitespace
    return re.sub(r"\s+", " ", raw).strip()


def load_stories() -> List[dict]:
    """
    Return a list of story dicts for all editions.
    Each dict has keys:
      story_id, edition, topics, category, text, xml_path
    """
    stories = []
    for fname in sorted(os.listdir(EDITIONS_DIR)):
        if not fname.endswith(".xml"):
            continue
        xml_path = os.path.join(EDITIONS_DIR, fname)
        edition = _edition_name(xml_path)
        try:
            tree = ET.parse(xml_path)
        except ET.ParseError:
            continue
        root = tree.getroot()
        for div in root.iter(f"{{{TEI}}}div"):
            if div.get("type") != "story":
                continue
            story_id = div.get(XML_ID, "")
            topics = []
            for span in div.iter(f"{{{TEI}}}span"):
                ana = span.get("ana", "")
                topics.extend(_parse_ana(ana))
            # filter out non-topic values
            topics = [t for t in topics if ":" in t and not t.startswith("TBD")]
            category = _derive_category(topics)
            text = _story_text(div)
            stories.append(
                {
                    "story_id": story_id,
                    "edition": edition,
                    "topics": topics,
                    "category": category,
                    "text": text,
                    "xml_path": xml_path,
                }
            )
    return stories


def is_annotated(edition: str, stories: Optional[List[dict]] = None) -> bool:
    """True if the edition has at least one women:* tag."""
    if stories is None:
        stories = load_stories()
    for s in stories:
        if s["edition"] == edition and s["category"] != "no":
            return True
    return False


# ── Write-back ────────────────────────────────────────────────────────────────

def update_women_tag(xml_path: str, story_id: str, new_category: str) -> bool:
    """
    Update the women:* tag for a story in its XML file.

    new_category must be one of: no / minor / major / major+minor
    Returns True if the file was modified.
    """
    # Map category → set of women topic tokens to set on the story's main span
    cat_to_tokens = {
        "no":          [],
        "minor":       ["women:minor_character"],
        "major":       ["women:major_character"],
        "major+minor": ["women:major_character", "women:minor_character"],
    }
    if new_category not in cat_to_tokens:
        raise ValueError(f"Unknown category: {new_category}")

    ET.register_namespace("", TEI)
    # Use raw text manipulation to preserve formatting; ET round-trips lose it
    with open(xml_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the story div and its first <span ana="...">
    # We locate the xml:id attribute, then find the next span ana= after it
    id_pattern = re.compile(
        rf'xml:id="{re.escape(story_id)}"'
    )
    m = id_pattern.search(content)
    if not m:
        return False

    # Find next span ana= after the story id position
    span_pattern = re.compile(r'<span\s+ana="([^"]*)"')
    sm = span_pattern.search(content, m.end())
    if not sm:
        return False

    old_ana = sm.group(1)
    old_tokens = _parse_ana(old_ana)

    # Remove existing women:* tokens
    filtered = [t for t in old_tokens if not t.startswith("women:")]

    # Add new women tokens
    new_tokens = filtered + cat_to_tokens[new_category]

    if new_tokens == old_tokens:
        return False  # no change

    new_ana = "; ".join(new_tokens)
    new_content = content[: sm.start(1)] + new_ana + content[sm.end(1):]

    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return True


# ── Empirical vocabulary ──────────────────────────────────────────────────────

def extract_empirical_vocabulary(stories: List[dict]) -> dict:
    """
    From annotated stories (with women tags), extract word frequencies.
    Returns {word: {women: int, no_women: int, ratio: float}}
    sorted by discrimination ratio descending.
    """
    from collections import Counter
    import math

    women_words: Counter = Counter()
    no_women_words: Counter = Counter()

    for s in stories:
        words = re.findall(r"[\u0590-\u05ff\ufb1d-\ufb4e]+", s["text"])
        if s["category"] != "no":
            women_words.update(words)
        else:
            no_women_words.update(words)

    total_women = max(sum(women_words.values()), 1)
    total_no_women = max(sum(no_women_words.values()), 1)

    all_words = set(women_words) | set(no_women_words)
    vocab = {}
    for w in all_words:
        wf = women_words.get(w, 0)
        nf = no_women_words.get(w, 0)
        # smoothed ratio
        ratio = (wf / total_women + 1e-6) / (nf / total_no_women + 1e-6)
        vocab[w] = {"women": wf, "no_women": nf, "ratio": ratio}

    return dict(sorted(vocab.items(), key=lambda x: -x[1]["ratio"]))
