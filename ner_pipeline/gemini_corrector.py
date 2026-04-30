"""
Gemini-based correction of existing NER annotations in TEI XML.

Correction-only workflow:
  1. Extract existing entities from annotated XML (via annotation_inserter)
  2. Strip existing annotations
  3. Chunk text by <div type="story"> (or character-based fallback)
  4. Send passages to Gemini for review/correction
  5. Re-locate corrected entity text strings in plain text (fuzzy matching)
  6. Preserve existing ref attributes for unchanged entities
  7. Re-insert via standoffconverter
"""

import json
import logging
import os
import re
import time
from pathlib import Path

from .config import GEMINI_MODEL, GEMINI_DELAY, TEI_NS

logger = logging.getLogger(__name__)

# Path to the finalized system prompt
_PROMPT_PATH = Path(__file__).parent / "gemini_correction_prompt.txt"

# Hebrew prefix particles that should not be part of entity spans
_HEB_PREFIXES = "מלבוהכ"

# Geresh / gershayim / ASCII quote characters used in fuzzy matching
_DIACRITICS_RE = re.compile(r"[׳״\"']")

# ── Label translation ──────────────────────────────────────────────────────────
# The prompt uses TEI tag names; the pipeline uses NER label codes.

_CODE_TO_PROMPT = {
    "PER": "persName",
    "GPE": "placeName",
    "LOC": "placeName",
    "ORG": "orgName",
    "TIMEX": "date",
    "WOA": "name[work]",
    "MISC": "name[misc]",
    "EVENT": "name[event]",
}

_PROMPT_TO_CODE = {
    "persName": "PER",
    "placeName": "GPE",
    "orgName": "ORG",
    "date": "TIMEX",
    "name[work]": "WOA",
    "name[misc]": "MISC",
    "name[event]": "EVENT",
    "name": "MISC",  # bare <name> fallback
}


def _repair_json(s: str) -> str:
    """
    Best-effort repair of slightly malformed JSON strings from Gemini.

    Fixes applied (in order):
    - Strip a leading/trailing Markdown code fence (```json ... ```)
    - Replace Python-style None/True/False with JSON null/true/false
    - Remove trailing commas before ] or }
    - Append a closing ] if the string looks like a truncated array

    Returns the repaired string (may still be invalid JSON).
    """
    s = s.strip()

    # Strip markdown code fences
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
        s = s.strip()

    # Python literals → JSON
    s = re.sub(r'\bNone\b', 'null', s)
    s = re.sub(r'\bTrue\b', 'true', s)
    s = re.sub(r'\bFalse\b', 'false', s)

    # Trailing commas before closing bracket/brace
    s = re.sub(r',\s*([}\]])', r'\1', s)

    # Truncated array: ends with a string value or number but missing ]
    if s.startswith('[') and not s.rstrip().endswith(']'):
        # Close any open objects, then close the array
        stripped = s.rstrip().rstrip(',')
        # If last char is } or a quote or digit, just append ]
        if stripped and stripped[-1] in ('}', '"', '0123456789'):
            s = stripped + ']'

    return s


def _code_to_prompt_label(label):
    return _CODE_TO_PROMPT.get(label, label)


def _prompt_to_code_label(label):
    return _PROMPT_TO_CODE.get(label, label)


# ── API key & client ───────────────────────────────────────────────────────────

def _get_api_key(api_key=None):
    """Return a Gemini/Google API key from arg, env vars, or .env file."""
    if api_key:
        return api_key

    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if key:
        return key

    # Try .env file at repo root
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv  # type: ignore
            load_dotenv(env_path, override=False)
        except ImportError:
            # Manual parse (avoid dependency on dotenv)
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    for var in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
                        if line.startswith(f"{var}="):
                            val = line.split("=", 1)[1].strip().strip("'\"")
                            os.environ[var] = val
        key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

    return key


