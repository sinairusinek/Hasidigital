#!/bin/bash
# Upload editions/online/*.xml to the live eXist server (teipub9) over WebDAV,
# then verify each file by fetching it back and comparing canonical XML.
#
# Credentials: EXIST_USER / EXIST_PASS from the environment, or from
# ~/.config/hasidigital/exist.env (chmod 600) containing:
#   EXIST_USER=...
#   EXIST_PASS=...
#
# Usage: editions/scripts/upload_to_exist.sh [--dry] [file.xml ...]
# With no files, uploads every XML in editions/online/.
# This PUBLISHES to hasidic-stories.org.
set -euo pipefail
cd "$(dirname "$0")/../.."

CRED=~/.config/hasidigital/exist.env
if [ -z "${EXIST_USER:-}" ] && [ -f "$CRED" ]; then set -a; . "$CRED"; set +a; fi
: "${EXIST_USER:?EXIST_USER not set (see header)}"
: "${EXIST_PASS:?EXIST_PASS not set (see header)}"

DAV=https://teipub9.dh-dev.com/exist/webdav/db/apps/HasidicStoriesServer/data
REST=https://teipub9.dh-dev.com/exist/rest/db/apps/HasidicStoriesServer/data

DRY=0; [ "${1:-}" = "--dry" ] && { DRY=1; shift; }
FILES=("$@"); [ ${#FILES[@]} -eq 0 ] && FILES=(editions/online/*.xml)

# The server keeps this edition under a capitalised name; keep it so links don't break.
server_name() { case "$1" in maase-zadikim.xml) echo Maase-Zadikim.xml ;; *) echo "$1" ;; esac; }

# Check the credentials authenticate before touching anything.
code=$(curl -s -o /dev/null -w '%{http_code}' -u "$EXIST_USER:$EXIST_PASS" -X PROPFIND -H 'Depth: 0' "$DAV/")
[ "$code" = 207 ] || { echo "Login check failed (HTTP $code). Nothing uploaded."; exit 1; }
echo "Login OK."

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
fail=0
for f in "${FILES[@]}"; do
  b=$(basename "$f"); s=$(server_name "$b")
  xmllint --noout "$f" || { echo "SKIP $b: not well-formed"; fail=1; continue; }
  if [ $DRY = 1 ]; then echo "would upload $b -> $s"; continue; fi
  code=$(curl -s -o /dev/null -w '%{http_code}' -u "$EXIST_USER:$EXIST_PASS" \
         -T "$f" -H 'Content-Type: application/xml' "$DAV/$s")
  case "$code" in 200|201|204) ;; *) echo "FAIL $s: HTTP $code"; fail=1; continue ;; esac
  curl -s -o "$TMP/$s" "$REST/$s"
  if python3 - "$f" "$TMP/$s" <<'EOF'
import sys, re, xml.etree.ElementTree as ET
c = lambda p: re.sub(r'\s+', ' ', ET.canonicalize(open(p, encoding='utf-8').read(), strip_text=True))
sys.exit(0 if c(sys.argv[1]) == c(sys.argv[2]) else 1)
EOF
  then echo "OK   $s (HTTP $code, verified)"; else echo "MISMATCH $s after upload"; fail=1; fi
done
exit $fail
