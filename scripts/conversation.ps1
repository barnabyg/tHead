#Requires -Version 7.0
param([switch]$NoBrowser, [switch]$Diagnostics, [switch]$FixtureProvider, [switch]$TestBackend)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if ($TestBackend) {
    # No downloads, credentials, GPU or paid requests. Media is deliberately not playable.
    & python scripts/conversation.py --test-backend --diagnostics
    exit $LASTEXITCODE
}
$launchArgs = @('--conversation')
if ($NoBrowser) { $launchArgs += '--no-browser' }
if ($Diagnostics) { $launchArgs += '--diagnostics' }
if ($FixtureProvider) { $launchArgs += '--fixture-provider' }
& python scripts/stream_demo.py @launchArgs
exit $LASTEXITCODE
