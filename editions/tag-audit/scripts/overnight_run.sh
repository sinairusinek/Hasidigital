#!/usr/bin/env bash
# Overnight launcher for the five large tag-audit categories.
#
# Usage:  bash overnight_run.sh
#
# Behavior:
#   - Reads the ordered queue below.
#   - For each category, if its DONE marker exists, skip.
#   - Otherwise run tag_audit.py --category X to completion (the cache makes
#     resume free — a partial prior run picks up where it left off).
#   - On natural completion, touch the DONE marker.
#   - 30-minute sleep between categories.
#
# Idempotent: re-launching multiple nights walks the queue further each time.
set -u
REPO="/Users/sinairusinek/Documents/GitHub/Hasidigital"
LOG_DIR="$REPO/editions/tag-audit/.rerun-logs"
DONE_DIR="$REPO/editions/tag-audit/.rerun-done"
PAUSE="${INTER_PAUSE_SEC:-300}"
mkdir -p "$LOG_DIR" "$DONE_DIR"

# Order: small-to-large within the "large" bucket, so a short overnight
# window still finishes something.
QUEUE=(folkloristics supernatural characters-and-roles social ethics-and-emotions)

export TAG_AUDIT_MODEL=claude-cli
export CLAUDE_CLI_MODEL=claude-sonnet-4-6
cd "$REPO"

for cat in "${QUEUE[@]}"; do
  marker="$DONE_DIR/${cat}.done"
  if [ -f "$marker" ]; then
    echo "[$(date '+%F %T')] $cat already DONE — skipping" >> "$LOG_DIR/overnight.log"
    continue
  fi
  echo "[$(date '+%F %T')] === START $cat ===" >> "$LOG_DIR/overnight.log"
  python3 -u Authorities/integration_tool/tag_audit.py --category "$cat" \
      >> "$LOG_DIR/${cat}.log" 2>&1
  rc=$?
  echo "[$(date '+%F %T')] === END   $cat rc=$rc ===" >> "$LOG_DIR/overnight.log"
  if [ "$rc" -eq 0 ]; then
    touch "$marker"
    echo "[$(date '+%F %T')] marked $cat DONE" >> "$LOG_DIR/overnight.log"
  else
    echo "[$(date '+%F %T')] $cat exited rc=$rc — will retry next night" \
        >> "$LOG_DIR/overnight.log"
    # Stop the queue so the next category doesn't start in a throttled state.
    exit "$rc"
  fi
  sleep "$PAUSE"
done

echo "[$(date '+%F %T')] overnight queue complete" >> "$LOG_DIR/overnight.log"
