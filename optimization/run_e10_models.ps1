param([switch]$Prepare, [switch]$Pilot, [switch]$Decomposition)
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$original=(Resolve-Path -LiteralPath (Join-Path $root '../football-rules-rag-project')).Path
$store=Join-Path $root '.runtime/phase2/e10-models'
$out=Join-Path $root '.runtime/phase2/e10-deployment'
$exe=Join-Path $original '.runtime/ollama/ollama.exe'
$endpoint='http://127.0.0.1:11434'
$candidate='e10-qwen2.5-7b-instruct-q4km:official'
$owned=$null
$env:PYTHONIOENCODING='utf-8'
$env:NO_PROXY='127.0.0.1,localhost'
foreach ($key in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')) {
    [Environment]::SetEnvironmentVariable($key,$null,'Process')
}
try {
    if (Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 11434 already in use; no process changed.' }
    New-Item -ItemType Directory -Force -Path $store,$out | Out-Null
    $sourceStore=Join-Path $original '.models/ollama'
    $relative='manifests/registry.ollama.ai/library/qwen2.5/3b'
    $sourceManifest=Join-Path $sourceStore $relative
    $manifest=Get-Content -LiteralPath $sourceManifest -Raw | ConvertFrom-Json
    $destinationManifest=Join-Path $store $relative
    New-Item -ItemType Directory -Force -Path (Split-Path $destinationManifest),(Join-Path $store 'blobs') | Out-Null
    if (-not (Test-Path -LiteralPath $destinationManifest)) { Copy-Item -LiteralPath $sourceManifest -Destination $destinationManifest }
    foreach ($part in @($manifest.config)+@($manifest.layers)) {
        $blob=($part.digest -replace ':','-')
        $destination=Join-Path (Join-Path $store 'blobs') $blob
        if (-not (Test-Path -LiteralPath $destination)) { Copy-Item -LiteralPath (Join-Path (Join-Path $sourceStore 'blobs') $blob) -Destination $destination }
    }
    $pinnedDigest=(Get-Content -LiteralPath (Join-Path $root 'config/answer_evaluation.json') -Raw | ConvertFrom-Json).llm.digest
    $pinnedManifest=Join-Path (Join-Path $store 'blobs') ('sha256-'+$pinnedDigest)
    if ((Get-FileHash -LiteralPath $pinnedManifest -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pinnedDigest) {throw 'Original baseline manifest blob does not match frozen digest.'}
    $beforeHash=(Get-FileHash -LiteralPath $destinationManifest -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllBytes($destinationManifest,[IO.File]::ReadAllBytes($pinnedManifest))
    $normalization=@{source_outer_manifest_sha256=(Get-FileHash -LiteralPath $sourceManifest -Algorithm SHA256).Hash.ToLowerInvariant();prior_isolated_manifest_sha256=$beforeHash;restored_frozen_manifest_sha256=$pinnedDigest;original_cache_changed=$false;utc=[DateTimeOffset]::UtcNow.ToString('o')}
    $normalization | ConvertTo-Json -Compress | Add-Content -LiteralPath (Join-Path $out 'baseline-manifest-events.jsonl') -Encoding utf8
    if (-not (Test-Path -LiteralPath (Join-Path $out 'baseline-manifest-normalization.json'))) {
        $normalization | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'baseline-manifest-normalization.json') -Encoding utf8
    }
    $env:OLLAMA_HOST='127.0.0.1:11434'
    $env:OLLAMA_MODELS=$store
    $env:OLLAMA_NOPRUNE='true'
    $env:OLLAMA_NO_CLOUD='1'
    $env:OLLAMA_MAX_LOADED_MODELS='1'
    $env:OLLAMA_NUM_PARALLEL='1'
    $stamp=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $owned=Start-Process -FilePath $exe -ArgumentList @('serve') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $out "ollama-$stamp.stdout.log") -RedirectStandardError (Join-Path $out "ollama-$stamp.stderr.log")
    $deadline=[DateTimeOffset]::UtcNow.AddSeconds(40)
    do {
        $version=$null
        try {$version=Invoke-RestMethod -Uri ($endpoint+'/api/version') -NoProxy -TimeoutSec 2} catch {}
        if ($version) {break}
        Start-Sleep -Milliseconds 250
    } while ([DateTimeOffset]::UtcNow -lt $deadline -and -not $owned.HasExited)
    if (-not $version -or $version.version -ne '0.40.16') {throw 'Pinned Ollama not ready.'}
    $owned.Id | Set-Content -LiteralPath (Join-Path $out 'server-pid.txt') -Encoding ascii
    Push-Location -LiteralPath $root
    try {
        if ($Prepare) {
            $gguf=Join-Path $root '.runtime/phase2/e10-download/qwen2.5-7b-instruct-q4_k_m.gguf'
            if (-not (Test-Path -LiteralPath ($gguf -replace '\.gguf$','.verified.json'))) {throw 'Verified merged official GGUF is required before import.'}
            $baseline=Invoke-RestMethod -Uri ($endpoint+'/api/show') -Method Post -Body (@{model='qwen2.5:3b'}|ConvertTo-Json -Compress) -ContentType 'application/json' -NoProxy -TimeoutSec 10
            $baseline | ConvertTo-Json -Depth 40 | Set-Content -LiteralPath (Join-Path $out 'baseline-show.json') -Encoding utf8
            $lines=@(('FROM "'+$gguf.Replace('\','/')+'"'),('TEMPLATE """'+$baseline.template+'"""'),('SYSTEM """'+$baseline.system+'"""'))
            foreach ($parameter in ($baseline.parameters -split "`n")) {if ($parameter.Trim()) {$lines+=('PARAMETER '+$parameter.Trim())}}
            $modelfile=Join-Path $out 'Modelfile'
            [IO.File]::WriteAllText($modelfile,($lines -join "`n"),[Text.UTF8Encoding]::new($false))
            & $exe create $candidate -f $modelfile *> (Join-Path $out 'import.log')
            if ($LASTEXITCODE -ne 0) {throw 'Candidate isolated import failed; see private import.log.'}
            $tags=Invoke-RestMethod -Uri ($endpoint+'/api/tags') -NoProxy -TimeoutSec 5
            $tags | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath (Join-Path $out 'tags.json') -Encoding utf8
            $show=Invoke-RestMethod -Uri ($endpoint+'/api/show') -Method Post -Body (@{model=$candidate}|ConvertTo-Json -Compress) -ContentType 'application/json' -NoProxy -TimeoutSec 10
            $show | ConvertTo-Json -Depth 40 | Set-Content -LiteralPath (Join-Path $out 'candidate-show.json') -Encoding utf8
            Write-Output 'E10 verified official candidate imported; model identity and quantization saved.'
        } elseif ($Pilot) {
            $python=Join-Path $root '.runtime/task17/venv/Scripts/python.exe'
            & $python -u -B optimization/e10_model_comparison.py run --prepared .runtime/phase2/e10-prepared-final/prepared.json --out .runtime/phase2/e10-pilot --server-pid $owned.Id
            if ($LASTEXITCODE -ne 0) {throw "E10 pilot failed with exit code $LASTEXITCODE"}
        } elseif ($Decomposition) {
            $decisionPath=Join-Path $root '.runtime/phase2/e10-score/metrics.json'
            $decision=Get-Content -Raw -LiteralPath $decisionPath | ConvertFrom-Json
            if ($decision.decision -notin @('NO_DEPLOYABLE_CANDIDATE','STOP_MODEL_CANDIDATE')) {throw 'Independent decomposition is conditional on deployment or model quality failure.'}
            $python=Join-Path $root '.runtime/task17/venv/Scripts/python.exe'
            & $python -u -B optimization/e10_decomposition.py run --prepared .runtime/phase2/e10-decomposition-prepared/prepared.json --out .runtime/phase2/e10-decomposition-live
            if ($LASTEXITCODE -ne 0) {throw "E10 decomposition failed with exit code $LASTEXITCODE"}
        }
    } finally {Pop-Location}
} finally {
    if ($owned -and -not $owned.HasExited) {
        taskkill /PID $owned.Id /T /F | Out-Null
        Write-Output "Stopped E10 temporary Ollama process $($owned.Id)."
    }
}
