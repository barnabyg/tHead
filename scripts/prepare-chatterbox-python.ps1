#Requires -Version 7.0
# Explicit, hash-verified Python acquisition for the isolated maintained profile.
param([Parameter(Mandatory)][string]$State, [switch]$ExtractOnly)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path $PSScriptRoot -Parent
$lock = Get-Content (Join-Path $root 'chatterbox-maintained-lock.json') -Raw | ConvertFrom-Json
$pin = $lock.python_distribution
$State = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($State))
New-Item -ItemType Directory -Force $State | Out-Null
$archive = Join-Path $State $pin.archive
if (-not (Test-Path -LiteralPath $archive)) {
    $partial = "$archive.partial"
    Write-Output "Acquiring CPython $($lock.python), Astral build $($pin.build): $($pin.bytes) bytes."
    Invoke-WebRequest -Uri $pin.url -OutFile $partial -TimeoutSec 1800
    if ((Get-Item -LiteralPath $partial).Length -ne $pin.bytes -or
        (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pin.sha256) {
        throw 'Python archive failed its pinned size/hash; preserve it and choose a fresh state.'
    }
    Move-Item -LiteralPath $partial -Destination $archive
}
if ((Get-Item -LiteralPath $archive).Length -ne $pin.bytes -or
    (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pin.sha256) {
    throw 'Python archive failed its pinned size/hash; preserve it and choose a fresh state.'
}

function Invoke-Bounded([string]$Program, [string[]]$Arguments) {
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
        if (-not $process.WaitForExit(300000)) {
            $process.Kill($true)
            $process.WaitForExit()
            throw "$Program exceeded the five-minute limit; its process tree was stopped."
        }
        [Console]::Error.Write($stderr.GetAwaiter().GetResult())
        if ($process.ExitCode -ne 0) { throw "$Program failed with exit code $($process.ExitCode)" }
        return $stdout.GetAwaiter().GetResult()
    } finally { $process.Dispose() }
}

$destination = Join-Path $State 'python-runtime'
$python = Join-Path $State $pin.relative_executable

function Remove-OwnedStage([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $parent = [IO.Path]::GetFullPath((Split-Path $full -Parent))
    $name = Split-Path $full -Leaf
    if ($parent -cne $State -or $name -notmatch '^python-runtime\.staging-[a-f0-9]{32}$') {
        throw 'Python cleanup destination escapes its selected state.'
    }
    if (-not (Test-Path -LiteralPath $full)) { return }
    $item = Get-Item -LiteralPath $full -Force
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Python staging must be a private directory; preserve it and choose a fresh state.'
    }
    $marker = Join-Path $full '.chatterbox-acquisition'
    # Older/unrecognized directories may contain user data. Never remove them.
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { return }
    $markerItem = Get-Item -LiteralPath $marker -Force
    if (($markerItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        $markerItem.Length -gt 128 -or (Get-Content -LiteralPath $marker -Raw).Trim() -cne $pin.sha256) {
        throw 'Unrecognized Python staging marker; preserve it and choose a fresh state.'
    }
    $links = Get-ChildItem -LiteralPath $full -Recurse -Force |
        Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }
    if ($links) { throw 'Python staging contains links; preserve it and choose a fresh state.' }
    # Exact direct child of State, our marker, and no links: native scoped cleanup only.
    Remove-Item -LiteralPath $full -Recurse -Force
}

if (-not (Test-Path -LiteralPath $python)) {
    if (Test-Path -LiteralPath $destination) {
        throw 'Python extraction is incomplete; preserve it and choose a fresh state.'
    }
    # The immutable archive is verified above before inspecting or replacing work.
    # Preserve the old unmarked staging name; new task-owned stages can be reaped.
    foreach ($abandoned in (Get-ChildItem -LiteralPath $State -Filter 'python-runtime.staging-*' -Force | Select-Object -First 32)) {
        if ($abandoned.Name -match '^python-runtime\.staging-[a-f0-9]{32}$') {
            Remove-OwnedStage $abandoned.FullName
        }
    }
    $staging = Join-Path $State ('python-runtime.staging-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory $staging | Out-Null
    Set-Content -LiteralPath (Join-Path $staging '.chatterbox-acquisition') -Value $pin.sha256 -Encoding ascii
    try {
        Invoke-Bounded tar @('-xzf', $archive, '-C', $staging) | Out-Null
        $relativePython = [IO.Path]::GetRelativePath($destination, $python)
        if (-not (Test-Path -LiteralPath (Join-Path $staging $relativePython) -PathType Leaf)) {
            throw 'Pinned Python archive is missing its expected executable.'
        }
        # Resolve/check both exact paths before moving within the explicitly selected State.
        foreach ($path in @($staging, $destination)) {
            if ([IO.Path]::GetFullPath((Split-Path $path -Parent)) -cne $State) {
                throw 'Python extraction destination escapes its selected state.'
            }
        }
        Move-Item -LiteralPath $staging -Destination $destination
    } finally {
        Remove-OwnedStage $staging
    }
}
if ($ExtractOnly) { return }
$probe = 'import json,platform,ssl,sys,pyexpat; expected=sys.argv[1]; actual=platform.python_version(); assert actual==expected, f"Python differs: {actual}, expected {expected}"; assert sys.platform=="win32" and sys.maxsize>2**32; print(json.dumps({"python":actual,"openssl":ssl.OPENSSL_VERSION,"expat":pyexpat.EXPAT_VERSION,"platform":platform.platform(),"architecture":platform.machine()}))'
$result = Invoke-Bounded $python @('-I', '-W', 'error', '-c', $probe, $lock.python)
$result.Trim() | Set-Content -LiteralPath (Join-Path $State 'python-runtime-result.json') -Encoding utf8
Write-Output "Verified CPython $($lock.python), Astral build $($pin.build); no host installation or PATH change."
