"""
LLM annotation module for Women-in-story categorization.

Supports two models:
  - Claude (claude-sonnet-4-6) via Anthropic SDK
  - Gemini (gemini-2.0-flash) via google-generativeai SDK

Results are cached in editions/women-llm-results.tsv.
The cache key is (story_id, criteria_hash) so changing the criteria
prompt forces a re-run.
"""
import csv
import hashlib
import json
import os
import time
from datetime import datetime
from typing import Dict, Optional, Tuple

from config import WOMEN_LLM_CACHE_PATH_V2 as WOMEN_LLM_CACHE_PATH, WOMEN_CRITERIA_PATH

CACHE_COLUMNS = [
    "story_id", "edition",
    "claude_category", "claude_collective", "claude_confidence", "claude_reasoning",
    "gemini_category", "gemini_collective", "gemini_confidence", "gemini_reasoning",
    "agreement", "human_category", "human_collective",
    "run_timestamp", "criteria_hash",
]

VALID_CATEGORIES = {
    "no-women", "mention-only", "minor-character",
    "catalyst-character", "major-character",
}
VALID_CONFIDENCES = {"high", "medium", "low"}


# ── Criteria ──────────────────────────────────────────────────────────────────

DEFAULT_CRITERIA = """\
You are annotating Hasidic stories (18th–19th century Hebrew/Yiddish) for the presence and role of women characters.

Assign exactly one primary category — pick the highest applicable tier:
- no-women: No women appear or are referenced in any way.
- mention-only: A woman is referenced as a relation, status, or context, with no presence as a character. She does not act, speak, suffer in a depicted way, decide, or appear in a depicted scene.
- minor-character: A woman appears in the story as a character but the story's main thrust does not depend on her.
- catalyst-character: A woman's situation (suffering, illness, plea, death, request, demand) is the reason the story exists, but a male protagonist is the active agent. The narrative orbits around her predicament.
- major-character: She is an active driver. Her decisions, actions, or speech visibly shape the plot.

Then independently set collective_women: true if anonymous female groups appear ("the women of the town", "many widows", "his daughters and wife as a group").

Respond in JSON only: {"category": "<no-women|mention-only|minor-character|catalyst-character|major-character>", "collective_women": <true|false>, "reasoning": "<1-2 sentences>"}
"""


def load_criteria() -> str:
    if os.path.exists(WOMEN_CRITERIA_PATH):
        with open(WOMEN_CRITERIA_PATH, encoding="utf-8") as f:
            text = f.read().strip()
        if text:
            return text
    return DEFAULT_CRITERIA


def criteria_hash(criteria: str) -> str:
    return hashlib.md5(criteria.encode()).hexdigest()[:8]


def save_criteria(text: str):
    os.makedirs(os.path.dirname(WOMEN_CRITERIA_PATH), exist_ok=True)
    with open(WOMEN_CRITERIA_PATH, "w", encoding="utf-8") as f:
        f.write(text)


# ── Cache ─────────────────────────────────────────────────────────────────────

def _load_cache() -> Dict[Tuple[str, str], dict]:
    """Load cache keyed by (story_id, criteria_hash)."""
    cache = {}
    if not os.path.exists(WOMEN_LLM_CACHE_PATH):
        return cache
    with open(WOMEN_LLM_CACHE_PATH, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            key = (row["story_id"], row.get("criteria_hash", ""))
            cache[key] = row
    return cache


def _save_cache(cache: Dict[Tuple[str, str], dict]):
    os.makedirs(os.path.dirname(WOMEN_LLM_CACHE_PATH), exist_ok=True)
    rows = list(cache.values())
    with open(WOMEN_LLM_CACHE_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CACHE_COLUMNS, delimiter="\t",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def update_human_category(story_id: str, human_category: str,
                          human_collective: Optional[bool] = None):
    """Persist a human decision to the cache for all rows matching story_id."""
    cache = _load_cache()
    updated = False
    for key, row in cache.items():
        if key[0] == story_id:
            row["human_category"] = human_category
            if human_collective is not None:
                row["human_collective"] = str(human_collective)
            updated = True
    if updated:
        _save_cache(cache)


# ── LLM calls ─────────────────────────────────────────────────────────────────

def _parse_response(raw: str) -> Tuple[str, bool, str, str]:
    """Parse JSON response from LLM. Returns (category, collective_women, confidence, reasoning)."""
    try:
        raw = raw.strip()
        # strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        cat = data.get("category", "").strip().lower()
        if cat not in VALID_CATEGORIES:
            cat = "no-women"
        collective = bool(data.get("collective_women", False))
        conf = str(data.get("confidence", "")).strip().lower()
        if conf not in VALID_CONFIDENCES:
            conf = "medium"
        return cat, collective, conf, data.get("reasoning", "")
    except Exception:
        return "no-women", False, "medium", f"[parse error] {raw[:200]}"


def _call_claude(story_text: str, criteria: str) -> Tuple[str, bool, str, str]:
    """Call Claude via the Anthropic SDK (uses ANTHROPIC_API_KEY)."""
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=criteria,
        messages=[{"role": "user", "content": story_text}],
    )
    raw = msg.content[0].text
    return _parse_response(raw)


def _call_gemini(story_text: str, criteria: str) -> Tuple[str, bool, str, str]:
    import google.generativeai as genai
    api_key = os.environ.get("GOOGLE_API_KEY") or _load_dotenv_key()
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=criteria,
    )
    resp = model.generate_content(
        story_text,
        generation_config={"response_mime_type": "application/json", "max_output_tokens": 256},
    )
    return _parse_response(resp.text)


