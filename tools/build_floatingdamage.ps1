# Builds the bundled Floating Damage plugin (d2rl-ruffneckk-floating-damage.dll, by RuffnecKk,
# https://github.com/RuffDood/RuffnecKk-D2RLoader-Suite plugins/floating-damage, MIT, docs/bundled-plugins.md) from the author's
# source at the commit this repo pins (the gitlink third_party\RuffnecKk-D2RLoader-Suite) with our patches applied
# (third_party\floating-damage-mxl2012\*.patch, in name order), into build\floatingdamage\Release\. The author's repository is
# never changed: no fork.
# Source: -Src DIR, else MXL_FLOATINGDAMAGE_DIR (env or .mxl-local.json: any clone of the author's repo that has the pinned
# commit), else the submodule third_party\RuffnecKk-D2RLoader-Suite. The pinned commit's plugins/floating-damage, common/,
# third_party/PluginSDK (the author's pinned SDK v3 copy, vendored in the repo), scripts/ and the licence files are exported
# (git archive) into build\floatingdamage-src, patched there and built from there.
# The plugin's CMake fetches MinHook and Dear ImGui at the commits it pins (FetchContent, GitHub); they are kept in
# build\floatingdamage-deps, so only the first build needs the network.
# Output next to the DLL: the shipped config (ruffneckk-floating-damage.toml, our defaults), the author's LICENSE, the bundled
# font (Cinzel Bold, SIL OFL 1.1, third_party\floating-damage-mxl2012\fonts) and its licence. Unit tests: the author's config
# tests and our legacy projection tests (FloatingDamageMxlTests), built and run unless -NoTests.
param([string]$Src, [switch]$NoTests)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
. "$PSScriptRoot\_cmake.ps1"
Use-ProjectTemp $root

$ours = Join-Path $root 'third_party\floating-damage-mxl2012'
$paths = @('plugins/floating-damage', 'common', 'third_party/PluginSDK', 'third_party/notices', 'scripts', 'LICENSE',
           'THIRD_PARTY_NOTICES.md')
$stage = (git ls-files -s third_party/RuffnecKk-D2RLoader-Suite) -split '\s+'
if ($stage.Count -lt 2 -or $stage[0] -ne '160000') { throw 'third_party/RuffnecKk-D2RLoader-Suite is not a pinned submodule of this repo' }
$pin = $stage[1]
if (-not $Src) { $Src = Get-LocalSetting 'MXL_FLOATINGDAMAGE_DIR' $root }
if (-not $Src) { $Src = Join-Path $root 'third_party\RuffnecKk-D2RLoader-Suite' }
git -C $Src cat-file -e "$pin^{commit}" 2>$null
if ($LASTEXITCODE) {
    throw "floating-damage: commit $pin is not in $Src. Run ``git submodule update --init third_party/RuffnecKk-D2RLoader-Suite`` " +
          "(needs the network), or set MXL_FLOATINGDAMAGE_DIR (.mxl-local.json) to a clone of RuffDood's repo that has it."
}
$out = Join-Path $root 'build\floatingdamage-src'
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force $out | Out-Null
$zip = Join-Path $root 'build\floatingdamage-src.zip'
# the files as committed (LF), whatever this machine's autocrlf: the patches are LF
git -C $Src -c core.autocrlf=false -c core.eol=lf archive --format=zip -o $zip $pin @paths
if ($LASTEXITCODE) { exit $LASTEXITCODE }
Expand-Archive -Path $zip -DestinationPath $out
Remove-Item $zip
$patches = Get-ChildItem $ours -Filter '*.patch' | Sort-Object Name
foreach ($p in $patches) {
    # autocrlf off: the patched files stay LF like the rest (the config test compares the shipped TOML byte for byte)
    git -C $root -c core.autocrlf=false apply --whitespace=nowarn --directory=build/floatingdamage-src $p.FullName
    if ($LASTEXITCODE) { throw "floating-damage: $($p.Name) does not apply to commit $pin" }
}
# our tests (pure logic of the patches) go next to the author's
Copy-Item (Join-Path $ours 'tests\*.cpp') (Join-Path $out 'plugins\floating-damage\tests\')
Set-Content -Path (Join-Path $out 'PINNED_COMMIT') -Value $pin -Encoding ascii
# which patches went in (name and sha256): package_release.py can refuse a build whose patches are not the repo's
$sums = $patches | ForEach-Object { "$((Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower())  $($_.Name)" }
Set-Content -Path (Join-Path $out 'PATCHES') -Value $sums -Encoding ascii

$cmake = Find-CMake
$deps = (Join-Path $root 'build\floatingdamage-deps') -replace '\\', '/'
$testing = if ($NoTests) { 'OFF' } else { 'ON' }
& $cmake -S build\floatingdamage-src\plugins\floating-damage -B build\floatingdamage -A x64 "-DFETCHCONTENT_BASE_DIR=$deps" `
    "-DBUILD_TESTING=$testing"
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$targets = @('ruffneckk_floating_damage')
if (-not $NoTests) { $targets += @('ruffneckk_floating_damage_tests', 'floating_damage_mxl_tests') }
& $cmake --build build\floatingdamage --config Release --target @targets
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$rel = Join-Path $root 'build\floatingdamage\Release'
if (-not $NoTests) {
    & (Join-Path $rel 'ruffneckk_floating_damage_tests.exe') (Join-Path $out 'plugins\floating-damage\config\ruffneckk-floating-damage.toml')
    if ($LASTEXITCODE) { throw 'floating-damage: the author''s config tests failed' }
    & (Join-Path $rel 'floating_damage_mxl_tests.exe')
    if ($LASTEXITCODE) { throw 'floating-damage: FloatingDamageMxlTests failed' }
}
Copy-Item (Join-Path $out 'plugins\floating-damage\config\ruffneckk-floating-damage.toml') $rel -Force
Copy-Item (Join-Path $out 'LICENSE') (Join-Path $rel 'LICENSE-floating-damage.txt') -Force
Copy-Item (Join-Path $ours 'fonts\Cinzel-Bold.ttf') (Join-Path $rel 'ruffneckk-floating-damage-font.ttf') -Force
Copy-Item (Join-Path $ours 'fonts\OFL.txt') (Join-Path $rel 'LICENSE-floating-damage-font.txt') -Force
Write-Host "d2rl-ruffneckk-floating-damage.dll at commit $pin + $($patches.Count) patches -> build\floatingdamage\Release\"
