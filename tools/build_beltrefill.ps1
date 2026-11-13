# Builds the bundled Auto Belt Refill plugin (d2rl-auto-belt-refill.dll, by jaycachou-svg,
# https://github.com/jaycachou-svg/auto-belt-refill, docs/bundled-plugins.md) from the author's source at the commit this repo
# pins (the gitlink third_party\auto-belt-refill, folder Auto-belt-refill-v0.35.9-EN) with our patches applied
# (third_party\auto-belt-refill-mxl2012\*.patch, in name order: the PluginSDK renames for D2RLoader 1.3.1 / ABI 4 and the Median
# belt rows), into build\beltrefill\Release\d2rl-auto-belt-refill.dll, with our CMakeLists.txt from that folder (the author's
# lists the sources next to it, while the repo keeps them in src\). The author's repo is never changed: no fork.
# Source: -Src DIR, else MXL_BELTREFILL_DIR (env or .mxl-local.json: any clone of the author's repo that has the pinned commit),
# else the submodule third_party\auto-belt-refill. Whatever that checkout has checked out, the pinned commit is exported (git
# archive) into build\beltrefill-src, patched there and built from there. Nothing is downloaded here.
# PluginSDK and CMake: as tools\build_plugin.ps1. The upstream plugin has no unit tests; our additions' pure logic (0003 - 0005,
# belt_match_logic.h) has BeltMatchTests, built and run here.
param([string]$Src, [string]$Sdk)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
. "$PSScriptRoot\_cmake.ps1"
Use-ProjectTemp $root

$folder = 'Auto-belt-refill-v0.35.9-EN'
$stage = (git ls-files -s third_party/auto-belt-refill) -split '\s+'
if ($stage.Count -lt 2 -or $stage[0] -ne '160000') { throw 'third_party/auto-belt-refill is not a pinned submodule of this repo' }
$pin = $stage[1]
if (-not $Src) { $Src = Get-LocalSetting 'MXL_BELTREFILL_DIR' $root }
if (-not $Src) { $Src = Join-Path $root 'third_party\auto-belt-refill' }
git -C $Src cat-file -e "$pin^{commit}" 2>$null
if ($LASTEXITCODE) {
    throw "auto-belt-refill: commit $pin is not in $Src. Run ``git submodule update --init third_party/auto-belt-refill`` (needs " +
          "the network), or set MXL_BELTREFILL_DIR (.mxl-local.json) to a clone of jaycachou-svg's repo that has it."
}
$out = Join-Path $root 'build\beltrefill-src'
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force $out | Out-Null
$zip = Join-Path $root 'build\beltrefill-src.zip'
# the files as committed (LF), whatever this machine's autocrlf: the patches are LF
git -C $Src -c core.autocrlf=false -c core.eol=lf archive --format=zip -o $zip $pin $folder
if ($LASTEXITCODE) { exit $LASTEXITCODE }
Expand-Archive -Path $zip -DestinationPath $out
Remove-Item $zip
$patches = Get-ChildItem (Join-Path $root 'third_party\auto-belt-refill-mxl2012') -Filter '*.patch' | Sort-Object Name
foreach ($p in $patches) {
    git -C $root apply --whitespace=nowarn --directory=build/beltrefill-src $p.FullName
    if ($LASTEXITCODE) { throw "auto-belt-refill: $($p.Name) does not apply to commit $pin" }
}
Set-Content -Path (Join-Path $out 'PINNED_COMMIT') -Value $pin -Encoding ascii
# which patches went in (name and sha256): package_release.py refuses a build whose patches are not the repo's
$sums = $patches | ForEach-Object { "$((Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower())  $($_.Name)" }
Set-Content -Path (Join-Path $out 'PATCHES') -Value $sums -Encoding ascii

$cmake = Find-CMake
if (-not $Sdk) { $Sdk = Get-LocalSetting 'MXL2012_PLUGINSDK_DIR' $root }
if (-not $Sdk) { $Sdk = Join-Path $root 'third_party\PluginSDK' }
if (-not (Test-Path (Join-Path $Sdk 'CMakeLists.txt'))) {
    throw "PluginSDK: $Sdk has no sources (an empty submodule). Run `py -3 tools/lane_setup.py` (takes them from a local checkout), " +
          "or `git submodule update --init third_party/PluginSDK` (needs the network)."
}
$abrSrc = (Join-Path $out "$folder\src") -replace '\\', '/'
& $cmake -S third_party\auto-belt-refill-mxl2012 -B build\beltrefill -A x64 "-DABR_SRC=$abrSrc" "-DABR_SDK=$($Sdk -replace '\\', '/')"
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $cmake --build build\beltrefill --config Release --target AutoBeltRefill BeltMatchTests
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& build\beltrefill\Release\BeltMatchTests.exe
if ($LASTEXITCODE) { throw 'auto-belt-refill: BeltMatchTests failed' }
Write-Host "d2rl-auto-belt-refill.dll at commit $pin + $($patches.Count) patches -> build\beltrefill\Release\d2rl-auto-belt-refill.dll"
