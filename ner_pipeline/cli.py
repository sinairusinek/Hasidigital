"""
CLI entry point for the NER annotation pipeline.

Full annotation (DictaBERT + optional Gemini):
    python -m ner_pipeline.cli --input editions/incoming/file.xml
    python -m ner_pipeline.cli --input editions/incoming/ --skip-annotated
    python -m ner_pipeline.cli --input file.xml --no-gemini --output-dir out/

Correction-only (Gemini re-review of already-annotated files):
    python -m ner_pipeline.cli --input editions/incoming/file.xml --correct
    python -m ner_pipeline.cli --input editions/incoming/ --correct
    python -m ner_pipeline.cli --input file.xml --correct --model gemini-2.0-flash
"""

import argparse
import os
import sys
import time
from pathlib import Path


def _find_xml_files(path):
    """Return list of XML file paths from a file or directory."""
    p = Path(path)
    if p.is_file() and p.suffix == ".xml":
        return [p]
    if p.is_dir():
        return sorted(p.glob("*.xml"))
    print(f"Error: {path} is not an XML file or directory.", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Run Hebrew NER annotation pipeline on TEI XML files."
    )
    parser.add_argument(
        "--input", required=True,
        help="Single XML file or directory of XMLs.",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory. Default: overwrite in place.",
    )
    parser.add_argument(
        "--output-suffix", default=None,
        help="Suffix for output files (e.g. '_annotated'). "
             "Defaults to '_corrected' in --correct mode, '' otherwise.",
    )
    parser.add_argument(
        "--gemini-api-key",
        help="Gemini API key (default: GOOGLE_API_KEY / GEMINI_API_KEY env var or .env).",
    )
    parser.add_argument(
        "--model", default=None,
        help="Gemini model name (default: from config, e.g. gemini-2.0-flash).",
    )
    parser.add_argument(
        "--correct", action="store_true",
        help=(
            "Correction-only mode: re-send existing annotations to Gemini for review. "
            "Skips DictaBERT. File must already be annotated."
        ),
    )
    parser.add_argument(
        "--nisba-fix", action="store_true",
        help=(
            "Nisba-fix-only mode: apply persName+placeName nesting fix to already-annotated "
            "files without re-running Gemini or DictaBERT. Modifies files in-place (or to "
            "--output-dir if specified)."
        ),
    )
    parser.add_argument(
        "--gemini-only", action="store_true",
        help=(
            "Gemini-only annotation: skip DictaBERT, let Gemini find all entities "
            "from scratch. For unannotated files."
        ),
    )
    parser.add_argument(
        "--no-gemini", action="store_true",
        help="Skip Gemini correction step (full-annotation mode only).",
    )
    parser.add_argument(
        "--skip-annotated", action="store_true",
        help="Skip files that already have NER annotations (full-annotation mode).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Strip existing annotations and re-annotate (full-annotation mode).",
    )
    parser.add_argument(
        "--no-preprocess", action="store_true",
        help="Skip structural preprocessing even if zones exist.",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show detailed progress.",
    )
    parser.add_argument(
        "--max-removal-pct",
        type=float,
        default=None,
        metavar="PCT",
        help=(
            "Retention guard for --correct mode (0–100).  When Gemini removes "
            "more than PCT%% of the existing entities in a story passage the "
            "passage is silently reverted to its original annotations instead of "
            "accepting the Gemini output.  Recommended: 40.  Default: disabled."
        ),
    )
    parser.add_argument(
        "--passages-per-call",
        type=int,
        default=3,
        metavar="N",
        help=(
            "Number of story passages to send per Gemini call in --correct/"
            "--gemini-only modes. Use 1 for strict story-by-story processing. "
            "Default: 3."
        ),
    )
    parser.add_argument(
        "--story-id",
        default=None,
        help=(
            "Optional xml:id of a single <div type=\"story\"> to process in "
            "--correct mode. Example: Kokhvei-Or_0001. Other stories remain "
            "unchanged."
        ),
    )

    args = parser.parse_args()

    if args.passages_per_call < 1:
        print("Error: --passages-per-call must be >= 1.", file=sys.stderr)
        sys.exit(1)

    # Resolve API key
    api_key = args.gemini_api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

    xml_files = _find_xml_files(args.input)
    if not xml_files:
        print("No XML files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(xml_files)} XML file(s) to process.")

    if args.correct and args.gemini_only:
        print("Error: --correct and --gemini-only are mutually exclusive.", file=sys.stderr)
        sys.exit(1)

    if args.story_id and not args.correct:
        print("Error: --story-id is supported only with --correct mode.", file=sys.stderr)
        sys.exit(1)

    if args.nisba_fix:
        print("Mode: Nisba-fix only (persName+placeName nesting, no Gemini/DictaBERT)")
    elif args.correct:
        print("Mode: Gemini correction-only (existing annotations will be re-reviewed)")
        if not api_key:
            print(
                "Error: Gemini API key required for --correct mode. "
                "Set GOOGLE_API_KEY or GEMINI_API_KEY.",
                file=sys.stderr,
            )
            sys.exit(1)
    elif args.gemini_only:
        print("Mode: Gemini-only annotation (no DictaBERT)")
        if not api_key:
            print(
                "Error: Gemini API key required for --gemini-only mode. "
                "Set GOOGLE_API_KEY or GEMINI_API_KEY.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        use_gemini = not args.no_gemini
        if use_gemini and not api_key:
            print(
                "Warning: No Gemini API key found. Running without Gemini correction.",
                file=sys.stderr,
            )
            use_gemini = False
        print(f"Mode: Full NER  |  Gemini correction: {'ON' if use_gemini else 'OFF'}")

    print()

    from .annotation_inserter import has_existing_annotations
    from lxml import etree

    if args.nisba_fix:
        from .nisba_fixer import fix_nisba_nesting
    elif args.correct:
        from .pipeline import run_correction_pass
    elif args.gemini_only:
        from .pipeline import run_gemini_only_pipeline
    else:
        from .pipeline import run_pipeline

    results = []

    # Resolve effective output suffix:
    # --correct mode defaults to "_corrected" to avoid overwriting originals.
    if args.output_suffix is not None:
        effective_suffix = args.output_suffix
    elif args.correct:
        effective_suffix = "_corrected"
    elif args.gemini_only:
        effective_suffix = "_gemini"
    else:
        effective_suffix = ""

    for i, xml_path in enumerate(xml_files, 1):
        name = xml_path.name
        print(f"[{i}/{len(xml_files)}] {name}")

        # Determine output path
        if args.output_dir:
            out_dir = Path(args.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = xml_path.stem + effective_suffix
            output_path = out_dir / f"{stem}{xml_path.suffix}"
        elif effective_suffix:
            stem = xml_path.stem + effective_suffix
            output_path = xml_path.parent / f"{stem}{xml_path.suffix}"
        else:
            output_path = xml_path

        # Progress callback (shared by both modes)
        def _progress(stage, detail=""):
            if args.verbose:
                print(f"  [{stage}] {detail}")

        t0 = time.time()

        if args.nisba_fix:
            # ── Nisba-fix-only mode ──────────────────────────────────────
            try:
                tree = etree.parse(str(xml_path))
                count = fix_nisba_nesting(tree)
                from .annotation_inserter import save_annotated_xml
                save_annotated_xml(tree, str(output_path))
                elapsed = time.time() - t0
                print(f"  -> {count} nisba merge(s) [{elapsed:.1f}s] -> {output_path.name}")
            except Exception as e:
                print(f"  -> ERROR: {e}", file=sys.stderr)
                if args.verbose:
                    import traceback
                    traceback.print_exc()

        elif args.correct:
            # ── Correction-only mode ─────────────────────────────────────
            try:
                result = run_correction_pass(
                    input_path=str(xml_path),
                    output_path=str(output_path),
                    gemini_api_key=api_key,
                    model=args.model,
                    passages_per_call=args.passages_per_call,
                    progress_cb=_progress,
                    max_removal_pct=args.max_removal_pct,
                    story_id=args.story_id,
                )
                elapsed = time.time() - t0
                results.append(result)

                type_str = ", ".join(
                    f"{k}={v}" for k, v in sorted(result.entities_by_type.items())
                )
                print(f"  -> {result.entity_count} entities ({type_str}) [{elapsed:.1f}s]")
                if result.gemini_stats:
                    gs = result.gemini_stats
                    print(
                        f"     Gemini: +{gs['added']} added, -{gs['removed']} removed, "
                        f"~{gs['reclassified']} reclassified"
                    )

            except ValueError as e:
                # File not annotated — skip with a clear message
                print(f"  -> Skipped: {e}", file=sys.stderr)
            except Exception as e:
                print(f"  -> ERROR: {e}", file=sys.stderr)
                if args.verbose:
                    import traceback
                    traceback.print_exc()

        elif args.gemini_only:
            # ── Gemini-only annotation mode ──────────────────────────────
            try:
                result = run_gemini_only_pipeline(
                    input_path=str(xml_path),
                    output_path=str(output_path),
                    gemini_api_key=api_key,
                    model=args.model,
                    passages_per_call=args.passages_per_call,
                    progress_cb=_progress,
                )
                elapsed = time.time() - t0
                results.append(result)

                type_str = ", ".join(
                    f"{k}={v}" for k, v in sorted(result.entities_by_type.items())
                )
                print(f"  -> {result.entity_count} entities ({type_str}) [{elapsed:.1f}s]")
                if result.gemini_stats:
                    gs = result.gemini_stats
                    print(f"     Gemini: +{gs['added']} added (from scratch)")

            except Exception as e:
                print(f"  -> ERROR: {e}", file=sys.stderr)
                if args.verbose:
                    import traceback
                    traceback.print_exc()

        else:
            # ── Full annotation mode ─────────────────────────────────────
            if args.skip_annotated:
                tree = etree.parse(str(xml_path))
                if has_existing_annotations(tree):
                    print(f"  -> Skipped (already annotated)")
                    continue

            try:
                result = run_pipeline(
                    input_path=str(xml_path),
                    output_path=str(output_path),
                    use_gemini=use_gemini,
                    gemini_api_key=api_key,
                    preprocess=not args.no_preprocess,
                    force=args.force,
                    progress_cb=_progress,
                )
                elapsed = time.time() - t0
                results.append(result)

                if result.entity_count == 0 and result.had_existing_annotations and not args.force:
                    print(f"  -> Skipped (already annotated)")
                else:
                    type_str = ", ".join(
                        f"{k}={v}" for k, v in sorted(result.entities_by_type.items())
                    )
                    print(f"  -> {result.entity_count} entities ({type_str}) [{elapsed:.1f}s]")
                    if result.gemini_stats:
                        gs = result.gemini_stats
                        print(
                            f"     Gemini: +{gs['added']} added, -{gs['removed']} removed, "
                            f"~{gs['reclassified']} reclassified"
                        )

            except Exception as e:
                print(f"  -> ERROR: {e}", file=sys.stderr)
                if args.verbose:
                    import traceback
                    traceback.print_exc()

    # Summary
    print()
    print("=" * 60)
    processed = [r for r in results if r.entity_count > 0]
    print(f"Processed: {len(processed)}/{len(xml_files)} files")
    total_entities = sum(r.entity_count for r in processed)
    print(f"Total entities: {total_entities}")


if __name__ == "__main__":
    main()
