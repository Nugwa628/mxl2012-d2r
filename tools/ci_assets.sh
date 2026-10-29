#!/usr/bin/env bash
# CI `assets` job (.forgejo/workflows/ci.yml, runner mxl-cross: Linux container, no host volumes, no game files).
#
# Fetches the asset pack pinned in assets.lock (Median XL 2012 v005's patch_d2.mpq, extracted: tools/mpq_extract.py) from
# the private forge release named in its urls, with the read token of the MXL_ASSETS_TOKEN secret; tools/asset_pack.py checks
# the pack's size and sha256 against assets.lock before unpacking it and every unpacked file against the pack's manifest. Then
# it runs the checks that need Median's files and no Blizzard file (tools/tests/test_assets_median.py).
#
# Without the secret (the owner has not uploaded the pack yet, docs/setup.md "CI asset pack") it prints a notice and exits 0,
# so CI stays green. MXL_ASSETS_REQUIRED=1 (job env) makes a missing secret fail instead.
# The token is only in this script's environment, sent to git.werdegames.com only, and unset right after the fetch.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"

skip() {
  echo "::notice title=Asset pack not fetched::$1; the asset-dependent checks were skipped (docs/setup.md, section CI asset pack)"
  if [ "${MXL_ASSETS_REQUIRED:-}" = 1 ]; then
    echo "MXL_ASSETS_REQUIRED=1: failing"
    exit 1
  fi
  exit 0
}

[ -f assets.lock ] || skip "assets.lock does not exist"
[ -n "${MXL_ASSETS_TOKEN:-}" ] || skip "the MXL_ASSETS_TOKEN secret is not set"

export MXL_ASSETS_CACHE="${MXL_ASSETS_CACHE:-$PWD/.assets-cache}"
"$PY" -I tools/asset_pack.py fetch
unset MXL_ASSETS_TOKEN
"$PY" -I tools/asset_pack.py verify --full --strict
"$PY" -I tools/asset_pack.py scan
MXL_ASSETS_REQUIRED=1 "$PY" -I -m unittest discover -s tools/tests -p 'test_assets_median.py' -v
