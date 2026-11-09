# Isolated maintenance candidate only; does not grant regular-use approval.
# Invoke under prepare.run with a 3-hour process-tree limit.
param([Parameter(Mandatory)][string]$State)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path $PSScriptRoot -Parent
$lock = Get-Content (Join-Path $root 'chatterbox-maintained-lock.json') -Raw | ConvertFrom-Json
$patch = Join-Path $root $lock.source_patch.file
if ((Get-FileHash -LiteralPath $patch -Algorithm SHA256).Hash.ToLowerInvariant() -ne $lock.source_patch.sha256) {
    throw 'Maintained source patch differs from its recorded hash.'
}
$State = [IO.Path]::GetFullPath($State)
$drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($State))
$memory = Get-CimInstance Win32_OperatingSystem
if ($drive.AvailableFreeSpace -lt 20GB -or $memory.FreePhysicalMemory * 1KB -lt 8GB) {
    throw 'Evaluation acquisition requires at least 20 GiB free disk and 8 GiB free RAM.'
}
Write-Output "Preflight: $($drive.AvailableFreeSpace) bytes free disk; $($memory.FreePhysicalMemory * 1KB) bytes free RAM; maintained CUDA candidate configuration."
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
    $info = [Diagnostics.ProcessStartInfo]::new($Program)
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::Start($info)
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    try {
        if (-not $process.WaitForExit(3600000)) {
            $process.Kill($true)
            $process.WaitForExit()
            throw "$Program exceeded the one-hour operation limit; its process tree was stopped."
        }
        [Console]::Out.Write($stdout.GetAwaiter().GetResult())
        [Console]::Error.Write($stderr.GetAwaiter().GetResult())
        if ($process.ExitCode -ne 0) { throw "$Program failed with exit code $($process.ExitCode)" }
    } finally { $process.Dispose() }
}

function Prepare-Source([string]$Name, [string]$Url, [string]$Revision) {
    $destination = Join-Path $State $Name
    if (-not (Test-Path -LiteralPath $destination)) {
        Invoke-Checked git @('init', $destination)
        Invoke-Checked git @('-C', $destination, 'remote', 'add', 'origin', $Url)
        Invoke-Checked git @('-C', $destination, '-c', 'http.lowSpeedLimit=1024', '-c', 'http.lowSpeedTime=120', 'fetch', '--depth=1', 'origin', $Revision)
        Invoke-Checked git @('-C', $destination, '-c', 'core.autocrlf=false', 'checkout', '--detach', 'FETCH_HEAD')
    }
    Invoke-Checked git @('-C', $destination, 'config', 'core.autocrlf', 'false')
    $actual = & git -C $destination rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $actual -ne $Revision) { throw "Source revision differs: $destination. Preserve it and choose a fresh --state directory." }
    $changes = @(& git -C $destination status --porcelain)
    if ($LASTEXITCODE -ne 0) { throw "Cannot inspect source: $destination" }
    if ($Name -eq 'source') {
        if (-not $changes) { Invoke-Checked git @('-C', $destination, 'apply', '--whitespace=error', $patch) }
        $changes = @(& git -C $destination status --porcelain)
        if ($LASTEXITCODE -ne 0) { throw "Cannot inspect patched source: $destination" }
        $expected = @($lock.source_patch.patched_files.file | Sort-Object)
        $actualNames = @($changes | ForEach-Object { $_.Substring(3).Replace('\', '/') } | Sort-Object)
        if (Compare-Object $expected $actualNames) { throw 'Patched source has unexpected changes; preserve it and choose a fresh state.' }
        foreach ($property in $lock.source_patch.patched_files) {
            $path = Join-Path $destination $property.file
            if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $property.sha256) {
                throw "Patched source hash differs: $($property.file). Preserve it and choose a fresh state."
            }
        }
    } elseif ($changes) { throw "Source has local changes: $destination. Preserve it and choose a fresh --state directory." }
}

Prepare-Source 'source' $lock.upstream_url $lock.upstream_revision
Prepare-Source 'perth' $lock.perth_url $lock.perth_revision
$python = Join-Path $State 'venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Invoke-Checked pwsh @('-NoProfile', '-File', (Join-Path $root 'scripts/prepare-chatterbox-python.ps1'), '-State', $State)
    Invoke-Checked uv @('venv', '--no-python-downloads', '--python', (Join-Path $State $lock.python_distribution.relative_executable), (Join-Path $State 'venv'))
}
$version = & $python -I -c 'import platform; print(platform.python_version())'
if ($LASTEXITCODE -ne 0 -or $version -ne $lock.python) { throw 'Candidate Python differs from its pin; choose a fresh --state directory.' }
$installedTorch = & $python -I -c 'import importlib.util; import torch; print(torch.__version__)' 2>$null
if ($LASTEXITCODE -eq 0 -and $installedTorch -ne $lock.torch) {
    throw 'Existing PyTorch configuration differs; choose a fresh -State directory. No environment was changed.'
}
Invoke-Checked uv @('pip', 'sync', '--python', $python, '--require-hashes', (Join-Path $root 'docs/runtime/chatterbox/requirements-maintained.lock'))
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
    Write-Output "Acquiring $($asset.name): $($asset.bytes) bytes from the pinned model revision."
    $url = "https://huggingface.co/$($lock.model.repository)/resolve/$($lock.model.revision)/$($asset.name)"
    $partial = "$path.partial"
    Invoke-WebRequest -Uri $url -OutFile $partial -TimeoutSec 1800
    if ((Get-Item -LiteralPath $partial).Length -ne $asset.bytes -or (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.sha256) {
        throw "Downloaded model asset failed size/hash validation: $partial"
    }
    Move-Item -LiteralPath $partial -Destination $path
    Write-Output "Verified $($asset.name)."
}
