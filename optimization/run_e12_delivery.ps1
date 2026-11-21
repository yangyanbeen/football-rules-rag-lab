param()
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$original=(Resolve-Path -LiteralPath (Join-Path $root '../football-rules-rag-project')).Path
$out=Join-Path $root '.runtime/phase2/e12-services'
$live=Join-Path $root '.runtime/phase2/e12-live'
$store=Join-Path $root '.runtime/phase2/e10-models'
$workerPython=Join-Path $root '.runtime/task13/venv-final/Scripts/python.exe'
$exe=Join-Path $original '.runtime/ollama/ollama.exe'
$server=$null;$ui=$null
$env:PYTHONIOENCODING='utf-8';$env:PYTHONDONTWRITEBYTECODE='1';$env:NO_PROXY='127.0.0.1,localhost'
foreach ($key in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')) {[Environment]::SetEnvironmentVariable($key,$null,'Process')}
function Test-Loopback([int]$Port) {
    $client=[Net.Sockets.TcpClient]::new()
    try {$client.Connect('127.0.0.1',$Port);return $true} catch {return $false} finally {$client.Dispose()}
}
try {
    if ((Test-Loopback 11434) -or (Test-Loopback 7867)) {throw 'Port occupied; preexisting services unchanged.'}
    if ((Test-Path -LiteralPath $out) -or (Test-Path -LiteralPath $live)) {throw 'Register a fresh run; E12 output already exists.'}
    New-Item -ItemType Directory -Path $out,$live | Out-Null
    $env:OLLAMA_HOST='127.0.0.1:11434';$env:OLLAMA_MODELS=$store;$env:OLLAMA_NOPRUNE='true';$env:OLLAMA_NO_CLOUD='1'
    $env:OLLAMA_MAX_LOADED_MODELS='1';$env:OLLAMA_NUM_PARALLEL='1'
    $server=Start-Process -FilePath $exe -ArgumentList @('serve') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $out 'ollama.stdout.log') -RedirectStandardError (Join-Path $out 'ollama.stderr.log')
    $deadline=[DateTimeOffset]::UtcNow.AddSeconds(40)
    do {
        $version=$null;try {$version=Invoke-RestMethod -Uri http://127.0.0.1:11434/api/version -NoProxy -TimeoutSec 2} catch {}
        if ($version) {break};Start-Sleep -Milliseconds 250
    } while ([DateTimeOffset]::UtcNow -lt $deadline -and -not $server.HasExited)
    if (-not $version -or $version.version -ne '0.40.16') {throw 'Pinned model server not ready.'}
    $tags=(Invoke-RestMethod -Uri http://127.0.0.1:11434/api/tags -NoProxy).models
    foreach ($spec in @((Get-Content -Raw (Join-Path $root 'config/answer_evaluation.json')|ConvertFrom-Json).llm,(Get-Content -Raw (Join-Path $root 'config/dense_index.json')|ConvertFrom-Json).model)) {
        if (@($tags|Where-Object {$_.name -eq $spec.name -and $_.digest -eq $spec.digest}).Count -ne 1) {throw 'Pinned 3B/BGE model identity missing.'}
    }
    $profile='e12-delivery-v1'
    $ui=Start-Process -FilePath $workerPython -ArgumentList @('-u','-B','optimization/e12_observed_ui.py','--out',$live,'--profile',$profile) -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $out 'ui.stdout.log') -RedirectStandardError (Join-Path $out 'ui.stderr.log')
    $deadline=[DateTimeOffset]::UtcNow.AddSeconds(180)
    do {
        if (Test-Loopback 7867) {break}
        if ($ui.HasExited) {throw 'Observed default UI exited; inspect logs.'}
        Start-Sleep -Milliseconds 500
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    if (-not (Test-Loopback 7867)) {throw 'UI readiness timed out.'}
    @{server_pid=$server.Id;ui_pid=$ui.Id;profile=$profile;version=$version;max_loaded_models=1;parallel_requests=1;port=7867} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $live 'owned-services.json') -Encoding utf8
    Write-Output 'E12 normal UI ready; waiting for browser D036 check and run.start flag.'
    $deadline=[DateTimeOffset]::UtcNow.AddMinutes(10)
    while (-not (Test-Path -LiteralPath (Join-Path $live 'run.start'))) {
        if ((Test-Path -LiteralPath (Join-Path $live 'run.stop')) -or [DateTimeOffset]::UtcNow -ge $deadline -or $ui.HasExited) {throw 'Browser-start window ended.'}
        Start-Sleep -Milliseconds 500
    }
    Push-Location -LiteralPath $root
    try {
        & $workerPython -u -B optimization/e12_browser_eval.py --out $live --server-pid $server.Id --ui-pid $ui.Id --profile $profile
        if ($LASTEXITCODE -ne 0) {throw "E12 browser/load runner failed: $LASTEXITCODE"}
    } finally {Pop-Location}
} finally {
    foreach ($owned in @($ui,$server)) {
        if ($owned -and -not $owned.HasExited) {taskkill /PID $owned.Id /T /F | Out-Null}
    }
    Write-Output 'E12 task-owned UI and model server stopped.'
}
