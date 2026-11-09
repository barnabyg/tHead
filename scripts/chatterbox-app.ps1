#Requires -Version 7.0
param([switch]$NoBrowser, [switch]$SkipPreparation, [switch]$TestBackend,
      [string]$Avatar = '', [int]$Port = 8767,
      [ValidateSet('cpu','cuda','maintained')][string]$Configuration = 'cpu',
      [string]$State = '',
      [string]$Output = '.runtime/chatterbox-integration')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not $State) {
    $State = @{ cpu = '.runtime/chatterbox-eval'; cuda = '.runtime/chatterbox-eval-gpu'; maintained = '.runtime/chatterbox-maintained' }[$Configuration]
}
$State = [IO.Path]::GetFullPath($State)
$Output = [IO.Path]::GetFullPath($Output)
if (-not $TestBackend -and -not $SkipPreparation) {
    if ($Configuration -eq 'maintained') {
        & uv run --locked python -c "import sys; sys.path.insert(0,'scripts'); from prepare import run; run(['pwsh','-NoProfile','-File','scripts/prepare-chatterbox-maintained.ps1','-State',sys.argv[1]],10800)" $State
    } else {
        & uv run --locked python -c "import sys; sys.path.insert(0,'scripts'); from prepare import run; run(['pwsh','-NoProfile','-File','scripts/prepare-chatterbox.ps1','-State',sys.argv[1],'-Configuration',sys.argv[2]],10800)" $State $Configuration
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$runtimePython = if ($TestBackend) { Join-Path (Get-Location) '.venv/Scripts/python.exe' } else { Join-Path (Get-Location) '.runtime/venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $runtimePython)) {
    throw 'Prepare the normal tHead application first, following README.md; the experiment does not modify its environment.'
}
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
$launchArgs = @('scripts/chatterbox_app.py', '--state', $State, '--output', $Output, '--port', "$Port", '--configuration', $Configuration)
if ($Avatar) { $launchArgs += @('--avatar', $Avatar) }
if ($TestBackend) { $launchArgs += '--test-backend' }
if (-not $NoBrowser) { $launchArgs += '--open-browser' }
& uv run --locked python -c "import os,sys; sys.path.insert(0,'scripts'); from prepare import run; os.environ.pop('PYTHONHOME',None); os.environ.pop('PYTHONPATH',None); run(sys.argv[1:],7500)" $runtimePython @launchArgs
exit $LASTEXITCODE
