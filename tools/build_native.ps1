# Builds StormLib.dll and CascLib.dll (used by the Python tools via ctypes, tools/native.py) from the submodule sources.
#   tools\build_native.ps1                      third_party\StormLib / CascLib -> build\<lib>\Release     (a normal clone)
#   tools\build_native.ps1 -Source DIR -Out DIR  sources in DIR\StormLib, DIR\CascLib -> DIR2\<lib>\Release (env MXL_NATIVE_SRC)
# tools\lane_setup.py calls the second form for the one build all worktrees share (<runs>\shared\native), with sources that it
# fetched from a local checkout when this worktree's submodules are empty (they are in a fresh `git worktree add`).
# Nothing is downloaded here: with empty sources the script stops and says how to get them. A build whose source commit is the
# one already built (build\<lib>\.source-sha) is skipped; -Force rebuilds. CMake: PATH, else Visual Studio's bundled one.
param([string]$Source = $env:MXL_NATIVE_SRC, [string]$Out, [switch]$Force)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
. "$PSScriptRoot\_cmake.ps1"
Use-ProjectTemp $root
if (-not $Source) { $Source = Join-Path $root 'third_party' }
if (-not $Out) { $Out = Join-Path $root 'build' }
$cmake = Find-CMake

# lib -> extra cmake arguments. CascLib still declares an old cmake_minimum_required.
$libs = [ordered]@{
    StormLib = @('-DBUILD_SHARED_LIBS=ON', '-DSTORM_USE_BUNDLED_LIBRARIES=ON', '-DSTORM_SKIP_INSTALL=ON')
    CascLib  = @('-DCMAKE_POLICY_VERSION_MINIMUM=3.5')
}
foreach ($lib in $libs.Keys) {
    $src = Join-Path $Source $lib
    if (-not (Test-Path (Join-Path $src 'CMakeLists.txt'))) {
        throw ("$src has no sources (an empty submodule). Either `git submodule update --init third_party/$lib` (needs the network), " +
               "or `py -3 tools/lane_setup.py` (takes them from a local checkout and builds once for every worktree).")
    }
    $bin = Join-Path $Out $lib
    $dll = Join-Path $bin "Release\$lib.dll"
    $sha = (& git -C $src rev-parse HEAD 2>$null)
    if ($LASTEXITCODE) { $sha = $null }
    $stamp = Join-Path $bin '.source-sha'
    if (-not $Force -and $sha -and (Test-Path $dll) -and (Test-Path $stamp) -and ((Get-Content $stamp -Raw).Trim() -eq $sha)) {
        Write-Host "$lib is up to date ($dll, source $($sha.Substring(0, 9)))"
        continue
    }
    $extra = $libs[$lib]
    & $cmake -S $src -B $bin -A x64 @extra
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    & $cmake --build $bin --config Release
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    if (-not (Test-Path $dll)) { throw "$lib built, but $dll is missing" }
    if ($sha) { Set-Content $stamp $sha -Encoding ascii }
}
