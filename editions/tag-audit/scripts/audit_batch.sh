#!/usr/bin/env bash
# One paced batch of the old-insert precision audit (Opus 4.7, Max plan).
# Resume-safe: each run judges the next N un-judged pairs, caches per call,
# and stops cleanly on a throttle wall (circuit breaker). Run one per session,
# leaving the rest of your 5-hour window free for other Claude work.
#
# Usage:   bash editions/tag-audit/scripts/audit_batch.sh [N]   (default N=250)
set -u
REPO="/Users/sinairusinek/Documents/GitHub/Hasidigital"
N="${1:-250}"
cd "$REPO"
LOG="editions/tag-audit/.rerun-logs/old-inserts-precision-audit.log"

echo "── remaining before this batch ──"
python3 editions/tag-audit/scripts/precision_audit_old_inserts.py --dry-run 2>/dev/null

echo "── running batch of $N (Opus 4.7) ──"
python3 -u editions/tag-audit/scripts/precision_audit_old_inserts.py \
    --model claude-opus-4-7 --limit "$N" 2>&1 | tee -a "$LOG" | tail -8

echo "── remaining after this batch ──"
python3 editions/tag-audit/scripts/precision_audit_old_inserts.py --dry-run 2>/dev/null
