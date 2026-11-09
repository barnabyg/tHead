#Requires -Version 7.0
# Explicit, hash-verified Python acquisition for the isolated maintained profile.
param([Parameter(Mandatory)][string]$State)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path $PSScriptRoot -Parent
$lock = Get-Content (Join-Path $root 'chatterbox-maintained-lock.json') -Raw | ConvertFrom-Json
$pin = $lock.python_distribution
$State = [IO.Path]::GetFullPath($State)
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
if (-not (Test-Path -LiteralPath $python)) {
    if (Test-Path -LiteralPath $destination) {
        throw 'Python extraction is incomplete; preserve it and choose a fresh state.'
    }
    $staging = Join-Path $State 'python-runtime.staging'
    if (Test-Path -LiteralPath $staging) {
        throw 'Python extraction was interrupted; preserve it and choose a fresh state.'
    }
    New-Item -ItemType Directory $staging | Out-Null
    Invoke-Bounded tar @('-xzf', $archive, '-C', $staging) | Out-Null
    # Directory moves must remain inside the explicitly selected task state.
    $boundary = $State.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    foreach ($path in @($staging, $destination)) {
        if (-not [IO.Path]::GetFullPath($path).StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Python extraction destination escapes its selected state.'
        }
    }
    Move-Item -LiteralPath $staging -Destination $destination
}
$probe = 'import json,platform,ssl,sys,pyexpat; expected=sys.argv[1]; actual=platform.python_version(); assert actual==expected, f"Python differs: {actual}, expected {expected}"; assert sys.platform=="win32" and sys.maxsize>2**32; print(json.dumps({"python":actual,"openssl":ssl.OPENSSL_VERSION,"expat":pyexpat.EXPAT_VERSION,"platform":platform.platform(),"architecture":platform.machine()}))'
$result = Invoke-Bounded $python @('-I', '-W', 'error', '-c', $probe, $lock.python)
$result.Trim() | Set-Content -LiteralPath (Join-Path $State 'python-runtime-result.json') -Encoding utf8
Write-Output "Verified CPython $($lock.python), Astral build $($pin.build); no host installation or PATH change."
