#!/usr/bin/env bash
# One D2R-XL 2012 release, every step or nothing (docs/release.md "Making a release", docs/hosting.md). Run from a Git Bash on
# the game PC, from the checkout at the release commit:
#
#   bash tools/release.sh <version> [--channel stable|test] [--rebuild-data] [--no-launcher] [--with-github] [--check-only]
#
#   --check-only    only the checks before the release (clean tree, PluginVersion, CHANGELOG, tests); nothing is built or sent
#   --channel       where the release goes (default stable; the first release of a new host belongs on `test`, then
#                   `py -3 tools/publish_release.py promote <v> --channel stable`)
#   --rebuild-data  tools/build.py first (needs extract/ and the native libs, docs/setup.md); without it work/mod must be current
#   --no-launcher   do not publish a downloader with this release (default: build/launcher/Release/D2R-XL-2012-Downloader.exe)
#   --with-github   after the release is live on stable: mirror main to GitHub and make the GitHub and forge releases
#                   (tools/github_release.py); needs MXL_SCRUB_MIRROR_CMD and MXL_SCRUB_WORKGIT below
#
# Settings come from the environment (nothing machine-specific is kept in the repository):
#   MXL_PUBLISH_TARGET    required: sftp://mxlup@<host>/mxl2012   (the site folder inside the SFTP chroot, docs/hosting.md)
#   MXL_PUBLISH_IDENTITY  the private key for it (default: ssh's own choice)
#   MXL_LIVE_URL          where players read it (default https://files.werdegames.com/mxl2012)
#   MXL_SCRUB_MIRROR_CMD  --with-github: the command that mirrors main to the public GitHub repository (scrubbed)
#   MXL_SCRUB_WORKGIT     --with-github: the bare repository that command writes; the release commit is found there by its subject
#   MXL_FORGE_TOKEN       --with-github: the forge token (or ~/.mxl2012-d2r/forge_token, tools/github_release.py)
#   MXL_CMAKE_DIR, MXL_7Z_DIR   folders to put on PATH for cmake (the release plugin is built by package_release.py) and 7-Zip
#
# The publish and verify steps run in the foreground with their full output and are never piped through tail/head/grep:
# the upload takes minutes (progress is the only sign of life), and a pipe would hide its exit status from `set -e`.
set -euo pipefail

usage() { awk '/^set -euo/ {exit} NR > 1 {sub(/^# ?/, ""); print}' "$0"; exit 2; }

V=""; CHANNEL=stable; REBUILD=0; LAUNCHER_ON=1; GITHUB=0; CHECK_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --channel) CHANNEL="${2:-}"; shift ;;
    --rebuild-data) REBUILD=1 ;;
    --no-launcher) LAUNCHER_ON=0 ;;
    --with-github) GITHUB=1 ;;
    --check-only) CHECK_ONLY=1 ;;
    -h|--help) usage ;;
    -*) echo "unknown option $1"; usage ;;
    *) [ -z "$V" ] || { echo "two versions given"; usage; }; V="$1" ;;
  esac
  shift
done
[ -n "$V" ] || usage
[[ "$V" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "version must be x.y.z, not '$V'"; exit 1; }
case "$CHANNEL" in stable|test) ;; *) echo "channel must be stable or test, not '$CHANNEL'"; exit 1 ;; esac
if [ "$GITHUB" = 1 ] && [ "$CHANNEL" != stable ]; then echo "--with-github belongs to a stable release"; exit 1; fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
[ -z "${MXL_CMAKE_DIR:-}" ] || export PATH="$MXL_CMAKE_DIR:$PATH"
[ -z "${MXL_7Z_DIR:-}" ] || export PATH="$MXL_7Z_DIR:$PATH"
LIVE="${MXL_LIVE_URL:-https://files.werdegames.com/mxl2012}"; LIVE="${LIVE%/}"
LAUNCHER=build/launcher/Release/D2R-XL-2012-Downloader.exe
VRE="${V//./\\.}"

