[CmdletBinding()]
param(
    [switch]$InstallDependencies,
    [switch]$CheckOnly,
    [string]$UpstreamPath = ''
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($UpstreamPath)) {
    $UpstreamPath = Join-Path $ProjectRoot 'third_party\kotaemon-v0.12.0'
}
$ExpectedCommit = '9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9'
$PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$LauncherPath = Join-Path $ProjectRoot 'scripts\run_kotaemon_local.py'
$RuntimeCheckPath = Join-Path $ProjectRoot 'scripts\check_kotaemon_runtime.py'
$ReportsPath = Join-Path $ProjectRoot 'reports'
New-Item -ItemType Directory -Force -Path $ReportsPath | Out-Null
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogPath = Join-Path $ReportsPath "kotaemon-baseline-$Stamp.log"
Start-Transcript -LiteralPath $LogPath -Force | Out-Null

try {
    Write-Host "Project: $ProjectRoot"
    Write-Host "Upstream: $UpstreamPath"
    Write-Host "Expected commit: $ExpectedCommit"
    Write-Host "Project Python: $PythonExe"
    Write-Host "Log: $LogPath"

    if (-not (Test-Path -LiteralPath $UpstreamPath -PathType Container)) {
        throw 'Pinned source directory is missing. Follow docs/UPSTREAM_VERSION.md to obtain v0.12.0. App was not started.'
    }

    $Origin = (& git -C $UpstreamPath remote get-url origin 2>&1 | Out-String).Trim()
    $AllowedOrigins = @('https://github.com/Cinnamon/kotaemon', 'https://github.com/Cinnamon/kotaemon.git', 'git@github.com:Cinnamon/kotaemon.git')
    if ($LASTEXITCODE -ne 0 -or $AllowedOrigins -notcontains $Origin) {
        throw "Origin does not match the official repository: $Origin"
    }

    $Head = (& git -C $UpstreamPath rev-parse HEAD 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $Head -ne $ExpectedCommit) {
        throw "Upstream HEAD does not match the pinned commit. Expected=$ExpectedCommit Actual=$Head"
    }
    Write-Host "Pinned upstream verified: $Head"

    if ($InstallDependencies) {
        $UvCommand = Get-Command uv -ErrorAction SilentlyContinue
        $UvExe = if ($UvCommand) { $UvCommand.Source } else { Join-Path $ProjectRoot '.runtime\uv\uv.exe' }
        if (-not (Test-Path -LiteralPath $UvExe -PathType Leaf)) {
            throw 'uv is not on PATH. Install uv, then follow docs/LOCAL_SETUP.md to sync the pinned uv.lock.'
        }
        $PreviousProjectEnvironment = $env:UV_PROJECT_ENVIRONMENT
        try {
            $env:UV_PROJECT_ENVIRONMENT = Join-Path $ProjectRoot '.venv'
            & (Join-Path $ProjectRoot 'scripts/install_local_runtime.ps1') -UvExe $UvExe
            if ($LASTEXITCODE -ne 0) { throw "Locked local runtime installation failed with exit code $LASTEXITCODE" }
        }
        finally {
            if ($null -eq $PreviousProjectEnvironment) {
                Remove-Item Env:\UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue
            }
            else {
                $env:UV_PROJECT_ENVIRONMENT = $PreviousProjectEnvironment
            }
        }
    }

    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
        throw 'Project .venv Python is missing. Follow docs/LOCAL_SETUP.md to create the locked Python 3.10 environment.'
    }
    $PythonVersionText = (& $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not read project Python version: $PythonVersionText" }
    $VersionParts = $PythonVersionText.Split('.') | ForEach-Object { [int]$_ }
    if ($VersionParts.Count -lt 2 -or $VersionParts[0] -lt 3 -or ($VersionParts[0] -eq 3 -and $VersionParts[1] -lt 10)) {
        throw "Python 3.10+ is required. Current project environment: $PythonVersionText"
    }
    Write-Host "Python: $PythonVersionText ($PythonExe)"

    if (-not (Test-Path -LiteralPath (Join-Path $UpstreamPath 'app.py') -PathType Leaf)) {
        throw "Could not find app.py in pinned checkout: $UpstreamPath"
    }
    if (-not (Test-Path -LiteralPath $LauncherPath -PathType Leaf)) {
        throw "Local compatibility launcher is missing: $LauncherPath"
    }

    $AssetScript = Join-Path $ProjectRoot 'scripts/prepare_kotaemon_assets.py'
    if ($InstallDependencies) { & $PythonExe $AssetScript }
    else { & $PythonExe $AssetScript --verify-only }
    if ($LASTEXITCODE -ne 0) { throw 'Required local tokenizer resources are missing or invalid.' }
    & $PythonExe $RuntimeCheckPath
    if ($LASTEXITCODE -ne 0) {
        throw 'Pinned runtime imports are missing. Run this script with -InstallDependencies when uv and package sources are available.'
    }

    if ($CheckOnly) {
        Write-Host 'CHECK ONLY: PASS. Pinned source, project Python, and runtime imports are available; app was not started.'
        return
    }

    Write-Host 'Starting the pinned app with scripts/run_kotaemon_local.py.'
    Write-Host 'The launcher uses the upstream SimpleFileDocumentStore compatibility overlay for this Windows setup.'
    Write-Host 'Submit the three fixed Chinese questions and record raw answers/citations in docs/KOTAEMON_BASELINE.md.'
    Write-Host 'Press Ctrl+C in this terminal to stop the app.'

    Push-Location $ProjectRoot
    try {
        & $PythonExe $LauncherPath
        if ($LASTEXITCODE -ne 0) {
            throw "Kotaemon local launcher exited with code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}
catch {
    Write-Host ("ERROR: " + $_.Exception.Message)
    Write-Host 'TASK 2 RESULT: NOT PASSED. Keep the exact error in this log.'
    throw
}
finally {
    Stop-Transcript | Out-Null
}
