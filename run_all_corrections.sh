#!/usr/bin/env bash
# Run Gemini correction pipeline on all annotated editions.
# Resume-safe: skips files that already have a _corrected.xml output.
#
# Usage:
#   cd /Users/sinairusinek/Documents/GitHub/Hasidigital
#   ./run_all_corrections.sh
#
# Optional: override model with env var:
#   GEMINI_MODEL=gemini-2.0-flash ./run_all_corrections.sh
# Optional safety/chunking overrides:
#   MAX_REMOVAL_PCT=40 PASSAGES_PER_CALL=1 ./run_all_corrections.sh
#
# Logs: run_corrections.log (appended, timestamped)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INPUT_DIR="$SCRIPT_DIR/editions/incoming"
LOG_FILE="$SCRIPT_DIR/run_corrections.log"
MODEL_FLAG=""
MAX_REMOVAL_PCT="${MAX_REMOVAL_PCT:-40}"
PASSAGES_PER_CALL="${PASSAGES_PER_CALL:-3}"

if [ -n "${GEMINI_MODEL:-}" ]; then
    MODEL_FLAG="--model $GEMINI_MODEL"
fi

# Load .env if present (for API key)
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Check API key (also accept .env loaded by Python — only warn, don't abort)
if [ -z "${GOOGLE_API_KEY:-}" ] && [ -z "${GEMINI_API_KEY:-}" ]; then
    if [ -f "$SCRIPT_DIR/.env" ] && grep -qE 'GOOGLE_API_KEY|GEMINI_API_KEY' "$SCRIPT_DIR/.env" 2>/dev/null; then
        echo "Note: API key found in .env (will be loaded by Python)"
    else
        echo "ERROR: No API key found. Set GOOGLE_API_KEY or GEMINI_API_KEY."
        echo "  Option 1: export GOOGLE_API_KEY=your-key"
        echo "  Option 2: echo 'GOOGLE_API_KEY=your-key' > $SCRIPT_DIR/.env"
        exit 1
    fi
fi

# Gather XML files (exclude already-corrected outputs)
FILES=()
for f in "$INPUT_DIR"/*.xml; do
    [[ "$(basename "$f")" == *_corrected.xml ]] && continue
    FILES+=("$f")
done

TOTAL=${#FILES[@]}
echo "=== Gemini Correction Pipeline ==="
echo "Found $TOTAL XML files in $INPUT_DIR"
echo "Retention guard: max_removal_pct=$MAX_REMOVAL_PCT"
echo "Passages per Gemini call: $PASSAGES_PER_CALL"
echo "Log: $LOG_FILE"
echo ""

SKIPPED=0
PROCESSED=0
FAILED=0

for i in "${!FILES[@]}"; do
    FILE="${FILES[$i]}"
    BASENAME="$(basename "$FILE")"
    STEM="${BASENAME%.xml}"
    CORRECTED="$INPUT_DIR/${STEM}_corrected.xml"
    NUM=$((i + 1))

    # Resume: skip if corrected file already exists
    if [ -f "$CORRECTED" ]; then
        echo "[$NUM/$TOTAL] $BASENAME — already corrected, skipping"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    echo "[$NUM/$TOTAL] $BASENAME — starting..."
    START_TIME=$(date +%s)

    # Log start
    echo "$(date '+%Y-%m-%d %H:%M:%S') START [$NUM/$TOTAL] $BASENAME" >> "$LOG_FILE"

    # Run correction
    if python -m ner_pipeline.cli \
        --input "$FILE" \
        --correct \
        --output-suffix _corrected \
        --max-removal-pct "$MAX_REMOVAL_PCT" \
        --passages-per-call "$PASSAGES_PER_CALL" \
        --verbose \
        $MODEL_FLAG \
        2>&1 | tee -a "$LOG_FILE"; then

        END_TIME=$(date +%s)
        ELAPSED=$(( END_TIME - START_TIME ))
        MINS=$(( ELAPSED / 60 ))
        SECS=$(( ELAPSED % 60 ))

        echo "[$NUM/$TOTAL] $BASENAME — done in ${MINS}m ${SECS}s"
        echo "$(date '+%Y-%m-%d %H:%M:%S') DONE  [$NUM/$TOTAL] $BASENAME (${MINS}m ${SECS}s)" >> "$LOG_FILE"
        PROCESSED=$((PROCESSED + 1))
    else
        echo "[$NUM/$TOTAL] $BASENAME — FAILED (see log)"
        echo "$(date '+%Y-%m-%d %H:%M:%S') FAIL  [$NUM/$TOTAL] $BASENAME" >> "$LOG_FILE"
        FAILED=$((FAILED + 1))
        # Continue to next file, don't abort the whole batch
    fi

    echo ""
done

echo "=========================================="
echo "Done! Processed: $PROCESSED | Skipped: $SKIPPED | Failed: $FAILED | Total: $TOTAL"
echo "$(date '+%Y-%m-%d %H:%M:%S') SUMMARY processed=$PROCESSED skipped=$SKIPPED failed=$FAILED total=$TOTAL" >> "$LOG_FILE"
