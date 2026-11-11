[CmdletBinding()]
param([switch]$PreparationOnly)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot '.venv/Scripts/python.exe'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
Push-Location $ProjectRoot
try {
    & $PythonExe scripts/validate_eval_dataset.py --phase structure
    if ($LASTEXITCODE -ne 0) { throw 'Task 4 candidate structure failed.' }
    & $PythonExe scripts/verify_task4_workflow.py
    if ($LASTEXITCODE -ne 0) { throw 'Task 4 arithmetic or negative checks failed.' }
    & $PythonExe scripts/validate_eval_dataset.py --phase delivery --report reports/acceptance/task4_delivery_gate.json
    $DeliveryResult = $LASTEXITCODE
    if ($DeliveryResult -ne 0) {
        if ($PreparationOnly) { Write-Host 'PREPARATION ONLY: automatic checks passed; original full delivery gate has NOT passed.'; exit 0 }
        throw 'Original task 4 delivery is pending. Complete actual human review, freeze test, and rerun; do not claim delivery.'
    }
    Write-Host 'Original task 4 delivery gate passed.'
}
finally { Pop-Location }
