# Import and auto-analyse a game image dump (tools/dump_image.py) in a headless Ghidra project.
# Runs detached (analysis of the ~30 MB code section takes hours); progress goes to the log file.
#   powershell -File tools/ghidra_analyze.ps1 [-Dump <path>] [-MaxMem 8G]
# Project: ..\ghidra\project\D2R.gpr (outside the repo; open it in the Ghidra GUI when analysis is done).
param(
    [string]$Dump = "",
    [string]$MaxMem = "8G"
)
$ErrorActionPreference = 'Stop'
$sugma = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$ghidra = Join-Path $sugma "tools\ghidra_12.1.4_PUBLIC"
$work = Join-Path $sugma "ghidra"
if (-not $Dump) { $Dump = (Get-ChildItem $work -Filter "D2RLoader_*_dump.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName }
if (-not (Test-Path $Dump)) { throw "no dump found; run python tools/dump_image.py while the game is running" }
New-Item -ItemType Directory -Force (Join-Path $work "project") | Out-Null
$log = Join-Path $work ("analyze_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")
$env:GHIDRA_HEADLESS_MAXMEM = $MaxMem
$args = @((Join-Path $work "project"), "D2R", "-import", $Dump, "-overwrite",
          "-log", $log)  # no -analysisTimeoutPerFile: 0 means zero seconds, not unlimited
Start-Process -FilePath (Join-Path $ghidra "support\analyzeHeadless.bat") -ArgumentList $args `
    -WindowStyle Hidden -RedirectStandardOutput "$log.out" -RedirectStandardError "$log.err"
Write-Output "started: $Dump"
Write-Output "log: $log"
