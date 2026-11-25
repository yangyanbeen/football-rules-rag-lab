param(
    [Parameter(Mandatory=$true)][string]$Out,
    [switch]$SourceFacts,
    [switch]$AnchorGuard,
    [string[]]$Only
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$outPath = Join-Path $root $Out
if (Test-Path -LiteralPath $outPath) { throw "Output already exists: $outPath" }
New-Item -ItemType Directory -Path $outPath | Out-Null
$worker = Join-Path $root '.runtime/task13/venv-final/Scripts/python.exe'
$questionMap = @{}
foreach ($name in @('dev_40.json','regression_50.json')) {
    foreach ($row in (Get-Content -Raw (Join-Path $root "optimization/datasets/$name") | ConvertFrom-Json)) {
        if (-not $questionMap.ContainsKey($row.question_id)) { $questionMap[$row.question_id] = $row.question }
    }
}
$cases = @(
    @('D011','wrong_evidence_selection'), @('D019','wrong_evidence_selection'),
    @('T014','wrong_evidence_selection'), @('T018','wrong_evidence_selection'),
    @('T028','wrong_evidence_selection'), @('D021','evidence_coverage_incomplete'),
    @('D026','evidence_coverage_incomplete'), @('T004','evidence_coverage_incomplete'),
    @('T023','evidence_coverage_incomplete'), @('T026','evidence_coverage_incomplete'),
    @('T032','evidence_coverage_incomplete_and_false_refusal'),
    @('D003','false_refusal_with_evidence'), @('D012','false_refusal_with_evidence'),
    @('D032','false_refusal_with_evidence'), @('T009','false_refusal_with_evidence'),
    @('T015','false_refusal_with_evidence'), @('T017','false_refusal_with_evidence')
)
if ($Only -and $Only.Count -gt 0) {
    $wanted = @($Only | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() })
    $cases = @($cases | Where-Object {$wanted -contains $_[0]})
}

function Set-RunEnvironment {
    $env:OLLAMA_HOST='127.0.0.1:11434'
    $env:OLLAMA_MODELS=Join-Path $root '.runtime/phase2/e10-models'
    $env:OLLAMA_NO_CLOUD='1'
    $env:FOOTBALL_SOURCE_FACTS=if ($SourceFacts) {'1'} else {'0'}
    $env:FOOTBALL_STRICT_SELECTION='0'
    $env:FOOTBALL_GENERATION_DECISION='0'
    $env:FOOTBALL_SELECTION_AUDIT='1'
    $env:FOOTBALL_PACKING_FILL_TOP10='0'
    $env:FOOTBALL_ANCHOR_GUARD=if ($AnchorGuard) {'1'} else {'0'}
    $env:PYTHONIOENCODING='utf-8'
    $env:PYTHONDONTWRITEBYTECODE='1'
    foreach ($key in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')) { Set-Item "Env:$key" '' }
}

function Invoke-DirectWorker([string]$Question,[string]$TracePath) {
    Set-RunEnvironment
    $errPath = "$TracePath.stderr"
    $started = Get-Date
    $stdout = & $worker -u -B (Join-Path $root 'scripts/query_task13_audit.py') --question=$Question --trace=$TracePath 2> $errPath
    $exitCode = $LASTEXITCODE
    $elapsed = ((Get-Date) - $started).TotalSeconds
    if ($exitCode -ne 0 -or -not (Test-Path -LiteralPath $TracePath)) {
        return [ordered]@{status='worker_error';error="exit=$exitCode";stderr=(Get-Content -Raw $errPath -ErrorAction SilentlyContinue);elapsed_seconds=$elapsed;trace=$TracePath}
    }
    $result = Get-Content -Raw -LiteralPath $TracePath | ConvertFrom-Json
    return [ordered]@{
        status=$result.status;error=$result.error;answer=$result.answer;selected_ids=@($result.selected_ids)
        offered_ids=@($result.offered_ids);retrieved_ids=@($result.retrieved_ids);refusal_reason=$result.refusal_reason
        prompt_utf8_bytes=$result.prompt_utf8_bytes;attempt_count=@($result.attempts).Count
        attempts=@($result.attempts | ForEach-Object {[ordered]@{attempt=$_.attempt;error=$_.error;prompt_eval_count=$_.prompt_eval_count;eval_count=$_.eval_count;done_reason=$_.done_reason}})
        selection_audit=$result.selection_audit;generation_decision=$result.generation_decision;fact_recovery=$result.fact_recovery
        timing=$result.timing;trace=$TracePath;elapsed_seconds=$elapsed;result=$result
    }
}

$rows = New-Object System.Collections.Generic.List[object]
for ($i=0; $i -lt $cases.Count; $i++) {
    $qid=$cases[$i][0];$category=$cases[$i][1]
    if (-not $questionMap.ContainsKey($qid)) { throw "Missing question $qid" }
    $trace = Join-Path $root ('.runtime/task13-audit/workers/e31-' + ([guid]::NewGuid().ToString('N')) + '.json')
    $value=Invoke-DirectWorker $questionMap[$qid] $trace
    $row=[ordered]@{qid=$qid;kind='generation';category=$category;variant='C';repetition=1;question=$questionMap[$qid]}
    foreach ($key in $value.Keys) {$row[$key]=$value[$key]}
    $rows.Add($row)
    $file=Join-Path $outPath ('{0:D3}-generation-{1}-C-1.json' -f ($i+1),$qid)
    ($row | ConvertTo-Json -Depth 40) + "`n" | Set-Content -LiteralPath $file -Encoding utf8
    [ordered]@{done=$i+1;total=$cases.Count;qid=$qid;status=$row.status;selected_ids=$row.selected_ids;offered_ids=$row.offered_ids;elapsed_seconds=$row.elapsed_seconds;error=$row.error} | ConvertTo-Json -Compress
}
$summary=[ordered]@{status='COMPLETED';source_commit=(& git -C $root rev-parse HEAD);model='qwen2.5:3b';ollama_version='0.40.16';variant='C_selection_audit';source_facts=[bool]$SourceFacts;anchor_guard=[bool]$AnchorGuard;generation_cases=$cases.Count;generation_observations=$rows.Count;rows=$rows}
($summary | ConvertTo-Json -Depth 40) + "`n" | Set-Content -LiteralPath (Join-Path $outPath 'summary.json') -Encoding utf8