def _get_client(api_key=None):
    """Create and return a google.genai Client."""
    from google import genai  # type: ignore

    key = _get_api_key(api_key)
    if not key:
        raise ValueError(
            "Gemini API key required. Set GOOGLE_API_KEY or GEMINI_API_KEY env var, "
            "or add it to a .env file at the repo root."
        )
    return genai.Client(api_key=key)


# ── Prompt loading ─────────────────────────────────────────────────────────────

def _load_prompt():
    return _PROMPT_PATH.read_text(encoding="utf-8")


# ── Story-div chunking ─────────────────────────────────────────────────────────

def get_story_div_chunks(tree, plain_text, entities):
    """
    Chunk text and entities by <div type="story"> elements.

    Walks the XML tree in document order, counting characters exactly as
    standoffconverter does (text + tail concatenation), to determine where
    each story div starts and ends in plain_text.

    Returns:
        List of (chunk_text, chunk_entities, chunk_offset, story_id) tuples.
        Falls back to a single full-text chunk if no story divs are found.

    chunk_entities offsets are relative to the chunk start (0-based).
    """
    from lxml import etree

    text_el = tree.find(f".//{{{TEI_NS}}}text")
    if text_el is None:
        return [(plain_text, entities, 0, None)]

    chunks = []
    pos = [0]  # mutable position counter

    def _walk(el):
        local = etree.QName(el.tag).localname if isinstance(el.tag, str) else None
        is_story = local == "div" and el.get("type") == "story"

        div_start = pos[0] if is_story else None

        if el.text:
            pos[0] += len(el.text)

        for child in el:
            _walk(child)
            if child.tail:
                pos[0] += len(child.tail)

        if is_story and div_start is not None:
            div_end = pos[0]
            chunk_text = plain_text[div_start:div_end]
            chunk_ents = [
                {
                    **e,
                    "start": e["start"] - div_start,
                    "end": e["end"] - div_start,
                }
                for e in entities
                if e["start"] >= div_start and e["end"] <= div_end
            ]
            story_id = el.get(f"{{http://www.w3.org/XML/1998/namespace}}id")
            chunks.append((chunk_text, chunk_ents, div_start, story_id))

    _walk(text_el)

    if not chunks:
        logger.debug("No <div type='story'> found; using full text as one chunk.")
        return [(plain_text, entities, 0, None)]

    return chunks


# ── Gemini API call ────────────────────────────────────────────────────────────

