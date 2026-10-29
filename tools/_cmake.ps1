# Dot-sourced by build_native.ps1 and build_plugin.ps1: Find-CMake (the one on PATH, else Visual Studio's bundled cmake.exe)
# and Get-LocalSetting (a value of the git-ignored .mxl-local.json that tools/lane_setup.py writes; an environment variable wins).
function Find-CMake {
    $cmake = (Get-Command cmake -ErrorAction SilentlyContinue).Source
    if ($cmake) { return $cmake }
    $vs = Get-ChildItem 'C:\Program Files\Microsoft Visual Studio\*\*\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe' -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $vs) { throw 'cmake not found (PATH or Visual Studio)' }
    return $vs.FullName
}

function Get-LocalSetting([string]$Name, [string]$Root) {
    $v = [Environment]::GetEnvironmentVariable($Name)
    if ($v) { return $v }
    $file = Join-Path $Root '.mxl-local.json'
    if (Test-Path $file) {
        $json = Get-Content $file -Raw | ConvertFrom-Json
        if ($json.PSObject.Properties.Name -contains $Name) { return [string]$json.$Name }
    }
    return $null
}

# Temp files of this script and of the tools it starts (CMake, MSBuild, the compilers) stay inside the project, like
# tools/projtemp.py does for Python: MXL_TMP, else a TEMP/TMP already inside the checkout or the runs folder, else <root>\work\tmp.
function Use-ProjectTemp([string]$Root) {
    $runs = if ($env:MXL2012_RUNS) { $env:MXL2012_RUNS } else { Join-Path (Split-Path (Split-Path $Root -Parent) -Parent) 'mxl2012-runs' }
    $target = $env:MXL_TMP
    if (-not $target) {
        foreach ($cur in @($env:TMPDIR, $env:TEMP, $env:TMP)) {
            if ($cur -and ($cur.TrimEnd('\') + '\').StartsWith($Root.TrimEnd('\') + '\', 'OrdinalIgnoreCase') -or
                ($cur -and ($cur.TrimEnd('\') + '\').StartsWith($runs.TrimEnd('\') + '\', 'OrdinalIgnoreCase'))) { $target = $cur; break }
        }
    }
    if (-not $target) { $target = Join-Path $Root 'work\tmp' }
    New-Item -ItemType Directory -Force $target | Out-Null
    $env:TMPDIR = $target; $env:TEMP = $target; $env:TMP = $target
}
