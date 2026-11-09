#Requires -Version 7.0
param([string]$UserData = (Join-Path ([IO.Path]::GetTempPath()) 'tHead-voice-manual'),
      [ValidateRange(1024,65535)][int]$Port = 8769)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& uv run --locked python scripts/prepare_voice_media.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$UserData = [IO.Path]::GetFullPath($UserData)
$inputs = Join-Path $UserData 'demo-inputs'
New-Item -ItemType Directory -Force $inputs | Out-Null
foreach ($name in @('portrait.jpg', 'hopper.jpg')) {
    Copy-Item -LiteralPath 'tests/fixtures/portrait.jpg' -Destination (Join-Path $inputs $name)
}
Write-Output "Open http://127.0.0.1:$Port. This is a no-cost protocol fixture, not cloned speech."
Write-Output 'Licensed reference: docs/runtime/chatterbox/reference-1089-10s.wav (CC BY 4.0; see ATTRIBUTION.md).'
$launch = @('scripts/conversation.py', '--test-backend', '--diagnostics', '--port', "$Port",
            '--inputs', $inputs, '--output', (Join-Path $UserData 'app-output'), '--user-data', $UserData)
& uv run --locked python -c "import sys; sys.path.insert(0,'scripts'); from prepare import run; run([sys.executable, *sys.argv[1:]],7500)" @launch
exit $LASTEXITCODE
