"""
Text extraction from TEI XML using standoffconverter, plus token-aware chunking.
"""

from standoffconverter import Standoff, View
from lxml import etree
from .config import NAMESPACES, TEI_NS


def strip_facsimile_elements(tree):
    """
    Remove all <facsimile> element blocks from the tree in-place.
    
    Facsimile blocks contain page/image metadata and are not needed for NER
    annotation. They typically appear in the TEI header and can be large.
    
    Args:
        tree: lxml ElementTree (modified in-place).
    """
    root = tree.getroot()
    for facsimile in root.findall(f".//{{{TEI_NS}}}facsimile"):
        parent = facsimile.getparent()
        if parent is not None:
            parent.remove(facsimile)


def create_standoff_view(tree):
    """
    Create a Standoff object and View from an lxml ElementTree.

    Strips <facsimile> element blocks first to clean up the metadata for processing.

    Returns:
        (so, view, plain_text): Standoff object, View object, and plain text string.
    """
    strip_facsimile_elements(tree)
    so = Standoff(tree, NAMESPACES)
    view = View(so)
    plain_text = view.get_plain()
    return so, view, plain_text


def chunk_text(text, tokenizer, max_tokens=512):
    """
    Chunk text into segments at sentence boundaries, respecting the token limit.

    Each chunk stays within *max_tokens* (minus special-token overhead).
    Boundaries prefer periods, then spaces.

    Args:
        text: Full plain text.
        tokenizer: HuggingFace tokenizer instance.
        max_tokens: Maximum tokens per chunk (default 512).

    Returns:
        List of (chunk_text, start_char_index) tuples.
    """
    if not text:
        return []

    tokens = tokenizer(text, return_offsets_mapping=True, truncation=False)
    input_ids = tokens["input_ids"]
    offsets = tokens["offset_mapping"]

    if not input_ids or not offsets:
        return [(text, 0)]

    # Reserve room for special tokens
    special_tokens = tokenizer.build_inputs_with_special_tokens([])
    max_tokens = max(1, max_tokens - len(special_tokens))

    chunks = []
    start_idx = 0

    while start_idx < len(input_ids):
        end_idx = min(start_idx + max_tokens, len(input_ids))
        if start_idx >= end_idx:
            break

        chunk_offsets = offsets[start_idx:end_idx]
        if not chunk_offsets:
            break

        char_start = chunk_offsets[0][0]
        char_end = chunk_offsets[-1][1]

        # Try to break at a sentence or word boundary
        if end_idx < len(input_ids):
            current_text = text[char_start:char_end]
            # Prefer period
            last_period = current_text.rfind(".")
            if last_period != -1:
                new_char_end = char_start + last_period + 1
            else:
                last_space = current_text.rfind(" ")
                if last_space != -1:
                    new_char_end = char_start + last_space + 1
                else:
                    new_char_end = None

            if new_char_end is not None:
                for i, (_, end) in enumerate(chunk_offsets):
                    if end > new_char_end:
                        end_idx = start_idx + i
                        char_end = new_char_end
                        break

        original_chunk = text[char_start:char_end]
        if original_chunk:
            chunks.append((original_chunk, char_start))

        start_idx = end_idx

    if not chunks:
        return [(text, 0)]

    # Catch any remaining text
    last_end = chunks[-1][1] + len(chunks[-1][0])
    if last_end < len(text):
        remaining = text[last_end:]
        if remaining:
            chunks.append((remaining, last_end))

    return chunks
