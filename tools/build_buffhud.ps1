# Builds the bundled Buff HUD plugin (d2rl-buff-panel.dll + d2rl-buff-panel.mpq; our fork https://github.com/Nugwa628/d2rl-buff-hud
# of Lukaszpg's d2rl-buff-hud, docs/bundled-plugins.md) from its source at the commit this repo pins (the gitlink
# third_party\d2rl-buff-hud, branch mxl2012), with the fork's own release preset, into build\buffhud\Release\, and runs its tests.
# Source: -Src DIR, else MXL_BUFFHUD_DIR (env or .mxl-local.json: any clone of the fork that has the pinned commit), else the
# submodule third_party\d2rl-buff-hud. Whatever that checkout has checked out, the pinned commit is exported (git archive) into
# build\buffhud-src and built from there. Its PluginSDK (a submodule of the fork, not in the archive) is exported the same way
# at the commit the fork pins, from -Sdk / MXL2012_PLUGINSDK_DIR / third_party\PluginSDK. Nothing is downloaded here.
# Needs Visual Studio 2022 with the C++ workload (the fork's scripts\build.ps1 finds it with vswhere; CMake and Ninja come with it).
param([string]$Src, [string]$Sdk)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
. "$PSScriptRoot\_cmake.ps1"
Use-ProjectTemp $root

$stage = (git ls-files -s third_party/d2rl-buff-hud) -split '\s+'
if ($stage.Count -lt 2 -or $stage[0] -ne '160000') { throw 'third_party/d2rl-buff-hud is not a pinned submodule of this repo' }
$pin = $stage[1]
if (-not $Src) { $Src = Get-LocalSetting 'MXL_BUFFHUD_DIR' $root }
if (-not $Src) { $Src = Join-Path $root 'third_party\d2rl-buff-hud' }
git -C $Src cat-file -e "$pin^{commit}" 2>$null
if ($LASTEXITCODE) {
    throw "d2rl-buff-hud: commit $pin is not in $Src. Run ``git submodule update --init third_party/d2rl-buff-hud`` (needs the " +
          "network), or set MXL_BUFFHUD_DIR (.mxl-local.json) to a clone of the fork that has it."
}
$sdkPin = ((git -C $Src ls-tree $pin external/PluginSDK) -split '\s+')[2]
if (-not $Sdk) { $Sdk = Get-LocalSetting 'MXL2012_PLUGINSDK_DIR' $root }
if (-not $Sdk) { $Sdk = Join-Path $root 'third_party\PluginSDK' }
git -C $Sdk cat-file -e "$sdkPin^{commit}" 2>$null
if ($LASTEXITCODE) {
    throw "PluginSDK: commit $sdkPin (the fork's external/PluginSDK) is not in $Sdk. Run ``py -3 tools/lane_setup.py`` or " +
          "``git submodule update --init third_party/PluginSDK``, or pass -Sdk a PluginSDK clone that has it."
}

function Export-Commit([string]$Repo, [string]$Commit, [string]$Dest) {
    $zip = "$Dest.zip"
    # the files as committed (LF), whatever this machine's autocrlf: the same MPQ bytes everywhere
    git -C $Repo -c core.autocrlf=false -c core.eol=lf archive --format=zip -o $zip $Commit
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    Expand-Archive -Path $zip -DestinationPath $Dest
    Remove-Item $zip
}
$out = Join-Path $root 'build\buffhud-src'
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force $out | Out-Null
Export-Commit $Src $pin $out
$sdkOut = Join-Path $out 'external\PluginSDK'
if (Test-Path $sdkOut) { Remove-Item -Recurse -Force $sdkOut }
Export-Commit $Sdk $sdkPin $sdkOut
Set-Content -Path (Join-Path $out 'PINNED_COMMIT') -Value $pin -Encoding ascii

# The fork's own build: vcvars, the release preset (Ninja), its unit tests; then the companion MPQ.
& (Join-Path $out 'scripts\build.ps1') -Preset release
if ($LASTEXITCODE) { Write-Host 'FAILED: d2rl-buff-hud build or tests'; exit $LASTEXITCODE }
Push-Location $out
try {
    cmake --build --preset release --target buff_panel_companion
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
} finally { Pop-Location }

$built = Join-Path $out 'build\release\stage\Release\d2rloader\plugins'
$dest = Join-Path $root 'build\buffhud\Release'
New-Item -ItemType Directory -Force $dest | Out-Null
foreach ($f in 'd2rl-buff-panel.dll', 'd2rl-buff-panel.mpq') { Copy-Item -Force (Join-Path $built $f) (Join-Path $dest $f) }
Write-Host "d2rl-buff-panel.dll + .mpq at commit $pin -> build\buffhud\Release\"
