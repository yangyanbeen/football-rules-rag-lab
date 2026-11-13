"""Strict public replay of Task9 fusion over the original two ranked channels."""
from __future__ import annotations
import json,re,subprocess
from pathlib import Path
from eval_dataset import ROOT,EVAL,digest,canonical,load_jsonl
from bm25_index import record,write_new,committed,RESOURCES
from bm25_retrieval_eval import (replay as replay_bm25,now,instant,producer_before,statistics,finite,
                                  V1_EXECUTION_FILES)
from dense_retrieval_eval import replay as replay_dense,SOURCES as DENSE_SOURCES
from retrieval_metrics import compute_metrics
from rrf import fuse,candidates,parameters,METHODS,CHANNELS

BASE='e5bdb700be09fae983f65ab2f7aae322a2789eda'
CONFIG='config/hybrid_rrf.json'
BASE_DIR=ROOT/'reports/retrieval/hybrid_rrf_b0'
LEDGER=BASE_DIR/'test_usage.jsonl'
NATIVE=('scripts/rrf.py','scripts/hybrid_retrieval_eval.py','scripts/run_hybrid_retrieval.py',
        'scripts/hybrid_live.py','scripts/verify_hybrid_contract.py')
SOURCES=tuple(dict.fromkeys(NATIVE+V1_EXECUTION_FILES+DENSE_SOURCES))


def component_dirs(split):
    if split not in ('dev','test'):raise ValueError('Invalid split')
    return {'dense':ROOT/'reports/retrieval/dense_b0'/split,
            'bm25':ROOT/'reports/retrieval/bm25_b0'/('development/title_body' if split=='dev' else 'test')}


ARTIFACTS=('predictions.jsonl','requests.jsonl','run_started.json','source_map.json','summary.json','error_analysis.json','run_manifest.json')
INPUTS=tuple(dict.fromkeys((CONFIG,)+RESOURCES+('config/dense_index.json','config/dense_retrieval_b0.json','config/rag_b0.json',
 'data/eval/dataset_manifest.json','data/eval/retrieval_dev.jsonl','data/eval/retrieval_test.jsonl','data/eval/human_review_receipt.json',
 'data/manifests/dense_index_manifest.json','data/manifests/dense_chunk_ids.json','data/manifests/bm25_indexes.json',
 'data/manifests/rag_dataset_manifest.json','docs/TECHNICAL_DESIGN.md','docs/DEVELOPMENT_PLAN_AND_REPORT.md')+
 tuple((p/n).relative_to(ROOT).as_posix() for split in ('dev','test') for p in component_dirs(split).values() for n in ARTIFACTS)))


def config(k=None):
    expected={'version':'hybrid-rrf-1.0','k':60,'channel_top_k':10,'output_top_k':10,'channels':['dense','bm25'],
              'bm25_template':'title_body','union_order':'round robin dense first; skip repeated chunk_id',
              'rrf_ties':'exact rational score then chunk_id ascending','warmup_repetitions':3,
              'measured_repetitions':3,'concurrency':1,'cache':False,'test_purpose':'final_report'}
    saved=json.loads((ROOT/CONFIG).read_text('utf-8'))
    if canonical(saved)!=canonical(expected):raise ValueError('Fixed experiment policy changed')
    if k is not None:saved['k']=k
    parameters(saved['k'],saved['output_top_k']);return saved


def snapshots():return {p:record(ROOT/p) for p in SOURCES+INPUTS}


def validate_inputs(items,commit,current=False):
    if not isinstance(items,dict) or set(items)!=set(SOURCES+INPUTS):raise ValueError('Incomplete source/input coverage')
    committed((),commit)
    for name in SOURCES+INPUTS:
        reference=commit if name in SOURCES or name==CONFIG else BASE
        raw=subprocess.check_output(['git','show',reference+':'+name],cwd=ROOT)
        expected={'path':name,'size_bytes':len(raw),'sha256':digest(raw)}
        if canonical(items[name])!=canonical(expected):raise ValueError('Input differs from frozen Git object: '+name)
        if (current or name in INPUTS) and items[name]!=record(ROOT/name):raise ValueError('Input changed: '+name)


