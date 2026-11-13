"""Four actual ad-hoc variants of the repaired adapter; not a quality benchmark."""
import argparse,json,subprocess,time
from pathlib import Path
from eval_dataset import ROOT,EVAL,canonical,digest,load_jsonl
from bm25_index import record,write_new,committed
from bm25_retrieval_eval import now,producer_before,instant
import reranker_eval as ev

QUESTION='请检索球员装备安全与守门员球衣颜色的资料段落。'
NAMES=ev.NATIVE+('scripts/verify_task10_live_audit.py',)


def validate(value):
    ev.fields(value,('version','started_at','completed_at','source_commit','source_sha256','config_sha256','question',
                     'packets','environment','index_snapshots','load_seconds','checks','status','passed','total',
                     'actual_embedding_queries','actual_reranker_pairs','new_locked_test_queries','answer_llm_requests','scope'),'audit live receipt')
    if value['version']!='task10-audit-live-1.0' or value['question']!=QUESTION:raise ValueError('Wrong ad-hoc scope')
    producer_before(value['source_commit'],value['started_at'])
    if not instant(value['started_at'])<instant(value['completed_at']):raise ValueError('Live chronology invalid')
    ev.fields(value['source_sha256'],NAMES,'live producer coverage')
    for name in NAMES:
        raw=subprocess.check_output(['git','show',value['source_commit']+':'+name],cwd=ROOT)
        if digest(raw)!=value['source_sha256'][name]:raise ValueError('Live source not bound to producer')
    if value['config_sha256']!=record(ROOT/ev.CONFIG)['sha256']:raise ValueError('Live configuration differs')
    known={r['chunk_id']:r for r in json.loads((ROOT/'reports/retrieval/dense_b0/dev/source_map.json').read_text('utf-8'))}
    ev.fields(value['packets'],ev.METHODS,'actual variants');checks={}
    for m in ev.METHODS:ev.validate_packet(value['packets'][m],QUESTION,m,known,ev.config());checks[m+'_actual_packet_recomputes']=True
    ev.validate_variant_inputs(value['packets']);checks['cross_budget_same_pair_inputs']=True
    ev.validate_runtime_snapshot(value);checks['original_indexes_cpu_embedding_and_hardware_bound']=True
    env=value['environment']
    if env['packages']!=ev.config()['packages'] or env['providers']!=['CPUExecutionProvider'] or env['model_inputs']!=['input_ids','attention_mask']:raise ValueError('Live model runtime differs')
    checks['official_cpu_reranker_environment']=True
    for name,expected in [('actual_embedding_queries',4),('actual_reranker_pairs',140),('new_locked_test_queries',0),('answer_llm_requests',0)]:
        if type(value[name]) is not int or value[name]!=expected:raise ValueError('Live request counter differs')
    if any(digest(q['question'].encode())==digest(QUESTION.encode()) for split in ('dev','test') for q in load_jsonl(EVAL/('retrieval_'+split+'.jsonl'))):raise ValueError('Ad-hoc example overlaps frozen questions')
    checks['four_embeddings140_pairs_no_test_or_answers']=True
    if value['checks']!=checks or not all(checks.values()) or value['status']!='PASS' or value['passed']!=value['total'] or value['total']!=len(checks):raise ValueError('Live receipt checks differ')
    return checks


def capture(output):
    source=committed(ev.SOURCES+ev.INPUTS+('scripts/verify_task10_live_audit.py',));started=now()
    from reranker_live import RerankerRetriever
    from hybrid_live import index_files
    t=time.perf_counter()
    with RerankerRetriever(ev.config()) as engine:
        load_seconds=time.perf_counter()-t;before=engine.before
        packets={m:engine.query(QUESTION,m) for m in ev.METHODS};environment=engine.environment()
    after=index_files()
    checks={m+'_actual_packet_recomputes':True for m in ev.METHODS}
    checks.update(cross_budget_same_pair_inputs=True,original_indexes_cpu_embedding_and_hardware_bound=before==after,
                  official_cpu_reranker_environment=True,four_embeddings140_pairs_no_test_or_answers=True)
    value={'version':'task10-audit-live-1.0','started_at':started,'completed_at':now(),'source_commit':source,
        'source_sha256':{p:record(ROOT/p)['sha256'] for p in NAMES},'config_sha256':record(ROOT/ev.CONFIG)['sha256'],
        'question':QUESTION,'packets':packets,'environment':environment,'index_snapshots':{'before':before,'after':after},
        'load_seconds':load_seconds,'checks':checks,'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),
        'actual_embedding_queries':4,'actual_reranker_pairs':140,'new_locked_test_queries':0,'answer_llm_requests':0,
        'scope':'One non-evaluation question through four real budget variants. Functional checks only; no warmup/latency benchmark, quality scoring or formal test rerun.'}
    validate(value);write_new(output,value);return value


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path);p.add_argument('--replay',type=Path);a=p.parse_args()
    if a.replay:checks=validate(json.loads(a.replay.read_text('utf-8')));print(json.dumps({'status':'PASS','passed':len(checks),'total':len(checks),'new_model_requests':0}));return
    from run_reranker_experiment import new_report
    value=capture(new_report(a.report));print(json.dumps({k:value[k] for k in ('status','passed','total')}))


if __name__=='__main__':main()
