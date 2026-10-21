#!/bin/sh
# Offline developer diagnostics: no runtime, Node.js or Python required.
set -eu
umask 077
PROJECT='@@PROJECT@@'
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUTPUT=""
HOURS=24
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output) [ "$#" -ge 2 ] || { echo 'missing --output value' >&2; exit 2; }; OUTPUT=$2; shift 2 ;;
    --hours) [ "$#" -ge 2 ] || { echo 'missing --hours value' >&2; exit 2; }; HOURS=$2; shift 2 ;;
    *) echo 'usage: export-diagnostics.sh [--output PATH] [--hours 1..168]' >&2; exit 2 ;;
  esac
done
case "$HOURS" in ''|*[!0-9]*) echo 'hours must be 1..168' >&2; exit 2 ;; esac
[ "$HOURS" -ge 1 ] && [ "$HOURS" -le 168 ] || { echo 'hours must be 1..168' >&2; exit 2; }
if [ -z "$OUTPUT" ]; then OUTPUT="$PWD/$PROJECT-diagnostics-$(date -u +%Y%m%dT%H%M%SZ).json"; fi
case "$OUTPUT" in /*) ;; *) OUTPUT="$PWD/$OUTPUT" ;; esac
/usr/bin/osascript -l JavaScript "$ROOT/scripts/export-diagnostics.jxa" \
  "$PROJECT" "$ROOT/assets/release.json" "$OUTPUT" "$HOURS"
