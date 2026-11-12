"""Independent standard-library replay of task 8 BM25 measurements."""
from __future__ import annotations
import json, math, re, subprocess
from datetime import datetime
from pathlib import Path
from bm25_index import ROOT, CONFIG, RESOURCES, SOURCES, SOURCE_FIELDS, TEMPLATES, TIMINGS, config, normalize, record
from eval_dataset import EVAL, canonical, digest, load_jsonl
from retrieval_metrics import compute_metrics

# Versioned execution policy. Future experimental policies need a new version.
V1_EXECUTION_FILES=SOURCES+('scripts/bm25_retrieval_eval.py','scripts/run_bm25_retrieval.py',
 'scripts/recompute_bm25_retrieval.py','scripts/retrieval_metrics.py','scripts/run_retrieval_metrics.py',
 'scripts/validate_eval_dataset.py','scripts/validate_eval_receipt.py','scripts/verify_bm25_contract.py')
DATA_FILES=('data/eval/dataset_manifest.json','data/eval/retrieval_dev.jsonl','data/eval/retrieval_test.jsonl',
 'data/eval/human_review_receipt.json','data/manifests/dense_index_manifest.json','data/manifests/rag_dataset_manifest.json',
 'data/manifests/bm25_indexes.json')


def snapshots():return {p:record(ROOT/p) for p in V1_EXECUTION_FILES+RESOURCES+DATA_FILES}
def now():
    from datetime import timezone
    return datetime.now(timezone.utc).isoformat()


def instant(value):
    if not isinstance(value,str):raise ValueError('Timestamp must be a string')
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None:raise ValueError('Timestamp needs timezone')
    return dt


def finite(value):
    try:return type(value) in (int,float) and math.isfinite(value) and value>=0
    except OverflowError:return False


def producer_before(commit,timestamp):
    """Historical producers must exist before the measurement/authorization."""
    from bm25_index import committed
    committed((),commit)
    created=subprocess.check_output(['git','show','-s','--format=%cI',commit],cwd=ROOT,text=True).strip()
    if instant(created)>instant(timestamp):raise ValueError('Producer commit postdates recorded work')


def validate_identity(split,template,run_id):
    if (split not in ('dev','test') or template not in TEMPLATES or not isinstance(run_id,str)
        or not re.fullmatch('[0-9a-f]{32}',run_id)):raise ValueError('Invalid run identity')


def valid_source(row):
    return (isinstance(row.get('chunk_id'),str) and re.fullmatch(r'[0-9A-Za-z_-]+',row['chunk_id'])
            and type(row.get('law_number')) is int and 1<=row['law_number']<=17
            and isinstance(row.get('source_url'),str) and row['source_url'].startswith('https://en.wikipedia.org/wiki/')
            and isinstance(row.get('source_lines'),list) and len(row['source_lines'])==2
            and all(type(n) is int for n in row['source_lines']) and 0<row['source_lines'][0]<=row['source_lines'][1]
            and all(isinstance(row.get(k),str) and re.fullmatch('[a-f0-9]{64}',row[k]) for k in ('record_sha256','content_zh_sha256')))


def percentile(values,q):
    if not values or any(not finite(v) for v in values):raise ValueError('Nonfinite/negative latency')
    s=sorted(values);p=q*(len(s)-1);lo=math.floor(p);hi=math.ceil(p)
    return s[lo]+(s[hi]-s[lo])*(p-lo)


def statistics(values):
    return {'samples':len(values),'P50_ms':1000*percentile(values,.5),
            'P95_ms':1000*percentile(values,.95),'mean_ms':1000*sum(values)/len(values)}


def summary(questions,predictions,template,split,run_id):
    quality=compute_metrics(questions,predictions)
    labels={q['question_id']:q for q in questions}
    latency={}
    for group in ('all','answerable','unanswerable'):
        rows=[r for r in predictions if group=='all' or labels[r['question_id']]['answerable']==(group=='answerable')]
        latency[group]={stage:statistics([m[stage] for r in rows for m in r['measurements']]) for stage in TIMINGS}
    return {'version':'bm25-summary-1.0','template':template,'split':split,'run_id':run_id,
            'quality':quality,'latency':latency,'latency_method':'linear interpolation at q*(n-1); milliseconds',
            'quality_repetition':1,'measured_repetitions':3,'no_model_or_answer_calls':True,
            'positive_scores_only':True,'zero_or_oov_matches_return_empty':True}


