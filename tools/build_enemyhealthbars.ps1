# Builds the bundled Enemy Health Bars plugin (d2rl-enemy-health-bars.dll, by Graxy_TV,
# https://github.com/graxytv/D2R-Over-the-Head-Health-Bars, GPL-3.0-only, docs/bundled-plugins.md) from the author's source with
# our patches applied (third_party\enemy-health-bars-mxl2012\*.patch, in name order), into build\enemyhealthbars\.
# The author's repository holds the release as a zip (EnemyHealthBars-0.2.6-Reimagined-Share.zip, added in the pinned commit and
# deleted in the next one); its source\EnemyHealthBars-0.2.6-Source.zip is the plugin's complete source with its build
# dependencies (PluginSDK, ImGui). Both zips are checked by sha256 before anything is extracted.
# Source: -Src DIR (a clone of the author's repo that has the pinned commit), else MXL_EHB_DIR (env or .mxl-local.json), else a
# clone into build\enemyhealthbars-repo (needs the network once). The source is extracted into build\enemyhealthbars-src, patched
# there and built from there with the source's own CMakeLists.txt and its bundled PluginSDK (as the author built it).
# Output, all of it shipped (GPL: the release carries the corresponding source):
#   build\enemyhealthbars\Release\d2rl-enemy-health-bars.dll
#   build\enemyhealthbars\LICENSE, THIRD_PARTY.md, licenses\ (the author's notices)
#   build\enemyhealthbars\enemy-health-bars.toml (the plugin's config with our defaults)
#   build\enemyhealthbars\d2rl-enemy-health-bars-source.zip (the patched source as built, our patches, SOURCE.txt with the refs)
# The author's policy tests (policy_tests.cpp) are built and run here.
param([string]$Src)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
. "$PSScriptRoot\_cmake.ps1"
Use-ProjectTemp $root

$repoUrl = 'https://github.com/graxytv/D2R-Over-the-Head-Health-Bars'
$pin = 'e6b929bfa5c59e79e0cbabf898eb777f6d359132'
$shareName = 'EnemyHealthBars-0.2.6-Reimagined-Share.zip'
$shareSha = 'c0ed2aa43205202601ec8075f3043e6dada5f0992ab9423e2a6378ad4eec10f4'
$sourceName = 'source/EnemyHealthBars-0.2.6-Source.zip'
$sourceSha = '8e26f4a9164f38d4f0970d1d4cd0e68c416c8df1272b01b1e1682195cd1acfa1'

if (-not $Src) { $Src = Get-LocalSetting 'MXL_EHB_DIR' $root }
if (-not $Src) {
    $Src = Join-Path $root 'build\enemyhealthbars-repo'
    if (-not (Test-Path (Join-Path $Src '.git'))) {
        git clone --quiet $repoUrl $Src
        if ($LASTEXITCODE) { throw "enemy-health-bars: cannot clone $repoUrl (set MXL_EHB_DIR to a local clone)" }
    }
}
git -C $Src cat-file -e "$pin^{commit}" 2>$null
if ($LASTEXITCODE) { throw "enemy-health-bars: commit $pin is not in $Src" }

$work = Join-Path $root 'build\enemyhealthbars-work'
if (Test-Path $work) { Remove-Item -Recurse -Force $work }
New-Item -ItemType Directory -Force $work | Out-Null
$share = Join-Path $work 'share.zip'
# git show to a file without any text conversion (PowerShell's > would re-encode the bytes)
$p = Start-Process -FilePath git -ArgumentList @('-C', $Src, 'show', "${pin}:$shareName") -RedirectStandardOutput $share -NoNewWindow -Wait -PassThru
if ($p.ExitCode) { throw "enemy-health-bars: $shareName is not in commit $pin" }
if ((Get-FileHash -Algorithm SHA256 $share).Hash.ToLower() -ne $shareSha) { throw "enemy-health-bars: $shareName sha256 differs" }
Expand-Archive -Path $share -DestinationPath (Join-Path $work 'share')
$inner = Join-Path $work "share\$sourceName"
if ((Get-FileHash -Algorithm SHA256 $inner).Hash.ToLower() -ne $sourceSha) { throw "enemy-health-bars: $sourceName sha256 differs" }

$out = Join-Path $root 'build\enemyhealthbars-src'
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
Expand-Archive -Path $inner -DestinationPath $out
$tree = Join-Path $out 'EnemyHealthBars'
$patches = Get-ChildItem (Join-Path $root 'third_party\enemy-health-bars-mxl2012') -Filter '*.patch' | Sort-Object Name
foreach ($patch in $patches) {
    git -C $root apply --whitespace=nowarn --ignore-whitespace --directory=build/enemyhealthbars-src/EnemyHealthBars $patch.FullName
    if ($LASTEXITCODE) { throw "enemy-health-bars: $($patch.Name) does not apply to the source of commit $pin" }
}
$sums = $patches | ForEach-Object { "$((Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower())  $($_.Name)" }
Set-Content -Path (Join-Path $tree 'PATCHES') -Value $sums -Encoding ascii
Set-Content -Path (Join-Path $tree 'SOURCE.txt') -Encoding ascii -Value @(
    'Enemy Health Bars 0.2.6 by Graxy_TV, GPL-3.0-only (LICENSE), as built for D2R-XL 2012.',
    "Upstream: $repoUrl commit $pin, $shareName (sha256 $shareSha),",
    "  inside it $sourceName (sha256 $sourceSha).",
    'This tree is that source with the patches in mxl2012-patches/ applied (in name order; their sha256 in PATCHES).')

$outDir = Join-Path $root 'build\enemyhealthbars'
if (Test-Path $outDir) { Remove-Item -Recurse -Force $outDir }
$cmake = Find-CMake
& $cmake -S $tree -B $outDir -A x64
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $cmake --build $outDir --config Release --target EnemyHealthBars policy_tests
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& (Join-Path $outDir 'Release\policy_tests.exe')
if ($LASTEXITCODE) { throw 'enemy-health-bars: policy_tests failed' }

Copy-Item (Join-Path $tree 'LICENSE') $outDir
Copy-Item (Join-Path $tree 'THIRD_PARTY.md') $outDir
# the config as built (our patches set its defaults), shipped as d2rloader\config\enemy-health-bars.toml
Copy-Item (Join-Path $tree 'enemy-health-bars.toml') $outDir
Copy-Item -Recurse (Join-Path $work 'share\licenses') (Join-Path $outDir 'licenses')
# the corresponding source: the patched tree as built plus the patches themselves
$srcStage = Join-Path $work 'source'
New-Item -ItemType Directory -Force $srcStage | Out-Null
Copy-Item -Recurse $tree (Join-Path $srcStage 'EnemyHealthBars')
New-Item -ItemType Directory -Force (Join-Path $srcStage 'EnemyHealthBars\mxl2012-patches') | Out-Null
$patches | ForEach-Object { Copy-Item $_.FullName (Join-Path $srcStage 'EnemyHealthBars\mxl2012-patches') }
Compress-Archive -Path (Join-Path $srcStage 'EnemyHealthBars') -DestinationPath (Join-Path $outDir 'd2rl-enemy-health-bars-source.zip')
Remove-Item -Recurse -Force $work
Write-Host "d2rl-enemy-health-bars.dll at commit $pin + $($patches.Count) patches -> build\enemyhealthbars\Release\d2rl-enemy-health-bars.dll"