def _call_gemini_passages(
    passages,
    client,
    model_name,
    max_retries=1,
    _allow_split=True,
    max_removal_pct=None,
):
    """
    Send N (text, entities) passages to Gemini in a single call.

    On truncated/invalid JSON, retries up to max_retries times (with a small
    delay). If the full batch still fails and contains multiple passages,
    retries each passage individually before falling back to originals.

    Args:
        passages: List of (chunk_text, chunk_entities) tuples.
                  Entities have code labels (PER, GPE, …) and offsets relative
                  to their chunk.
        client: google.genai Client instance.
        model_name: Gemini model name string.
        max_retries: Number of retries on invalid JSON (default 1).
        _allow_split: Internal flag; when False, prevents recursive splitting.
        max_removal_pct: If set (0–100), fall back to the original entity list
                         for any passage where Gemini removed more than this
                         percentage of the existing entities.  E.g. 40.0 means
                         "fall back if more than 40 % were removed".
                         None (default) disables the guard.

    Returns:
        List of corrected entity lists (one per passage).
        Entities use code labels and have start/end offsets relative to their chunk.
        Falls back to the original entity list for any passage that fails to parse
        or trips the retention guard.
    """
    n = len(passages)
    prompt_template = _load_prompt()

    # Build the PASSAGES block: each passage is labelled PASSAGE N
    passage_blocks = []
    for i, (text, entities) in enumerate(passages, 1):
        # Translate labels to prompt names; strip ref (Gemini doesn't need it)
        gemini_ents = [
            {
                "text": e["text"],
                "start": e["start"],
                "end": e["end"],
                "label": _code_to_prompt_label(e["label"]),
            }
            for e in entities
        ]
        ents_json = json.dumps(gemini_ents, ensure_ascii=False, indent=2)
        passage_blocks.append(
            f"PASSAGE {i}:\n{text}\n\nCURRENT ANNOTATIONS:\n{ents_json}"
        )

    passages_str = "\n\n---\n\n".join(passage_blocks)
    prompt = prompt_template.replace("{N}", str(n)).replace("{PASSAGES}", passages_str)

    from google.genai import types  # type: ignore

    result = None
    last_error = None

    for attempt in range(1 + max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            raw = response.text
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                repaired = _repair_json(raw)
                result = json.loads(repaired)
            if isinstance(result, dict):
                break  # valid response
            last_error = "response is not a dict"
            result = None
        except json.JSONDecodeError as exc:
            last_error = str(exc)
            result = None
        except Exception as exc:
            last_error = str(exc)
            result = None

        if attempt < max_retries:
            logger.warning(
                "Gemini attempt %d/%d failed (%s), retrying…",
                attempt + 1, 1 + max_retries, last_error,
            )
            time.sleep(1)

    if result is None:
        # If batch contained multiple passages, retry each individually before
        # giving up — one malformed response shouldn't silence the whole batch.
        if _allow_split and len(passages) > 1:
            logger.warning(
                "Batch of %d passages failed; retrying each passage individually.",
                len(passages),
            )
            individual_results = []
            for idx, p in enumerate(passages):
                single = _call_gemini_passages(
                    [p], client, model_name,
                    max_retries=max_retries, _allow_split=False,
                    max_removal_pct=max_removal_pct,
                )
                individual_results.append(single[0])
                if idx < len(passages) - 1:
                    time.sleep(1)
            return individual_results

        logger.warning(
            "Gemini failed after %d attempts (%s); falling back to originals.",
            1 + max_retries, last_error,
        )
        return [ents for _, ents in passages]

    corrected_all = []
    for i in range(1, n + 1):
        key = f"passage_{i}"
        if key not in result:
            logger.warning("Missing key %s in Gemini response; using originals.", key)
            corrected_all.append(passages[i - 1][1])
            continue

        passage_result = result[key]
        if not isinstance(passage_result, dict):
            corrected_all.append(passages[i - 1][1])
            continue

        raw_ents = passage_result.get("entities", [])
        if not isinstance(raw_ents, list):
            corrected_all.append(passages[i - 1][1])
            continue

        validated = []
        for ent in raw_ents:
            if not isinstance(ent, dict):
                continue
            if "text" not in ent or "label" not in ent:
                continue
            validated.append({
                "text": ent["text"],
                "start": int(ent.get("start", 0)),
                "end": int(ent.get("end", 0)),
                "label": _prompt_to_code_label(ent["label"]),
            })

        # ── Retention guard ────────────────────────────────────────────────
        if max_removal_pct is not None:
            n_orig = len(passages[i - 1][1])
            if n_orig > 0:
                n_removed = n_orig - len(validated)
                pct_removed = n_removed / n_orig * 100
                if pct_removed > max_removal_pct:
                    logger.warning(
                        "Passage %d/%d: Gemini removed %.0f%% of entities "
                        "(%d → %d; threshold %.0f%%); falling back to originals.",
                        i, n, pct_removed, n_orig, len(validated), max_removal_pct,
                    )
                    corrected_all.append(passages[i - 1][1])
                    continue

        # Sort by Gemini's reported offset before relocation — even though
        # these offsets are unreliable, ordering by them reduces false-position
        # matches when the same text appears multiple times in a passage.
        validated.sort(key=lambda e: (e["start"], e["end"]))

        corrected_all.append(validated)

    return corrected_all


# ── Entity location ────────────────────────────────────────────────────────────

def locate_entities_in_text(entities, plain_text, unmatched_log=None,
                            source_file=None, story_id=None):
    """
    Map entity text strings to character offsets in plain_text.

    Gemini's returned offsets are unreliable, so we re-locate by text string.

    Strategy (in order):
    1. Exact match, continuing from the last match position.
    2. Strip geresh/gershayim (׳ ״ " ') and retry.
    3. Strip one leading Hebrew prefix particle (מ/ל/ב/ו/ה/כ) and retry.
    4. Retry strategies 1–3 from position 0 (in case entities are out of order).
    5. Log unmatched to unmatched_log (JSONL) and skip.

    Args:
        entities: List of entity dicts with text and label (start/end ignored).
        plain_text: Full plain text of the chunk/document.
        unmatched_log: Path-like for JSONL failure log (optional).
        source_file: Source XML filename (for enriched logging).
        story_id: Story div xml:id (for enriched logging).

    Returns:
        List of entity dicts with accurate start/end offsets.
    """
    located = []
    unmatched = []
    search_from = 0

    for ent in entities:
        original_text = ent["text"]
        label = ent["label"]
        ref = ent.get("ref")

        # Strategy 1: exact match from current position
        matched_text, start = _locate_one(original_text, plain_text, search_from)

        if start is None:
            # Strategy 2: strip geresh/gershayim
            stripped = _DIACRITICS_RE.sub("", original_text)
            if stripped != original_text:
                matched_text, start = _locate_one(stripped, plain_text, search_from)

        if start is None:
            # Strategy 3: strip leading Hebrew prefix particle
            if original_text and original_text[0] in _HEB_PREFIXES and len(original_text) > 1:
                candidate = original_text[1:]
                matched_text, start = _locate_one(candidate, plain_text, search_from)

        if start is None:
            # Retry all strategies from position 0
            matched_text, start = _locate_one(original_text, plain_text, 0)
            if start is None:
                stripped = _DIACRITICS_RE.sub("", original_text)
                if stripped != original_text:
                    matched_text, start = _locate_one(stripped, plain_text, 0)
            if start is None and original_text and original_text[0] in _HEB_PREFIXES:
                matched_text, start = _locate_one(original_text[1:], plain_text, 0)

        if start is None:
            entry = {"text": original_text, "label": label}
            if source_file:
                entry["source_file"] = source_file
            if story_id:
                entry["story_id"] = story_id
            # Add a context snippet: first 120 chars of the passage
            entry["passage_preview"] = plain_text[:120].replace("\n", " ")
            unmatched.append(entry)
            continue

        end = start + len(matched_text)
        entry = {"text": matched_text, "start": start, "end": end, "label": label}
        if ref:
            entry["ref"] = ref
        located.append(entry)
        search_from = end

    if unmatched:
        logger.warning(
            "%d/%d entities could not be located in text.",
            len(unmatched), len(entities),
        )
        if unmatched_log:
            _append_jsonl(unmatched_log, unmatched)

    return located


def _locate_one(text, plain_text, search_from):
    """Return (matched_text, start_index) or (text, None) if not found."""
    idx = plain_text.find(text, search_from)
    if idx >= 0:
        return text, idx
    return text, None


# ── Ref preservation ───────────────────────────────────────────────────────────

def preserve_refs(corrected_entities, original_entities):
    """
    Attach ref attributes from original_entities to corrected_entities.

    Matches by normalized (text, label) pair. When the same text appears as
    both GPE and LOC in originals, GPE is preferred (since both map to placeName).

    Args:
        corrected_entities: List of corrected entity dicts (may lack ref).
        original_entities: List of original entity dicts (with ref).

    Returns:
        corrected_entities with ref filled in where a match is found.
    """
    # Build lookup: (normalized_text, code_label) → ref
    ref_map = {}
    for ent in original_entities:
        if ent.get("ref"):
            key = (_norm(ent["text"]), ent["label"])
            ref_map[key] = ent["ref"]
            # Also index under placeName for LOC↔GPE flexibility
            if ent["label"] in ("GPE", "LOC"):
                ref_map[(_norm(ent["text"]), "placeName")] = ent["ref"]

    result = []
    for ent in corrected_entities:
        key = (_norm(ent["text"]), ent["label"])
        ref = ref_map.get(key) or ref_map.get((_norm(ent["text"]), "placeName"))
        entry = dict(ent)
        if ref:
            entry["ref"] = ref
        result.append(entry)
    return result


def _norm(text):
    """Normalize text for ref lookup: strip geresh/gershayim and whitespace."""
    return _DIACRITICS_RE.sub("", text).strip()


# ── Statistics ─────────────────────────────────────────────────────────────────

def compute_correction_stats(original, corrected):
    """
    Compare original and corrected entity lists.

    Returns dict with keys: added, removed, reclassified,
    total_original, total_corrected.
    """
    orig_spans = {(e["start"], e["end"]): e for e in original}
    corr_spans = {(e["start"], e["end"]): e for e in corrected}

    orig_keys = set(orig_spans)
    corr_keys = set(corr_spans)

    return {
        "added": len(corr_keys - orig_keys),
        "removed": len(orig_keys - corr_keys),
        "reclassified": sum(
            1 for k in orig_keys & corr_keys
            if orig_spans[k]["label"] != corr_spans[k]["label"]
        ),
        "total_original": len(original),
        "total_corrected": len(corrected),
    }


# ── High-level correction orchestration ───────────────────────────────────────

def correct_entities(
    plain_text,
    existing_entities,
    tree,
    api_key=None,
    model=None,
    passages_per_call=3,
    source_file=None,
    delay=None,
    progress_cb=None,
    unmatched_log=None,
    max_removal_pct=None,
    story_id=None,
):
    """
    Correct existing annotations in a document using Gemini.

    Chunks the document by <div type="story"> (or falls back to one big chunk),
    sends batches of passages_per_call stories to Gemini, re-locates the
    corrected entities in the plain text, and returns the full corrected list.

    Args:
        plain_text: Full plain text of the document (after stripping annotations).
        existing_entities: Entity list from extract_existing_entities_simple()
                           (start/end relative to plain_text, includes ref).
        tree: lxml ElementTree (stripped of annotations) — used for div structure.
        api_key: Gemini API key (or read from env/dotenv).
        model: Gemini model name (default: GEMINI_MODEL from config).
        passages_per_call: Number of story divs per Gemini API call.
        delay: Seconds between API calls (default: GEMINI_DELAY from config).
        progress_cb: Optional callable(current_call, total_calls).
        unmatched_log: Path to JSONL file for logging unmatched entities.
        max_removal_pct: Retention guard threshold (0–100).  Any passage where
                         Gemini removes more than this percentage of existing
                         entities is silently reverted to the originals.  None
                         (default) disables the guard.  Recommended: 40.0.
        story_id: Optional xml:id of a single story div to correct. When set,
              only that story is sent to Gemini; entities outside that
              story are preserved unchanged.

    Returns:
        Corrected list of entity dicts with start/end offsets in plain_text.
        ref attributes from original entities are NOT yet attached — call
        preserve_refs() afterwards.
    """
    delay_s = delay if delay is not None else GEMINI_DELAY
    model_name = model or GEMINI_MODEL
    client = _get_client(api_key)

    chunks = get_story_div_chunks(tree, plain_text, existing_entities)
    if story_id is not None:
        selected_chunks = [chunk for chunk in chunks if chunk[3] == story_id]
        if not selected_chunks:
            raise ValueError(f"Story id not found: {story_id}")
    else:
        selected_chunks = chunks

    selected_spans = [
        (offset, offset + len(chunk_text))
        for chunk_text, _, offset, _ in selected_chunks
    ]

    untouched_entities = [
        dict(ent)
        for ent in existing_entities
        if not any(
            ent["start"] >= start and ent["end"] <= end
            for start, end in selected_spans
        )
    ]

    total_calls = (len(selected_chunks) + passages_per_call - 1) // passages_per_call

    all_corrected = untouched_entities
    seen_spans = {
        (e["start"], e["end"], e["label"])
        for e in untouched_entities
    }  # (abs_start, abs_end, label) — dedup across batch overlaps

    for batch_idx in range(0, len(selected_chunks), passages_per_call):
        batch = selected_chunks[batch_idx : batch_idx + passages_per_call]
        passages = [(chunk_text, chunk_ents) for chunk_text, chunk_ents, _, _ in batch]

        corrected_batch = _call_gemini_passages(
            passages, client, model_name,
            max_removal_pct=max_removal_pct,
        )

        for passage_corrected, (chunk_text, _, offset, div_id) in zip(corrected_batch, batch):
            # Re-locate: don't trust Gemini's offsets, re-find by text
            log_path = str(unmatched_log) if unmatched_log else None
            located = locate_entities_in_text(
                passage_corrected, chunk_text, unmatched_log=log_path,
                source_file=source_file, story_id=div_id,
            )
            # Map chunk-relative offsets → full-text absolute offsets
            for ent in located:
                abs_start = ent["start"] + offset
                abs_end = ent["end"] + offset
                span_key = (abs_start, abs_end, ent["label"])
                if span_key not in seen_spans:
                    seen_spans.add(span_key)
                    all_corrected.append(
                        {**ent, "start": abs_start, "end": abs_end}
                    )

        call_num = batch_idx // passages_per_call + 1
        if progress_cb:
            progress_cb(call_num, total_calls)

        # Rate-limit between calls (not after the last one)
        if batch_idx + passages_per_call < len(selected_chunks) and delay_s > 0:
            time.sleep(delay_s)

    all_corrected.sort(key=lambda e: (e["start"], e["end"]))
    return all_corrected


# ── Utilities ──────────────────────────────────────────────────────────────────

def _append_jsonl(path, records):
    """Append records to a JSONL file (creates file if needed)."""
    with open(path, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ── Correction diff logging ──────────────────────────────────────────────────

def log_correction_diff(original, corrected, output_path, source_file=None):
    """
    Write a detailed entity-level diff between original and corrected lists
    to a TSV file for human review.

    Each row is one change: added, removed, or reclassified.
    Entities that are identical in both lists are omitted (no noise).

    Args:
        original: List of original entity dicts.
        corrected: List of corrected entity dicts.
        output_path: Path to write the TSV.
        source_file: Optional source filename for context column.
    """
    import csv

    orig_spans = {(e["start"], e["end"]): e for e in original}
    corr_spans = {(e["start"], e["end"]): e for e in corrected}

    orig_keys = set(orig_spans)
    corr_keys = set(corr_spans)

    rows = []

    # Removed entities
    for key in sorted(orig_keys - corr_keys):
        e = orig_spans[key]
        rows.append({
            "action": "removed",
            "text": e["text"],
            "original_label": e["label"],
            "corrected_label": "",
            "start": e["start"],
            "end": e["end"],
            "source_file": source_file or "",
        })

    # Added entities
    for key in sorted(corr_keys - orig_keys):
        e = corr_spans[key]
        rows.append({
            "action": "added",
            "text": e["text"],
            "original_label": "",
            "corrected_label": e["label"],
            "start": e["start"],
            "end": e["end"],
            "source_file": source_file or "",
        })

    # Reclassified entities
    for key in sorted(orig_keys & corr_keys):
        o = orig_spans[key]
        c = corr_spans[key]
        if o["label"] != c["label"]:
            rows.append({
                "action": "reclassified",
                "text": o["text"],
                "original_label": o["label"],
                "corrected_label": c["label"],
                "start": o["start"],
                "end": o["end"],
                "source_file": source_file or "",
            })

    if not rows:
        logger.info("No corrections to log (original == corrected).")
        return

    rows.sort(key=lambda r: r["start"])

    fieldnames = [
        "action", "text", "original_label", "corrected_label",
        "start", "end", "source_file",
    ]

    write_header = not Path(output_path).exists()
    with open(output_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)

    logger.info(
        "Logged %d corrections to %s (%d added, %d removed, %d reclassified)",
        len(rows), output_path,
        sum(1 for r in rows if r["action"] == "added"),
        sum(1 for r in rows if r["action"] == "removed"),
        sum(1 for r in rows if r["action"] == "reclassified"),
    )
