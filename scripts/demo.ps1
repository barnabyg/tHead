#Requires -Version 7.0
param([switch]$NoPlay)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Force .runtime | Out-Null
$demoArgs = @()
if ($NoPlay) { $demoArgs += '--no-play' }
& python scripts/demo.py @demoArgs 2>&1 | Tee-Object -FilePath .runtime/demo.log
exit $LASTEXITCODE
