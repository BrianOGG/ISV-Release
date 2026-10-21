#!/bin/sh
# ISV-Release bootstrap: pinned SHA256 download, then invoke the original compiled installer.
set -eu
umask 077
PROJECT='@@PROJECT@@'
STAGE=''
CURRENT_STAGE='platform'
CURRENT_CODE='unsupported_platform'
log_bootstrap() {
  # Only fixed stages/codes; never persist exception text, URLs or credentials.
  ( LOG_DIR="$HOME/Library/Application Support/ISV-Release/$PROJECT/logs"
    mkdir -p "$LOG_DIR" && chmod 700 "$LOG_DIR"
    printf '{"schema_version":1,"time":"%s","module":"bootstrap","stage":"%s","code":"%s"}\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >> "$LOG_DIR/bootstrap.jsonl"
    chmod 600 "$LOG_DIR/bootstrap.jsonl"
  ) 2>/dev/null || true
}
on_exit() {
  status=$1
  if [ "$status" -ne 0 ]; then log_bootstrap "$CURRENT_STAGE" "$CURRENT_CODE"; fi
  if [ -n "$STAGE" ] && [ -d "$STAGE" ]; then rm -rf "$STAGE"; fi
}
trap 'on_exit "$?"' 0
VERSION='@@VERSION@@'
URL='@@MAC_URL@@'
EXPECTED_SHA='@@MAC_SHA@@'
PLATFORM=macos-arm64
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo '{"ok":false,"error":"requires_apple_silicon_macos"}' >&2
  exit 1
fi
CURRENT_STAGE='cache'
CURRENT_CODE='runtime_cache_failed'
CACHE_ROOT="$HOME/Library/Caches/ISV-Release/$PROJECT/$VERSION"
CACHE="$CACHE_ROOT/$EXPECTED_SHA"
if [ ! -f "$CACHE/.ready" ]; then
  mkdir -p "$CACHE_ROOT"
  STAGE=$(mktemp -d "$CACHE_ROOT/.install.XXXXXXXX")
  mkdir -p "$STAGE/assets" "$STAGE/scripts"
  CURRENT_STAGE='download'
  CURRENT_CODE='runtime_download_failed'
  curl --proto '=https' --tlsv1.2 --fail --location --retry 3 --silent --show-error \
    --output "$STAGE/runtime.zip" "$URL" >&2
  CURRENT_STAGE='checksum'
  CURRENT_CODE='runtime_checksum_mismatch'
  ACTUAL_SHA=$(shasum -a 256 "$STAGE/runtime.zip" | awk '{print $1}')
  if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then
    echo '{"ok":false,"error":"runtime_checksum_mismatch"}' >&2
    exit 1
  fi
  CURRENT_STAGE='unpack'
  CURRENT_CODE='runtime_extract_failed'
  mkdir "$STAGE/unpack"
  unzip -q "$STAGE/runtime.zip" -d "$STAGE/unpack"
  CURRENT_STAGE='assets'
  CURRENT_CODE='runtime_assets_missing'
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
  CURRENT_STAGE='cache'
  CURRENT_CODE='runtime_cache_failed'
  cp "$ROOT/assets/release.json" "$STAGE/assets/release.json"
  cp "$ROOT/scripts/setup-bundled.sh" "$STAGE/scripts/setup.sh"
  cp "$ROOT/SKILL.md" "$STAGE/SKILL.md"
  (cd "$STAGE" && find assets -type f ! -name MANIFEST.sha256 |
    while IFS= read -r entry; do shasum -a 256 "$entry"; done) > "$STAGE/assets/MANIFEST.sha256"
  rm -rf "$STAGE/unpack" "$STAGE/runtime.zip"
  : > "$STAGE/.ready"
  if [ -e "$CACHE" ]; then rm -rf "$CACHE"; fi
  mv "$STAGE" "$CACHE"
fi
CURRENT_STAGE='installer'
CURRENT_CODE='installer_failed'
sh "$CACHE/scripts/setup.sh" "$@"
