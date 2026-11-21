param([ValidateSet('special','regression')][string]$Phase='special',[string]$RunName='e13-special01')
$ErrorActionPreference='Stop'
if ($RunName -notmatch '^e13-[a-z0-9-]+$') {throw 'Use a bounded E13 run name.'}
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$original=(Resolve-Path -LiteralPath (Join-Path $root '../football-rules-rag-project')).Path
$base=Join-Path $root ('.runtime/phase2/'+$RunName)
$services=Join-Path $base 'services'
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
    if (Test-Path -LiteralPath $base) {throw 'Fresh output directory required.'}
    if ($Phase -eq 'regression') {
        $gate=Get-Content -Raw (Join-Path $root 'optimization/reports/E13_special_metrics.json')|ConvertFrom-Json
        if (-not $gate.all_gates_passed) {throw 'E13 special gates must pass before regression.'}
    }
    New-Item -ItemType Directory -Path $services | Out-Null
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
    $ui=Start-Process -FilePath $workerPython -ArgumentList @('-u','-B','optimization/e13_ui.py','--profile',$profile) -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $services 'ui.stdout.log') -RedirectStandardError (Join-Path $services 'ui.stderr.log')
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
        & $workerPython -u -B optimization/e13_live.py $Phase --out (Join-Path $base 'worker') --server-pid $server.Id
        if ($LASTEXITCODE -ne 0) {throw 'E13 normal Worker experiment failed.'}
        $done=Get-Content -Raw (Join-Path $base 'worker/completed.json')|ConvertFrom-Json
        if ($Phase -eq 'special') {
            if ($done.status -eq 'COMPLETED') {
                & $workerPython -u -B optimization/e13_browser.py --out (Join-Path $base 'browser') --server-pid $server.Id
                if ($LASTEXITCODE -ne 0) {throw 'E13 browser experiment failed.'}
            }
            & $workerPython -u -B optimization/score_e13_special.py --run (Join-Path $base 'worker') --browser (Join-Path $base 'browser/result.json') --out optimization/reports/E13_special_metrics.json
            if ($LASTEXITCODE -ne 0) {throw 'E13 scoring failed.'}
        }
    } finally {Pop-Location}
} finally {
    foreach ($owned in @($ui,$server)) {
        if ($owned -and -not $owned.HasExited) {taskkill /PID $owned.Id /T /F | Out-Null}
    }
    Write-Output 'E13 task-owned UI and model server stopped.'
}
