#!/bin/zsh
# Topic tagging queue (PIPELINE step 12), Max plan; resumable (cached per division).
# Started 2026-11-22 after Sinai: "do everything that wasn't done yet".
cd "$(dirname $0)/../.."
export CLAUDE_CLI_BIN=${CLAUDE_CLI_BIN:-~/.vscode/extensions/anthropic.claude-code-2.1.330-darwin-arm64/resources/native-binary/claude}
L=editions/llm-tagging/logs
for f in editions/incoming/ready/Shaarei-Haemuna.xml editions/incoming/ready/Eser-Kedushot.xml editions/incoming/ready/Eser-Orot.xml \
         editions/online/{Maim-Rabim,Derech-Haemuna,Likutim-Hadashim,Maasim-Tovim,Peulat-Hatzadikim,Seva-Ratzon,Tiferet-Hayyim,Toldot-Haniflaot}.xml; do
  python3 editions/llm-tagging/tag_edition.py $f >> $L/$(basename $f .xml).log 2>&1 || { echo "STOPPED at $f" >> $L/queue.log; exit 1; }
  echo "done $f $(date)" >> $L/queue.log
done
# curated editions: only their non-story divisions, to find stories in paratext
for f in editions/online/*.xml; do
  grep -q 'resp="#llm-tagging"' $f && continue
  case $(basename $f .xml) in Maim-Rabim|Derech-Haemuna|Likutim-Hadashim|Maasim-Tovim|Peulat-Hatzadikim|Seva-Ratzon|Tiferet-Hayyim|Toldot-Haniflaot) continue;; esac
  python3 editions/llm-tagging/tag_edition.py $f --non-story-only >> $L/$(basename $f .xml).log 2>&1 || { echo "STOPPED at $f" >> $L/queue.log; exit 1; }
  echo "done $f $(date)" >> $L/queue.log
done
echo "QUEUE COMPLETE $(date)" >> $L/queue.log