def error_analysis(questions,predictions,split):
    scores=compute_metrics(questions,predictions);by_id={r['question_id']:r for r in predictions}
    cases=[];categories={}
    for q,metric in zip(questions,scores['per_question']):
        if not q['answerable']:continue
        missing5=not bool(metric['Recall@5']);missing10=not bool(metric['Recall@10'])
        partial=metric['all_gold_coverage@5']<1
        for category in q['categories']:
            target=categories.setdefault(category,{'questions':0,'miss_at_5':0,'miss_at_10':0,'partial_gold_at_5':0})
            for k,v in [('questions',1),('miss_at_5',missing5),('miss_at_10',missing10),('partial_gold_at_5',partial)]:target[k]+=int(v)
        if split=='dev':
            cases.append({'question_id':q['question_id'],'question':q['question'],'categories':q['categories'],
                          'gold_ids':q['expected_chunk_ids'],'ranked_ids':[r['chunk_id'] for r in by_id[q['question_id']]['results']],
                          'query_tokens':by_id[q['question_id']]['query_tokens'],'miss_at_5':missing5,'miss_at_10':missing10,
                          'all_gold_coverage_at_5':metric['all_gold_coverage@5']})
    return {'scope':'Development examples' if split=='dev' else 'Locked test aggregate only; never used to select parameters',
            'categories':categories,'development_cases':cases if split=='dev' else None,
            'miss_at_5':sum(1 for r in scores['per_question'] if r.get('Recall@5')==0),
            'miss_at_10':sum(1 for r in scores['per_question'] if r.get('Recall@10')==0)}


def validate_predictions(questions,predictions,sources,split,template,run_id):
    validate_identity(split,template,run_id)
    known={r['chunk_id']:r for r in sources}
    if len(sources)!=99 or len(known)!=99 or any(set(r)!=set(SOURCE_FIELDS) or not valid_source(r) for r in sources):raise ValueError('Invalid source mapping')
    # The canonical source map is already bound to the frozen corpus by the producer
    # and the original Dense source metadata, without requiring corpus bodies here.
    reference=json.loads((ROOT/'reports/retrieval/dense_b0/dev/source_map.json').read_text('utf-8'))
    if canonical(sources)!=canonical(reference):raise ValueError('Sources differ from original corpus metadata')
    qs={q['question_id']:q for q in questions}
    if len(qs)!=len(questions) or len(predictions)!=len(qs):raise ValueError('Incomplete/duplicate questions')
    seen=set()
    for row in predictions:
        if not isinstance(row,dict) or set(row)!={'question_id','question_sha256','query','query_tokens','split','template','run_id','results','measurements'}:raise ValueError('Prediction schema; no extra source bodies')
        qid=row['question_id']
        if not isinstance(qid,str) or qid not in qs or qid in seen:raise ValueError('Unknown/duplicate question')
        seen.add(qid);q=qs[qid]
        if (row['query']!=normalize(q['question']) or row['question_sha256']!=digest(q['question'].encode())
            or row['split']!=split or row['template']!=template or row['run_id']!=run_id):raise ValueError('Query/run mismatch')
        tokens=row['query_tokens']
        if not isinstance(tokens,list) or any(not isinstance(t,str) or not t or len(t)>1200 for t in tokens):raise ValueError('Invalid query tokens')
        results=row['results']
        if not isinstance(results,list) or len(results)>10:raise ValueError('At most Top10 required')
        ids=[];values=[]
        for rank,result in enumerate(results,1):
            if not isinstance(result,dict) or set(result)!=set(SOURCE_FIELDS)|{'rank','score'}:raise ValueError('Invalid result fields')
            cid=result['chunk_id']
            if (not valid_source(result) or not isinstance(cid,str) or cid not in known or cid in ids or type(result['rank']) is not int or result['rank']!=rank
                or {k:result[k] for k in SOURCE_FIELDS}!=known[cid] or not finite(result['score']) or result['score']<=0):raise ValueError('Invalid result source/rank/score')
            ids.append(cid);values.append(result['score'])
        if list(zip([-v for v in values],ids))!=sorted(zip([-v for v in values],ids)):raise ValueError('Unsorted scores or ties')
        measures=row['measurements']
        if not isinstance(measures,list) or len(measures)!=3:raise ValueError('Three measurements required')
        for i,m in enumerate(measures,1):
            if (not isinstance(m,dict) or set(m)!=set(TIMINGS)|{'repetition','ranked_ids','scores'}
                or type(m['repetition']) is not int or m['repetition']!=i
                or m['ranked_ids']!=ids or m['scores']!=values or not isinstance(m['scores'],list)
                or any(not finite(v) or v<=0 for v in m['scores'])):raise ValueError('Unstable/incomplete repeated ranking')
            if any(not finite(m[t]) for t in TIMINGS) or abs(m['total_seconds']-sum(m[t] for t in TIMINGS[:-1]))>1e-8:raise ValueError('Invalid timing containment')
    compute_metrics(questions,predictions)


