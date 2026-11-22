#!/bin/zsh
# Non-story NER correction for all editions (Sinai approved up to $10, 2026-11-22).
# Stops before starting an edition once the measured spend passes $8.80.
cd "$(dirname $0)/../.."
export GEMINI_THINKING_BUDGET=1024 GEMINI_USAGE_LOG=editions/ner-logs/non-story-usage.tsv
mkdir -p editions/ner-logs
cost() { if [ -f $GEMINI_USAGE_LOG ]; then awk -F'\t' '{i+=$3; o+=$4+$5} END {printf "%.2f", (i*0.3+o*2.5)/1e6}' $GEMINI_USAGE_LOG; else echo 0; fi; }
for f in "$@"; do
  c=$(cost)
  if (( c > 8.8 )); then echo "BUDGET STOP at $f (spent \$$c)"; exit 2; fi
  echo "== $f (spent so far \$$c) $(date +%H:%M)"
  python3 editions/scripts/correct_non_story.py $f $f > editions/ner-logs/last.out 2>&1 || { echo "FAILED $f"; grep "scratch copy" editions/ner-logs/last.out; tail -3 editions/ner-logs/last.out; cp editions/ner-logs/last.out "editions/ner-logs/failed-$(basename $f .xml).out"; continue; }
  grep -E "^before|^after" editions/ner-logs/last.out
done
echo "ALL DONE, spent \$$(cost)"
