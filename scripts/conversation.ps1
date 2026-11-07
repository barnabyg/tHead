#Requires -Version 7.0
param([switch]$NoBrowser, [switch]$Diagnostics, [switch]$FixtureProvider, [switch]$TestBackend,
      [switch]$InitializeBudget, [string]$Budget, [string]$Pair = $env:THEAD_PAIR,
      [int]$Port = 8765)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if ($TestBackend) {
    # No downloads, credentials, GPU or paid requests. Media is deliberately not playable.
    $fixtureArgs = @('--test-backend', '--diagnostics', '--port', "$Port")
    if ($Pair) { $fixtureArgs += @('--pair', $Pair) }
    if ($Budget) { $fixtureArgs += @('--budget', $Budget) }
    & python scripts/conversation.py @fixtureArgs
    exit $LASTEXITCODE
}
$launchArgs = @('--conversation', '--port', "$Port")
if ($Pair) { $launchArgs += @('--pair', $Pair) }
if ($NoBrowser) { $launchArgs += '--no-browser' }
if ($Diagnostics) { $launchArgs += '--diagnostics' }
if ($FixtureProvider) { $launchArgs += '--fixture-provider' }
if ($InitializeBudget) { $launchArgs += '--initialize-budget' }
if ($Budget) { $launchArgs += @('--budget', $Budget) }
& python scripts/stream_demo.py @launchArgs
exit $LASTEXITCODE