def require_inputs(items,current_sources=False):
    if set(items)!=set(V1_EXECUTION_FILES+RESOURCES+DATA_FILES):raise ValueError('Incomplete input/source coverage')
    names=V1_EXECUTION_FILES+RESOURCES+DATA_FILES if current_sources else RESOURCES+DATA_FILES
    if any(items[p]!=record(ROOT/p) for p in names):raise ValueError('Frozen data/resources/code changed')


def validate_index_manifest(index,template,inputs):
    public=json.loads((ROOT/'data/manifests/bm25_indexes.json').read_text('utf-8'))['indexes'][template]
    if not isinstance(index,dict) or set(index)!=set(public):raise ValueError('Index metadata fields differ')
    # Rebuilding from a later clean commit changes producer provenance, while the
    # deterministic postings/source-map bytes must retain the original identity.
    identity=set(public)-{'source_commit','sources'}
    if any(canonical(index[k])!=canonical(public[k]) for k in identity):raise ValueError('Index payload or resource identity differs')
    if index['inputs']!={p:inputs[p] for p in RESOURCES} or set(index['sources'])!=set(SOURCES):raise ValueError('Incomplete index source coverage')
    from bm25_index import committed
    committed((),index['source_commit'])
    for name,entry in index['sources'].items():
        raw=subprocess.check_output(['git','show',index['source_commit']+':'+name],cwd=ROOT)
        if entry!={'path':name,'size_bytes':len(raw),'sha256':digest(raw)}:raise ValueError('Rebuilt index producer differs from Git')


