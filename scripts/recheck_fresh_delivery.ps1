[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$UiCapture,
    [string]$AppUrl = 'http://127.0.0.1:7861/',
    [string]$OriginalRoot = '',
    [string]$OriginalSnapshot = ''
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $PythonExe)) { throw 'Install the independent local runtime first.' }
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:NO_PROXY = '127.0.0.1,localhost,::1'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$OutputDirectory = Join-Path $ProjectRoot ".runtime/fresh-recheck-$Stamp"
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$Regression = Join-Path $OutputDirectory 'development-regression.json'
Push-Location $ProjectRoot
try {
    & $PythonExe scripts/prepare_kotaemon_assets.py --verify-only
    if ($LASTEXITCODE -ne 0) { throw 'Runtime assets failed.' }
    & $PythonExe scripts/check_kotaemon_runtime.py
    if ($LASTEXITCODE -ne 0) { throw 'Runtime imports failed.' }
    & $PythonExe scripts/verify_task3_isolated.py --report reports/acceptance/task3_fresh_environment.json
    if ($LASTEXITCODE -ne 0) { throw 'Original task 3 acceptance failed.' }
    & $PythonExe scripts/run_answer_quality_regression.py --output $Regression
    if ($LASTEXITCODE -ne 0) { throw 'Development regressions failed.' }
    & $PythonExe scripts/verify_answer_quality.py --regression-report $Regression --output reports/acceptance/fresh_answer_quality_contract.json
    if ($LASTEXITCODE -ne 0) { throw 'Evidence contracts failed.' }
    $PreservationArgs = @()
    if ($OriginalRoot -or $OriginalSnapshot) {
        if (-not ($OriginalRoot -and $OriginalSnapshot)) { throw 'Provide both original preservation arguments.' }
        $PreservationArgs = @('--original-root', $OriginalRoot, '--original-snapshot', $OriginalSnapshot)
    }
    & $PythonExe scripts/verify_fresh_delivery.py --ui-capture $UiCapture --regression-report $Regression --app-url $AppUrl @PreservationArgs
    if ($LASTEXITCODE -ne 0) { throw 'Fresh delivery acceptance failed; retain the failure receipt.' }
    Write-Host 'Fresh delivery accepted. Browser DOM is revalidated, not automatically resubmitted.'
}
finally { Pop-Location }