def components(split):
    dirs=component_dirs(split);replay_dense(dirs['dense']);replay_bm25(dirs['bm25'])
    rows={name:load_jsonl(path/'predictions.jsonl') for name,path in dirs.items()}
    if {r['question_id'] for r in rows['dense']}!={r['question_id'] for r in rows['bm25']}:raise ValueError('Channel question IDs differ')
    return {name:{r['question_id']:r for r in values} for name,values in rows.items()}


def compare(metrics):
    result={}
    for baseline in ('dense','bm25'):
        diff={key:metrics['rrf']['quality']['metrics'][key]-metrics[baseline]['quality']['metrics'][key]
              for key in ('Recall@5','Recall@10','MRR@10')}
        signs={0 if abs(v)<1e-12 else (1 if v>0 else -1) for v in diff.values()}
        verdict='tied' if signs=={0} else 'superior' if signs<={0,1} else 'inferior' if signs<={0,-1} else 'mixed'
        result[baseline]={'difference':diff,'per_metric':{k:'tied' if abs(v)<1e-12 else 'higher' if v>0 else 'lower' for k,v in diff.items()},'verdict':verdict}
    return result


def summarize(questions,rows,cfg,split,run_id):
    methods={}
    for method in METHODS:
        scored=compute_metrics(questions,[{'question_id':r['question_id'],'results':r['results'][method]} for r in rows])
        methods[method]={'quality':{k:v for k,v in scored.items() if k!='per_question'}}
    labelled={q['question_id']:q for q in questions};answerable=[r for r in rows if labelled[r['question_id']]['answerable']]
    coverage=sum(bool(set(r['candidate_union'])&set(labelled[r['question_id']]['expected_chunk_ids'])) for r in answerable)/len(answerable)
    return {'version':'hybrid-summary-1.0','split':split,'run_id':run_id,'config':cfg,'methods':methods,
            'rrf_vs_single_channels':compare(methods),
            'full_union_diagnostic':{'ranked':False,'max_budget':20,'min_size':min(len(r['candidate_union']) for r in rows),
                  'max_size':max(len(r['candidate_union']) for r in rows),'mean_size':sum(len(r['candidate_union']) for r in rows)/len(rows),
                  'answerable_denominator':len(answerable),'any_support_coverage':coverage,'MRR':None,
                  'scope':'Unranked union coverage only; not an equal-Top10 quality comparison'},
            'latency':{'fusion_only':statistics([m['fusion_seconds'] for r in rows for m in r['measurements']]),
                       'original_channel_totals':{c:statistics([m['total_seconds'] for r in rows for m in r['channels'][c]['measurements']]) for c in CHANNELS},
                       'scope':'Reused channel measurements and new fusion processing measured separately; no synthetic end-to-end sum'},
            'new_channel_retrieval_requests':0,'llm_requests':0,'nDCG_reason':'No graded relevance labels'}


def errors_for(questions,rows,split):
    counts={m:{'miss_at_5':0,'miss_at_10':0} for m in METHODS};cases=[]
    for q,row in zip(questions,rows):
        if not q['answerable']:continue
        gold=set(q['expected_chunk_ids']);ranks={m:[v['chunk_id'] for v in row['results'][m]] for m in METHODS}
        for method,ids in ranks.items():
            counts[method]['miss_at_5']+=int(not gold.intersection(ids[:5]));counts[method]['miss_at_10']+=int(not gold.intersection(ids[:10]))
        if split=='dev':cases.append({'question_id':q['question_id'],'question':q['question'],'expected_chunk_ids':q['expected_chunk_ids'],
                                     'ranked_ids':ranks,'rrf_miss_at_5':not bool(gold.intersection(ranks['rrf'][:5]))})
    return {'scope':'Development cases' if split=='dev' else 'Locked test aggregate only; not used to tune parameters',
            'counts':counts,'development_cases':cases if split=='dev' else None}


