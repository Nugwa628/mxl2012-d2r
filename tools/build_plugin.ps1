# Builds the mxl2012-core D2RLoader plugin: the dev DLL (test harness) into build\plugin\Release\mxl2012-core.dll (installed
# by tools\install_mod.py) and, with -Release, the player DLL (-DMXL_RELEASE=ON, no harness) into build\plugin-release\Release.
# PluginSDK: -Sdk DIR, else env MXL2012_PLUGINSDK_DIR, else MXL2012_PLUGINSDK_DIR of .mxl-local.json (tools\lane_setup.py puts the
# shared <runs>\shared\native\src\PluginSDK there), else the submodule third_party\PluginSDK; an empty submodule stops the
# script with the way to fill it (nothing is downloaded here).
# CMake: the one on PATH, else Visual Studio's bundled cmake.exe.
param([string]$Sdk, [switch]$Release, [switch]$Tests)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
. "$PSScriptRoot\_cmake.ps1"
Use-ProjectTemp $root

$cmake = Find-CMake
if (-not $Sdk) { $Sdk = Get-LocalSetting 'MXL2012_PLUGINSDK_DIR' $root }
if (-not $Sdk) { $Sdk = Join-Path $root 'third_party\PluginSDK' }
if (-not (Test-Path (Join-Path $Sdk 'CMakeLists.txt'))) {
    throw "PluginSDK: $Sdk has no sources (an empty submodule). Run `py -3 tools/lane_setup.py` (takes them from a local checkout), " +
          "or `git submodule update --init third_party/PluginSDK` (needs the network)."
}
$sdkArg = "-DMXL2012_PLUGINSDK_DIR=$($Sdk -replace '\\', '/')"

& $cmake -S plugin -B build\plugin -A x64 $sdkArg
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $cmake --build build\plugin --config Release
if ($LASTEXITCODE) { exit $LASTEXITCODE }
if ($Release) {
    & $cmake -S plugin -B build\plugin-release -A x64 -DMXL_RELEASE=ON $sdkArg
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    & $cmake --build build\plugin-release --config Release
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
}
if ($Tests) {
    # the unit tests of the pure parts (plugin\tests\CMakeLists.txt), built next to the dev DLL and run one by one
    & $cmake --build build\plugin --config Release --target tests
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    foreach ($t in Get-ChildItem build\plugin\Release\*_tests.exe) {
        & $t.FullName
        if ($LASTEXITCODE) { Write-Host "FAILED: $($t.Name)"; exit $LASTEXITCODE }
    }
}