def _load_dotenv_key() -> str:
    """Read GOOGLE_API_KEY from .env in project root."""
    env_path = os.path.join(
        os.path.dirname(__file__), "..", "..", ".env"
    )
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("GOOGLE_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return ""


# ── Public API ────────────────────────────────────────────────────────────────

def annotate_story(
    story: dict,
    criteria: Optional[str] = None,
    force: bool = False,
    models: Tuple[bool, bool] = (True, False),  # (run_claude, run_gemini); Gemini off by default
) -> dict:
    """
    Annotate a single story with Claude (and optionally Gemini).
    Returns a result dict with claude_*, gemini_*, agreement fields.
    Uses cache unless force=True or criteria changed.
    """
    if criteria is None:
        criteria = load_criteria()
    chash = criteria_hash(criteria)
    cache = _load_cache()
    key = (story["story_id"], chash)

    cached = cache.get(key, {})
    run_claude, run_gemini = models
    needs_claude = run_claude and (force or not cached.get("claude_category") or cached.get("claude_category") == "error")
    needs_gemini = run_gemini and (force or not cached.get("gemini_category") or cached.get("gemini_category") == "error")

    if not needs_claude and not needs_gemini and cached:
        return cached

    result = dict(cached) if cached else {
        "story_id": story["story_id"],
        "edition": story["edition"],
        "human_category": story.get("category", ""),
        "human_collective": str(story.get("collective_women", False)),
        "run_timestamp": "",
        "criteria_hash": chash,
        "claude_category": "", "claude_collective": "", "claude_confidence": "", "claude_reasoning": "",
        "gemini_category": "", "gemini_collective": "", "gemini_confidence": "", "gemini_reasoning": "",
        "agreement": "",
    }

    text = story.get("text", "")[:12000]  # cap tokens; covers >95% of stories

    if needs_claude:
        try:
            cat, coll, conf, reason = _call_claude(text, criteria)
        except Exception as e:
            cat, coll, conf, reason = "error", False, "", str(e)
        result["claude_category"] = cat
        result["claude_collective"] = str(coll)
        result["claude_confidence"] = conf
        result["claude_reasoning"] = reason

    if needs_gemini:
        try:
            cat, coll, conf, reason = _call_gemini(text, criteria)
        except Exception as e:
            cat, coll, conf, reason = "error", False, "", str(e)
        result["gemini_category"] = cat
        result["gemini_collective"] = str(coll)
        result["gemini_confidence"] = conf
        result["gemini_reasoning"] = reason

    # agreement (between Claude and Gemini, when both ran)
    cc = result.get("claude_category", "")
    gc = result.get("gemini_category", "")
    if cc and gc:
        result["agreement"] = "agree" if cc == gc else "disagree"
    else:
        result["agreement"] = "partial"

    result["run_timestamp"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    result["criteria_hash"] = chash

    cache[key] = result
    _save_cache(cache)
    return result


def annotate_batch(
    stories: list,
    criteria: Optional[str] = None,
    force: bool = False,
    models: Tuple[bool, bool] = (True, False),  # Gemini off by default
    progress_callback=None,
) -> list:
    """
    Annotate a list of stories. Returns list of result dicts.
    progress_callback(i, total) called after each story.
    """
    if criteria is None:
        criteria = load_criteria()
    results = []
    for i, story in enumerate(stories):
        r = annotate_story(story, criteria=criteria, force=force, models=models)
        results.append(r)
        if progress_callback:
            progress_callback(i + 1, len(stories))
        time.sleep(0.05)  # gentle rate limiting
    return results


def get_cached_results(edition: Optional[str] = None) -> list:
    """Load all cached results, optionally filtered by edition."""
    cache = _load_cache()
    rows = list(cache.values())
    if edition:
        rows = [r for r in rows if r.get("edition") == edition]
    return rows


def generate_apriori_keywords() -> dict:
    """Ask Claude to suggest Hebrew/Yiddish keywords for women, before reading any texts."""
    import anthropic
    client = anthropic.Anthropic()
    prompt = (
        "You are helping build a search vocabulary for identifying women characters "
        "in 18th–19th century Hasidic stories written in Hebrew and Yiddish. "
        "Without reading any specific texts, suggest a comprehensive list of Hebrew/Yiddish "
        "words and word-forms that would be used to refer to women (named or unnamed). "
        "Organize by category. Return JSON: "
        '{"kinship": [...], "roles_titles": [...], "pronouns_gendered": [...], '
        '"action_contexts": [...], "other": [...]}'
    )
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)
