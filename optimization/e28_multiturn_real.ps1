param([Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$outPath=Join-Path $root $Out
if(Test-Path $outPath){throw "Output already exists: $outPath"}
New-Item -ItemType Directory -Path $outPath | Out-Null
$worker=Join-Path $root '.runtime/task13/venv-final/Scripts/python.exe'
$py=$worker

function Set-RunEnvironment {
    $env:OLLAMA_HOST='127.0.0.1:11434';$env:OLLAMA_MODELS=Join-Path $root '.runtime/phase2/e10-models';$env:OLLAMA_NO_CLOUD='1'
    $env:FOOTBALL_SOURCE_FACTS='0';$env:FOOTBALL_STRICT_SELECTION='0';$env:FOOTBALL_GENERATION_DECISION='0';$env:FOOTBALL_PACKING_FILL_TOP10='0'
    $env:PYTHONIOENCODING='utf-8';$env:PYTHONDONTWRITEBYTECODE='1'
    foreach($key in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')){Set-Item "Env:$key" ''}
}

function Invoke-Scenario([string]$Name,[string]$Question,[object[]]$RawHistory) {
    Set-RunEnvironment
    $boundedJson = ''
    if($RawHistory.Count -gt 0){
        $rawJson=ConvertTo-Json -Compress -Depth 8 -InputObject $RawHistory
        $boundedJson = $rawJson | & $py -c "import json,sys;sys.path.insert(0,'scripts');from task13_query_rewrite import bounded_history;print(json.dumps(bounded_history(json.loads(sys.stdin.read())),ensure_ascii=False))"
        if($LASTEXITCODE -ne 0){throw "bounded_history failed for $Name"}
        $boundedJson=($boundedJson -join "`n").Trim()
    }
    $trace=Join-Path $root ('.runtime/task13-audit/workers/e28-multiturn-' + ([guid]::NewGuid().ToString('N')) + '.json')
    $errPath="$trace.stderr";$started=Get-Date
    if($RawHistory.Count -gt 0){
        $stdout=$boundedJson | & $py -u (Join-Path $root 'scripts/query_task13_audit.py') --question=$Question --trace=$trace --history-stdin 2> $errPath
    } else {
        $stdout=& $py -u (Join-Path $root 'scripts/query_task13_audit.py') --question=$Question --trace=$trace 2> $errPath
    }
    $exit=$LASTEXITCODE;$elapsed=((Get-Date)-$started).TotalSeconds
    $row=[ordered]@{scenario=$Name;question=$Question;raw_history_turns=$RawHistory.Count;bounded_history_json=$boundedJson;exit_code=$exit;elapsed_seconds=$elapsed;trace=$trace}
    if($exit -ne 0 -or -not(Test-Path $trace)){$row.status='worker_error';$row.error=Get-Content -Raw $errPath -ErrorAction SilentlyContinue}
    else {$r=Get-Content -Raw $trace | ConvertFrom-Json;$row.status=$r.status;$row.error=$r.error;$row.selected_ids=@($r.selected_ids);$row.offered_ids=@($r.offered_ids);$row.retrieved_ids=@($r.retrieved_ids);$row.refusal_reason=$r.refusal_reason;$row.query_resolution=$r.query_resolution;$row.attempt_count=@($r.attempts).Count;$row.timing=$r.timing;$row.answer=$r.answer}
    ($row|ConvertTo-Json -Depth 30)+"`n" | Set-Content -LiteralPath (Join-Path $outPath "$Name.json") -Encoding utf8
    return $row
}

$scenarios=New-Object System.Collections.Generic.List[object]
$h1=New-Object 'System.Collections.Generic.List[object]';[void]$h1.Add([object[]]@('足球的球门宽度和高度是多少？','球门尺寸的上一轮回答。'))
$h2=New-Object 'System.Collections.Generic.List[object]';[void]$h2.Add([object[]]@('中超2025赛季累计黄牌制度为何因赛事而不同？','需要结合具体赛事规程。'))
$scenarios.Add([pscustomobject]@{Name='reference_rewrite';Question='它们分别是多少？';History=$h1})
$scenarios.Add([pscustomobject]@{Name='disciplinary_parameter_inherit';Question='那累计三张黄牌停赛几场？';History=$h2})
$scenarios.Add([pscustomobject]@{Name='new_topic_isolation';Question='换个话题，球门有多宽？';History=$h2})
$raw=New-Object 'System.Collections.Generic.List[object]'
[void]$raw.Add([object[]]@('早期问题','早期回答'))
[void]$raw.Add([object[]]@('请把刚才的答案整理成表格。','展示动作，不作为事实'))
[void]$raw.Add([object[]]@('足球的球门宽度是多少？','球门宽度的回答。'))
[void]$raw.Add([object[]]@('继续问一下球门高度？','球门高度的回答。'))
[void]$raw.Add([object[]]@('把上一轮回答列成要点。','展示动作，不作为事实'))
[void]$raw.Add([object[]]@('它是多少？','最近一轮的尺寸回答。'))
$scenarios.Add([pscustomobject]@{Name='compressed_six_to_three';Question='它的标准尺寸呢？';History=$raw})
$rows=New-Object System.Collections.Generic.List[object]
foreach($s in $scenarios){$row=Invoke-Scenario $s.Name $s.Question $s.History;$rows.Add($row);[ordered]@{scenario=$s.Name;status=$row.status;raw_history_turns=$row.raw_history_turns;query_resolution=$row.query_resolution;elapsed_seconds=$row.elapsed_seconds;error=$row.error}|ConvertTo-Json -Compress}
$summary=[ordered]@{status='COMPLETED';source_commit=(& git -C $root rev-parse HEAD);model='qwen2.5:3b';ollama_version='0.40.16';scenarios=$rows}
($summary|ConvertTo-Json -Depth 30)+"`n"|Set-Content -LiteralPath (Join-Path $outPath 'summary.json') -Encoding utf8
