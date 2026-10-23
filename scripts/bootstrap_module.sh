#!/bin/sh
# Public generic bootstrap: EC-AI private business source is never distributed.
set -eu
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON=$(command -v python3.12 || command -v python3 || true)
if [ -z "$PYTHON" ]; then
  printf '%s\n' 'Python 3.12 is required. Ask your Agent to install CPython 3.12 first.' >&2
  exit 1
fi
exec "$PYTHON" "$ROOT/scripts/module_installer.py" "$@"
