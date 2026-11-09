#Requires -Version 7.0
param([switch]$NoBrowser, [switch]$Diagnostics, [switch]$FixtureProvider, [switch]$TestBackend,
      [switch]$InitializeBudget, [string]$Budget, [Alias("Pair")][string]$Avatar = $(if ($env:THEAD_AVATAR) { $env:THEAD_AVATAR } else { $env:THEAD_PAIR }),
      [string]$UserData = $env:THEAD_USER_DATA, [int]$Port = 8765,
      [switch]$CandidateChatterbox, [string]$ChatterboxState = '', [switch]$SkipPreparation)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if ($TestBackend) {
    # No downloads, credentials, GPU or paid requests. Media is deliberately not playable.
    $fixtureArgs = @('--test-backend', '--diagnostics', '--port', "$Port")
    if ($Avatar) { $fixtureArgs += @('--avatar', $Avatar) }
    if ($UserData) { $fixtureArgs += @('--user-data', $UserData) }
    if ($Budget) { $fixtureArgs += @('--budget', $Budget) }
    & python scripts/conversation.py @fixtureArgs
    exit $LASTEXITCODE
}
$launchArgs = @('--conversation', '--port', "$Port")
if ($Avatar) { $launchArgs += @('--avatar', $Avatar) }
if ($NoBrowser) { $launchArgs += '--no-browser' }
if ($Diagnostics) { $launchArgs += '--diagnostics' }
if ($FixtureProvider) { $launchArgs += '--fixture-provider' }
if ($InitializeBudget) { $launchArgs += '--initialize-budget' }
if ($UserData) { $launchArgs += @('--user-data', $UserData) }
if ($Budget) { $launchArgs += @('--budget', $Budget) }
if ($CandidateChatterbox) { $launchArgs += '--candidate-chatterbox' }
if ($ChatterboxState) { $launchArgs += @('--chatterbox-state', $ChatterboxState) }
if ($SkipPreparation) { $launchArgs += '--skip-preparation' }
& python scripts/stream_demo.py @launchArgs
exit $LASTEXITCODE
