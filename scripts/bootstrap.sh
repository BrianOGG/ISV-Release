#!/bin/sh
# ISV-Release bootstrap: pinned SHA256 download, then invoke the original compiled installer.
set -eu
PROJECT='@@PROJECT@@'
VERSION='@@VERSION@@'
URL='@@MAC_URL@@'
EXPECTED_SHA='@@MAC_SHA@@'
PLATFORM=macos-arm64
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo '{"ok":false,"error":"requires_apple_silicon_macos"}' >&2
  exit 1
fi
CACHE_ROOT="$HOME/Library/Caches/ISV-Release/$PROJECT/$VERSION"
CACHE="$CACHE_ROOT/$EXPECTED_SHA"
if [ ! -f "$CACHE/.ready" ]; then
  mkdir -p "$CACHE_ROOT"
  STAGE=$(mktemp -d "$CACHE_ROOT/.install.XXXXXXXX")
  cleanup() { rm -rf "$STAGE"; }
  trap cleanup EXIT HUP INT TERM
  mkdir -p "$STAGE/assets" "$STAGE/scripts"
  curl --proto '=https' --tlsv1.2 --fail --location --retry 3 --silent --show-error \
    --output "$STAGE/runtime.zip" "$URL" >&2
  ACTUAL_SHA=$(shasum -a 256 "$STAGE/runtime.zip" | awk '{print $1}')
  if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then
    echo '{"ok":false,"error":"runtime_checksum_mismatch"}' >&2
    exit 1
  fi
  mkdir "$STAGE/unpack"
  unzip -q "$STAGE/runtime.zip" -d "$STAGE/unpack"
  test -f "$STAGE/unpack/runtime/$PLATFORM/$(if [ "$PROJECT" = product-grabber ]; then echo product-grabber; else echo audience-portrait; fi)"
  mv "$STAGE/unpack/runtime" "$STAGE/assets/runtime"
  if [ "$PROJECT" = "product-grabber" ]; then
    test -f "$STAGE/unpack/ext/manifest.json"
    mv "$STAGE/unpack/ext" "$STAGE/assets/ext"
    chmod u+x "$STAGE/assets/runtime/$PLATFORM/product-grabber"
  else
    chmod u+x "$STAGE/assets/runtime/$PLATFORM/audience-portrait"
    chmod u+x "$STAGE/assets/runtime/$PLATFORM/"*.sh
  fi
  cp "$ROOT/assets/release.json" "$STAGE/assets/release.json"
  cp "$ROOT/scripts/setup-bundled.sh" "$STAGE/scripts/setup.sh"
  cp "$ROOT/SKILL.md" "$STAGE/SKILL.md"
  (cd "$STAGE" && find assets -type f ! -name MANIFEST.sha256 |
    while IFS= read -r entry; do shasum -a 256 "$entry"; done) > "$STAGE/assets/MANIFEST.sha256"
  rm -rf "$STAGE/unpack" "$STAGE/runtime.zip"
  : > "$STAGE/.ready"
  if [ -e "$CACHE" ]; then rm -rf "$CACHE"; fi
  mv "$STAGE" "$CACHE"
  trap - EXIT HUP INT TERM
fi
exec sh "$CACHE/scripts/setup.sh" "$@"