def validate_predictions(questions,rows,original,cfg,split,run_id):
    if len(rows)!=len(questions) or len({r['question_id'] for r in rows})!=len(rows):raise ValueError('Question coverage differs')
    for q,row in zip(questions,rows):
        if (set(row)!={'question_id','question_sha256','split','run_id','channels','results','candidate_union','measurements'}
            or row['question_id']!=q['question_id'] or row['question_sha256']!=digest(q['question'].encode())
            or row['split']!=split or row['run_id']!=run_id or set(row['channels'])!=set(CHANNELS)):
            raise ValueError('Invalid prediction identity/schema')
        for c in CHANNELS:
            if canonical(row['channels'][c])!=canonical(original[c][q['question_id']]):raise ValueError('Original channel ranking, score or timing changed')
        channels={c:row['channels'][c]['results'] for c in CHANNELS}
        if any(len(values)>cfg['channel_top_k'] for values in channels.values()):raise ValueError('Candidate budget changed')
        result=fuse(channels,cfg['k'],cfg['output_top_k'])
        if canonical(row['results'])!=canonical(result) or row['candidate_union']!=sorted(candidates(channels)):raise ValueError('Fusion ranking, scores, sources or union differ')
        measures=row['measurements']
        if not isinstance(measures,list) or len(measures)!=3:raise ValueError('Three fusion repetitions required')
        for rep,m in enumerate(measures,1):
            if (set(m)!={'repetition','fusion_seconds','result_sha256'} or type(m['repetition']) is not int or m['repetition']!=rep
                or not finite(m['fusion_seconds']) or m['result_sha256']!=digest(canonical(result))):raise ValueError('Invalid fusion timing/ranking repetition')


def validate_grant(grant,directory,current=False):
    fields={'version','purpose','used_for_parameter_selection','prepared_at','source_commit','inputs','config',
            'development_manifest','development_summary','verification','allowed_run_directory','test_sha256','new_channel_retrieval_requests'}
    if (set(grant)!=fields or grant['version']!='hybrid-final-report-1.0' or grant['purpose']!='final_report'
        or grant['used_for_parameter_selection'] is not False or type(grant['new_channel_retrieval_requests']) is not int
        or grant['new_channel_retrieval_requests']!=0):raise ValueError('Invalid fusion report grant')
    producer_before(grant['source_commit'],grant['prepared_at']);validate_inputs(grant['inputs'],grant['source_commit'],current)
    release=json.loads((EVAL/'dataset_manifest.json').read_text('utf-8'))
    if release['test_lock']['state']!='locked' or grant['test_sha256']!=release['test_lock']['sha256']:raise ValueError('Original test lock differs')
    if (ROOT/grant['allowed_run_directory']).resolve()!=Path(directory).resolve() or Path(directory).resolve()!=BASE_DIR/'test':raise ValueError('Unauthorized fusion test directory')
    if canonical(grant['config'])!=canonical(config(grant['config']['k'])):raise ValueError('Grant config differs')
    for key in ('development_manifest','development_summary','verification'):
        item=grant[key];path=ROOT/item['path']
        if record(path)!=item:raise ValueError('Grant evidence changed')
        raw=subprocess.run(['git','show',grant['source_commit']+':'+item['path']],cwd=ROOT,capture_output=True)
        if raw.returncode or raw.stdout!=path.read_bytes():raise ValueError('Grant evidence was not committed before authorization')
    dev=(ROOT/grant['development_manifest']['path']).parent;s=replay(dev)
    dm=json.loads((dev/'run_manifest.json').read_text('utf-8'))
    if (s['split']!='dev' or record(dev/'summary.json')!=grant['development_summary'] or s['config']!=grant['config']
        or instant(dm['completed_at'])>instant(grant['prepared_at'])):raise ValueError('Development config/time differs')
    receipt=json.loads((ROOT/grant['verification']['path']).read_text('utf-8'))
    if (receipt.get('version')!='hybrid-contract-1.0' or receipt.get('status')!='PASS'
        or type(receipt.get('total')) is not int or receipt['total']<1 or type(receipt.get('passed')) is not int
        or receipt['passed']!=receipt['total'] or len(receipt['checks'])!=receipt['total'] or any(v is not True for v in receipt['checks'].values())
        or receipt.get('development_replay_checked') is not True or set(receipt['source_sha256'])!=set(SOURCES)
        or receipt.get('development_manifest')!=grant['development_manifest']
        or any(receipt['source_sha256'][p]!=grant['inputs'][p]['sha256'] for p in SOURCES)
        or instant(receipt['captured_at'])>instant(grant['prepared_at'])):raise ValueError('Verification does not bind the complete frozen implementation')


