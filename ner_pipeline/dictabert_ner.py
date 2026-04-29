"""
DictaBERT NER: lazy model loading, inference on text chunks,
morphological segmentation alignment, and entity extraction.
"""

from itertools import chain
from .config import MODEL_NAME, MODEL_TYPE, MAX_TOKENS_PER_CHUNK, SKIP_LABELS

# Lazy-loaded singletons
_model = None
_tokenizer = None
_ner_pipeline = None


def get_model_and_tokenizer():
    """Load DictaBERT joint model and tokenizer once (lazy singleton)."""
    global _model, _tokenizer
    if _model is None:
        from transformers import AutoModel, AutoTokenizer

        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModel.from_pretrained(MODEL_NAME, trust_remote_code=True)
        _model.eval()
    return _model, _tokenizer


def get_tokenizer():
    """Return just the tokenizer (loads model if not yet loaded)."""
    if MODEL_TYPE == "pipeline":
        # For pipeline models, tokenizer is bundled in the pipeline itself.
        # Return None; callers that only need a tokenizer for chunking should
        # fall back to the joint tokenizer.
        from transformers import AutoTokenizer
        return AutoTokenizer.from_pretrained(MODEL_NAME)
    _, tok = get_model_and_tokenizer()
    return tok


def get_ner_pipeline():
    """Load a standard HuggingFace token-classification pipeline (lazy singleton)."""
    global _ner_pipeline
    if _ner_pipeline is None:
        from transformers import pipeline
        _ner_pipeline = pipeline(
            "ner",
            model=MODEL_NAME,
            tokenizer=MODEL_NAME,
            aggregation_strategy="simple",
        )
    return _ner_pipeline


# ---------------------------------------------------------------------------
# NER prediction helpers (adapted from xml_to_df_utils.py)
# ---------------------------------------------------------------------------


def _extract_ner_with_words(data):
    """
    Map NER entities back to token text.
    Returns list of dicts: {label, word, start, end}.
    """
    tokens = data["tokens"]
    position_to_token = {i: t["token"] for i, t in enumerate(tokens)}
    results = []
    for ent in data.get("ner_entities", []):
        word = "".join(
            position_to_token[i]
            for i in range(ent["token_start"], ent["token_end"] + 1)
        )
        results.append({
            "label": ent["label"],
            "word": word,
            "start": ent["start"],
            "end": ent["end"],
        })
    return results


def _words_with_positions(preds):
    """Return list of ((start, end), (word, label))."""
    return [((e["start"], e["end"]), (e["word"], e["label"])) for e in preds]


def _parse_segmentation(tokens):
    """
    Parse morphological segmentation from tokens.
    Returns (joined_segments_str, seg_tups_list).
    seg_tups_list entries: ((start, end), seg_tuple) for multi-segment tokens.
    """
    seg_elems = []
    seg_tups = []
    for token in tokens:
        seg = token["seg"]
        offsets = token["offsets"]
        if len(seg) == 1:
            seg_elems.append(seg[0])
        elif len(seg) == 2:
            # First segment is a prefix particle (BACHLAM) — skip it
            seg_elems.append(seg[1])
            seg_tups.append(((offsets["start"], offsets["end"]), seg))
        else:
            # 3+ segments — unusual, keep last
            seg_elems.append(seg[-1])
            seg_tups.append(((offsets["start"], offsets["end"]), seg))
    return " ".join(seg_elems), seg_tups


def _align_ner_with_segments(ner_by_word, seg_tups):
    """
    Align NER entities with morphological segmentation to strip Hebrew
    prefix particles from entity spans.

    Returns dict: (start, end) -> (original_tuple, seg_parts_or_None, corrected_tuple).
    """
    ner_dict = {pos: val for pos, val in ner_by_word}
    seg_dict = {s[0][0]: s[1] for s in seg_tups}

    mapping = {}
    for key, val in ner_dict.items():
        if key[0] in seg_dict:
            seg_parts = seg_dict[key[0]]
            corrected_word = val[0].removeprefix(seg_parts[0])
            mapping[key] = (val, seg_parts, (corrected_word, val[1]))
        else:
            mapping[key] = (val, None, val)
    return mapping


def _adjust_offsets(preds, start_idx):
    """Shift all token and NER entity offsets by start_idx."""
    for token in preds.get("tokens", []):
        offsets = token.get("offsets", {})
        if "start" in offsets:
            offsets["start"] += start_idx
        if "end" in offsets:
            offsets["end"] += start_idx
    for ent in preds.get("ner_entities", []):
        ent["start"] += start_idx
        ent["end"] += start_idx
    return preds


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _run_ner_pipeline(plain_text, progress_cb=None):
    """
    Run a standard HuggingFace NER pipeline on *plain_text*.

    Handles long texts by splitting into ~450-token chunks (by character
    estimate) to avoid the model's max-sequence-length limit.

    Returns list of entity dicts: {text, start, end, label}.
    """
    from .text_extraction import chunk_text
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    chunks = chunk_text(plain_text, tokenizer, max_tokens=MAX_TOKENS_PER_CHUNK)

    ner = get_ner_pipeline()
    entities = []

    for i, (chunk, start_idx) in enumerate(chunks):
        results = ner(chunk)
        for ent in results:
            label = ent["entity_group"]
            if label in SKIP_LABELS:
                continue
            entities.append({
                "text": ent["word"],
                "start": ent["start"] + start_idx,
                "end": ent["end"] + start_idx,
                "label": label,
            })
        if progress_cb:
            progress_cb(i + 1, len(chunks))

    return entities


def run_ner(plain_text, progress_cb=None):
    """
    Run DictaBERT NER on *plain_text*.

    Dispatches to the joint model (.predict() API) or a standard HuggingFace
    pipeline based on the MODEL_TYPE config setting.

    Args:
        plain_text: Full document text.
        progress_cb: Optional callable(current, total) for progress reporting.

    Returns:
        List of entity dicts: {text, start, end, label}.
    """
    if MODEL_TYPE == "pipeline":
        return _run_ner_pipeline(plain_text, progress_cb=progress_cb)

    from .text_extraction import chunk_text

    model, tokenizer = get_model_and_tokenizer()

    chunks = chunk_text(plain_text, tokenizer, max_tokens=MAX_TOKENS_PER_CHUNK)

    all_preds = []
    for i, (chunk, start_idx) in enumerate(chunks):
        preds = model.predict(chunk, tokenizer, output_style="json")
        preds = _adjust_offsets(preds, start_idx)
        all_preds.append(preds)
        if progress_cb:
            progress_cb(i + 1, len(chunks))

    # Extract and align entities across all chunks
    entities = []
    for preds in all_preds:
        ner_words = _extract_ner_with_words(preds)
        ner_by_word = _words_with_positions(ner_words)
        _, seg_tups = _parse_segmentation(preds["tokens"])
        aligned = _align_ner_with_segments(ner_by_word, seg_tups)

        for (start, end), (original, seg_parts, corrected) in aligned.items():
            label = corrected[1]
            if label in SKIP_LABELS:
                continue

            # Calculate prefix offset if segmentation removed a prefix
            offset = 0
            if seg_parts is not None:
                offset = len(seg_parts[0])

            entities.append({
                "text": corrected[0],
                "start": start + offset,
                "end": end,
                "label": label,
            })

    return entities
