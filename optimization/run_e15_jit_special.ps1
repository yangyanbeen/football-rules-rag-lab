param([string]$RunName='e15-jit-special01')
$Phase='probe'
$ErrorActionPreference='Stop'
if ($RunName -notmatch '^e15-[a-z0-9-]+$') {throw 'Use a bounded E15 run name.'}
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$original=(Resolve-Path -LiteralPath (Join-Path $root '../football-rules-rag-project')).Path
$base=Join-Path $root ('.runtime/phase2/'+$RunName)
$services=Join-Path $base 'services'
$workerPython=Join-Path $root '.runtime/task13/venv-final/Scripts/python.exe'
$exe=Join-Path $original '.runtime/ollama/ollama.exe'
$server=$null;$ui=$null
$env:PYTHONIOENCODING='utf-8';$env:PYTHONDONTWRITEBYTECODE='1';$env:NO_PROXY='127.0.0.1,localhost'
$env:FOOTBALL_LAZY_RETRIEVAL='1';$env:FOOTBALL_RUNTIME_MEMORY='1';$env:FOOTBALL_RELEASE_RERANKER='1';$env:FOOTBALL_JIT_RERANKER='0';$env:FOOTBALL_E15_MODE='jit'
foreach ($key in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')) {[Environment]::SetEnvironmentVariable($key,$null,'Process')}
function Test-Loopback([int]$Port) {
    $client=[Net.Sockets.TcpClient]::new()
    try {$client.Connect('127.0.0.1',$Port);return $true} catch {return $false} finally {$client.Dispose()}
}
try {
    if ((Test-Loopback 11434) -or (Test-Loopback 7867)) {throw 'Port occupied; preexisting services unchanged.'}
    if (Test-Path -LiteralPath $base) {throw 'Fresh output directory required.'}
    $capacityText=& $workerPython -B -c "import sys,json;sys.path.insert(0,'optimization');from e10_resources import snapshot;print(json.dumps(snapshot()))"
    if ($LASTEXITCODE -ne 0) {throw 'Cannot verify available memory before startup.'}
    $capacity=$capacityText|ConvertFrom-Json
    if ($capacity.available_GiB -lt 6.5) {
        New-Item -ItemType Directory -Path $base|Out-Null
        @{status='START_HEADROOM_STOP';snapshot=$capacity;required_GiB=6.5;model_calls=0}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $base 'preflight.json') -Encoding utf8
        throw 'Available memory below6.5GiB before deployment startup; no model service started.'
    }
    New-Item -ItemType Directory -Path $services | Out-Null
    @{status='START_HEADROOM_PASSED';snapshot=$capacity;required_GiB=6.5}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $base 'preflight.json') -Encoding utf8
    $env:OLLAMA_HOST='127.0.0.1:11434';$env:OLLAMA_MODELS=Join-Path $root '.runtime/phase2/e10-models'
    $env:OLLAMA_NOPRUNE='true';$env:OLLAMA_NO_CLOUD='1';$env:OLLAMA_MAX_LOADED_MODELS='1';$env:OLLAMA_NUM_PARALLEL='1'
    $server=Start-Process -FilePath $exe -ArgumentList @('serve') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $services 'ollama.stdout.log') -RedirectStandardError (Join-Path $services 'ollama.stderr.log')
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
    $profile=$RunName+'-facts';$env:FOOTBALL_SOURCE_FACTS='1'
    $events=Join-Path $base 'events';New-Item -ItemType Directory -Path $events | Out-Null
    $env:FOOTBALL_RUNTIME_EVENTS=$events
    [IO.File]::WriteAllText((Join-Path $base 'release-flag.json'),'{"enabled":false}')
    $ui=Start-Process -FilePath $workerPython -ArgumentList @('-u','-B','optimization/e15_ui.py','--profile',$profile,'--out',$base) -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $services 'ui.stdout.log') -RedirectStandardError (Join-Path $services 'ui.stderr.log')
    $deadline=[DateTimeOffset]::UtcNow.AddSeconds(180)
    do {
        if (Test-Loopback 7867) {break}
        if ($ui.HasExited) {throw 'Default UI exited; inspect logs.'}
        Start-Sleep -Milliseconds 500
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    if (-not (Test-Loopback 7867)) {throw 'UI readiness timed out.'}
    @{server_pid=$server.Id;ui_pid=$ui.Id;profile=$profile;version=$version;max_loaded_models=1;parallel_requests=1;port=7867;phase=$Phase} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $services 'owned-services.json') -Encoding utf8
    Push-Location -LiteralPath $root
    try {
        & $workerPython -u -B optimization/e15_jit_special.py --out $base --server-pid $server.Id --ui-pid $ui.Id
        if ($LASTEXITCODE -ne 0) {throw 'E15 probe failed.'}
    } finally {Pop-Location}
} finally {
    foreach ($owned in @($ui,$server)) {
        if ($owned -and -not $owned.HasExited) {taskkill /PID $owned.Id /T /F | Out-Null}
    }
    Write-Output 'E15 task-owned UI and model server stopped.'
}
