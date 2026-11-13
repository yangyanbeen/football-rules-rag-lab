"""Independent current/historical public checkouts; all original evidence restored."""
import argparse,json,os,subprocess,sys,uuid
from pathlib import Path
from eval_dataset import ROOT,canonical,digest,load_jsonl
from bm25_index import record,write_new
from bm25_retrieval_eval import now
from verify_task11_audit import BASE
import structure_retrieval_eval as ev


def child(complete):
    from verify_task11_audit_delivery import DIRECTORY,validate_parent_receipt
    checks={};errors=[]
    def check(name,fn):
        try:
            checks[name]=bool(fn())
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error':str(exc)})
    for split in ('dev','test'):check(split+'_original_results_replay',lambda split=split:ev.replay(ev.DIRECTORY/split)['split']==split)
    check('new_query_proof_without_model_recomputes',lambda:ev.validate_saved_query(json.loads((DIRECTORY/'query-current.json').read_text('utf-8'))))
    raw=(ev.DIRECTORY/'acceptance/actual-query.json').read_bytes()
    check('legacy_exact_published_query_still_valid',lambda:ev.validate_saved_query(json.loads(raw),raw))
    for name in ('parent-from-current.json','parent-from-legacy.json','parent-fresh.json'):check(name+'_metadata_recomputes',lambda name=name:len(validate_parent_receipt(DIRECTORY/name))==5)
    directory=ev.DIRECTORY/'dev';files=ev.ARTIFACTS+('run_manifest.json',);original={name:(directory/name).read_bytes() for name in files}
    def bad_run(change):
        manifest=json.loads(original['run_manifest.json']);start=json.loads(original['run_started.json']);rows=[json.loads(x) for x in original['predictions.jsonl'].splitlines()]
        change(manifest,start,rows)
        try:
            (directory/'run_started.json').write_bytes(canonical(start)+b'\n');(directory/'predictions.jsonl').write_bytes(b''.join(canonical(r)+b'\n' for r in rows))
            manifest['artifacts']={n:record(directory/n) for n in ev.ARTIFACTS};(directory/'run_manifest.json').write_bytes(canonical(manifest)+b'\n')
            try:ev.replay(directory)
            except (ValueError,KeyError,TypeError):return True
            return False
        finally:
            for name,raw in original.items():(directory/name).write_bytes(raw)
    cases={
        'empty_run_started':lambda m,s,r:s.clear(),
        'false_answer_counter':lambda m,s,r:m.update(answer_llm_requests=False),
        'float_request_count':lambda m,s,r:m.update(actual_embedding_queries=float(m['actual_embedding_queries'])),
        'extra_manifest_field':lambda m,s,r:m.update(content_zh='SYNTHETIC'),
        'float_runtime_context':lambda m,s,r:m['environment']['embedding_runtime'].update(context_length=8192.),
        'impossible_serial_wall':lambda m,s,r:[row.update(timing={k:v*1000 for k,v in row['timing'].items()}) for row in r],
        'producer_record_size':lambda m,s,r:m['inputs']['scripts/structure_retrieval_eval.py'].update(size_bytes=m['inputs']['scripts/structure_retrieval_eval.py']['size_bytes']+1)}
    for name,fn in cases.items():check('reject_rehashed_'+name,lambda fn=fn:bad_run(fn))
    check('python_no_site_and_private_data_absent',lambda:sys.flags.no_site==1 and all(not(ROOT/p).exists() for p in ('.venv','.models','data/processed','data/indexes')))
    check('all_original_bytes_and_test_ledger_restored',lambda:all((directory/n).read_bytes()==raw for n,raw in original.items()) and [r['event'] for r in load_jsonl(ev.LEDGER)]==['STARTED','COMPLETED'])
    gate=None
    if complete:
        from verify_task11_audit_delivery import verify
        gate=verify(ROOT/'reports/rechecks/task11-audit-public-inner.json',True,True)
        check('complete_supplemental_public_gate',lambda:gate['status']=='PASS' and gate['passed']==gate['total'])
    return {'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'delivery_gate':gate}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path);p.add_argument('--historical',action='store_true');p.add_argument('--complete',action='store_true');p.add_argument('--child',action='store_true');a=p.parse_args()
    if a.child:
        value=child(a.complete);print(json.dumps(value));return 0 if value['status']=='PASS' else 1
    from run_structure_comparison import output_path
    output=output_path(a.report);source=BASE if a.historical else subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    target=ROOT/'.tmp'/('task11-audit-public-'+uuid.uuid4().hex)
    subprocess.run(['git','worktree','add','--detach',str(target),source],cwd=ROOT,check=True,capture_output=True)
    env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['PYTHONDONTWRITEBYTECODE']='1'
    command=[sys.executable,'-S','-B','scripts/verify_structure_delivery.py','--public-only','--complete','--report','reports/rechecks/task11-historical-public.json'] if a.historical else [sys.executable,'-S','-B','scripts/verify_task11_public_audit.py','--child']+(['--complete'] if a.complete else [])
    proc=subprocess.run(command,cwd=target,env=env,capture_output=True,timeout=600)
    if proc.returncode:raise RuntimeError(proc.stdout.decode('utf-8')[-3500:]+proc.stderr.decode('utf-8')[-1800:])
    value=json.loads((target/'reports/rechecks/task11-historical-public.json').read_text('utf-8')) if a.historical else json.loads(proc.stdout)
    value.update(version='task11-audit-public-1.0',captured_at=now(),checkout_commit=source,historical_release=a.historical,
        site_packages_disabled=True,new_model_requests=0,new_test_queries=0,source_sha256=record(__file__)['sha256'],complete=a.complete)
    write_new(output,value);print(json.dumps({k:value[k] for k in ('status','passed','total','errors')}));return 0 if value['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
