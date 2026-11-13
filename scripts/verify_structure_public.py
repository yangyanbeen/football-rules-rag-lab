"""Actual detached Python -S replay and controlled bad copies, never model calls."""
import argparse,copy,json,os,subprocess,sys,uuid
from datetime import datetime,timedelta
from pathlib import Path
from eval_dataset import ROOT,EVAL,canonical,load_jsonl
from bm25_index import record,write_new
from bm25_retrieval_eval import now
import structure_retrieval_eval as ev


def child(complete):
    checks={};errors=[]
    def check(name,fn):
        try:
            checks[name]=bool(fn())
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error':str(exc)})
    def rejects(fn):
        try:fn()
        except (ValueError,TypeError,KeyError):return True
        return False
    for split in ('dev','test'):check(split+'_all_original_ranks_spans_metrics_recompute',lambda split=split:ev.replay(ev.DIRECTORY/split)['split']==split)
    check('no_private_data_model_indexes_or_site_packages',lambda:all(not(ROOT/p).exists() for p in ('.models','.venv','data/processed','data/indexes')) and sys.flags.no_site==1)
    m=ev.mapping();q=load_jsonl(EVAL/'retrieval_dev.jsonl')[0];packet=load_jsonl(ev.DIRECTORY/'dev/predictions.jsonl')[0]
    def mutated(fn):
        row=copy.deepcopy(packet);fn(row);return rejects(lambda:ev.summarize([q],[row],'dev',m))
    mutations={
      'boolean_dense_rank':lambda r:r['channels']['base']['dense'][0].update(rank=True),
      'nonfinite_distance':lambda r:r['channels']['child']['dense'][0].update(distance=float('nan')),
      'altered_rrf_score':lambda r:r['rankings']['child'][0].update(score=9.),
      'wrong_source_id':lambda r:r['channels']['child']['dense'][0].update(chunk_id='UNKNOWN'),
      'boolean_embedding_inputs':lambda r:r['embedding_observation'].update(inputs=True),
      'omitted_embedding_wall':lambda r:r['timing'].update(total_seconds=.000001),
      'wrong_question_hash':lambda r:r.update(question_sha256='0'*64),
      'unknown_extra_body_field':lambda r:r.update(content_zh='UNEXPECTED'),
      'missing_candidate':lambda r:r['channels']['base']['dense'].pop()}
    for name,fn in mutations.items():check('reject_'+name,lambda fn=fn:mutated(fn))
    directory=ev.DIRECTORY/'dev';path=directory/'run_manifest.json';original=path.read_bytes()
    def manifest_bad(fn):
        value=json.loads(original);fn(value)
        try:path.write_bytes(canonical(value)+b'\n');return rejects(lambda:ev.replay(directory))
        finally:path.write_bytes(original)
    for name,fn in {
      'future_time':lambda v:v.update(completed_at=(datetime.fromisoformat(v['completed_at'])+timedelta(days=365)).isoformat()),
      'wall_clock_conflict':lambda v:v.update(wall_seconds=v['wall_seconds']+90),
      'gpu_runtime':lambda v:v['environment']['embedding_runtime'].update(size_vram=1),
      'changed_index_snapshot':lambda v:next(iter(v['index_snapshots']['after'].values())).update(sha256='0'*64)
    }.items():check('reject_'+name,lambda fn=fn:manifest_bad(fn))
    check('manifest_restored_exactly',lambda:path.read_bytes()==original)
    check('test_ledger_still_one_completed_matrix',lambda:[r['event'] for r in load_jsonl(ev.LEDGER)]==['STARTED','COMPLETED'])
    if complete:
        from verify_structure_delivery import verify
        value=verify(ROOT/'reports/rechecks/task11-public-inner.json',True,True)
        check('complete_public_delivery_gate',lambda:value['status']=='PASS' and value['passed']==value['total'])
    return {'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'delivery_gate':value if complete else None}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path);p.add_argument('--complete',action='store_true');p.add_argument('--child',action='store_true');a=p.parse_args()
    if a.child:
        result=child(a.complete);print(json.dumps(result));return 0 if result['status']=='PASS' else 1
    from run_structure_comparison import output_path
    output=output_path(a.report);source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    target=ROOT/'.tmp'/('task11-public-'+uuid.uuid4().hex)
    subprocess.run(['git','worktree','add','--detach',str(target),source],cwd=ROOT,check=True,capture_output=True)
    env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['PYTHONDONTWRITEBYTECODE']='1'
    command=[sys.executable,'-S','-B','scripts/verify_structure_public.py','--child']+(['--complete'] if a.complete else [])
    proc=subprocess.run(command,cwd=target,env=env,capture_output=True,timeout=600)
    if proc.returncode:raise RuntimeError(proc.stdout.decode('utf-8')[-4000:]+proc.stderr.decode('utf-8')[-2000:])
    result=json.loads(proc.stdout);result.update(version='structure-public-replay-1.0',captured_at=now(),checkout_commit=source,
       source_sha256=record(__file__)['sha256'],site_packages_disabled=True,new_model_requests=0,new_test_queries=0,
       scope='Actual independent public checkout; source/body/model absence checked. Public metadata cannot recompute model embeddings or private tokenizer counts.',complete=a.complete)
    write_new(output,result);print(json.dumps({k:result[k] for k in ('status','passed','total','errors')}))


if __name__=='__main__':raise SystemExit(main())
