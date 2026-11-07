#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Force .runtime | Out-Null
& python scripts/prepare.py 2>&1 | Tee-Object -FilePath .runtime/setup.log
exit $LASTEXITCODE
