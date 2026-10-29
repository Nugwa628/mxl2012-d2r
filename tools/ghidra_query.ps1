# Run a Ghidra script from tools/ghidra_scripts against the analysed project (read-only, no re-analysis) and print
# its output lines.   powershell -File tools/ghidra_query.ps1 <Script.java> [-Project D2R|D2Sigma] [args...]
# D2R: the dumped game image (..\ghidra\project); D2Sigma: Median's D2Sigma.dll (..\ghidra\sigma); D2Game:
# 1.13 D2Game.dll from Median's Annihilus launcher (..\ghidra\d2game; base 0x6fc20000, the one D2Sigma imports from).
# Full Ghidra output: ..\ghidra\query.log (or <ProjectDir>\query.log). Parallel lanes pass -ProjectDir with their own
# copy (..\ghidra-lanes\<lane>\d2r): two headless runs can't open one project at once.
param([Parameter(Mandatory = $true, Position = 0)][string]$Script, [string]$Project = "D2R", [string]$ProjectDir = "",
      [Parameter(ValueFromRemainingArguments = $true)][string[]]$ScriptArgs)
$sugma = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$ghidra = Join-Path $sugma "tools\ghidra_12.1.4_PUBLIC"
$work = Join-Path $sugma "ghidra"
if ($Project -eq "D2Sigma") { $projDir = Join-Path $work "sigma"; $program = "D2Sigma.dll" }
elseif ($Project -eq "D2Game") { $projDir = Join-Path $work "d2game"; $program = "D2Game_113.dll" }
else { $projDir = Join-Path $work "project"; $program = (Get-ChildItem $work -Filter "D2RLoader_*_dump.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).Name }
if ($ProjectDir) { $projDir = $ProjectDir }
$log = if ($ProjectDir) { Join-Path $ProjectDir "query.log" } else { Join-Path $work "query.log" }
$env:GHIDRA_HEADLESS_MAXMEM = "6G"
$argLine = @("`"$projDir`"", $Project, "-process", $program, "-noanalysis", "-readOnly",
             "-scriptPath", "`"$(Join-Path $PSScriptRoot 'ghidra_scripts')`"", "-postScript", $Script) + $ScriptArgs
$p = Start-Process -FilePath (Join-Path $ghidra "support\analyzeHeadless.bat") -ArgumentList $argLine -NoNewWindow `
    -Wait -PassThru -RedirectStandardOutput $log -RedirectStandardError "$log.err"
Get-Content $log | Where-Object { $_ -match "\.java> " } | ForEach-Object { $_ -replace '^.*?\.java> ', '' -replace '\s+\(GhidraScript\)\s*$', '' }
Get-Content $log | Where-Object { $_ -match "ERROR|Exception" } | Select-Object -First 5
exit $p.ExitCode
