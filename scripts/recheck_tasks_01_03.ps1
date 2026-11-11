[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RuntimeRoot)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = (Resolve-Path -LiteralPath $RuntimeRoot).Path
$PythonExe = Join-Path $RuntimeRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { throw 'The existing isolated runtime Python is missing.' }
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$AuditRelative = ".tmp/task123-recheck-$Stamp/task1_task2.json"
$PrivateRelative = ".runtime/task123-recheck-$Stamp/development-regression.json"
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot ".tmp/task123-recheck-$Stamp"), (Join-Path $ProjectRoot ".runtime/task123-recheck-$Stamp") | Out-Null
$env:TIKTOKEN_CACHE_DIR = Join-Path $RuntimeRoot '.cache/tiktoken'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:NO_PROXY = '127.0.0.1,localhost,::1'
Push-Location $ProjectRoot
try {
    & $PythonExe (Join-Path $RuntimeRoot 'scripts/audit_task1_task2.py') --live --ui-evidence reports/answer-quality-ui-evidence-2026-11-11.json --model-evidence reports/task2-model-runtime-2026-11-11.json --startup-log reports/kotaemon-quality-fix-final-2026-11-11.log --output $AuditRelative
    if ($LASTEXITCODE -ne 0) { throw 'Original task 1/2 acceptance failed. Start the documented local services and inspect the retained receipt.' }
    & $PythonExe scripts/verify_task3_isolated.py
    if ($LASTEXITCODE -ne 0) { throw 'Task 3 isolated acceptance failed.' }
    & $PythonExe scripts/run_answer_quality_regression.py --output $PrivateRelative
    if ($LASTEXITCODE -ne 0) { throw 'Development answer/citation regressions failed.' }
    & $PythonExe scripts/verify_answer_quality.py --regression-report $PrivateRelative --output reports/acceptance/answer_quality_contract.json
    if ($LASTEXITCODE -ne 0) { throw 'Evidence contracts failed.' }
    & $PythonExe scripts/collect_delivery_evidence.py --runtime-root $RuntimeRoot --audit-report $AuditRelative --regression-report $PrivateRelative
    if ($LASTEXITCODE -ne 0) { throw 'Combined delivery review failed.' }
    Write-Host 'Tasks 1-3 rechecked. Reports: reports/acceptance/; full model output remains private.'
}
finally { Pop-Location }
