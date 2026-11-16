#!/bin/sh
# One motif round on the sample in $MOTIF_SAMPLE; embedding steps run under a free-memory guard (kill below 15%).
cd "$(dirname "$0")"; PY=../../../.venv/bin/python; L=../../../private/motif-experiment/round.log
log() { echo "$(date '+%F %T') $*" >> $L; }
guarded() { "$@" >> $L 2>&1 & P=$!; while kill -0 $P 2>/dev/null; do f=$(memory_pressure | tail -1 | grep -o '[0-9]*'); [ "$f" -lt 15 ] && { kill $P; log "GUARD killed $* at $f% free"; return 1; }; sleep 5; done; wait $P; }
log "round start: $MOTIF_SAMPLE"
$PY step1_read.py >> $L 2>&1 && log "step1 done" || { log "step1 FAILED"; exit 1; }
guarded $PY step2_shortlist.py && log "step2 done" || exit 1
$PY step3_pick.py >> $L 2>&1 && log "step3 done" || { log "step3 FAILED"; exit 1; }
$PY step4_align.py >> $L 2>&1 && log "step4 done" || { log "step4 FAILED"; exit 1; }
rm -f ../../../private/motif-experiment/recall_shortlists.json   # rebuild for the new none-events (cached files are reused)
guarded $PY recall_check.py && log "recall done" || exit 1
$PY report.py >> $L 2>&1; log "round end"
