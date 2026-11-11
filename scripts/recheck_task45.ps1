[CmdletBinding()]
param([string]$ReportDir, [string]$OriginalRoot, [string]$OriginalSnapshot)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot '.venv/Scripts/python.exe'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
if (-not $ReportDir) { $ReportDir = 'reports/rechecks/task45-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffffff') }
if (-not [System.IO.Path]::IsPathRooted($ReportDir)) { $ReportDir = Join-Path $ProjectRoot $ReportDir }
Push-Location $ProjectRoot
try {
    & $PythonExe scripts/validate_eval_dataset.py --phase delivery --report (Join-Path $ReportDir 'acceptance/task4_delivery_gate.json')
    if ($LASTEXITCODE -ne 0) { throw 'Original task 4 human delivery gate failed.' }
    & $PythonExe scripts/validate_eval_receipt.py --report (Join-Path $ReportDir 'acceptance/task4_public_receipt.json')
    if ($LASTEXITCODE -ne 0) { throw 'Task 4 published review receipt failed.' }
    & $PythonExe scripts/verify_task4_workflow.py --report (Join-Path $ReportDir 'acceptance/task4_workflow_verification.json')
    if ($LASTEXITCODE -ne 0) { throw 'Task 4 workflow failed.' }
    & $PythonExe scripts/verify_task4_human_release.py --report (Join-Path $ReportDir 'acceptance/task4_human_release_verification.json')
    if ($LASTEXITCODE -ne 0) { throw 'Task 4 human release checks failed.' }
    $DenseArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/recheck_task5.ps1','-ReportDir',$ReportDir)
    if ($OriginalRoot -or $OriginalSnapshot) {
        if (-not $OriginalRoot -or -not $OriginalSnapshot) { throw 'Provide original root and snapshot together.' }
        $DenseArgs += @('-OriginalRoot',$OriginalRoot,'-OriginalSnapshot',$OriginalSnapshot)
    }
    & powershell @DenseArgs
    if ($LASTEXITCODE -ne 0) { throw 'Task 5 full delivery gate failed.' }
    & $PythonExe scripts/verify_task45_regressions.py --report (Join-Path $ReportDir 'acceptance/task45_regressions.json')
    if ($LASTEXITCODE -ne 0) { throw 'Task 4/5 defect regression checks failed.' }
    Write-Host "Task 4/5 supplement PASS. New evidence: $ReportDir. Original reports preserved."
}
finally { Pop-Location }
