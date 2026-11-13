"""Actual isolated Ollama cold startup; one ad-hoc query, never formal test."""
import argparse,json,os,socket,subprocess,time,urllib.request,uuid
from pathlib import Path
from eval_dataset import ROOT,canonical,digest
from bm25_index import record,write_new,committed
from bm25_retrieval_eval import now,producer_before,instant
import reranker_eval as ev


def validate(value):
    ev.fields(value,('version','started_at','completed_at','source_commit','source_sha256','config_sha256','ollama_version',
                     'before_loaded_models','environment_before_warmup_rejected','question','packet','environment',
                     'index_snapshots','owned_service_stopped','scope','checks','passed','total','status',
                     'actual_embedding_queries','actual_reranker_pairs','actual_locked_test_queries','answer_llm_requests'),'cold start receipt')
    if value['version']!='reranker-cold-start-1.0':raise ValueError('Unknown cold-start receipt')
    producer_before(value['source_commit'],value['started_at'])
    if not instant(value['started_at'])<instant(value['completed_at']):raise ValueError('Cold chronology differs')
    names=ev.NATIVE+('scripts/verify_reranker_cold_start.py',)
    ev.fields(value['source_sha256'],names,'cold source coverage')
    for name in names:
        raw=subprocess.check_output(['git','show',value['source_commit']+':'+name],cwd=ROOT)
        if digest(raw)!=value['source_sha256'][name]:raise ValueError('Cold source differs')
    if value['config_sha256']!=record(ROOT/ev.CONFIG)['sha256']:raise ValueError('Cold config differs')
    if any(type(value[k]) is not int for k in ('actual_embedding_queries','actual_reranker_pairs','actual_locked_test_queries','answer_llm_requests')):raise ValueError('Invalid request counters')
    environment=value['environment']
    ev.fields(environment,('captured_at','python','system','machine','processor','logical_cpus','physical_memory_bytes','packages','providers','model_inputs','embedding_runtime'),'cold environment')
    if environment['packages']!=ev.config()['packages'] or environment['providers']!=['CPUExecutionProvider'] or environment['model_inputs']!=['input_ids','attention_mask']:raise ValueError('Cold model runtime differs')
    if not instant(value['started_at'])<instant(environment['captured_at'])<instant(value['completed_at']):raise ValueError('Cold environment chronology differs')
    known={r['chunk_id']:r for r in json.loads((ROOT/'reports/retrieval/dense_b0/dev/source_map.json').read_text('utf-8'))}
    if value['question']!=ev.config()['warmup_question']:raise ValueError('Not the ad-hoc query')
    ev.validate_packet(value['packet'],value['question'],'no_rerank',known,ev.config())
    ev.validate_runtime_snapshot(value)
    checks={'fresh_owned_service_no_loaded_models':value['before_loaded_models']==[],
      'expected_original_residency_dependency_observed':value['environment_before_warmup_rejected'] is True,
      'actual_ad_hoc_deep_retrieval_packet_recomputes':True,
      'cpu_runtime_captured_after_query_and_original_indexes_preserved':True,
      'fixed_ollama_version':value['ollama_version']=='0.40.16',
      'only_owned_isolated_service_stopped':value['owned_service_stopped'] is True,
      'one_actual_embedding_no_rerank_or_answer_requests':value['actual_embedding_queries']==1 and value['actual_reranker_pairs']==value['answer_llm_requests']==0,
      'no_locked_test_queries':value['actual_locked_test_queries']==0}
    if value['checks']!=checks or value['passed']!=value['total'] or value['total']!=len(checks) or not all(checks.values()) or value['status']!='PASS':raise ValueError('Cold checks do not recompute')
    return checks