def replay(directory):
    directory=Path(directory).resolve()
    if (directory/'failure.json').exists():raise ValueError('Failed run evidence cannot be accepted as COMPLETE')
    manifest=json.loads((directory/'run_manifest.json').read_text('utf-8'))
    required={'version','status','run_id','split','template','purpose','used_for_parameter_selection','source_commit','inputs',
              'started_at','completed_at','wall_seconds','load_seconds','warmups','index_manifest','environment','artifacts','authorization'}
    if set(manifest)!=required or manifest['version']!='bm25-run-1.0' or manifest['status']!='COMPLETE':raise ValueError('Incomplete/versioned run manifest')
    m=manifest;require_inputs(m['inputs'])
    validate_identity(m['split'],m['template'],m['run_id'])
    producer_before(m['source_commit'],m['started_at'])
    from bm25_index import committed
    committed((),m['source_commit'])
    for name in V1_EXECUTION_FILES:
        raw=subprocess.check_output(['git','show',m['source_commit']+':'+name],cwd=ROOT)
        if m['inputs'][name]!={'path':name,'size_bytes':len(raw),'sha256':digest(raw)}:raise ValueError('Producer differs from Git object')
    start,end=instant(m['started_at']),instant(m['completed_at'])
    if end<start or not finite(m['wall_seconds']) or not finite(m['load_seconds']):raise ValueError('Run times invalid')
    split=m['split'];template=m['template'];run_id=m['run_id']
    if m['purpose']!=('development' if split=='dev' else 'final_report') or m['used_for_parameter_selection'] is not (split=='dev'):raise ValueError('Invalid run purpose')
    env=m['environment']
    if (not isinstance(env,dict) or set(env)!={'python','implementation','system','machine','processor','logical_cpu_count','concurrency'}
        or any(not isinstance(env[k],str) for k in ('python','implementation','system','machine','processor'))
        or type(env['logical_cpu_count']) is not int or env['logical_cpu_count']<1
        or type(env['concurrency']) is not int or env['concurrency']!=1):raise ValueError('Invalid runtime metadata')
    files={'predictions.jsonl','requests.jsonl','source_map.json','summary.json','error_analysis.json','run_started.json'}
    if set(m['artifacts'])!=files:raise ValueError('Incomplete artifact coverage')
    for name,entry in m['artifacts'].items():
        if entry!={k:v for k,v in record(directory/name).items() if k!='path'}:raise ValueError('Artifact mismatch: '+name)
    started=json.loads((directory/'run_started.json').read_text('utf-8'))
    if started!={k:m[k] for k in ('version','run_id','split','template','purpose','source_commit','inputs','started_at','authorization')}:raise ValueError('Start receipt differs')
    questions=load_jsonl(EVAL/f'retrieval_{split}.jsonl');predictions=load_jsonl(directory/'predictions.jsonl')
    sources=json.loads((directory/'source_map.json').read_text('utf-8'))
    validate_predictions(questions,predictions,sources,split,template,run_id)
    requests=load_jsonl(directory/'requests.jsonl');expected=[]
    for row in predictions:
        expected.extend({'question_id':row['question_id'],'run_id':run_id,'split':split,'template':template,
                         'question_sha256':row['question_sha256'],**measure} for measure in row['measurements'])
    if len(requests)!=len(expected):raise ValueError('Request journal coverage differs')
    previous=start
    for event,wanted in zip(requests,expected):
        if set(event)!=set(wanted)|{'recorded_at'} or {k:v for k,v in event.items() if k!='recorded_at'}!=wanted:raise ValueError('Journal and predictions disagree')
        timestamp=instant(event['recorded_at'])
        if not previous<=timestamp<=end:raise ValueError('Request timestamp out of order')
        previous=timestamp
    if not isinstance(m['warmups'],list) or len(m['warmups'])!=3:raise ValueError('Three warmups required')
    for number,warmup in enumerate(m['warmups'],1):
        if set(warmup)!={'repetition','query','timing'} or type(warmup['repetition']) is not int or warmup['repetition']!=number or warmup['query']!=config()['warmup_query']:raise ValueError('Invalid warmup policy')
        t=warmup['timing']
        if set(t)!=set(TIMINGS) or any(not finite(t[k]) for k in TIMINGS) or abs(t['total_seconds']-sum(t[k] for k in TIMINGS[:-1]))>1e-8:raise ValueError('Invalid warmup timing')
    measured=sum(e['total_seconds'] for e in requests)+sum(e['timing']['total_seconds'] for e in m['warmups'])+m['load_seconds']
    if m['wall_seconds']+1e-6<measured or (end-start).total_seconds()+.1<m['wall_seconds']:raise ValueError('Wall timing omits work')
    index=m['index_manifest']
    validate_index_manifest(index,template,m['inputs'])
    producer_before(index['source_commit'],m['started_at'])
    result=summary(questions,predictions,template,split,run_id)
    if canonical(result)!=canonical(json.loads((directory/'summary.json').read_text('utf-8'))):raise ValueError('Saved metrics/latency differ from raw records')
    if canonical(error_analysis(questions,predictions,split))!=canonical(json.loads((directory/'error_analysis.json').read_text('utf-8'))):raise ValueError('Error analysis differs')
    if split=='test':
        grant_path=ROOT/m['authorization']['path']
        if record(grant_path)!=m['authorization']:raise ValueError('Authorization bytes changed')
        grant=json.loads(grant_path.read_text('utf-8'));validate_grant(grant,directory)
        if grant['source_commit']!=m['source_commit'] or grant['inputs']!=m['inputs'] or not instant(grant['prepared_at'])<=start:raise ValueError('Test source or authorization time differs')
    elif m['authorization'] is not None:raise ValueError('Development cannot claim a test grant')
    return result


