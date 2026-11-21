param([int]$MemoryWaitSeconds=600)
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$original=(Resolve-Path -LiteralPath (Join-Path $root '../football-rules-rag-project')).Path
$store=Join-Path $root '.runtime/phase2/e10-models'
$sourceStore=Join-Path $original '.models/ollama'
$out=Join-Path $root '.runtime/phase2/e11-services'
$live=Join-Path $root '.runtime/phase2/e11-live'
$exe=Join-Path $original '.runtime/ollama/ollama.exe'
$python=Join-Path $root '.runtime/task17/venv/Scripts/python.exe'
$workerPython=Join-Path $root '.runtime/task13/venv-final/Scripts/python.exe'
$server=$null; $ui=$null; $worker=$null
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONDONTWRITEBYTECODE='1'
$env:NO_PROXY='127.0.0.1,localhost'
foreach ($key in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')) {[Environment]::SetEnvironmentVariable($key,$null,'Process')}
function Test-Loopback([int]$Port) {
    $client=[Net.Sockets.TcpClient]::new()
    try {$client.Connect('127.0.0.1',$Port);return $true} catch {return $false} finally {$client.Dispose()}
}
try {
    if ((Test-Loopback 11434) -or (Test-Loopback 7867)) {throw 'Required port already occupied; no existing service changed.'}
    if ((Test-Path -LiteralPath $live) -or (Test-Path -LiteralPath $out)) {throw 'E11 output exists; register a fresh run instead of overwriting.'}
    New-Item -ItemType Directory -Path $out | Out-Null
    # Reuse verified E10 weights. Restore only the isolated legacy manifests.
    foreach ($entry in @(@{name='qwen2.5';tag='3b';digest=(Get-Content -Raw (Join-Path $root 'config/answer_evaluation.json')|ConvertFrom-Json).llm.digest},@{name='bge-m3';tag='latest';digest=(Get-Content -Raw (Join-Path $root 'config/dense_index.json')|ConvertFrom-Json).model.digest})) {
        $relative='manifests/registry.ollama.ai/library/'+$entry.name+'/'+$entry.tag
        $source=Join-Path $sourceStore $relative
        $destination=Join-Path $store $relative
        $outer=Get-Content -Raw -LiteralPath $source|ConvertFrom-Json
        New-Item -ItemType Directory -Force -Path (Split-Path $destination) | Out-Null
        foreach ($part in @($outer.config)+@($outer.layers)) {
            $blob=$part.digest.Replace(':','-');$target=Join-Path (Join-Path $store 'blobs') $blob
            if (-not (Test-Path -LiteralPath $target)) {Copy-Item -LiteralPath (Join-Path (Join-Path $sourceStore 'blobs') $blob) -Destination $target}
        }
        $pinned=Join-Path (Join-Path $store 'blobs') ('sha256-'+$entry.digest)
        if ((Get-FileHash -LiteralPath $pinned -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.digest) {throw 'Frozen model manifest hash differs.'}
        [IO.File]::WriteAllBytes($destination,[IO.File]::ReadAllBytes($pinned))
    }
    $env:OLLAMA_HOST='127.0.0.1:11434';$env:OLLAMA_MODELS=$store;$env:OLLAMA_NOPRUNE='true';$env:OLLAMA_NO_CLOUD='1'
    $env:OLLAMA_MAX_LOADED_MODELS='1';$env:OLLAMA_NUM_PARALLEL='1'
    $server=Start-Process -FilePath $exe -ArgumentList @('serve') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $out 'ollama.stdout.log') -RedirectStandardError (Join-Path $out 'ollama.stderr.log')
    $deadline=[DateTimeOffset]::UtcNow.AddSeconds(40)
    do {
        $version=$null;try {$version=Invoke-RestMethod -Uri http://127.0.0.1:11434/api/version -NoProxy -TimeoutSec 2} catch {}
        if ($version) {break};Start-Sleep -Milliseconds 250
    } while ([DateTimeOffset]::UtcNow -lt $deadline -and -not $server.HasExited)
    if (-not $version -or $version.version -ne '0.40.16') {throw 'Pinned server not ready.'}
    $ui=Start-Process -FilePath $workerPython -ArgumentList @('-u','-B','scripts/run_integrated_rag_audit.py') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $out 'ui.stdout.log') -RedirectStandardError (Join-Path $out 'ui.stderr.log')
    $deadline=[DateTimeOffset]::UtcNow.AddSeconds(180)
    do {
        if (Test-Loopback 7867) {break}
        if ($ui.HasExited) {throw 'Default UI exited; inspect E11 private service logs.'}
        Start-Sleep -Milliseconds 500
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    if (-not (Test-Loopback 7867)) {throw 'Default UI readiness timed out.'}
    $ready=Join-Path $out 'worker-ready.json';$stop=Join-Path $out 'worker.stop'
    $worker=Start-Process -FilePath $workerPython -ArgumentList @('-u','-B','optimization/e11_resident.py','--ready',$ready,'--stop',$stop) -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $out 'worker.stdout.log') -RedirectStandardError (Join-Path $out 'worker.stderr.log')
    $deadline=[DateTimeOffset]::UtcNow.AddSeconds(120)
    do {
        if (Test-Path -LiteralPath $ready) {break}
        if ($worker.HasExited) {throw 'Resident retrieval worker exited; inspect E11 service logs.'}
        Start-Sleep -Milliseconds 500
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    if (-not (Test-Path -LiteralPath $ready)) {throw 'Resident worker readiness timed out.'}
    @{server_pid=$server.Id;ui_pid=$ui.Id;worker_launcher_pid=$worker.Id;store=$store;version=$version;max_loaded_models=1;parallel_requests=1} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'owned-services.json') -Encoding utf8
    Push-Location -LiteralPath $root
    try {
        & $python -u -B optimization/e11_deployment.py run --prepared .runtime/phase2/e11-prepared/prepared.json --out .runtime/phase2/e11-live --server-pid $server.Id --ui-pid $ui.Id --worker-ready $ready --memory-wait-seconds $MemoryWaitSeconds
        if ($LASTEXITCODE -ne 0) {throw "E11 runner failed: $LASTEXITCODE"}
    } finally {Pop-Location}
} finally {
    if ($worker -and -not $worker.HasExited) {
        New-Item -ItemType File -Force -Path (Join-Path $out 'worker.stop') | Out-Null
        if (-not $worker.WaitForExit(10000)) {taskkill /PID $worker.Id /T /F | Out-Null}
    }
    foreach ($owned in @($ui,$server)) {
        if ($owned -and -not $owned.HasExited) {taskkill /PID $owned.Id /T /F | Out-Null}
    }
    Write-Output 'E11 task-owned services stopped; preexisting processes were not changed.'
}