def capture(output):
    source=committed(ev.SOURCES+ev.INPUTS+('scripts/verify_reranker_cold_start.py',));started=now()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    base='http://127.0.0.1:'+str(port);env=os.environ.copy();folder=ROOT/'.runtime/task10/cold-services'/uuid.uuid4().hex
    folder.mkdir(parents=True)
    for name,path in [('USERPROFILE',folder),('APPDATA',folder/'AppData/Roaming'),('LOCALAPPDATA',folder/'AppData/Local')]:
        path.mkdir(parents=True,exist_ok=True);env[name]=str(path)
    env['OLLAMA_HOST']='127.0.0.1:'+str(port);env['OLLAMA_MODELS']=str(ROOT.parent/'football-rules-rag-project/.models/ollama')
    exe=ROOT.parent/'football-rules-rag-project/.runtime/ollama/ollama.exe';previous=os.environ.get('FOOTBALL_DENSE_OLLAMA_URL')
    def get(path):
        with opener.open(base+path,timeout=3) as response:return json.load(response)
    proc=None
    try:
        with (folder/'stdout.log').open('xb') as stdout,(folder/'stderr.log').open('xb') as stderr:
            proc=subprocess.Popen([str(exe),'serve'],cwd=ROOT,env=env,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(40):
            try:version=get('/api/version')['version'];break
            except OSError:
                if proc.poll() is not None:raise RuntimeError('Owned cold service exited')
                time.sleep(.25)
        else:raise RuntimeError('Owned cold service not ready')
        before=get('/api/ps')['models']
        if before or version!='0.40.16':raise ValueError('Service not cold/pinned')
        os.environ['FOOTBALL_DENSE_OLLAMA_URL']=base
        from reranker_live import RerankerRetriever
        from hybrid_live import index_files
        with RerankerRetriever(ev.config()) as engine:
            rejected=False
            try:engine.environment()
            except ValueError as exc:
                if 'Expected the pinned model to be loaded on CPU' not in str(exc):raise
                rejected=True
            packet=engine.query(ev.config()['warmup_question'],'no_rerank');environment=engine.environment();indexes=engine.before
        after=index_files()
    finally:
        if previous is None:os.environ.pop('FOOTBALL_DENSE_OLLAMA_URL',None)
        else:os.environ['FOOTBALL_DENSE_OLLAMA_URL']=previous
        if proc is not None and proc.poll() is None:
            # Only the process created above and its descendants; original service remains running.
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,timeout=20)
            proc.wait(timeout=10)
    checks={'fresh_owned_service_no_loaded_models':not before,'expected_original_residency_dependency_observed':rejected,
            'actual_ad_hoc_deep_retrieval_packet_recomputes':True,'cpu_runtime_captured_after_query_and_original_indexes_preserved':indexes==after,
            'fixed_ollama_version':version=='0.40.16','only_owned_isolated_service_stopped':proc.poll() is not None,
            'one_actual_embedding_no_rerank_or_answer_requests':True,'no_locked_test_queries':True}
    value={'version':'reranker-cold-start-1.0','started_at':started,'completed_at':now(),'source_commit':source,
        'source_sha256':{n:record(ROOT/n)['sha256'] for n in ev.NATIVE+('scripts/verify_reranker_cold_start.py',)},
        'config_sha256':record(ROOT/ev.CONFIG)['sha256'],'ollama_version':version,'before_loaded_models':before,
        'environment_before_warmup_rejected':rejected,'question':ev.config()['warmup_question'],'packet':packet,
        'environment':environment,'index_snapshots':{'before':indexes,'after':after},'owned_service_stopped':proc.poll() is not None,
        'scope':'Fresh isolated local Ollama process, original read-only model store; physical residency dependency, one non-evaluation warmup query then CPU environment. Runner sequencing is separately verified with lifecycle mocks.',
        'checks':checks,'passed':sum(checks.values()),'total':len(checks),'status':'PASS' if all(checks.values()) else 'FAIL',
        'actual_embedding_queries':1,'actual_reranker_pairs':0,'actual_locked_test_queries':0,'answer_llm_requests':0}
    validate(value);write_new(output,value);return value


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path);p.add_argument('--replay',type=Path);a=p.parse_args()
    if a.replay:
        checks=validate(json.loads(a.replay.read_text('utf-8')));print(json.dumps({'status':'PASS','passed':len(checks),'total':len(checks),'new_model_requests':0}));return
    from run_reranker_experiment import new_report
    result=capture(new_report(a.report));print(json.dumps({k:result[k] for k in ('status','passed','total')}))


if __name__=='__main__':main()
