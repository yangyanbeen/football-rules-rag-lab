"""Independent detached checkout, python -S, replay and deliberately bad copies."""
import argparse,json,os,subprocess,sys,uuid
from pathlib import Path
from eval_dataset import ROOT
from bm25_index import write_new,record
from bm25_retrieval_eval import now

CHILD=r'''
import copy,json,sys,subprocess,hashlib
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'scripts'))
import reranker_eval as ev
from verify_reranker_delivery import strong_manifest
from eval_dataset import canonical,digest
directory=ev.DIRECTORY/'dev';checks={};errors=[]
def check(name,fn):
 try:checks[name]=bool(fn())
 except Exception as exc:checks[name]=False;errors.append({'check':name,'type':type(exc).__name__,'error':str(exc)})
check('no_private_corpus_model_index_or_site_packages',lambda:not any((root/p).exists() for p in ('data/processed/rag_chunks_zh.jsonl','data/indexes/dense','.models/bge-reranker-base','.venv')) and sys.flags.no_site==1)
check('dev_all_four_method_results_recompute',lambda:ev.replay(directory)['split']=='dev')
check('dev_original_index_and_device_metadata_recompute',lambda:strong_manifest(directory))
if '--test' in sys.argv:
 check('test_all_four_method_results_recompute',lambda:ev.replay(ev.DIRECTORY/'test')['split']=='test')
 check('test_original_index_and_device_metadata_recompute',lambda:strong_manifest(ev.DIRECTORY/'test'))
 from verify_reranker_delivery import validate_ledger
 check('test_single_owned_start_completed_ledger',validate_ledger)
 from verify_reranker_cold_start import validate as validate_cold
 check('physical_isolated_cold_start_receipt_recomputes',lambda:len(validate_cold(json.loads((ev.DIRECTORY/'acceptance/cold-start-actual.json').read_text('utf-8'))))==8)
 def current_receipt(name,count,source):
  r=json.loads((ev.DIRECTORY/'acceptance'/name).read_text('utf-8'))
  return r['status']=='PASS' and r['passed']==r['total']==len(r['checks'])==count and all(v is True for v in r['checks'].values()) and all(r['source_sha256'][p]==digest((root/p).read_bytes()) for p in source)
 check('current_cold_start_and_output_regressions12_pass',lambda:current_receipt('cold-start-regressions.json',12,('scripts/run_reranker_experiment.py','scripts/verify_reranker_lifecycle.py','scripts/reranker_live.py')))
 check('current_contract74_binds_delivered_native_code',lambda:current_receipt('contract-current.json',74,ev.NATIVE))
files={n:(directory/n).read_bytes() for n in (*ev.ARTIFACTS,'run_manifest.json')}
original=json.loads(files['run_manifest.json'])
def wrong(name,mutate,rehash=True):
 value=json.loads(files[name]) if not name.endswith('.jsonl') else [json.loads(x) for x in files[name].decode().splitlines()]
 mutate(value)
 data=(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n').encode() if not name.endswith('.jsonl') else b''.join(canonical(r)+b'\n' for r in value)
 try:
  (directory/name).write_bytes(data)
  if rehash and name!='run_manifest.json':
   m=copy.deepcopy(original);m['artifacts'][name]={'size_bytes':len(data),'sha256':digest(data)}
   (directory/'run_manifest.json').write_text(json.dumps(m,ensure_ascii=False)+'\n','utf-8')
  try:ev.replay(directory);strong_manifest(directory)
  except (ValueError,TypeError,KeyError,OSError):return True
  return False
 finally:
  (directory/name).write_bytes(files[name]);(directory/'run_manifest.json').write_bytes(files['run_manifest.json'])
cases=[
 ('raw_hash_mismatch','predictions.jsonl',lambda v:v[0].update(question_id='wrong'),False),
 ('question_count','predictions.jsonl',lambda v:v.pop(),True),
 ('duplicate_question','predictions.jsonl',lambda v:v[1].update(question_id=v[0]['question_id']),True),
 ('rotating_order','predictions.jsonl',lambda v:v[0]['order'].reverse(),True),
 ('missing_variant','predictions.jsonl',lambda v:v[0]['variants'].pop('top40'),True),
 ('forged_top80_from20','predictions.jsonl',lambda v:v[0]['variants'].update(top80=copy.deepcopy(v[0]['variants']['top20'])),True),
 ('fulltext_in_packet','predictions.jsonl',lambda v:v[0]['variants']['top20'].update(content_zh='FORBIDDEN'),True),
 ('changed_reranker_logit_sort','predictions.jsonl',lambda v:v[0]['variants']['top20']['reranker']['results'][0].update(score=-999.),True),
 ('changed_rrf_score','predictions.jsonl',lambda v:v[0]['variants']['no_rerank']['before'][0].update(score=.8),True),
 ('omitted_batch','predictions.jsonl',lambda v:v[0]['variants']['top20']['reranker']['batches'].pop(),True),
 ('fabricated_token_count','predictions.jsonl',lambda v:v[0]['variants']['top20']['reranker']['results'][0].update(used_tokens=1),True),
 ('wrong_source_map','source_map.json',lambda v:v[0].update(source_url='https://example.com/forged'),True),
 ('quality_counter','summary.json',lambda v:v['methods']['top20']['quality']['metrics'].update(MRR=1.),True),
 ('false_ndcg','summary.json',lambda v:v.update(**{'nDCG@10':1.}),True),
 ('latency_p95','summary.json',lambda v:v['methods']['top20']['latency']['total_seconds'].update(P95_ms=1.),True),
 ('error_count','error_analysis.json',lambda v:v['counts']['top20'].update(miss_at_5=999),True),
 ('unknown_manifest_field','run_manifest.json',lambda v:v.update(extra='unexpected'),True),
 ('uncommitted_source','run_manifest.json',lambda v:v.update(source_commit='0'*40),True),
 ('fake_wall_duration','run_manifest.json',lambda v:v.update(wall_seconds=v['wall_seconds']+100),True),
 ('reranker_gpu_provider','run_manifest.json',lambda v:v['environment'].update(providers=['CUDAExecutionProvider']),True),
 ('embedding_gpu','run_manifest.json',lambda v:v['environment']['embedding_runtime'].update(size_vram=1024),True),
 ('wrong_embedding_digest','run_manifest.json',lambda v:v['environment']['embedding_runtime'].update(digest='0'*64),True),
 ('false_hardware_cpu','run_manifest.json',lambda v:v['environment'].update(logical_cpus=True),True),
 ('wrong_original_index_paths','run_manifest.json',lambda v:[v['index_snapshots'][side].update(fake=v['index_snapshots'][side].pop(next(iter(v['index_snapshots'][side])))) for side in ('before','after')],True),
 ('wrong_both_index_hashes','run_manifest.json',lambda v:[item.update(sha256='0'*64) for side in v['index_snapshots'].values() for item in side.values()],True)]
for name,file,mutate,rehash in cases:check('reject_'+name,lambda file=file,mutate=mutate,rehash=rehash:wrong(file,mutate,rehash))
check('all_copies_restored_after_negative_cases',lambda:all((directory/n).read_bytes()==raw for n,raw in files.items()))
print(json.dumps({'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'new_model_requests':0}))
'''


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--include-test',action='store_true');a=p.parse_args()
    from run_reranker_experiment import new_report
    output=new_report(a.report);source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    target=ROOT/'.tmp'/('task10-public-'+uuid.uuid4().hex);target.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['git','worktree','add','--detach',str(target),source],cwd=ROOT,check=True,capture_output=True)
    child=target.parent/(target.name+'-checks.py');child.write_text(CHILD,'utf-8')
    env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['PYTHONDONTWRITEBYTECODE']='1'
    command=[sys.executable,'-S','-B',str(child),str(target)]+(['--test'] if a.include_test else [])
    proc=subprocess.run(command,cwd=target,env=env,capture_output=True,timeout=600)
    if proc.returncode:raise RuntimeError(proc.stderr.decode('utf-8',errors='replace')[-3000:])
    result=json.loads(proc.stdout);result.update({'version':'reranker-public-replay-1.0','captured_at':now(),
        'checkout_commit':source,'site_packages_disabled':True,'includes_test':a.include_test,
        'scope':'Independent public files only; negative cases modify disposable copies and restore them, never rerun models or formal test.',
        'source_sha256':record(__file__)['sha256']})
    write_new(output,result);print(json.dumps({k:result[k] for k in ('status','passed','total','errors')}));return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
