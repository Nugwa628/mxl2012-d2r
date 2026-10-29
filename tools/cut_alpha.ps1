# Cuts the hand-copied alpha (docs/release.md "Alpha for hand copying") in one command: full data build, the release plugin,
# the package and its check. Nothing is uploaded or published; nothing outside the project is written.
#   1. py -3 tools/build.py                       full build -> work/mod (stops on validate errors; -SkipBuild uses work/mod as it is)
#   2. tools\build_plugin.ps1 -Release [-Tests]    release DLL (no test harness) -> build\plugin-release\Release\mxl2012-core.dll
#   3. py -3 tools/package_release.py              -> <Out>: D2R-XL-2012-<v>.7z, release-manifest.json, RELEASE_NOTES-<v>.md
#                                                  (tools/data/release_notes_alpha.md: the player's install notes), SHA256SUMS
#   4. py -3 tools/verify_package.py               unpacks the 7z into <Scratch> and compares it with what install_mod.py installs
# Version: PluginVersion of plugin/src/mxl2012_core.cpp (the packager requires it).
# Out and Scratch default to <runs>\dist-alpha and <runs>\alpha-verify (<runs> = MXL2012_RUNS, else mxl2012-runs two levels
# above the checkout); Out may not be inside the checkout.
#   pwsh -NoProfile -File tools\cut_alpha.ps1 [-Out DIR] [-Scratch DIR] [-SkipBuild] [-Tests] [-NoReference]
param([string]$Out, [string]$Scratch, [switch]$SkipBuild, [switch]$Tests, [switch]$NoReference)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
. "$PSScriptRoot\_cmake.ps1"
Use-ProjectTemp $root

$runs = if ($env:MXL2012_RUNS) { $env:MXL2012_RUNS } else { Join-Path (Split-Path (Split-Path $root -Parent) -Parent) 'mxl2012-runs' }
if (-not $Out) { $Out = Join-Path $runs 'dist-alpha' }
if (-not $Scratch) { $Scratch = Join-Path $runs 'alpha-verify' }
$Out = [IO.Path]::GetFullPath($Out)
if (($Out.TrimEnd('\') + '\').StartsWith($root.TrimEnd('\') + '\', 'OrdinalIgnoreCase')) {
    throw "-Out $Out is inside the checkout: the package goes next to it (default $runs\dist-alpha)"
}

function Step([string]$Name, [scriptblock]$Run) {
    Write-Host "== $Name"
    $t = Get-Date
    & $Run
    if ($LASTEXITCODE) { Write-Host "FAILED: $Name (exit $LASTEXITCODE)"; exit $LASTEXITCODE }
    Write-Host ("   {0} done in {1:n0} s" -f $Name, ((Get-Date) - $t).TotalSeconds)
}

if (-not $SkipBuild) { Step 'build.py' { py -3 tools/build.py } }
$plugin = Join-Path $root 'build\plugin-release\Release\mxl2012-core.dll'
Step 'build_plugin.ps1 -Release' { if ($Tests) { & "$PSScriptRoot\build_plugin.ps1" -Release -Tests } else { & "$PSScriptRoot\build_plugin.ps1" -Release } }
Step 'package_release.py' { py -3 tools/package_release.py --plugin $plugin --out $Out --notes tools/data/release_notes_alpha.md }
$v = (Get-Content (Join-Path $root 'plugin\src\mxl2012_core.cpp') -Raw | Select-String 'PluginVersion = "([^"]+)"').Matches[0].Groups[1].Value
$archive = Join-Path $Out "D2R-XL-2012-$v.7z"
$verifyArgs = @('tools/verify_package.py', $archive, '--scratch', $Scratch)
if ($NoReference) { $verifyArgs += '--no-reference' }
Step 'verify_package.py' { py -3 @verifyArgs }
Write-Host "alpha $v ready in ${Out}:"
Get-ChildItem $Out -File | ForEach-Object { Write-Host ("  {0}  {1:n0} bytes" -f $_.Name, $_.Length) }
