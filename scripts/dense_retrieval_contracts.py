"""Versioned provenance and lifecycle contracts; standard library only."""
from __future__ import annotations
import ast,json,math,re,subprocess
from datetime import datetime,timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
from eval_dataset import ROOT,digest

MANIFEST_FIELDS=set('manifest_version status run_id split purpose used_for_parameter_selection started_at completed_at source_commit config input_snapshots dataset_version corpus_version corpus_sha256 index_manifest_sha256 index_version index_vector_fingerprint index_producer_implementation_sha256 model_artifact model_runtime_before model_runtime_after environment startup_loading_seconds warmups whole_run_wall_seconds query_request_count warmup_request_count llm_generation_requests gold_passed_to_retrieval formal_index_artifacts_unchanged authorization artifacts scope'.split())
START_FIELDS=set('run_id started_at split source_commit input_snapshots authorization'.split())
GRANT_FIELDS=set('authorization_version prepared_at purpose used_for_parameter_selection dataset_version test_sha256 test_locked_at config config_sha256 source_commit input_snapshots development_manifest development_summary development_verification allowed_run_directory formal_test_parameter_choices original_dataset_manifest_not_modified'.split())

def fields(value,names,label):
    if not isinstance(value,dict) or set(value)!=set(names):raise ValueError('Invalid '+label+' fields')

def number(value,positive=False):
    try:return type(value) in (int,float) and math.isfinite(value) and (value>0 if positive else value>=0)
    except OverflowError:return False

def instant(value):
    if not isinstance(value,str):raise ValueError('Timestamp must be text')
    try:t=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as exc:raise ValueError('Invalid timestamp') from exc
    if t.utcoffset() is None:raise ValueError('Timestamp must have timezone')
    return t

def ancestor(commit):
    if not isinstance(commit,str) or not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('Invalid source commit')
    if subprocess.run(['git','merge-base','--is-ancestor',commit,'HEAD'],cwd=ROOT,capture_output=True).returncode:
        raise ValueError('Source commit is not an ancestor of checkout')

@lru_cache(maxsize=512)
def git_blob(commit,path):
    result=subprocess.run(['git','show',commit+':'+path],cwd=ROOT,capture_output=True)
    if result.returncode:raise ValueError('Historical source object unavailable: '+path)
    return result.stdout

@lru_cache(maxsize=32)
def committed_at(commit):
    result=subprocess.run(['git','show','-s','--format=%ct',commit],cwd=ROOT,capture_output=True,text=True)
    if result.returncode:raise ValueError('Historical commit unavailable')
    return datetime.fromtimestamp(int(result.stdout.strip()),timezone.utc)

def recorded_sources(commit,current_sources):
    ancestor(commit)
    module=ast.parse(git_blob(commit,'scripts/dense_retrieval_eval.py'))
    values=[ast.literal_eval(n.value) for n in module.body if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id=='SOURCES' for t in n.targets)]
    if len(values)!=1 or not isinstance(values[0],tuple):raise ValueError('Missing committed source policy')
    names=values[0]
    legacy={'scripts/dense_retrieval_eval.py','scripts/run_dense_retrieval.py','scripts/recompute_dense_retrieval.py',
      'scripts/retrieval_metrics.py','scripts/verify_dense_metric_arithmetic.py','scripts/verify_dense_retrieval_contract.py',
      'scripts/dense_index.py','scripts/dense_telemetry.py','scripts/eval_dataset.py',
      'scripts/validate_eval_dataset.py','scripts/validate_eval_receipt.py'}
    # Read the producer's committed policy. Adding a later helper must not
    # retroactively expand the expected keys of an old immutable snapshot.
    if (any(not isinstance(p,str) or not re.fullmatch(r'scripts/[A-Za-z_0-9]+\.py',p) for p in names)
        or len(names)!=len(set(names)) or not legacy<=set(names)):
        raise ValueError('Unknown committed source snapshot policy')
    return names