# ---- checks: nothing below runs when one fails
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || [ "${MXL_RELEASE_ANY_BRANCH:-}" = 1 ] || { echo "not on main (MXL_RELEASE_ANY_BRANCH=1 overrides)"; exit 1; }
git diff --quiet && git diff --cached --quiet || { echo "the working tree is not clean: commit or stash first"; git status --short --untracked-files=no; exit 1; }
grep -qF "PluginVersion = \"$V\"" plugin/src/mxl2012_core.cpp || { echo "PluginVersion in plugin/src/mxl2012_core.cpp is not $V"; exit 1; }
grep -qE "^### $VRE( |$)" CHANGELOG.md || { echo "CHANGELOG.md has no '### $V' section"; exit 1; }
if [ "$CHECK_ONLY" = 0 ]; then
  [ -n "${MXL_PUBLISH_TARGET:-}" ] || { echo "MXL_PUBLISH_TARGET is not set (sftp://mxlup@<host>/mxl2012)"; exit 1; }
  case "$MXL_PUBLISH_TARGET" in */mxl2012|*/mxl2012/) ;; *) echo "MXL_PUBLISH_TARGET must end in /mxl2012 (/mxl belongs to another product): $MXL_PUBLISH_TARGET"; exit 1 ;; esac
  if [ "$LAUNCHER_ON" = 1 ] && [ ! -f "$LAUNCHER" ]; then echo "$LAUNCHER is missing (build it, docs/launcher.md, or pass --no-launcher)"; exit 1; fi
  if [ "$GITHUB" = 1 ]; then
    [ -n "${MXL_SCRUB_MIRROR_CMD:-}" ] && [ -n "${MXL_SCRUB_WORKGIT:-}" ] || { echo "--with-github needs MXL_SCRUB_MIRROR_CMD and MXL_SCRUB_WORKGIT"; exit 1; }
  fi
fi
( cd tools && py -3 -m unittest test_package_release test_publish_release test_dl_ingest test_dl_sync test_github_release )
C="$(git rev-parse HEAD)"
echo "release $V (channel $CHANNEL) from $C"
[ "$CHECK_ONLY" = 0 ] || { echo "checks passed; nothing was built or sent (--check-only)"; exit 0; }

# ---- build, package
if [ "$REBUILD" = 1 ]; then
  mkdir -p build
  py -3 tools/build.py > "build/release-$V-build.log" 2>&1 || { echo "tools/build.py failed: see build/release-$V-build.log"; exit 1; }
  grep -q "errors 0" "build/release-$V-build.log" || { echo "the data build reports validation errors: see build/release-$V-build.log"; exit 1; }
  git diff --quiet --ignore-cr-at-eol --ignore-space-at-eol -- plugin/src || { echo "the data build changed generated plugin sources: commit them first"; git diff --stat --ignore-cr-at-eol -- plugin/src; exit 1; }
fi
rm -rf -- "$REPO/dist"
py -3 tools/package_release.py --version "$V"

# ---- publish: the server checks and builds, then writes the channel file last
ARGS=(publish --channel "$CHANNEL" --version "$V")
[ "$LAUNCHER_ON" = 0 ] || ARGS+=(--launcher "$LAUNCHER")
[ -z "${MXL_PUBLISH_IDENTITY:-}" ] || ARGS+=(--identity "$MXL_PUBLISH_IDENTITY")
py -3 tools/publish_release.py "${ARGS[@]}"

# ---- wait until the Space mirror shows it (the server's ingest, then dl_sync, take a few minutes)
live=0
for i in $(seq 1 80); do
  body="$(curl -fsS --max-time 30 "$LIVE/channels/$CHANNEL.json" 2>/dev/null || true)"  # not `curl | grep -q`: grep's early exit kills curl, and pipefail then fails the test
  case "$body" in *"\"version\": \"$V\""*) live=1; break ;; esac
  sleep 15
done
[ "$live" = 1 ] || { echo "$V is not on $LIVE after 20 minutes (see docs/hosting.md 'Useful commands'): no verify, no GitHub / forge release"; exit 1; }
echo "$V is on channel $CHANNEL at $LIVE"
py -3 tools/publish_release.py verify --url "$LIVE/" --channel "$CHANNEL" --sample 200
[ "$GITHUB" = 1 ] || { echo "released $V on $CHANNEL (no GitHub / forge release: --with-github)"; exit 0; }

# ---- GitHub and forge releases (stable only)
bash -c "$MXL_SCRUB_MIRROR_CMD"
G="$(git -C "$MXL_SCRUB_WORKGIT" log main --format=%H -1 --fixed-strings --grep="$(git log -1 --format=%s "$C")")"
[ -n "$G" ] || { echo "release commit not found on the scrubbed main"; exit 1; }
DL=(); [ "$LAUNCHER_ON" = 0 ] || DL=(--downloader "$LAUNCHER")
py -3 tools/github_release.py "$V" --commit "$G" ${DL[@]+"${DL[@]}"} --latest
py -3 tools/github_release.py "$V" --commit "$C" ${DL[@]+"${DL[@]}"} --forge
echo "released $V"
