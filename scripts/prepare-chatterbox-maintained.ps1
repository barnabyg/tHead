# Isolated maintenance candidate only; does not grant regular-use approval.
# Invoke under prepare.run with a 3-hour process-tree limit.
param([Parameter(Mandatory)][string]$State, [switch]$SourcesOnly)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path $PSScriptRoot -Parent
$lock = Get-Content (Join-Path $root 'chatterbox-maintained-lock.json') -Raw | ConvertFrom-Json
$patch = Join-Path $root $lock.source_patch.file
if ((Get-FileHash -LiteralPath $patch -Algorithm SHA256).Hash.ToLowerInvariant() -ne $lock.source_patch.sha256) {
    throw 'Maintained source patch differs from its recorded hash.'
}
$State = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($State))
if (-not $SourcesOnly) {
    $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($State))
    $memory = Get-CimInstance Win32_OperatingSystem
    if ($drive.AvailableFreeSpace -lt 20GB -or $memory.FreePhysicalMemory * 1KB -lt 8GB) {
        throw 'Evaluation acquisition requires at least 20 GiB free disk and 8 GiB free RAM.'
    }
    Write-Output "Preflight: $($drive.AvailableFreeSpace) bytes free disk; $($memory.FreePhysicalMemory * 1KB) bytes free RAM; maintained CUDA candidate configuration."
}
New-Item -ItemType Directory -Force $State | Out-Null
$leasePath = Join-Path $State 'preparation.lease'
if ((Get-Item -LiteralPath $State -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'Preparation state must be a private directory, not a link.'
}
if ((Test-Path -LiteralPath $leasePath) -and
    ((Get-Item -LiteralPath $leasePath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Preparation lease must not be a link.'
}
try {
    $lease = [IO.File]::Open($leasePath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
} catch [IO.IOException] {
    throw 'Another local voice preparation is active. Wait or cancel it before retrying this state.'
}
try {
$env:UV_CACHE_DIR = Join-Path $State 'uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $State 'python'
$env:UV_LINK_MODE = 'copy'
$env:UV_HTTP_TIMEOUT = '120'
$env:SOURCE_DATE_EPOCH = '0'
# uv's development-Python launcher can export its own home to child processes.
# It must not make the candidate's Python 3.12 build import Python 3.13 libraries.
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

function Assert-StatePath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $boundary = $State.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $full.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Git recovery path escapes its selected state.'
    }
    $current = $State
    foreach ($part in [IO.Path]::GetRelativePath($State, $full).Split([IO.Path]::DirectorySeparatorChar)) {
        $current = Join-Path $current $part
        if ((Test-Path -LiteralPath $current) -and
            ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Git recovery paths must not contain links; preserve this state.'
        }
    }
    return $full
}

$journal = Assert-StatePath (Join-Path $State 'git-acquisition.json')
$allowedLocks = @('config.lock', 'index.lock', 'HEAD.lock', 'shallow.lock', 'FETCH_HEAD.lock', 'packed-refs.lock')

function Git-LockPath([string]$Source, [string]$Name) {
    if ($Source -notin @('source', 'perth') -or $Name -cnotin $allowedLocks) {
        throw 'Unrecognized Git acquisition lock name; preserve this state.'
    }
    return Assert-StatePath (Join-Path $State "$Source/.git/$Name")
}

function Process-IsAlive([int]$Identity, [long]$Started) {
    $owner = Get-Process -Id $Identity -ErrorAction SilentlyContinue
    if (-not $owner) { return $false }
    try { return $owner.StartTime.ToUniversalTime().Ticks -eq $Started }
    catch [System.ComponentModel.Win32Exception] { return $true }
}

function Write-GitJournal($Record) {
    $temporary = Assert-StatePath (Join-Path $State ('git-acquisition-' + [Guid]::NewGuid().ToString('N') + '.tmp'))
    $Record | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $temporary -Encoding utf8
    $null = Assert-StatePath $journal
    Move-Item -LiteralPath $temporary -Destination $journal -Force
}

function Resume-GitAcquisition {
    if (-not (Test-Path -LiteralPath $journal)) { return }
    if ((Get-Item -LiteralPath $journal -Force).Length -gt 16384) {
        throw 'Unrecognized Git acquisition journal; preserve this state.'
    }
    $record = Get-Content -LiteralPath $journal -Raw | ConvertFrom-Json
    foreach ($field in @('owner_pid', 'owner_started', 'child_pid', 'child_started')) {
        if ($record.$field -isnot [int] -and $record.$field -isnot [long]) {
            throw 'Unrecognized Git acquisition process identity; preserve this state.'
        }
    }
    if ($record.version -ne 1 -or $record.source -notin @('source', 'perth') -or
        $record.locks -isnot [Array] -or $record.locks.Count -gt $allowedLocks.Count -or
        $record.finished -isnot [bool] -or
        $record.owner_pid -gt [int]::MaxValue -or $record.child_pid -gt [int]::MaxValue -or
        $record.owner_pid -le 0 -or $record.owner_started -le 0 -or
        $record.child_pid -lt 0 -or $record.child_started -lt 0 -or
        (($record.child_pid -eq 0) -ne ($record.child_started -eq 0))) {
        throw 'Incomplete Git acquisition journal; preserve this state and choose a fresh state.'
    }
    if ((-not $record.finished -and (Process-IsAlive $record.owner_pid $record.owner_started)) -or
        ($record.child_pid -gt 0 -and (Process-IsAlive $record.child_pid $record.child_started))) {
        throw 'The recorded Git acquisition is still active. Wait or cancel it before retrying.'
    }
    if ($record.child_pid -eq 0) {
        # Cancellation can precede recording the child PID. Refuse recovery while
        # any possible unrecorded Git child still exists; no active lock is moved.
        foreach ($possible in (Get-Process -Name 'git*' -ErrorAction SilentlyContinue)) {
            if ($possible.StartTime.ToUniversalTime().Ticks -ge $record.owner_started) {
                throw 'Git acquisition startup was interrupted; wait for active Git processes before retrying.'
            }
        }
    }
    foreach ($name in $record.locks) {
        $path = Git-LockPath $record.source $name
        if (-not (Test-Path -LiteralPath $path)) { continue }
        # The journal records possible names before Git starts, not an identity
        # of a lock actually created by that child. A later manual operation can
        # reuse the same path after both recorded processes exit. Inactivity or
        # an available file handle cannot establish ownership, so preserve it.
        throw "Git lock ownership is ambiguous; preserve the lock and journal and choose a fresh -State directory: $path"
    }
    Remove-Item -LiteralPath $journal
}

Resume-GitAcquisition

function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    $info = [Diagnostics.ProcessStartInfo]::new($Program)
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    $record = $null
    if ($Program -eq 'git') {
        $directory = $Arguments[1]
        $source = Split-Path $directory -Leaf
        $locks = @('config.lock')
        if ($Arguments -contains 'fetch') { $locks = @('shallow.lock', 'FETCH_HEAD.lock', 'packed-refs.lock') }
        elseif ($Arguments -contains 'checkout') { $locks = @('index.lock', 'HEAD.lock') }
        elseif ($Arguments -contains 'read-tree' -or $Arguments -contains 'checkout-index') { $locks = @('index.lock') }
        elseif ($Arguments -contains 'apply') { $locks = @() }
        elseif ($Arguments[0] -eq 'init') { $locks = @('config.lock', 'HEAD.lock') }
        foreach ($name in $allowedLocks) {
            $path = Git-LockPath $source $name
            if (Test-Path -LiteralPath $path) {
                throw "Unrecognized Git lock; preserve it, stop any manual Git operation, then retry or choose a fresh state: $path"
            }
        }
        $record = [ordered]@{
            version = 1; source = $source; locks = @($locks)
            owner_pid = $PID; owner_started = [Diagnostics.Process]::GetCurrentProcess().StartTime.ToUniversalTime().Ticks
            child_pid = 0; child_started = 0; finished = $false
        }
        Write-GitJournal $record
    }
    $process = [Diagnostics.Process]::Start($info)
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    try {
        if ($null -ne $record) {
            $record.child_pid = $process.Id
            $record.child_started = $process.StartTime.ToUniversalTime().Ticks
            Write-GitJournal $record
        }
        if (-not $process.WaitForExit(3600000)) {
            $process.Kill($true)
            $process.WaitForExit()
            throw "$Program exceeded the one-hour operation limit; its process tree was stopped."
        }
        [Console]::Out.Write($stdout.GetAwaiter().GetResult())
        [Console]::Error.Write($stderr.GetAwaiter().GetResult())
        if ($process.ExitCode -ne 0) { throw "$Program failed with exit code $($process.ExitCode)" }
        if ($null -ne $record) { Remove-Item -LiteralPath $journal }
    } finally {
        if (-not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
        if ($null -ne $record -and (Test-Path -LiteralPath $journal)) {
            $record.finished = $true
            Write-GitJournal $record
        }
        $process.Dispose()
    }
}

function Resume-MaterializedCheckout([string]$Destination, [string]$Revision) {
    $metadata = Join-Path $Destination '.git'
    $children = @(Get-ChildItem -LiteralPath $Destination -Force | Where-Object Name -ne '.git')
    if (-not $children -and -not (Test-Path -LiteralPath (Join-Path $metadata 'index'))) { return }

    # Missing index entries are expected after a first checkout was interrupted.
    # Any addition, changed blob/mode or unmerged entry is private staged data.
    & git -C $Destination diff --cached --quiet --diff-filter=ACMRTUXB $Revision --
    if ($LASTEXITCODE -ne 0) { throw 'Interrupted checkout has index changes; preserve this state and choose a fresh -State directory.' }
    $modes = @(& git -C $Destination ls-tree -r '--format=%(objectmode)' $Revision)
    if ($LASTEXITCODE -ne 0 -or @($modes | Where-Object { $_ -cnotin @('100644', '100755') }).Count) {
        throw 'Interrupted checkout has unsupported tree entries; preserve this state and choose a fresh -State directory.'
    }
    $paths = @(& git -C $Destination ls-tree -r --name-only $Revision)
    if ($LASTEXITCODE -ne 0 -or @($paths | Where-Object { $_.StartsWith('"') }).Count) {
        throw 'Interrupted checkout has unsupported tree paths; preserve this state and choose a fresh -State directory.'
    }
    $boundary = $metadata + [IO.Path]::DirectorySeparatorChar
    foreach ($entry in (Get-ChildItem -LiteralPath $Destination -Recurse -Force)) {
        if ($entry.FullName -eq $metadata -or $entry.FullName.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase)) { continue }
        $null = Assert-StatePath $entry.FullName
        $relative = [IO.Path]::GetRelativePath($Destination, $entry.FullName).Replace('\', '/')
        $objects = @(& git --literal-pathspecs -C $Destination ls-tree '--format=%(objectmode) %(objecttype) %(objectname)' $Revision -- $relative)
        if ($LASTEXITCODE -ne 0 -or $objects.Count -ne 1) {
            throw 'Interrupted checkout contains unknown paths; preserve this state and choose a fresh -State directory.'
        }
        if ($entry.PSIsContainer) {
            if ($objects[0] -notmatch '^040000 tree [a-f0-9]{40}$') { throw 'Interrupted checkout path type differs; preserve this state.' }
            continue
        }
        if ($objects[0] -notmatch '^100(?:644|755) blob ([a-f0-9]{40})$') {
            throw 'Interrupted checkout contains an unsupported file type; preserve this state.'
        }
        $expected = $Matches[1]
        $actual = & git -C $Destination hash-object --no-filters -- $relative
        if ($LASTEXITCODE -ne 0 -or $actual -cne $expected) {
            throw 'Interrupted checkout contains changed file bytes; preserve this state and choose a fresh -State directory.'
        }
    }
    $missing = @($paths | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Destination $_) -PathType Leaf) })
    Invoke-Checked git @('-C', $Destination, 'read-tree', $Revision)
    # Populate only absent paths. Without --force, Git also refuses a file that
    # appears after validation; existing matching files are never overwritten.
    foreach ($path in $missing) { Invoke-Checked git @('-C', $Destination, '-c', 'core.autocrlf=false', 'checkout-index', '--', $path) }
}

