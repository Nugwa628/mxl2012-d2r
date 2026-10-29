# Samples machine and per-process load every few seconds and prints one JSON object per sample (read by
# tools/parallel_smoke.py). Processes: every D2RLoader / D2R process whose image is inside one of the -Folders.
#   powershell -File tools\resource_sample.ps1 -Folders 'D:\D2R-93847','D:\D2R-93847-s3' -Interval 3 -Count 100
# Per process: cpu = share of ONE core in percent (100 = one core busy), ws = working set MB, gpu = GPU engine
# utilisation summed over the process's engines (3D, copy, compute...), gpumem = dedicated GPU memory MB.
param([string[]]$Folders = @(), [int]$Interval = 3, [int]$Count = 1000000)
$Folders = @($Folders | ForEach-Object { $_ -split ',' } | Where-Object { $_ })  # -File passes "a,b" as one string
$cores = [Environment]::ProcessorCount
$prev = @{}
for ($n = 0; $n -lt $Count; $n++) {
    $t0 = Get-Date
    $ctr = Get-Counter -Counter '\Processor(_Total)\% Processor Time', '\Memory\Available MBytes', '\GPU Engine(*)\Utilization Percentage', '\GPU Process Memory(*)\Dedicated Usage' -SampleInterval 1 -MaxSamples 2 -ErrorAction SilentlyContinue
    $ctr = @($ctr)[-1]  # the second reading: rate counters need two points
    $cpu = 0; $avail = 0; $gpu = @{}; $gmem = @{}; $gpuTotal = 0
    foreach ($s in $ctr.CounterSamples) {
        if ($s.Path -like '*\processor(_total)\*') { $cpu = $s.CookedValue }
        elseif ($s.Path -like '*\memory\available mbytes') { $avail = $s.CookedValue }
        elseif ($s.Path -like '*gpu engine*') {
            $gpuTotal += $s.CookedValue
            if ($s.InstanceName -match 'pid_(\d+)_') { $p = [int]$Matches[1]; $gpu[$p] = [double]$gpu[$p] + $s.CookedValue }
        }
        elseif ($s.Path -like '*gpu process memory*') {
            if ($s.InstanceName -match 'pid_(\d+)_') { $p = [int]$Matches[1]; $gmem[$p] = [double]$gmem[$p] + $s.CookedValue }
        }
    }
    $now = Get-Date
    $procs = @()
    $games = @(Get-Process D2RLoader*, D2R -ErrorAction SilentlyContinue | Where-Object { $p = $_.Path; $p -and ($Folders | Where-Object { $p.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) }) })
    foreach ($pr in $games) {
        $id = $pr.Id
        $cpuPct = 0
        if ($prev.ContainsKey($id)) {
            $dt = ($now - $prev[$id].t).TotalSeconds
            if ($dt -gt 0) { $cpuPct = ($pr.TotalProcessorTime.TotalSeconds - $prev[$id].c) / $dt * 100 }
        }
        $prev[$id] = @{ t = $now; c = $pr.TotalProcessorTime.TotalSeconds }
        $procs += [pscustomobject]@{ pid = $id; cpu = [math]::Round($cpuPct, 1); ws = [math]::Round($pr.WorkingSet64 / 1MB); gpu = [math]::Round([double]$gpu[$id], 1); gpumem = [math]::Round([double]$gmem[$id] / 1MB) }
    }
    [pscustomobject]@{ t = $now.ToString('HH:mm:ss'); cores = $cores; cpu = [math]::Round($cpu, 1); availMB = [math]::Round($avail); gpuAll = [math]::Round($gpuTotal, 1); procs = $procs } | ConvertTo-Json -Compress -Depth 4
    $sleep = $Interval - ((Get-Date) - $t0).TotalSeconds
    if ($sleep -gt 0) { Start-Sleep -Milliseconds ([int]($sleep * 1000)) }
}
