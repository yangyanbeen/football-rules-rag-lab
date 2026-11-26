$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$ollamaExe = Join-Path $root '.runtime\ollama-0.40.16\bin\ollama.exe'
$modelDir = Join-Path $root '.runtime\phase2\e10-models'
$pythonExe = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $ollamaExe)) { throw "Missing pinned Ollama: $ollamaExe" }
if (-not (Test-Path -LiteralPath $pythonExe)) { throw "Missing project Python: $pythonExe" }

$env:OLLAMA_MODELS = $modelDir
$env:OLLAMA_NO_CLOUD = '1'
$env:FOOTBALL_OLLAMA_BASE_URL = 'http://127.0.0.1:11434'
$env:FOOTBALL_API_HOST = '127.0.0.1'
$env:FOOTBALL_API_PORT = '8080'

$modelListener = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue
if (-not $modelListener) {
    Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WorkingDirectory $root -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 2
}

$apiListener = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
if (-not $apiListener) {
    Start-Process -FilePath $pythonExe -ArgumentList 'scripts\run_api.py' -WorkingDirectory $root -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 2
}

Write-Output 'Football Rules RAG is available at http://localhost:8080/'
Write-Output 'Health: http://localhost:8080/health'
