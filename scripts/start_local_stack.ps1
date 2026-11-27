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

$modelListener = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$needsModelRestart = $false
if ($modelListener) {
    $owner = Get-Process -Id $modelListener.OwningProcess -ErrorAction SilentlyContinue
    $version = $null; $models = @()
    try {
        $version = (Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -Proxy $null -TimeoutSec 3).version
        $models = @((Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -Proxy $null -TimeoutSec 3).models | ForEach-Object { $_.name })
    } catch { $needsModelRestart = $true }
    if (-not $owner -or $owner.Path -ne $ollamaExe -or $version -ne '0.40.16' -or
        -not ($models -contains 'qwen2.5:3b') -or -not ($models -contains 'bge-m3:latest')) {
        $needsModelRestart = $true
    }
}
if ($needsModelRestart -and $modelListener) {
    Get-Process -Name ollama -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Get-Process -Name 'ollama app' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    $modelListener = $null
}
if (-not $modelListener) {
    Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WorkingDirectory $root -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 2
}

$checkVersion = (Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -Proxy $null -TimeoutSec 5).version
$checkModels = @((Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -Proxy $null -TimeoutSec 5).models | ForEach-Object { $_.name })
if ($checkVersion -ne '0.40.16' -or -not ($checkModels -contains 'qwen2.5:3b') -or -not ($checkModels -contains 'bge-m3:latest')) {
    throw "Pinned Ollama check failed: version=$checkVersion models=$($checkModels -join ',')"
}

$apiListener = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
if (-not $apiListener) {
    Start-Process -FilePath $pythonExe -ArgumentList 'scripts\run_api.py' -WorkingDirectory $root -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 2
}

Write-Output 'Football Rules RAG is available at http://localhost:8080/'
Write-Output 'Health: http://localhost:8080/health'
