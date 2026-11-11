$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
& (Join-Path $ProjectRoot '.venv/Scripts/python.exe') (Join-Path $ProjectRoot 'scripts/run_rag_b0.py')
exit $LASTEXITCODE
