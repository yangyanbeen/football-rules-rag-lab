[CmdletBinding()]
param([string]$OriginalRoot, [string]$OriginalSnapshot, [string]$ReportDir)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot '.venv/Scripts/python.exe'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
Push-Location $ProjectRoot
try {
    $ReviewArgs = @('scripts/verify_task5_delivery.py')
    if ($ReportDir) { $ReviewArgs += @('--report-dir',$ReportDir) }
    if ($OriginalRoot -or $OriginalSnapshot) {
        if (-not $OriginalRoot -or -not $OriginalSnapshot) { throw 'Provide both original root and original snapshot.' }
        $ReviewArgs += @('--original-root',$OriginalRoot,'--original-snapshot',$OriginalSnapshot)
    }
    & $PythonExe @ReviewArgs
    if ($LASTEXITCODE -ne 0) { throw 'Task 5 full acceptance failed. Keep failed evidence; do not claim delivery.' }
    $ExportArgs = @('scripts/export_dense_manifest.py')
    if ($ReportDir) { $ExportArgs += @('--output-dir',(Join-Path $ReportDir 'manifests')) }
    & $PythonExe @ExportArgs
    if ($LASTEXITCODE -ne 0) { throw 'Task 5 public metadata export failed.' }
    Write-Host 'Task 5 original delivery criteria passed; no quality benchmark was computed.'
}
finally { Pop-Location }
