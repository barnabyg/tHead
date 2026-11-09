#Requires -Version 7.0
param([Parameter(Mandatory)][ValidatePattern('^[a-z0-9-]{1,50}$')][string]$Label,
      [Parameter(Mandatory)][ValidateSet('jfk-zira','chatterbox-nano-1089','chatterbox-nano-121')][string]$Avatar,
      [ValidateSet("cpu","cuda","maintained")][string]$Configuration = "cpu",
      [string]$State = '',
      [ValidateRange(1024,65535)][int]$Port = 8767,
      [switch]$ProbesOnly, [switch]$Probes, [switch]$SkipAssetProbes,
      [switch]$KeepOpen, [switch]$Prepare)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$directory = Join-Path (Get-Location) '.runtime/chatterbox-benchmarks'
New-Item -ItemType Directory -Force $directory | Out-Null
$prefix = Join-Path $directory $Label
if ((Test-Path -LiteralPath "$prefix.json") -or (Test-Path -LiteralPath "$prefix.stop")) {
    throw 'Choose a new label; prior attempts are never overwritten.'
}
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is in use; shut down the previous task application first."
}
$gpuBefore = & nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits
$launch = @('-NoProfile','-File','scripts/chatterbox-app.ps1','-NoBrowser','-Port',"$Port",
            '-Output',".runtime/chatterbox-integration-$Label",'-Avatar',$Avatar,'-Configuration',$Configuration)
if (-not $Prepare) { $launch += '-SkipPreparation' }
if ($State) { $launch += @('-State', [IO.Path]::GetFullPath($State)) }
$app = Start-Process pwsh -ArgumentList $launch -WindowStyle Hidden -PassThru -RedirectStandardOutput "$prefix-app.out.log" -RedirectStandardError "$prefix-app.err.log"
$app.Id | Set-Content "$prefix-launcher.pid"
$measure = @('scripts/chatterbox-benchmark.cjs',"$prefix.json",$Avatar)
if ($Probes -or $ProbesOnly) { $measure += '--probes' }
if ($ProbesOnly) { $measure += '--probes-only' }
if ($SkipAssetProbes) { $measure += '--skip-asset-probes' }
$env:THEAD_URL = "http://127.0.0.1:$Port"
if ($State) { $env:THEAD_CHATTERBOX_STATE = [IO.Path]::GetFullPath($State) }
else { Remove-Item Env:THEAD_CHATTERBOX_STATE -ErrorAction SilentlyContinue }
$bench = Start-Process node -ArgumentList $measure -WindowStyle Hidden -PassThru -RedirectStandardOutput "$prefix.out.log" -RedirectStandardError "$prefix.err.log"
$monitor = $null
try {
    $deadline = [DateTime]::UtcNow.AddSeconds(120)
    do {
        Start-Sleep -Milliseconds 100
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    } while (-not $listener -and [DateTime]::UtcNow -lt $deadline)
    if (-not $listener) { throw 'Experimental application did not bind its task port' }
    $serverPid = $listener.OwningProcess
    $monitor = Start-Process .runtime/venv/Scripts/python.exe -ArgumentList @('-I','scripts/chatterbox_monitor.py','--pid',"$serverPid","$($bench.Id)",'--output',"$prefix-resources.jsonl",'--stop-file',"$prefix.stop",'--seconds','3600') -WindowStyle Hidden -PassThru -RedirectStandardOutput "$prefix-monitor.out.log" -RedirectStandardError "$prefix-monitor.err.log"
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
            Invoke-RestMethod -Uri "http://127.0.0.1:$Port/shutdown" -Method Post -Body '{}' -ContentType application/json -TimeoutSec 15 | Out-Null
        } catch { }
        if (-not $app.WaitForExit(150000)) { taskkill /PID $app.Id /T /F | Out-Null }
    }
}
$gpuAfter = & nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits
@{ global_vram_before_mib = [int]$gpuBefore; global_vram_after_mib = [int]$gpuAfter;
   task_app_exited = $app.HasExited; kept_open = [bool]$KeepOpen;
   note = 'Device-wide values include background applications; app shutdown waited before sampling.'
} | ConvertTo-Json | Set-Content "$prefix-release.json"
if ($monitor -and $monitor.ExitCode -ne 0) { throw "Resource monitor failed; retain this attempt and investigate its error log." }
Get-Content "$prefix.out.log" -Tail 6
Get-Content "$prefix.err.log" -Tail 6
exit $code