function Prepare-Source([string]$Name, [string]$Url, [string]$Revision) {
    $destination = Join-Path $State $Name
    if ($Revision -notmatch '^[a-f0-9]{40}$') { throw 'Source revision must be an exact pinned commit.' }
    if (-not (Test-Path -LiteralPath $destination)) {
        Invoke-Checked git @('init', $destination)
    } else {
        $item = Get-Item -LiteralPath $destination -Force
        $metadata = Join-Path $destination '.git'
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            -not $item.PSIsContainer) { throw "Source is not a private directory: $destination" }
        if (-not (Test-Path -LiteralPath $metadata)) {
            if (Get-ChildItem -LiteralPath $destination -Force) {
                throw "Unrecognized source files; preserve them and choose a fresh state: $destination"
            }
            Invoke-Checked git @('init', $destination)
        } else {
            $gitItem = Get-Item -LiteralPath $metadata -Force
            if (-not $gitItem.PSIsContainer -or
                ($gitItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw "Source Git metadata must stay inside its state: $destination"
            }
        }
    }
    $top = & git -C $destination rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -ne 0) {
        if (Get-ChildItem -LiteralPath $destination -Force | Where-Object Name -ne '.git') {
            throw "Incomplete Git initialization has unrecognized files; preserve them: $destination"
        }
        Invoke-Checked git @('init', $destination)
        $top = & git -C $destination rev-parse --show-toplevel
    }
    if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::GetFullPath($top).Equals(
            [IO.Path]::GetFullPath($destination), [StringComparison]::OrdinalIgnoreCase)) {
        throw "Source worktree escapes its selected state: $destination"
    }
    $origin = @(& git -C $destination config --get-all remote.origin.url)
    if ($origin.Count -eq 0) {
        # An interrupted init may not yet have an origin. Only an empty worktree
        # is ours to resume; never adopt an unrelated checkout or private files.
        if (Get-ChildItem -LiteralPath $destination -Force | Where-Object Name -ne '.git') {
            throw "Source origin is missing; preserve existing files: $destination"
        }
        Invoke-Checked git @('-C', $destination, 'remote', 'add', 'origin', $Url)
    } elseif ($origin.Count -ne 1 -or $origin[0] -cne $Url) {
        throw "Source origin differs from its pin; preserve it: $destination"
    }
    $actual = & git -C $destination rev-parse --verify HEAD 2>$null
    if ($LASTEXITCODE -ne 0) {
        # Fetch/checkout may have been cancelled. A normal checkout (never force)
        # protects any local files or index changes created before the interruption.
        Invoke-Checked git @('-C', $destination, '-c', 'http.lowSpeedLimit=1024', '-c', 'http.lowSpeedTime=120', 'fetch', '--depth=1', 'origin', $Revision)
        Resume-MaterializedCheckout $destination $Revision
        Invoke-Checked git @('-C', $destination, '-c', 'core.autocrlf=false', 'checkout', '--detach', $Revision)
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
if ($SourcesOnly) { return }
$python = Join-Path $State 'venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Invoke-Checked pwsh @('-NoProfile', '-File', (Join-Path $root 'scripts/prepare-chatterbox-python.ps1'), '-State', $State)
    Invoke-Checked uv @('venv', '--no-python-downloads', '--python', (Join-Path $State $lock.python_distribution.relative_executable), (Join-Path $State 'venv'))
}
$version = & $python -I -c 'import platform; print(platform.python_version())'
if ($LASTEXITCODE -ne 0 -or $version -ne $lock.python) { throw 'Candidate Python differs from its pin; choose a fresh --state directory.' }
$installedTorch = & $python -I -c 'from importlib.metadata import version; print(version("torch"))' 2>$null
if ($LASTEXITCODE -eq 0 -and $installedTorch -ne $lock.torch) {
    throw 'Existing PyTorch configuration differs; choose a fresh -State directory. No environment was changed.'
}
$environmentCheck = Join-Path $root 'scripts/chatterbox_environment.py'
& $python -I $environmentCheck --state $State
$needsRepair = $LASTEXITCODE -ne 0
if ($needsRepair) {
    Invoke-Checked uv @('pip', 'sync', '--python', $python, '--require-hashes', (Join-Path $root 'docs/runtime/chatterbox/requirements-maintained.lock'))
    Invoke-Checked uv @('pip', 'install', '--python', $python, '--no-deps', '--no-build-isolation', (Join-Path $State 'source'), (Join-Path $State 'perth'))
}
Invoke-Checked uv @('pip', 'check', '--python', $python)
if ($needsRepair) { Invoke-Checked $python @('-I', $environmentCheck, '--state', $State, '--record') }

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
} finally { $lease.Dispose() }
