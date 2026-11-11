[CmdletBinding()]
param(
    [string]$UvExe = 'uv',
    [string]$Python = '3.10.22',
    [switch]$Offline,
    [switch]$RecreateEnvironment
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Upstream = Join-Path $ProjectRoot 'third_party/kotaemon-v0.12.0'
$EnvironmentPath = Join-Path $ProjectRoot '.venv'
$CachePath = Join-Path $ProjectRoot '.cache/uv'
$ReceiptPath = Join-Path $ProjectRoot '.runtime/install-local'
New-Item -ItemType Directory -Force -Path $ReceiptPath | Out-Null
$ExpectedCommit = '9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9'
if ((& git -C $Upstream rev-parse HEAD).Trim() -ne $ExpectedCommit) { throw 'Pinned upstream commit mismatch' }
$NetworkArgs = @()
if ($Offline) { $NetworkArgs += '--offline' }
$PythonDirectory = Join-Path $ProjectRoot '.runtime/python'
if ($Python -match '^\d+\.\d+\.\d+$') {
    $RequestedVersion = $Python
    $Candidates = @(Get-ChildItem -LiteralPath $PythonDirectory -Filter python.exe -Recurse -ErrorAction SilentlyContinue)
    $Python = $null
    foreach ($candidate in $Candidates) {
        $ActualVersion = (& $candidate.FullName -c 'import platform; print(platform.python_version())' | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and $ActualVersion -eq $RequestedVersion) { $Python = $candidate.FullName; break }
    }
    if (-not $Python) {
        & $UvExe python install @NetworkArgs --cache-dir $CachePath --install-dir $PythonDirectory --no-bin --no-registry $RequestedVersion
        if ($LASTEXITCODE -ne 0) { throw 'Project-local standalone Python installation failed' }
        foreach ($candidate in (Get-ChildItem -LiteralPath $PythonDirectory -Filter python.exe -Recurse)) {
            $ActualVersion = (& $candidate.FullName -c 'import platform; print(platform.python_version())' | Out-String).Trim()
            if ($LASTEXITCODE -eq 0 -and $ActualVersion -eq $RequestedVersion) { $Python = $candidate.FullName; break }
        }
    }
}
if (-not $Python -or -not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'No project-local standalone Python was found' }
$ResolvedPython = (Resolve-Path -LiteralPath $Python).Path
if (-not $ResolvedPython.StartsWith([IO.Path]::GetFullPath($PythonDirectory) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Use a standalone interpreter under this project .runtime/python; do not reuse an old virtualenv.'
}
$Python = $ResolvedPython
if ($RecreateEnvironment -or -not (Test-Path -LiteralPath (Join-Path $EnvironmentPath 'Scripts/python.exe'))) {
    # --clear is restricted to the explicitly named, project-local virtual environment.
    $ResolvedEnvironment = [IO.Path]::GetFullPath($EnvironmentPath)
    $ExpectedEnvironment = [IO.Path]::GetFullPath((Join-Path $ProjectRoot '.venv'))
    if ($ResolvedEnvironment -ne $ExpectedEnvironment -or (Split-Path -Parent $ResolvedEnvironment) -ne $ProjectRoot) { throw 'Unsafe environment target' }
    $ClearArgs = @()
    if ($RecreateEnvironment) { $ClearArgs += '--clear' }
    & $UvExe venv @NetworkArgs @ClearArgs --cache-dir $CachePath --python $Python $EnvironmentPath
    if ($LASTEXITCODE -ne 0) { throw 'Isolated environment creation failed' }
}
$PythonExe = Join-Path $EnvironmentPath 'Scripts/python.exe'
$Requirements = Join-Path $ReceiptPath 'runtime-requirements.txt'
# Export the two runtime workspace members. Optional torch/graph/dev extras are
# outside the current local Ollama profile; the upstream lock remains unchanged.
& $UvExe export @NetworkArgs --locked --no-dev --package kotaemon --package ktem --no-emit-workspace --python $PythonExe --project $Upstream --cache-dir $CachePath --no-header --no-annotate --output-file $Requirements | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Locked runtime export failed' }
& $UvExe pip install @NetworkArgs --require-hashes --python $PythonExe --cache-dir $CachePath -r $Requirements
if ($LASTEXITCODE -ne 0) { throw 'Locked dependency installation failed' }
& $UvExe pip install @NetworkArgs --no-deps --python $PythonExe --cache-dir $CachePath -e (Join-Path $Upstream 'libs/kotaemon') -e (Join-Path $Upstream 'libs/ktem')
if ($LASTEXITCODE -ne 0) { throw 'Pinned workspace installation failed' }
Write-Host 'Local Ollama runtime installed from the unmodified upstream lock.'
