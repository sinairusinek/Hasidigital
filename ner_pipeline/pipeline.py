"""
NER pipeline orchestrator.

Ties together: structural preprocessing → text extraction → DictaBERT NER
→ Gemini correction → annotation insertion → cleanup → save.

Also provides run_correction_pass() for Gemini-only re-correction of
already-annotated files (no DictaBERT involved).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

from lxml import etree

from .config import NAMESPACES, GEMINI_MODEL


@dataclass
class PipelineResult:
    """Summary of a pipeline run."""
    input_path: str
    output_path: str
    was_preprocessed: bool = False
    had_existing_annotations: bool = False
    stripped_existing: bool = False
    entity_count: int = 0
    entities_by_type: dict = field(default_factory=dict)
    gemini_used: bool = False
    gemini_stats: Optional[dict] = None


def run_pipeline(
    input_path,
    output_path=None,
    use_gemini=True,
    gemini_api_key=None,
    preprocess=True,
    force=False,
    progress_cb=None,
):
    """
    Run the full NER annotation pipeline on a TEI XML file.

    Args:
        input_path: Path to the input XML file.
        output_path: Path for the output XML. Defaults to overwriting input.
        use_gemini: Whether to run Gemini post-correction.
        gemini_api_key: Gemini API key (or uses env var).
        preprocess: Whether to run structural preprocessing if needed.
        force: If True, strip existing annotations and re-annotate.
        progress_cb: Optional callable(stage_name, detail) for progress.

    Returns:
        PipelineResult with summary statistics.
    """
    from .structural_preprocess import (
        needs_structural_preprocessing,
        restructure_facsimile_zones,
        remove_facsimile_and_attrs,
    )
    from .text_extraction import create_standoff_view
    from .dictabert_ner import run_ner
    from .annotation_inserter import (
        insert_annotations,
        save_annotated_xml,
        has_existing_annotations,
        strip_existing_annotations,
    )

    input_path = str(input_path)
    output_path = output_path or input_path

    def _progress(stage, detail=""):
        if progress_cb:
            progress_cb(stage, detail)

    # ── Parse XML ─────────────────────────────────────────────────────────
    _progress("parse", f"Parsing {Path(input_path).name}")
    tree = etree.parse(input_path)

    result = PipelineResult(input_path=input_path, output_path=str(output_path))

    # ── Check existing annotations ────────────────────────────────────────
    result.had_existing_annotations = has_existing_annotations(tree)
    if result.had_existing_annotations and not force:
        _progress("skip", "File already annotated (use force=True to re-annotate)")
        return result

    if result.had_existing_annotations and force:
        _progress("strip", "Stripping existing annotations")
        strip_existing_annotations(tree)
        result.stripped_existing = True

    # ── Structural preprocessing ──────────────────────────────────────────
    if preprocess and needs_structural_preprocessing(tree):
        _progress("preprocess", "Restructuring facsimile zones")
        restructure_facsimile_zones(tree)
        result.was_preprocessed = True

    # ── Create standoff view ──────────────────────────────────────────────
    _progress("standoff", "Creating standoff view")
    so, view, plain_text = create_standoff_view(tree)

    # ── DictaBERT NER ─────────────────────────────────────────────────────
    _progress("ner", "Running DictaBERT NER")

    def _ner_progress(current, total):
        _progress("ner", f"DictaBERT chunk {current}/{total}")

    entities = run_ner(plain_text, progress_cb=_ner_progress)
    dictabert_count = len(entities)

    # ── Gemini correction ─────────────────────────────────────────────────
    gemini_stats = None
    if use_gemini:
        _progress("gemini", "Running Gemini correction")
        from .gemini_corrector import (
            correct_entities as _correct,
            compute_correction_stats,
            log_correction_diff,
        )

        def _gemini_progress(current, total):
            _progress("gemini", f"Gemini batch {current}/{total}")

        corrected = _correct(
            plain_text=plain_text,
            existing_entities=entities,
            tree=tree,
            api_key=gemini_api_key,
            progress_cb=_gemini_progress,
            source_file=Path(input_path).name,
        )
        gemini_stats = compute_correction_stats(entities, corrected)

        # Log detailed diff
        diff_log = Path(input_path).parent / "gemini-correction-log.tsv"
        log_correction_diff(
            entities, corrected, str(diff_log),
            source_file=Path(input_path).name,
        )

        entities = corrected
        result.gemini_used = True
        result.gemini_stats = gemini_stats

    # ── Insert annotations ────────────────────────────────────────────────
    _progress("insert", f"Inserting {len(entities)} annotations")
    insert_annotations(so, view, entities)

    # ── Nisba/bio nesting fix ────────────────────────────────────────────
    from .nisba_fixer import fix_nisba_nesting
    nisba_count = fix_nisba_nesting(tree)
    if nisba_count:
        _progress("nisba", f"Merged {nisba_count} nisba patterns")

    # ── Cleanup ───────────────────────────────────────────────────────────
    _progress("cleanup", "Removing facsimile attributes")
    remove_facsimile_and_attrs(tree)

    # ── Save ──────────────────────────────────────────────────────────────
    _progress("save", f"Saving to {Path(output_path).name}")
    save_annotated_xml(tree, output_path)

    # ── Validate ─────────────────────────────────────────────────────────
    from .tei_validator import validate_and_log
    vwarnings = validate_and_log(tree, label=Path(output_path).name)
    if vwarnings:
        _progress("validate", f"{len(vwarnings)} validation warning(s)")
    else:
        _progress("validate", "Passed")

    # ── Statistics ────────────────────────────────────────────────────────
    result.entity_count = len(entities)
    by_type = {}
    for ent in entities:
        by_type[ent["label"]] = by_type.get(ent["label"], 0) + 1
    result.entities_by_type = by_type

    _progress("done", f"Complete: {result.entity_count} entities")
    return result


def run_correction_pass(
    input_path,
    output_path=None,
    gemini_api_key=None,
    model=None,
    passages_per_call=3,
    progress_cb=None,
    max_removal_pct=None,
    story_id=None,
):
    """
    Run Gemini correction on an already-annotated TEI XML file.

    Extracts existing entities, sends them to Gemini for review and correction,
    then re-inserts the corrected entities (with ref attributes preserved).

    Args:
        input_path: Path to an annotated TEI XML file.
        output_path: Output path. Defaults to overwriting input_path.
        gemini_api_key: Gemini API key (or read from GOOGLE_API_KEY / .env).
        model: Gemini model name (default: GEMINI_MODEL from config).
        passages_per_call: Story divs sent per Gemini API call.
        progress_cb: Optional callable(stage_name, detail_str).
        max_removal_pct: Retention guard (0–100).  Passages where Gemini removes
                         more than this percentage of entities fall back to
                         originals.  None disables the guard.  Recommended: 40.0.
        story_id: Optional xml:id of a single story div to correct. When set,
              only that story is sent to Gemini and the rest of the file is
              preserved unchanged.

    Returns:
        PipelineResult with summary statistics.

    Raises:
        ValueError: If the file has no existing annotations
                    (use run_pipeline() for fresh annotation).
    """
    from .annotation_inserter import (
        extract_existing_entities_simple,
        has_existing_annotations,
        strip_existing_annotations,
        insert_annotations,
        save_annotated_xml,
    )
    from .text_extraction import create_standoff_view
    from .gemini_corrector import (
        correct_entities,
        preserve_refs,
        compute_correction_stats,
        log_correction_diff,
    )

    input_path = str(input_path)
    output_path = str(output_path) if output_path else input_path
    model = model or GEMINI_MODEL

    def _progress(stage, detail=""):
        if progress_cb:
            progress_cb(stage, detail)

    # ── Parse ──────────────────────────────────────────────────────────────
    _progress("parse", f"Parsing {Path(input_path).name}")
    tree = etree.parse(input_path)

    result = PipelineResult(input_path=input_path, output_path=output_path)
    result.had_existing_annotations = has_existing_annotations(tree)

    if not result.had_existing_annotations:
        raise ValueError(
            f"{Path(input_path).name} has no existing annotations. "
            "Use run_pipeline() for full NER annotation."
        )

    # ── Extract existing entities ──────────────────────────────────────────
    _progress("extract", "Extracting existing annotations")
    existing_entities, plain_text = extract_existing_entities_simple(tree)
    _progress("extract", f"Found {len(existing_entities)} existing entities")

    # ── Strip annotations ──────────────────────────────────────────────────
    # IMPORTANT: plain_text is captured BEFORE stripping.  Stripping adjacent
    # annotation tags can fuse their text content (no whitespace between tags),
    # producing strings like "אברהםישמעאל" that Gemini then annotates as a
    # single entity.  Using the pre-strip plain_text avoids this entirely.
    _progress("strip", "Stripping existing annotations")
    strip_existing_annotations(tree)
    result.stripped_existing = True

    # ── Create fresh standoff view (clean tree, for re-insertion only) ──────
    _progress("standoff", "Creating standoff view")
    so, view, _ = create_standoff_view(tree)

    # ── Gemini correction ──────────────────────────────────────────────────
    _progress("gemini", f"Running Gemini correction ({len(existing_entities)} entities)")

    unmatched_log = Path(__file__).parent / "unmatched_entities.jsonl"

    def _gemini_progress(current, total):
        _progress("gemini", f"Gemini batch {current}/{total}")

    corrected = correct_entities(
        plain_text=plain_text,
        existing_entities=existing_entities,
        tree=tree,
        api_key=gemini_api_key,
        model=model,
        passages_per_call=passages_per_call,
        source_file=Path(input_path).name,
        progress_cb=_gemini_progress,
        unmatched_log=str(unmatched_log),
        max_removal_pct=max_removal_pct,
        story_id=story_id,
    )

    # ── Preserve refs from original entities ──────────────────────────────
    corrected = preserve_refs(corrected, existing_entities)

    # ── Document-level retention guard ────────────────────────────────────
    # Per-passage guard only covers entities inside story divs.
    # This global check catches silent drops of entities outside story divs
    # or any other wholesale removal that slipped through.
    n_orig = len(existing_entities)
    n_corr = len(corrected)
    if max_removal_pct is not None and n_orig > 0:
        global_loss_pct = (n_orig - n_corr) / n_orig * 100
        if global_loss_pct > max_removal_pct:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "Document-level retention guard triggered: %.0f%% entity loss "
                "(%d → %d; threshold %.0f%%). Reverting to original annotations.",
                global_loss_pct, n_orig, n_corr, max_removal_pct,
            )
            _progress(
                "guard",
                f"REVERTED: {global_loss_pct:.0f}% loss ({n_orig}→{n_corr}) "
                f"exceeds {max_removal_pct:.0f}% threshold — keeping original",
            )
            # Re-parse original and write it unchanged to output_path
            original_tree = etree.parse(input_path)
            save_annotated_xml(original_tree, output_path)
            result.entity_count = n_orig
            result.entities_by_type = {}
            for ent in existing_entities:
                lbl = ent["label"]
                result.entities_by_type[lbl] = result.entities_by_type.get(lbl, 0) + 1
            result.gemini_stats = {
                "added": 0, "removed": 0, "reclassified": 0,
                "total_original": n_orig, "total_corrected": n_orig,
                "reverted": True,
                "global_loss_pct": round(global_loss_pct, 1),
            }
            result.gemini_used = True
            _progress("done", f"Reverted: {n_orig} original entities preserved")
            return result

    # ── Statistics ────────────────────────────────────────────────────────
    gemini_stats = compute_correction_stats(existing_entities, corrected)
    result.gemini_used = True
    result.gemini_stats = gemini_stats

    # ── Log detailed diff ──────────────────────────────────────────────────
    diff_log = Path(input_path).parent / "gemini-correction-log.tsv"
    log_correction_diff(
        existing_entities, corrected, str(diff_log),
        source_file=Path(input_path).name,
    )
    _progress("log", f"Correction diff → {diff_log.name}")

    # ── Insert corrected annotations ───────────────────────────────────────
    _progress("insert", f"Inserting {len(corrected)} annotations")
    insert_annotations(so, view, corrected)

    # ── Nisba/bio nesting fix ────────────────────────────────────────────
    from .nisba_fixer import fix_nisba_nesting
    nisba_count = fix_nisba_nesting(tree)
    if nisba_count:
        _progress("nisba", f"Merged {nisba_count} nisba patterns")

    # ── Save ──────────────────────────────────────────────────────────────
    _progress("save", f"Saving to {Path(output_path).name}")
    save_annotated_xml(tree, output_path)

    # ── Validate ─────────────────────────────────────────────────────────
    from .tei_validator import validate_and_log
    vwarnings = validate_and_log(tree, label=Path(output_path).name)
    if vwarnings:
        _progress("validate", f"{len(vwarnings)} validation warning(s)")
    else:
        _progress("validate", "Passed")

    result.entity_count = len(corrected)
    by_type = {}
    for ent in corrected:
        by_type[ent["label"]] = by_type.get(ent["label"], 0) + 1
    result.entities_by_type = by_type

    _progress("done", f"Complete: {result.entity_count} entities")
    return result


def run_gemini_only_pipeline(
    input_path,
    output_path=None,
    gemini_api_key=None,
    model=None,
    passages_per_call=3,
    progress_cb=None,
):
    """
    Run Gemini-only NER annotation on a TEI XML file (no DictaBERT).

    Sends plain text to Gemini with an empty entity list, letting Gemini
    find all entities from scratch using its "Find missed entities" instruction.
    """
    from .annotation_inserter import (
        has_existing_annotations,
        strip_existing_annotations,
        insert_annotations,
        save_annotated_xml,
    )
    from .text_extraction import create_standoff_view
    from .gemini_corrector import (
        correct_entities,
        compute_correction_stats,
        log_correction_diff,
    )

    input_path = str(input_path)
    output_path = str(output_path) if output_path else input_path
    model = model or GEMINI_MODEL

    def _progress(stage, detail=""):
        if progress_cb:
            progress_cb(stage, detail)

    _progress("parse", f"Parsing {Path(input_path).name}")
    tree = etree.parse(input_path)

    result = PipelineResult(input_path=input_path, output_path=output_path)
    result.had_existing_annotations = has_existing_annotations(tree)

    if result.had_existing_annotations:
        _progress("strip", "Stripping existing annotations")
        strip_existing_annotations(tree)
        result.stripped_existing = True

    _progress("standoff", "Creating standoff view")
    so, view, plain_text = create_standoff_view(tree)

    _progress("gemini", "Running Gemini annotation (from scratch)")
    unmatched_log = Path(__file__).parent / "unmatched_entities.jsonl"

    def _gemini_progress(current, total):
        _progress("gemini", f"Gemini batch {current}/{total}")

    corrected = correct_entities(
        plain_text=plain_text,
        existing_entities=[],
        tree=tree,
        api_key=gemini_api_key,
        model=model,
        passages_per_call=passages_per_call,
        source_file=Path(input_path).name,
        progress_cb=_gemini_progress,
        unmatched_log=str(unmatched_log),
    )

    gemini_stats = compute_correction_stats([], corrected)
    result.gemini_used = True
    result.gemini_stats = gemini_stats

    # Log detailed diff (gemini-only: everything is "added")
    diff_log = Path(input_path).parent / "gemini-correction-log.tsv"
    log_correction_diff(
        [], corrected, str(diff_log),
        source_file=Path(input_path).name,
    )

    _progress("insert", f"Inserting {len(corrected)} annotations")
    insert_annotations(so, view, corrected)

    from .nisba_fixer import fix_nisba_nesting
    nisba_count = fix_nisba_nesting(tree)
    if nisba_count:
        _progress("nisba", f"Merged {nisba_count} nisba patterns")

    _progress("save", f"Saving to {Path(output_path).name}")
    save_annotated_xml(tree, output_path)

    # ── Validate ─────────────────────────────────────────────────────────
    from .tei_validator import validate_and_log
    vwarnings = validate_and_log(tree, label=Path(output_path).name)
    if vwarnings:
        _progress("validate", f"{len(vwarnings)} validation warning(s)")
    else:
        _progress("validate", "Passed")

    result.entity_count = len(corrected)
    by_type = {}
    for ent in corrected:
        by_type[ent["label"]] = by_type.get(ent["label"], 0) + 1
    result.entities_by_type = by_type

    _progress("done", f"Complete: {result.entity_count} entities (gemini-only)")
    return result
