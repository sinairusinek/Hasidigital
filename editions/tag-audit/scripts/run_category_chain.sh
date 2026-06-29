#!/usr/bin/env bash
# Sequentially re-run a list of tag-audit categories with the patched
# definitions. Cache makes every step restart-safe — re-running a category
# whose cache rows already exist is a no-op (~2 min funnel re-walk + 0 LLM
# calls). A 30-minute pause is inserted between categories to let the Max
# throttle bucket recover.
#
# Usage:  bash run_category_chain.sh cat1 cat2 cat3 ...
# Env:    optional INTER_PAUSE_SEC (default 1800), optional LOG_DIR.
set -u
REPO="/Users/sinairusinek/Documents/GitHub/Hasidigital"
LOG_DIR="${LOG_DIR:-$REPO/editions/tag-audit/.rerun-logs}"
PAUSE="${INTER_PAUSE_SEC:-300}"
mkdir -p "$LOG_DIR"

export TAG_AUDIT_MODEL=claude-cli
export CLAUDE_CLI_MODEL=claude-sonnet-4-6

cd "$REPO"
for cat in "$@"; do
  ts=$(date '+%Y-%m-%d %H:%M:%S')
  log="$LOG_DIR/${cat}.log"
  echo "[$ts] === START $cat (log=$log) ===" >> "$LOG_DIR/chain.log"
  python3 -u Authorities/integration_tool/tag_audit.py --category "$cat" \
      >> "$log" 2>&1
  rc=$?
  ts=$(date '+%Y-%m-%d %H:%M:%S')
  echo "[$ts] === END   $cat (rc=$rc) ===" >> "$LOG_DIR/chain.log"
  if [ "$cat" != "${@: -1}" ]; then
    echo "[$ts] sleeping ${PAUSE}s before next category" >> "$LOG_DIR/chain.log"
    sleep "$PAUSE"
  fi
done
echo "[$(date '+%Y-%m-%d %H:%M:%S')] chain complete" >> "$LOG_DIR/chain.log"
