#Requires -Version 7.0
param([Parameter(Mandatory)][ValidatePattern('^[a-z0-9-]{1,50}$')][string]$Label,
      [Parameter(Mandatory)][ValidateSet('jfk-zira','chatterbox-nano-1089','chatterbox-nano-121')][string]$Avatar,
      [ValidateSet("cpu","cuda")][string]$Configuration = "cpu",
      [switch]$ProbesOnly, [switch]$Probes, [switch]$KeepOpen, [switch]$Prepare)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$directory = Join-Path (Get-Location) '.runtime/chatterbox-benchmarks'
New-Item -ItemType Directory -Force $directory | Out-Null
$prefix = Join-Path $directory $Label
if ((Test-Path -LiteralPath "$prefix.json") -or (Test-Path -LiteralPath "$prefix.stop")) {
    throw 'Choose a new label; prior attempts are never overwritten.'
}
if (Get-NetTCPConnection -LocalPort 8767 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8767 is in use; shut down the previous task application first.'
}
$launch = @('-NoProfile','-File','scripts/chatterbox-app.ps1','-NoBrowser','-Port','8767',
            '-Output',".runtime/chatterbox-integration-$Label",'-Avatar',$Avatar,'-Configuration',$Configuration)
if (-not $Prepare) { $launch += '-SkipPreparation' }
$app = Start-Process pwsh -ArgumentList $launch -WindowStyle Hidden -PassThru -RedirectStandardOutput "$prefix-app.out.log" -RedirectStandardError "$prefix-app.err.log"
$app.Id | Set-Content "$prefix-launcher.pid"
$measure = @('scripts/chatterbox-benchmark.cjs',"$prefix.json",$Avatar)
if ($Probes -or $ProbesOnly) { $measure += '--probes' }
if ($ProbesOnly) { $measure += '--probes-only' }
$bench = Start-Process node -ArgumentList $measure -WindowStyle Hidden -PassThru -RedirectStandardOutput "$prefix.out.log" -RedirectStandardError "$prefix.err.log"
$monitor = $null
try {
    $deadline = [DateTime]::UtcNow.AddSeconds(120)
    do {
        Start-Sleep -Milliseconds 100
        $listener = Get-NetTCPConnection -LocalPort 8767 -State Listen -ErrorAction SilentlyContinue
    } while (-not $listener -and [DateTime]::UtcNow -lt $deadline)
    if (-not $listener) { throw 'Experimental application did not bind its task port' }
    $serverPid = $listener.OwningProcess
    $monitor = Start-Process .runtime/venv/Scripts/python.exe -ArgumentList @('scripts/chatterbox_monitor.py','--pid',"$serverPid","$($bench.Id)",'--output',"$prefix-resources.jsonl",'--stop-file',"$prefix.stop",'--seconds','3600') -WindowStyle Hidden -PassThru -RedirectStandardOutput "$prefix-monitor.out.log" -RedirectStandardError "$prefix-monitor.err.log"
    if (-not $bench.WaitForExit(3900000)) { throw 'Benchmark exceeded its 65-minute wall limit' }
    $code = $bench.ExitCode
} finally {
    if (-not $bench.HasExited) { taskkill /PID $bench.Id /T /F | Out-Null }
    New-Item -ItemType File -Force "$prefix.stop" | Out-Null
    if ($monitor -and -not $monitor.WaitForExit(45000)) {
        taskkill /PID $monitor.Id /T /F | Out-Null
    }
    if (-not $KeepOpen) {
        try {
            Invoke-RestMethod -Uri http://127.0.0.1:8767/shutdown -Method Post -Body '{}' -ContentType application/json -TimeoutSec 15 | Out-Null
        } catch { }
        if (-not $app.WaitForExit(150000)) { taskkill /PID $app.Id /T /F | Out-Null }
    }
}
Get-Content "$prefix.out.log" -Tail 6
Get-Content "$prefix.err.log" -Tail 6
exit $code
