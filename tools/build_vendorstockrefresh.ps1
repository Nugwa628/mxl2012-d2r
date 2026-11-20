# Builds the bundled Vendor Stock Refresh plugin (d2rl-ruffneckk-vendor-stock-refresh.dll, by RuffnecKk,
# https://github.com/RuffDood/RuffnecKk-D2RLoader-Suite plugins/vendor-stock-refresh, MIT, docs/bundled-plugins.md) from the
# author's source at the commit this repo pins (the gitlink third_party\RuffnecKk-D2RLoader-Suite, the commit Floating
# Damage is built from), unchanged, into build\vendorstockrefresh\Release\. The author's repository is never changed: no fork.
# Source: -Src DIR, else MXL_FLOATINGDAMAGE_DIR (env or .mxl-local.json: any clone of the author's repo that has the pinned
# commit), else the submodule third_party\RuffnecKk-D2RLoader-Suite. The whole pinned commit is exported (git archive) into
# build\vendorstockrefresh-src and built from there with the suite's own CMake (its top level adds every plugin; only this
# plugin's targets are built).
# The suite's CMake fetches MinHook and nlohmann/json at the commits it pins (FetchContent, GitHub); they are kept in
# build\vendorstockrefresh-deps, so only the first build needs the network.
# Output next to the DLL: the shipped config (ruffneckk-vendor-stock-refresh.toml, the author's) and the suite's LICENSE.
# The companion MPQ (the button art) is not built here: it is the author's hub file, checked by tools/package_release.py.
# Unit tests: the author's policy, panel layout and compact layout tests, built and run unless -NoTests.
param([string]$Src, [switch]$NoTests)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
. "$PSScriptRoot\_cmake.ps1"
Use-ProjectTemp $root

$stage = (git ls-files -s third_party/RuffnecKk-D2RLoader-Suite) -split '\s+'
if ($stage.Count -lt 2 -or $stage[0] -ne '160000') { throw 'third_party/RuffnecKk-D2RLoader-Suite is not a pinned submodule of this repo' }
$pin = $stage[1]
if (-not $Src) { $Src = Get-LocalSetting 'MXL_FLOATINGDAMAGE_DIR' $root }
if (-not $Src) { $Src = Join-Path $root 'third_party\RuffnecKk-D2RLoader-Suite' }
git -C $Src cat-file -e "$pin^{commit}" 2>$null
if ($LASTEXITCODE) {
    throw "vendor-stock-refresh: commit $pin is not in $Src. Run ``git submodule update --init third_party/RuffnecKk-D2RLoader-Suite`` " +
          "(needs the network), or set MXL_FLOATINGDAMAGE_DIR (.mxl-local.json) to a clone of RuffDood's repo that has it."
}
$out = Join-Path $root 'build\vendorstockrefresh-src'
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force $out | Out-Null
$zip = Join-Path $root 'build\vendorstockrefresh-src.zip'
git -C $Src -c core.autocrlf=false -c core.eol=lf archive --format=zip -o $zip $pin
if ($LASTEXITCODE) { exit $LASTEXITCODE }
Expand-Archive -Path $zip -DestinationPath $out
Remove-Item $zip
Set-Content -Path (Join-Path $out 'PINNED_COMMIT') -Value $pin -Encoding ascii

$cmake = Find-CMake
$deps = (Join-Path $root 'build\vendorstockrefresh-deps') -replace '\\', '/'
$testing = if ($NoTests) { 'OFF' } else { 'ON' }
& $cmake -S build\vendorstockrefresh-src -B build\vendorstockrefresh -A x64 "-DFETCHCONTENT_BASE_DIR=$deps" `
    "-DBUILD_TESTING=$testing"
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$targets = @('ruffneckk_vendor_stock_refresh')
$tests = @('ruffneckk_vendor_stock_refresh_tests', 'ruffneckk_vendor_stock_refresh_panel_tests',
           'ruffneckk_vendor_stock_refresh_layout_tests')
if (-not $NoTests) { $targets += $tests }
& $cmake --build build\vendorstockrefresh --config Release --target @targets
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$plugin = 'plugins\vendor-stock-refresh'
$rel = Join-Path $root "build\vendorstockrefresh\$plugin\Release"
$config = Join-Path $out "$plugin\config\ruffneckk-vendor-stock-refresh.toml"
if (-not $NoTests) {
    foreach ($t in $tests) {
        $exe = Join-Path $rel "$t.exe"
        if ($t -eq 'ruffneckk_vendor_stock_refresh_tests') { & $exe $config } else { & $exe }
        if ($LASTEXITCODE) { throw "vendor-stock-refresh: $t failed" }
    }
}
$final = Join-Path $root 'build\vendorstockrefresh\Release'
New-Item -ItemType Directory -Force $final | Out-Null
Copy-Item (Join-Path $rel 'd2rl-ruffneckk-vendor-stock-refresh.dll') $final -Force
Copy-Item $config $final -Force
Copy-Item (Join-Path $out 'LICENSE') (Join-Path $final 'LICENSE-vendor-stock-refresh.txt') -Force
Write-Host "d2rl-ruffneckk-vendor-stock-refresh.dll at commit $pin -> build\vendorstockrefresh\Release\"
