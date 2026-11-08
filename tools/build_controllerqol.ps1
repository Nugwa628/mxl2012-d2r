# Builds the bundled Controller QOL Updates plugin ("Controller QOL Updates.dll", by PyreFly, https://github.com/Pyre-Flies/D2R-Mods
# plugins/controller-qol, docs/bundled-plugins.md) from PyreFly's source at the commit this repo pins (the gitlink
# third_party\D2R-Mods) with our patches applied (third_party\controller-qol-mxl2012\*.patch, in name order), into
# build\controllerqol\Release\Controller QOL Updates.dll. PyreFly's repository is never changed: no fork.
# Source: -Src DIR, else MXL_CONTROLLERQOL_DIR (env or .mxl-local.json: any clone of PyreFly's repo that has the pinned commit;
# a sparse or blob-less clone needs plugins/controller-qol and plugins/inventory-deposit checked out once), else the
# submodule third_party\D2R-Mods. The pinned commit's plugins/controller-qol, plugins/inventory-deposit/src and tests (its build reuses
# the stash feedback from there) and LICENSE are exported (git archive) into build\controllerqol-src, patched there and built
# from there with the PluginSDK of tools\build_plugin.ps1 (its own pin is the submodule of PyreFly's repo, which this build does
# not use). Nothing is downloaded here. -NoTests skips the plugin's own unit tests (built and run by default).
# -SkillProfile FILE: the mxl2012 skill seed (tools/controller_skill_profile.py from the built skills.txt) replaces the plugin's
# embedded skill-defaults.toml (vanilla skill ids). The plugin fills a missing per-install profile
# (d2rloader\config\controller-qol-skills\<scope>.overrides.toml) from it at the first start and only adds missing keys later,
# so a player's own choices are never replaced. Its sha256 goes into build\controllerqol-src\SKILL_PROFILE; package_release.py
# refuses a build without it.
param([string]$Src, [string]$Sdk, [string]$SkillProfile, [switch]$NoTests)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
. "$PSScriptRoot\_cmake.ps1"
Use-ProjectTemp $root

$paths = @('plugins/controller-qol', 'plugins/inventory-deposit/src', 'plugins/inventory-deposit/tests', 'LICENSE')
$stage = (git ls-files -s third_party/D2R-Mods) -split '\s+'
if ($stage.Count -lt 2 -or $stage[0] -ne '160000') { throw 'third_party/D2R-Mods is not a pinned submodule of this repo' }
$pin = $stage[1]
if (-not $Src) { $Src = Get-LocalSetting 'MXL_CONTROLLERQOL_DIR' $root }
if (-not $Src) { $Src = Join-Path $root 'third_party\D2R-Mods' }
git -C $Src cat-file -e "$pin^{commit}" 2>$null
if ($LASTEXITCODE) {
    throw "controller-qol: commit $pin is not in $Src. Run ``git submodule update --init third_party/D2R-Mods`` (needs the " +
          "network), or set MXL_CONTROLLERQOL_DIR (.mxl-local.json) to a clone of PyreFly's repo that has it."
}
$out = Join-Path $root 'build\controllerqol-src'
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force $out | Out-Null
$zip = Join-Path $root 'build\controllerqol-src.zip'
# the files as committed (LF), whatever this machine's autocrlf: the patches are LF
git -C $Src -c core.autocrlf=false -c core.eol=lf archive --format=zip -o $zip $pin @paths
if ($LASTEXITCODE) { exit $LASTEXITCODE }
Expand-Archive -Path $zip -DestinationPath $out
Remove-Item $zip
$ours = Join-Path $root 'third_party\controller-qol-mxl2012'
$patches = Get-ChildItem $ours -Filter '*.patch' | Sort-Object Name
foreach ($p in $patches) {
    git -C $root apply --whitespace=nowarn --directory=build/controllerqol-src $p.FullName
    if ($LASTEXITCODE) { throw "controller-qol: $($p.Name) does not apply to commit $pin" }
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
# the licence of the PluginSDK it links, shipped next to the DLL (package_release.py)
Copy-Item -Force (Join-Path $Sdk 'LICENSE') (Join-Path $out 'PluginSDK-LICENSE')
$tests = if ($NoTests) { 'OFF' } else { 'ON' }
& $cmake -S build\controllerqol-src\plugins\controller-qol -B build\controllerqol -A x64 "-DPLUGIN_SDK=$($Sdk -replace '\\', '/')" `
    "-DCONTROLLER_QOL_BUILD_TESTS=$tests"
if ($LASTEXITCODE) { exit $LASTEXITCODE }
# its UTF-8 string literals compile on any system code page (932 on the build PC fails C5297 under /WX)
$env:CL = '/utf-8'
if ($NoTests) {
    & $cmake --build build\controllerqol --config Release --target controller-qol
} else {
    & $cmake --build build\controllerqol --config Release
}
if ($LASTEXITCODE) { exit $LASTEXITCODE }
if (-not $NoTests) {
    $ctest = Join-Path (Split-Path $cmake -Parent) 'ctest.exe'
    & $ctest --test-dir build\controllerqol -C Release --output-on-failure
    if ($LASTEXITCODE) { throw 'controller-qol: its unit tests failed' }
}
# the seed after the tests: two of them check PyreFly's own reference defaults (vanilla names and ids). The DLL is linked again
# with the seed embedded (the resource depends on the file, so only the plugin rebuilds).
if ($SkillProfile) {
    $defaults = Join-Path $out 'plugins\controller-qol\skill-defaults.toml'
    Copy-Item -Force $SkillProfile $defaults
    (Get-Item $defaults).LastWriteTime = Get-Date  # newer than the configure: CMake copies it again
    & $cmake --build build\controllerqol --config Release --target controller-qol
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    Set-Content -Path (Join-Path $out 'SKILL_PROFILE') -Value (Get-FileHash -Algorithm SHA256 $SkillProfile).Hash.ToLower() -Encoding ascii
}
Write-Host "Controller QOL Updates.dll at commit $pin + $($patches.Count) patches -> build\controllerqol\Release\Controller QOL Updates.dll"
