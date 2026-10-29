# Lane variant of ghidra_query.ps1 for git worktrees (the original derives ..\ghidra from the script location).
#   powershell -File tools\ghidra_lane.ps1 <Script.java> -ProjectDir <dir> [-Project D2R|D2Game|D2Sigma] [args...]
# Script path = this worktree's tools\ghidra_scripts plus the main repo's.
param([Parameter(Mandatory = $true, Position = 0)][string]$Script, [string]$Project = "D2R", [Parameter(Mandatory = $true)][string]$ProjectDir,
      [Parameter(ValueFromRemainingArguments = $true)][string[]]$ScriptArgs)
$ghidra = Join-Path $env:USERPROFILE "tools\ghidra_12.1.4_PUBLIC"
$work = Join-Path $env:USERPROFILE "ghidra"
if ($Project -eq "D2Sigma") { $program = "D2Sigma.dll" }
elseif ($Project -eq "D2Game") { $program = "D2Game_113.dll" }
else { $program = (Get-ChildItem $work -Filter "D2RLoader_*_dump.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).Name }
$log = Join-Path $ProjectDir "query.log"
$env:GHIDRA_HEADLESS_MAXMEM = "6G"
$sp = (Join-Path $PSScriptRoot 'ghidra_scripts') + ";" + (Join-Path $env:USERPROFILE "mxl2012-d2r\tools\ghidra_scripts")
$argLine = @("`"$ProjectDir`"", $Project, "-process", $program, "-noanalysis", "-readOnly",
             "-scriptPath", "`"$sp`"", "-postScript", $Script) + $ScriptArgs
$p = Start-Process -FilePath (Join-Path $ghidra "support\analyzeHeadless.bat") -ArgumentList $argLine -NoNewWindow `
    -Wait -PassThru -RedirectStandardOutput $log -RedirectStandardError "$log.err"
Get-Content $log | Where-Object { $_ -match "\.java> " } | ForEach-Object { $_ -replace '^.*?\.java> ', '' -replace '\s+\(GhidraScript\)\s*$', '' }
Get-Content $log | Where-Object { $_ -match "ERROR|Exception" } | Select-Object -First 5
exit $p.ExitCode
