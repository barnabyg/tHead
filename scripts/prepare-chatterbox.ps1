# Invoked only by chatterbox_eval.py --prepare, under its process-tree timeout.
param([Parameter(Mandatory)][string]$State)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path $PSScriptRoot -Parent
$lock = Get-Content (Join-Path $root 'chatterbox-lock.json') -Raw | ConvertFrom-Json
$State = [IO.Path]::GetFullPath($State)
$drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($State))
$memory = Get-CimInstance Win32_OperatingSystem
if ($drive.AvailableFreeSpace -lt 20GB -or $memory.FreePhysicalMemory * 1KB -lt 8GB) {
    throw 'Evaluation acquisition requires at least 20 GiB free disk and 8 GiB free RAM.'
}
Write-Output "Preflight: $($drive.AvailableFreeSpace) bytes free disk; $($memory.FreePhysicalMemory * 1KB) bytes free RAM; CPU configuration (no VRAM allocation)."
New-Item -ItemType Directory -Force $State | Out-Null
$env:UV_CACHE_DIR = Join-Path $State 'uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $State 'python'
$env:UV_LINK_MODE = 'copy'
$env:UV_HTTP_TIMEOUT = '120'
$env:SOURCE_DATE_EPOCH = '0'
# uv's development-Python launcher can export its own home to child processes.
# It must not make the candidate's Python 3.12 build import Python 3.13 libraries.
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}

function Prepare-Source([string]$Name, [string]$Url, [string]$Revision) {
    $destination = Join-Path $State $Name
    if (-not (Test-Path -LiteralPath $destination)) {
        Invoke-Checked git @('init', $destination)
        Invoke-Checked git @('-C', $destination, 'remote', 'add', 'origin', $Url)
        Invoke-Checked git @('-C', $destination, '-c', 'http.lowSpeedLimit=1024', '-c', 'http.lowSpeedTime=120', 'fetch', '--depth=1', 'origin', $Revision)
        Invoke-Checked git @('-C', $destination, 'checkout', '--detach', 'FETCH_HEAD')
    }
    $actual = & git -C $destination rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $actual -ne $Revision) { throw "Source revision differs: $destination. Preserve it and choose a fresh --state directory." }
    $changes = & git -C $destination status --porcelain
    if ($LASTEXITCODE -ne 0 -or $changes) { throw "Source has local changes: $destination. Preserve it and choose a fresh --state directory." }
}

Prepare-Source 'source' $lock.upstream_url $lock.upstream_revision
Prepare-Source 'perth' $lock.perth_url $lock.perth_revision
$python = Join-Path $State 'venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Invoke-Checked uv @('venv', '--python', $lock.python, (Join-Path $State 'venv'))
}
$version = & $python -I -c 'import platform; print(platform.python_version())'
if ($LASTEXITCODE -ne 0 -or $version -ne $lock.python) { throw 'Candidate Python differs from its pin; choose a fresh --state directory.' }
Invoke-Checked uv @('pip', 'sync', '--python', $python, '--require-hashes', (Join-Path $root 'docs/runtime/chatterbox/requirements.lock'))
Invoke-Checked uv @('pip', 'install', '--python', $python, '--no-deps', '--no-build-isolation', (Join-Path $State 'source'), (Join-Path $State 'perth'))
Invoke-Checked uv @('pip', 'check', '--python', $python)

$model = Join-Path $State 'model'
New-Item -ItemType Directory -Force $model | Out-Null
foreach ($asset in $lock.model.files) {
    $path = Join-Path $model $asset.name
    if (Test-Path -LiteralPath $path) {
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.sha256) {
            throw "Existing model asset differs: $path. Preserve it and choose a fresh --state directory."
        }
        continue
    }
    $url = "https://huggingface.co/$($lock.model.repository)/resolve/$($lock.model.revision)/$($asset.name)"
    $partial = "$path.partial"
    Invoke-WebRequest -Uri $url -OutFile $partial -TimeoutSec 1800
    if ((Get-Item -LiteralPath $partial).Length -ne $asset.bytes -or (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.sha256) {
        throw "Downloaded model asset failed size/hash validation: $partial"
    }
    Move-Item -LiteralPath $partial -Destination $path
}
