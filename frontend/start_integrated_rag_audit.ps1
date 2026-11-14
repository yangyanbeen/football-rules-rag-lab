[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Task13Project = Split-Path -Parent $PSScriptRoot
$Task13Python = Join-Path $Task13Project '.runtime/task13/venv-final/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $Task13Python -PathType Leaf)) { throw '请先按 docs/TASK_13_AUDIT.md 准备独立环境。' }
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
& $Task13Python (Join-Path $Task13Project 'scripts/run_integrated_rag_audit.py')
exit $LASTEXITCODE
