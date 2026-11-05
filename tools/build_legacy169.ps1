# Builds the bundled D2R Legacy 16:9 plugin (legacy169.dll, https://github.com/Nugwa628/D2R-Legacy169, docs/bundled-plugins.md)
# from its source at the commit this repo pins (the gitlink third_party\D2R-Legacy169), release options only (no test harness,
# no bad-bytes table), into build\legacy169\Release\legacy169.dll, and runs its unit tests.
# Source: -Src DIR, else MXL_LEGACY169_DIR (env or .mxl-local.json: any clone of D2R-Legacy169 that has the pinned commit), else
# the submodule third_party\D2R-Legacy169. Whatever that checkout has checked out, the pinned commit is exported (git archive)
# into build\legacy169-src and built from there. Nothing is downloaded here.
# PluginSDK and CMake: as tools\build_plugin.ps1.
param([string]$Src, [string]$Sdk)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
. "$PSScriptRoot\_cmake.ps1"
Use-ProjectTemp $root

$stage = (git ls-files -s third_party/D2R-Legacy169) -split '\s+'
if ($stage.Count -lt 2 -or $stage[0] -ne '160000') { throw 'third_party/D2R-Legacy169 is not a pinned submodule of this repo' }
$pin = $stage[1]
if (-not $Src) { $Src = Get-LocalSetting 'MXL_LEGACY169_DIR' $root }
if (-not $Src) { $Src = Join-Path $root 'third_party\D2R-Legacy169' }
git -C $Src cat-file -e "$pin^{commit}" 2>$null
if ($LASTEXITCODE) {
    throw "D2R-Legacy169: commit $pin is not in $Src. Run ``git submodule update --init third_party/D2R-Legacy169`` (needs the " +
          "network), or set MXL_LEGACY169_DIR (.mxl-local.json) to a clone that has it."
}
$out = Join-Path $root 'build\legacy169-src'
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force $out | Out-Null
$zip = Join-Path $root 'build\legacy169-src.zip'
git -C $Src archive --format=zip -o $zip $pin
if ($LASTEXITCODE) { exit $LASTEXITCODE }
Expand-Archive -Path $zip -DestinationPath $out
Remove-Item $zip
Set-Content -Path (Join-Path $out 'PINNED_COMMIT') -Value $pin -Encoding ascii

$cmake = Find-CMake
if (-not $Sdk) { $Sdk = Get-LocalSetting 'MXL2012_PLUGINSDK_DIR' $root }
if (-not $Sdk) { $Sdk = Join-Path $root 'third_party\PluginSDK' }
if (-not (Test-Path (Join-Path $Sdk 'CMakeLists.txt'))) {
    throw "PluginSDK: $Sdk has no sources (an empty submodule). Run `py -3 tools/lane_setup.py` (takes them from a local checkout), " +
          "or `git submodule update --init third_party/PluginSDK` (needs the network)."
}
& $cmake -S $out -B build\legacy169 -A x64 "-DLEGACY169_PLUGINSDK_DIR=$($Sdk -replace '\\', '/')" -DLEGACY169_TEST_HARNESS=OFF -DLEGACY169_TEST_BAD_BYTES=OFF
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $cmake --build build\legacy169 --config Release
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& (Join-Path $root 'build\legacy169\tests\Release\legacy169_tests.exe')
if ($LASTEXITCODE) { Write-Host 'FAILED: legacy169_tests'; exit $LASTEXITCODE }
Write-Host "legacy169.dll at commit $pin -> build\legacy169\Release\legacy169.dll"