def provenance(items,commit,current_sources,data_paths,file_record):
    sources=recorded_sources(commit,current_sources)
    if not isinstance(items,dict) or set(items)!=set(sources)|set(data_paths):raise ValueError('Incomplete historical snapshot')
    for path,record in items.items():
        raw=git_blob(commit,path)
        expected={'path':path,'size_bytes':len(raw),'sha256':digest(raw)}
        if record!=expected:raise ValueError('Snapshot differs from recorded Git object: '+path)
        if path in data_paths and file_record(ROOT/path)!=record:raise ValueError('Frozen data/config differs: '+path)

def source_record(row):
    if not isinstance(row.get('chunk_id'),str) or not re.fullmatch('[0-9A-Za-z_-]+',row['chunk_id']):raise ValueError('Invalid chunk ID')
    url=row.get('source_url')
    if not isinstance(url,str) or len(url)>4096 or re.search(r'\s',url) or urlsplit(url).scheme!='https' or not urlsplit(url).netloc:
        raise ValueError('Invalid source URL')
    lines=row.get('source_lines')
    if not isinstance(lines,list) or len(lines)!=2 or any(type(v) is not int or v<1 for v in lines) or lines[1]<lines[0]:
        raise ValueError('Invalid source line range')
    if type(row.get('law_number')) is not int or not 1<=row['law_number']<=17:raise ValueError('Invalid law number')
    if any(not isinstance(row.get(k),str) or not re.fullmatch('[a-f0-9]{64}',row[k]) for k in ('record_sha256','content_zh_sha256')):
        raise ValueError('Invalid source hash')

def measurement_timing(m):
    observation=m['embedding_observation']
    if not all(number(m[k],True) for k in ('query_embedding_seconds','vector_search_seconds','total_seconds')):
        raise ValueError('Actual request stages must have positive duration')
    if observation['elapsed_seconds']>m['query_embedding_seconds']+1e-7:raise ValueError('HTTP timing exceeds embedding stage')
    if observation['server_load_duration_ns']>observation['server_total_duration_ns']:raise ValueError('Server load exceeds server total')
    if observation['server_total_duration_ns']/1e9>observation['elapsed_seconds']+1e-6:raise ValueError('Server duration exceeds HTTP observation')

def manifest_metadata(m,cfg,original):
    fields(m,MANIFEST_FIELDS,'run manifest')
    if json.dumps(m['config'],sort_keys=True)!=json.dumps(cfg,sort_keys=True):raise ValueError('Run configuration types differ')
    start,end=instant(m['started_at']),instant(m['completed_at'])
    if not committed_at(m['source_commit'])<=start<=end<=datetime.now(timezone.utc):raise ValueError('Invalid run time order')
    for runtime in (m['model_runtime_before'],m['model_runtime_after']):
        fields(runtime,('name','digest','size','size_vram','context_length','runner'),'model runtime')
        model=original['config']['model']
        if (runtime['name']!=model['name'] or runtime['digest']!=model['digest'] or runtime['runner']!='llamacpp'
            or type(runtime['context_length']) is not int or runtime['context_length']!=original['config']['embedding']['num_ctx']
            or type(runtime['size']) is not int or runtime['size']<1 or type(runtime['size_vram']) is not int or runtime['size_vram']!=0):
            raise ValueError('Runtime differs from pinned CPU model')
    env=m['environment'];fields(env,('python','platform','processor','logical_cpus','packages'),'environment')
    if (any(not isinstance(env[k],str) or not env[k].strip() or len(env[k])>1024 for k in ('python','platform','processor'))
        or type(env['logical_cpus']) is not int or env['logical_cpus']<1):raise ValueError('Invalid environment values')
    packages={'numpy':original['config']['storage']['numpy_version'],'chromadb':original['config']['storage']['version'],
              'chroma-hnswlib':original['config']['storage']['hnswlib_version']}
    if env['packages']!=packages:raise ValueError('Runtime dependency versions differ')
    if type(m['query_request_count']) is not int or type(m['warmup_request_count']) is not int:raise ValueError('Invalid request count type')
    for rep,w in enumerate(m['warmups'],1):
        fields(w,('repetition','query','timing','total_seconds'),'warmup')
        if type(w['repetition']) is not int or w['repetition']!=rep:raise ValueError('Invalid warmup repetition')
        if (not number(w['total_seconds'],True) or any(not number(v,True) for v in w['timing'].values())
            or w['total_seconds']+1e-7<sum(w['timing'].values())):raise ValueError('Warmup timing omits stages')
    if not isinstance(m['scope'],str) or len(m['scope'])>512:raise ValueError('Invalid run scope text')

