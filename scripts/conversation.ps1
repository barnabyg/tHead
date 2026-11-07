#Requires -Version 7.0
param([switch]$NoBrowser, [switch]$Diagnostics, [switch]$FixtureProvider, [switch]$TestBackend,
      [switch]$InitializeBudget, [string]$Budget)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if ($TestBackend) {
    # No downloads, credentials, GPU or paid requests. Media is deliberately not playable.
    $fixtureArgs = @('--test-backend', '--diagnostics')
    if ($Budget) { $fixtureArgs += @('--budget', $Budget) }
    & python scripts/conversation.py @fixtureArgs
    exit $LASTEXITCODE
}
$launchArgs = @('--conversation')
if ($NoBrowser) { $launchArgs += '--no-browser' }
if ($Diagnostics) { $launchArgs += '--diagnostics' }
if ($FixtureProvider) { $launchArgs += '--fixture-provider' }
if ($InitializeBudget) { $launchArgs += '--initialize-budget' }
if ($Budget) { $launchArgs += @('--budget', $Budget) }
& python scripts/stream_demo.py @launchArgs
exit $LASTEXITCODE
