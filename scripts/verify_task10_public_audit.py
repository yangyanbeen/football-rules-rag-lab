"""Actual independent public checkout; current and historical replay, bad copies."""
import argparse,json,os,subprocess,sys,uuid
from pathlib import Path
from eval_dataset import ROOT
from bm25_index import record,write_new
from bm25_retrieval_eval import now

BASE='e24e5c1b37585fe91047a6c6f64c6bdaf7273291'
CHILD=r'''
import copy,json,sys,subprocess,types
from datetime import datetime,timedelta
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'scripts'))
import reranker_eval as ev
from eval_dataset import canonical,digest
from analyze_reranker_support import payload
from verify_task10_audit import historic
old=historic('scripts/reranker_eval.py');directory=ev.DIRECTORY/'dev';checks={};errors=[];observed={}
def check(name,fn):
 try:checks[name]=bool(fn())
 except Exception as exc:checks[name]=False;errors.append({'check':name,'type':type(exc).__name__,'error':str(exc)})
check('stdlib_only_without_corpus_index_models_packages',lambda:sys.flags.no_site==1 and not any((root/p).exists() for p in ('.venv','.models','data/processed/rag_chunks_zh.jsonl','data/indexes/dense')))
for split in ('dev','test'):
 check(split+'_original_rank_quality_and_timing_replay',lambda split=split:ev.replay(ev.DIRECTORY/split)['split']==split)
 check(split+'_partial_support_supplement_recomputes',lambda split=split:canonical(payload(split))==canonical(json.loads((root/'reports/rechecks/task10-audit-20261113'/(split+'_support_diagnostics.json')).read_text('utf-8'))))
original={n:(directory/n).read_bytes() for n in (*ev.ARTIFACTS,'run_manifest.json')}
def mutate_case(name,change,old_should_accept=True):
 manifest=json.loads(original['run_manifest.json']);start=json.loads(original['run_started.json']);rows=[json.loads(line) for line in original['predictions.jsonl'].decode().splitlines()]
 change(manifest,start,rows)
 try:
  for file,data in [('run_started.json',canonical(start)+b'\n'),('predictions.jsonl',b''.join(canonical(r)+b'\n' for r in rows))]:
   (directory/file).write_bytes(data);manifest['artifacts'][file]={'size_bytes':len(data),'sha256':digest(data)}
  (directory/'run_manifest.json').write_bytes(canonical(manifest)+b'\n')
  accepted=False
  try:old.replay(directory);accepted=True
  except (ValueError,KeyError,TypeError,OSError):pass
  rejected=False
  try:ev.replay(directory)
  except (ValueError,KeyError,TypeError,OSError):rejected=True
  observed[name]={'original_accepted':accepted,'current_rejected':rejected}
  return accepted is old_should_accept and rejected
 finally:
  for file,data in original.items():(directory/file).write_bytes(data)
cases=[
 ('future_complete_time',lambda m,s,r:m.update(completed_at=(datetime.fromisoformat(m['completed_at'])+timedelta(days=365)).isoformat()),True),
 ('wall_duration_differs_from_utc',lambda m,s,r:m.update(wall_seconds=m['wall_seconds']+100.),True),
 ('boolean_concurrency_config',lambda m,s,r:(m['config'].update(concurrency=True),s['config'].update(concurrency=True)),True),
 ('cross_budget_passage_identity',lambda m,s,r:r[0]['variants']['top40']['reranker']['results'][0].update(passage_sha256='3'*64),True),
 ('cross_budget_input_ids_identity',lambda m,s,r:r[0]['variants']['top40']['reranker']['results'][0].update(input_ids_sha256='4'*64),True),
 ('boolean_top10_rank',lambda m,s,r:r[0]['variants']['top20']['results'][0].update(rank=True),True),
 ('unsupported_new_schema_from_old_source',lambda m,s,r:(m.update(version='reranker-run-1.1'),s.update(version='reranker-run-1.1')),False)]
for name,change,accept in cases:check('reject_'+name,lambda name=name,change=change,accept=accept:mutate_case(name,change,accept))
check('original_bytes_restored_after_every_mutation',lambda:all((directory/n).read_bytes()==raw for n,raw in original.items()))
check('original_formal_test_ledger_still_completed_once',lambda:[json.loads(x)['event'] for x in ev.LEDGER.read_text('utf-8').splitlines()]==['STARTED','COMPLETED'])
print(json.dumps({'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'observed':observed,'new_model_requests':0,'new_locked_test_queries':0}))
'''


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--historical',action='store_true');a=p.parse_args()
    from run_reranker_experiment import new_report
    output=new_report(a.report);source=BASE if a.historical else subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    target=ROOT/'.tmp'/('task10-audit-public-'+uuid.uuid4().hex);target.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['git','worktree','add','--detach',str(target),source],cwd=ROOT,check=True,capture_output=True)
    env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['PYTHONDONTWRITEBYTECODE']='1'
    if a.historical:
        command=[sys.executable,'-S','-B','scripts/verify_reranker_delivery.py','--public-only','--complete','--report','reports/historical-task10-gate.json']
    else:
        child=target.parent/(target.name+'-check.py');child.write_text(CHILD,'utf-8')
        command=[sys.executable,'-S','-B',str(child),str(target)]
    proc=subprocess.run(command,cwd=target,env=env,capture_output=True,timeout=600)
    if proc.returncode:raise RuntimeError(proc.stderr.decode('utf-8',errors='replace')[-3000:]+proc.stdout.decode('utf-8',errors='replace')[-3000:])
    result=json.loads((target/'reports/historical-task10-gate.json').read_text('utf-8')) if a.historical else json.loads(proc.stdout)
    result={'version':'task10-audit-public-1.0','captured_at':now(),'historical_release':a.historical,'checkout_commit':source,
            'status':result['status'],'passed':result['passed'],'total':result['total'],'checks':result['checks'],'errors':result['errors'],
            'observed':result.get('observed',{}),'site_packages_disabled':True,'new_model_requests':0,'new_locked_test_queries':0,
            'source_sha256':record(__file__)['sha256'],
            'scope':'Historical release gate' if a.historical else 'Current independent public replay and controlled mutations; original files restored'}
    write_new(output,result);print(json.dumps({k:result[k] for k in ('status','passed','total','errors')}));return 0 if result['status']=='PASS' else 1


if __name__=='__main__':main()