def choose(development_root):
    root=Path(development_root);runs=[]
    for template in TEMPLATES:
        s=replay(root/template)
        if s['split']!='dev' or s['template']!=template:raise ValueError('Template development run mismatch')
        runs.append({'template':template,'metrics':s['quality']['metrics'],
                     'run_manifest':record(root/template/'run_manifest.json'),'summary':record(root/template/'summary.json')})
    selected=max(runs,key=lambda r:tuple(r['metrics'][n] for n in ('MRR@10','Recall@5','Recall@10'))+(-TEMPLATES.index(r['template']),))
    return {'version':'bm25-selection-1.0','selected_template':selected['template'],'policy':config()['selection'],
            'development_only':True,'test_scores_read_for_selection':False,'development_runs':runs}


def validate_grant(grant,directory,current=False):
    fields={'version','purpose','used_for_parameter_selection','dataset_version','test_sha256','source_commit','inputs',
            'prepared_at','selection','verification','allowed_run_directory','template'}
    if set(grant)!=fields or grant['version']!='bm25-final-report-1.0' or grant['purpose']!='final_report' or grant['used_for_parameter_selection'] is not False:raise ValueError('Invalid test authorization')
    if not re.fullmatch('[0-9a-f]{40}',grant['source_commit']):raise ValueError('Invalid authorization commit')
    producer_before(grant['source_commit'],grant['prepared_at'])
    release=json.loads((EVAL/'dataset_manifest.json').read_text('utf-8'))
    if grant['dataset_version']!=release['dataset_version'] or grant['test_sha256']!=release['test_lock']['sha256'] or release['test_lock']['state']!='locked':raise ValueError('Test lock mismatch')
    if (ROOT/grant['allowed_run_directory']).resolve()!=Path(directory).resolve() or not Path(directory).resolve().is_relative_to(ROOT/'reports/retrieval'):raise ValueError('Unauthorized test directory')
    require_inputs(grant['inputs'],current_sources=current)
    chosen=ROOT/grant['selection']['path'];verification=ROOT/grant['verification']['path']
    if record(chosen)!=grant['selection'] or record(verification)!=grant['verification']:raise ValueError('Selection/verification receipt changed')
    for path in (chosen,verification):
        name=path.resolve().relative_to(ROOT).as_posix()
        raw=subprocess.run(['git','show',grant['source_commit']+':'+name],cwd=ROOT,capture_output=True)
        if raw.returncode or raw.stdout!=path.read_bytes():raise ValueError('Grant receipt was not frozen in the authorized commit')
    selection=json.loads(chosen.read_text('utf-8'))
    root=(ROOT/selection['development_runs'][0]['run_manifest']['path']).parent.parent
    if selection!=choose(root) or grant['template']!=selection['selected_template']:raise ValueError('Selection not derived from all three development runs')
    for run in selection['development_runs']:
        if instant(json.loads((ROOT/run['run_manifest']['path']).read_text('utf-8'))['completed_at'])>instant(grant['prepared_at']):raise ValueError('Development postdates grant')
    receipt=json.loads(verification.read_text('utf-8'))
    if (receipt.get('version')!='bm25-contract-1.0' or receipt.get('status')!='PASS'
        or type(receipt.get('total')) is not int or receipt['total']<30
        or type(receipt.get('passed')) is not int or receipt['passed']!=receipt['total'] or len(receipt['checks'])!=receipt['total']
        or not all(v is True for v in receipt['checks'].values()) or receipt.get('development_replay_checked') is not True):raise ValueError('Incomplete development verification')
    if set(receipt['source_sha256'])!=set(V1_EXECUTION_FILES):raise ValueError('Incomplete verification source coverage')
    if any(receipt['source_sha256'].get(p)!=grant['inputs'][p]['sha256'] for p in V1_EXECUTION_FILES):raise ValueError('Verification source binding differs')
    if instant(receipt['captured_at'])>instant(grant['prepared_at']):raise ValueError('Verification postdates grant')
