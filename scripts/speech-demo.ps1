#Requires -Version 7.0
param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Force .runtime | Out-Null
$demoArgs = @('--speech')
if ($NoBrowser) { $demoArgs += '--no-browser' }
& python scripts/stream_demo.py @demoArgs 2>&1 | Tee-Object -FilePath .runtime/speech-demo.log
exit $LASTEXITCODE
