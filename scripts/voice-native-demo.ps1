#Requires -Version 7.0
param([string]$UserData = (Join-Path ([IO.Path]::GetTempPath()) 'tHead-voice-native'),
      [string]$ChatterboxState = '.runtime/chatterbox-maintained',
      [ValidateRange(1024,65535)][int]$Port = 8771, [switch]$NoBrowser, [switch]$Offline)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$UserData = [IO.Path]::GetFullPath($UserData)
$ChatterboxState = [IO.Path]::GetFullPath($ChatterboxState)
# Explicit opt-in only: acquire this isolated pinned runtime, never mutate FlashHead.
if (-not $Offline) {
    & uv run --locked python -c "import sys; sys.path.insert(0,'scripts'); from prepare import run; run(['pwsh','-NoProfile','-File','scripts/prepare-chatterbox-maintained.ps1','-State',sys.argv[1]],10800)" $ChatterboxState
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    $env:HF_HUB_OFFLINE = '1'
    $env:TRANSFORMERS_OFFLINE = '1'
    $env:HF_HUB_DISABLE_TELEMETRY = '1'
}
Write-Output 'Native release candidate: real local speech/portrait with free fixture provider text.'
$launch = @('-Diagnostics', '-FixtureProvider', '-CandidateChatterbox', '-InitializeBudget',
            '-UserData', $UserData, '-ChatterboxState', $ChatterboxState, '-Port', "$Port")
if ($NoBrowser) { $launch += '-NoBrowser' }
if ($Offline) { $launch += '-SkipPreparation' }
& pwsh -NoProfile -File scripts/conversation.ps1 @launch
exit $LASTEXITCODE