def whole_timing(m,predictions):
    minimum=m['startup_loading_seconds']+sum(w['total_seconds'] for w in m['warmups'])
    minimum+=sum(r['total_seconds'] for p in predictions for r in p['measurements'])
    if m['whole_run_wall_seconds']+1e-6<minimum:raise ValueError('Run wall time omits measured stages')

def grant_metadata(g,release,cfg,config_sha,run_path,source_commit=None,start=None):
    fields(g,GRANT_FIELDS,'test authorization')
    prepared=instant(g['prepared_at']);ancestor(g['source_commit'])
    if (g['authorization_version']!='dense-final-report-1.0' or g['purpose']!='final_report'
        or g['used_for_parameter_selection'] is not False or g['original_dataset_manifest_not_modified'] is not True
        or g['dataset_version']!=release['dataset_version'] or g['test_sha256']!=release['test_lock']['sha256']
        or g['test_locked_at']!=release['test_lock'].get('locked_at') or json.dumps(g['config'],sort_keys=True)!=json.dumps(cfg,sort_keys=True)
        or g['config_sha256']!=config_sha or g['allowed_run_directory']!=run_path):raise ValueError('Invalid test authorization binding')
    if not committed_at(g['source_commit'])<=prepared<=datetime.now(timezone.utc):raise ValueError('Invalid authorization time')
    if source_commit is not None and source_commit!=g['source_commit']:raise ValueError('Authorized code commit differs')
    if start is not None and prepared>instant(start):raise ValueError('Authorization must predate test')
    if not isinstance(g['development_verification'],list) or len(g['development_verification'])!=2:raise ValueError('Two verification receipts required')

def verification_receipts(records,commit,file_record):
    producers={'verify_dense_metric_arithmetic.py':54,'verify_dense_retrieval_contract.py':110};seen=set()
    for record in records:
        path=(ROOT/record['path']).resolve()
        if file_record(path)!=record:raise ValueError('Verification receipt changed')
        value=json.loads(path.read_text('utf-8'));hashes=value.get('source_sha256',{})
        selected=set(hashes)&set(producers)
        if len(selected)!=1 or seen&selected:raise ValueError('Missing/duplicate verification producer')
        producer=next(iter(selected));seen.add(producer)
        checks=value.get('checks');values=list(checks.values()) if isinstance(checks,dict) else [r.get('passed') for r in checks] if isinstance(checks,list) else []
        declared=value.get('checks_total',value.get('check_count'))
        passed=value.get('checks_passed',value.get('passed_checks'))
        if value.get('status')!='PASS' or len(values)<producers[producer] or declared!=len(values) or passed!=len(values) or not all(v is True for v in values):
            raise ValueError('Incomplete verification receipt')
        for name,sha in hashes.items():
            if not isinstance(name,str) or '/' in name or '\\' in name or not name.endswith('.py'):
                raise ValueError('Invalid verification source path')
            if digest(git_blob(commit,'scripts/'+name))!=sha:raise ValueError('Verification code differs from committed producer')
        yield value

def usage_matches(events,manifest,run_path,authorization,release):
    if not isinstance(events,list) or any(not isinstance(e,dict) or not isinstance(e.get('run_id'),str)
        or not re.fullmatch('[a-f0-9]{32}',e['run_id']) or e.get('event') not in ('STARTED','COMPLETED','FAILED') for e in events):return False
    selected=[e for e in events if e['run_id']==manifest['run_id']]
    if len(selected)!=2 or [e['event'] for e in selected]!=['STARTED','COMPLETED']:return False
    expected={'run_id':manifest['run_id'],'run_directory':run_path,'split':'test','purpose':'final_report',
      'used_for_parameter_selection':False,'source_commit':manifest['source_commit'],
      'config_sha256':digest((ROOT/'config/dense_retrieval_b0.json').read_bytes()),
      'test_sha256':release['test_lock']['sha256'],'authorization':authorization}
    if not all(all(e.get(k)==v for k,v in expected.items()) for e in selected):return False
    return selected