def replay(directory):
    directory=Path(directory).resolve()
    if (directory/'failure.json').exists():raise ValueError('Recorded failure cannot be accepted')
    m=json.loads((directory/'run_manifest.json').read_text('utf-8'))
    fields={'version','status','run_id','split','purpose','source_commit','inputs','config','started_at','completed_at',
            'wall_seconds','module_warmups','authorization','artifacts','new_channel_retrieval_requests','llm_requests'}
    if (set(m)!=fields or m['version']!='hybrid-run-1.0' or m['status']!='COMPLETE' or m['split'] not in ('dev','test')
        or not isinstance(m['run_id'],str) or not re.fullmatch('[a-f0-9]{32}',m['run_id'])):raise ValueError('Invalid completed fusion manifest')
    if m['purpose']!=('development' if m['split']=='dev' else 'final_report'):raise ValueError('Run purpose differs')
    for key in ('new_channel_retrieval_requests','llm_requests'):
        if type(m[key]) is not int or m[key]!=0:raise ValueError('Offline fusion scope differs')
    cfg=config(m['config']['k'])
    if canonical(cfg)!=canonical(m['config']):raise ValueError('Fusion configuration differs')
    producer_before(m['source_commit'],m['started_at']);validate_inputs(m['inputs'],m['source_commit'])
    start,end=instant(m['started_at']),instant(m['completed_at'])
    if end<start or not finite(m['wall_seconds']):raise ValueError('Invalid wall timing')
    names={'predictions.jsonl','summary.json','error_analysis.json','run_started.json'}
    if set(m['artifacts'])!=names:raise ValueError('Incomplete fusion artifacts')
    for n in names:
        if m['artifacts'][n]!={k:v for k,v in record(directory/n).items() if k!='path'}:raise ValueError('Fusion artifact changed: '+n)
    started=json.loads((directory/'run_started.json').read_text('utf-8'))
    if canonical(started)!=canonical({k:m[k] for k in ('version','run_id','split','purpose','source_commit','inputs','config','started_at','authorization')}):raise ValueError('Fusion start receipt differs')
    questions=load_jsonl(EVAL/('retrieval_'+m['split']+'.jsonl'));rows=load_jsonl(directory/'predictions.jsonl')
    original=components(m['split']);validate_predictions(questions,rows,original,cfg,m['split'],m['run_id'])
    warmups=m['module_warmups']
    if not isinstance(warmups,list) or len(warmups)!=3 or any(not finite(v) for v in warmups):raise ValueError('Invalid module warmups')
    measured=sum(x['fusion_seconds'] for r in rows for x in r['measurements'])+sum(warmups)
    if m['wall_seconds']+1e-6<measured or (end-start).total_seconds()+.1<m['wall_seconds']:raise ValueError('Wall time omits fusion work')
    result=summarize(questions,rows,cfg,m['split'],m['run_id'])
    if canonical(result)!=canonical(json.loads((directory/'summary.json').read_text('utf-8'))):raise ValueError('Saved fusion metrics differ')
    if canonical(errors_for(questions,rows,m['split']))!=canonical(json.loads((directory/'error_analysis.json').read_text('utf-8'))):raise ValueError('Saved fusion errors differ')
    if m['split']=='test':
        auth=m['authorization']
        if record(ROOT/auth['path'])!=auth:raise ValueError('Fusion authorization changed')
        grant=json.loads((ROOT/auth['path']).read_text('utf-8'));validate_grant(grant,directory)
        if (grant['source_commit']!=m['source_commit'] or grant['inputs']!=m['inputs'] or grant['config']!=cfg
            or instant(grant['prepared_at'])>start):raise ValueError('Fusion grant does not bind this run')
    elif m['authorization'] is not None:raise ValueError('Development cannot claim a test grant')
    return result
