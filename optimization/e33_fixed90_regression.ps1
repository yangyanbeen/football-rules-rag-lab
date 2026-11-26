param(
    [Parameter(Mandatory=$true)][string]$Out,
    [switch]$Resume
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$outPath = Join-Path $root $Out
if ((Test-Path -LiteralPath $outPath) -and -not $Resume) {
    throw "Output already exists: $outPath (use -Resume only for an interrupted run)"
}
New-Item -ItemType Directory -Force -Path $outPath | Out-Null
$workerDir = Join-Path $outPath 'worker'
New-Item -ItemType Directory -Force -Path $workerDir | Out-Null
$traceDir = Join-Path $root '.runtime/task13-audit/workers'
New-Item -ItemType Directory -Force -Path $traceDir | Out-Null
$worker = Join-Path $root '.runtime/task13/venv-final/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $worker)) { throw "Worker Python not found: $worker" }

$labels = @()
foreach ($name in @('dev_40.json','regression_50.json')) {
    # The frozen labels are UTF-8 Chinese JSON; Windows PowerShell otherwise
    # decodes them with the active ANSI code page and can corrupt the JSON.
    $rows = Get-Content -Raw -Encoding UTF8 (Join-Path $root "optimization/datasets/$name") | ConvertFrom-Json
    $labels += @($rows)
}
$labels = @($labels | Sort-Object @{Expression={ if ($_.question_id -match '^[DT](\d+)$') {[int]$Matches[1]} else {9999} }}, question_id)
if ($labels.Count -ne 90) { throw "Expected 90 fixed labels, found $($labels.Count)" }

function Get-AvailableMemoryGiB {
    try {
        $os = Get-CimInstance Win32_OperatingSystem
        return [math]::Round(([double]$os.FreePhysicalMemory * 1KB) / 1GB, 3)
    } catch { return $null }
}

function Set-RunEnvironment {
    $env:OLLAMA_HOST='127.0.0.1:11434'
    $env:OLLAMA_MODELS=Join-Path $root '.runtime/phase2/e10-models'
    $env:OLLAMA_NO_CLOUD='1'
    $env:FOOTBALL_SOURCE_FACTS='1'
    $env:FOOTBALL_STRICT_SELECTION='0'
    $env:FOOTBALL_GENERATION_DECISION='0'
    $env:FOOTBALL_SELECTION_AUDIT='1'
    $env:FOOTBALL_PACKING_FILL_TOP10='0'
    $env:FOOTBALL_ANCHOR_GUARD='1'
    $env:PYTHONIOENCODING='utf-8'
    $env:PYTHONDONTWRITEBYTECODE='1'
    foreach ($key in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')) { Set-Item "Env:$key" '' }
}

function Invoke-DirectWorker([object]$Label,[string]$TracePath) {
    Set-RunEnvironment
    $errPath = "$TracePath.stderr"
    $stdoutPath = "$TracePath.stdout"
    $before = Get-AvailableMemoryGiB
    $started = Get-Date
    $question = [string]$Label.question
    # Start-Process keeps benign Python warnings on stderr from being treated
    # as terminating native-command errors by Windows PowerShell 5.1.
    $proc = Start-Process -FilePath $worker -ArgumentList @('-u','-B',(Join-Path $root 'scripts/query_task13_audit.py'),("--question=" + $question),("--trace=" + $TracePath)) -WorkingDirectory $root -Wait -PassThru -WindowStyle Hidden -RedirectStandardError $errPath -RedirectStandardOutput $stdoutPath
    $exitCode = $proc.ExitCode
    $elapsed = ((Get-Date) - $started).TotalSeconds
    $after = Get-AvailableMemoryGiB
    $avail = @($before,$after) | Where-Object { $null -ne $_ }
    $minAvail = if ($avail.Count) { ($avail | Measure-Object -Minimum).Minimum } else { $null }
    if ($exitCode -ne 0 -or -not (Test-Path -LiteralPath $TracePath)) {
        return [ordered]@{
            status='worker_error'; error="exit=$exitCode"; answer=$null; selected_ids=@(); offered_ids=@(); retrieved_ids=@()
            refusal_reason=$null; prompt_utf8_bytes=$null; attempt_count=0; attempts=@(); selection_audit=$null
            generation_decision=$null; fact_recovery=$null; timing=$null; trace=$TracePath; elapsed_seconds=$elapsed
            resources=[ordered]@{available_before_GiB=$before;available_after_GiB=$after;available_min_GiB=$minAvail}
            stderr=(Get-Content -Raw $errPath -ErrorAction SilentlyContinue); result=$null
        }
    }
    $result = Get-Content -Raw -Encoding UTF8 -LiteralPath $TracePath | ConvertFrom-Json
    return [ordered]@{
        status=$result.status; error=$result.error; answer=$result.answer; selected_ids=@($result.selected_ids)
        offered_ids=@($result.offered_ids); retrieved_ids=@($result.retrieved_ids); refusal_reason=$result.refusal_reason
        prompt_utf8_bytes=$result.prompt_utf8_bytes; attempt_count=@($result.attempts).Count
        attempts=@($result.attempts | ForEach-Object {[ordered]@{attempt=$_.attempt;error=$_.error;prompt_eval_count=$_.prompt_eval_count;eval_count=$_.eval_count;done_reason=$_.done_reason}})
        selection_audit=$result.selection_audit; generation_decision=$result.generation_decision; fact_recovery=$result.fact_recovery
        timing=$result.timing; trace=$TracePath; elapsed_seconds=$elapsed
        resources=[ordered]@{available_before_GiB=$before;available_after_GiB=$after;available_min_GiB=$minAvail}
        stderr=(Get-Content -Raw $errPath -ErrorAction SilentlyContinue); result=$result
    }
}

$manifestPath = Join-Path $outPath 'manifest.json'
$manifest = [ordered]@{
    status='RUNNING'; experiment='E33_fixed90_generation_candidate'; variant='candidate'
    source_commit=(& git -C $root rev-parse HEAD); model='qwen2.5:3b'; embedding='bge-m3'; ollama_version='0.40.16'
    flags=[ordered]@{FOOTBALL_SOURCE_FACTS=1;FOOTBALL_SELECTION_AUDIT=1;FOOTBALL_ANCHOR_GUARD=1;FOOTBALL_GENERATION_DECISION=0;FOOTBALL_PACKING_FILL_TOP10=0}
    labels_sha256=(Get-FileHash (Join-Path $root 'optimization/datasets/dev_40.json') -Algorithm SHA256).Hash.ToLower() + ':' + (Get-FileHash (Join-Path $root 'optimization/datasets/regression_50.json') -Algorithm SHA256).Hash.ToLower()
    total=90; started_at=(Get-Date).ToString('o'); completed=0
}
($manifest | ConvertTo-Json -Depth 20) + "`n" | Set-Content -LiteralPath $manifestPath -Encoding utf8

for ($i=0; $i -lt $labels.Count; $i++) {
    $label = $labels[$i]
    $qid = [string]$label.question_id
    $file = Join-Path $outPath "$qid-B.json"
    if ($Resume -and (Test-Path -LiteralPath $file)) { continue }
    # query_task13_audit enforces private traces under .runtime/task13-audit/workers.
    $trace = Join-Path $traceDir ("e33-" + $qid + "-" + ([guid]::NewGuid().ToString('N')) + '.json')
    $value = Invoke-DirectWorker $label $trace
    $row = [ordered]@{
        name=$qid; qid=$qid; question=$label.question; variant='B'; category=($label.categories -join ',')
        expected_answer_points=@($label.expected_answer_points); required_conditions=@($label.required_conditions)
        expected_chunk_ids=@($label.expected_chunk_ids); must_refuse=[bool]$label.must_refuse
        expected_refusal_reason=$label.expected_refusal_reason; source_references=@($label.source_references)
        result=$value.result; status=$value.status; error=$value.error; answer=$value.answer; selected_ids=@($value.selected_ids)
        offered_ids=@($value.offered_ids); retrieved_ids=@($value.retrieved_ids); refusal_reason=$value.refusal_reason
        prompt_utf8_bytes=$value.prompt_utf8_bytes; attempt_count=$value.attempt_count; attempts=$value.attempts
        selection_audit=$value.selection_audit; generation_decision=$value.generation_decision; fact_recovery=$value.fact_recovery
        timing=$value.timing; seconds=$value.elapsed_seconds; resources=$value.resources; trace=$value.trace; stderr=$value.stderr
        captured_at=(Get-Date).ToString('o')
    }
    ($row | ConvertTo-Json -Depth 50) + "`n" | Set-Content -LiteralPath $file -Encoding utf8
    $manifest.completed = $i + 1
    ($manifest | ConvertTo-Json -Depth 20) + "`n" | Set-Content -LiteralPath $manifestPath -Encoding utf8
    [ordered]@{done=$i+1;total=$labels.Count;qid=$qid;status=$row.status;selected_ids=$row.selected_ids;seconds=$row.seconds;available_min_GiB=$row.resources.available_min_GiB;error=$row.error} | ConvertTo-Json -Compress
}

$files = @(Get-ChildItem -LiteralPath $outPath -Filter '*-B.json' -File)
$manifest.status = if ($files.Count -eq 90) {'COMPLETED'} else {'INCOMPLETE'}
$manifest.completed = $files.Count
$manifest.finished_at = (Get-Date).ToString('o')
($manifest | ConvertTo-Json -Depth 20) + "`n" | Set-Content -LiteralPath $manifestPath -Encoding utf8

# Keep the same immutable completion envelope as the historical 90-question runs.
# The scorer uses these hashes to ensure no result was edited after the live calls.
$hashes = [ordered]@{}
foreach ($file in $files) {
    $hashes[$file.Name] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLower()
}
$completed = [ordered]@{status=$manifest.status;completed_at=$manifest.finished_at;records=$files.Count;hashes=$hashes}
($completed | ConvertTo-Json -Depth 20) + "`n" | Set-Content -LiteralPath (Join-Path $outPath 'completed.json') -Encoding utf8

$summary = [ordered]@{status=$manifest.status; experiment=$manifest.experiment; variant='candidate'; source_commit=$manifest.source_commit; model=$manifest.model; ollama_version=$manifest.ollama_version; flags=$manifest.flags; total=$labels.Count; completed=$files.Count; files=@($files.Name); generated_at=(Get-Date).ToString('o')}
($summary | ConvertTo-Json -Depth 20) + "`n" | Set-Content -LiteralPath (Join-Path $outPath 'summary.json') -Encoding utf8
$summary | ConvertTo-Json -Depth 5
