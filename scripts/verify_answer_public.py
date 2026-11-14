"""Run Task12 replay and adversarial checks in a public-only Python -S checkout."""
import argparse,copy,json,os,subprocess,sys,uuid
from answer_eval_core import *


def child(complete=False):
    from verify_answer_delivery import validate_run,verify
    checks={};errors=[]
    def check(name,fn):
        try:
            checks[name]=bool(fn())
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error':str(exc)})
    check('python_no_site_and_no_private_runtime',lambda:sys.flags.no_site==1 and all(not(ROOT/p).exists() for p in ('.venv','.models','.runtime','data/processed','data/indexes')))
    for s in ('dev','test'):check(s+'_original_producer_and_all_metrics_replay',lambda s=s:validate_run(s)['samples']==config()['formal_samples'][s])
    qs=questions('test');predictions=rows(DIRECTORY/'test/predictions.jsonl');grades=rows(DIRECTORY/'test/judgments.jsonl')
    original=canonical([predictions,grades]);index=next(i for i,p in enumerate(predictions) if p['status']=='answered')
    def reject(change):
        ps=copy.deepcopy(predictions);gs=copy.deepcopy(grades);change(ps,gs,index)
        try:summarize('test',ps,gs)
        except (ValueError,KeyError,TypeError,IndexError):return True
        return False
    cases={
      'question_binding':lambda p,g,i:p[i].update(question='changed'),
      'unoffered_id':lambda p,g,i:p[i].update(selected_ids=['L99-99']),
      'wrong_source_url':lambda p,g,i:p[i]['citations'][0].update(source_url='https://example.com'),
      'wrong_source_lines':lambda p,g,i:p[i]['citations'][0].update(source_lines=[1,2]),
      'wrong_law':lambda p,g,i:p[i]['citations'][0].update(law_number=17 if p[i]['citations'][0]['law_number']!=17 else 1),
      'upgraded_official_version':lambda p,g,i:p[i]['citations'][0].update(source_revision_verified=True),
      'lost_review_flag':lambda p,g,i:p[i]['citations'][0].update(needs_rule_review=not p[i]['citations'][0]['needs_rule_review']),
      'changed_quote_hash':lambda p,g,i:p[i]['citations'][0].update(quote_sha256='0'*64),
      'wrong_model':lambda p,g,i:p[i].update(model_digest='0'*64),
      'missing_boundary':lambda p,g,i:p[i].update(boundary_preserved=False),
      'over_budget':lambda p,g,i:p[i].update(prompt_utf8_bytes=6201),
      'private_path_escape':lambda p,g,i:p[i]['trace'].update(path='../outside.json'),
      'answered_with_error':lambda p,g,i:p[i].update(error='runtime_error'),
      'incomplete_generation':lambda p,g,i:p[i].update(generation_attempts=[]),
      'integer_as_judge_boolean':lambda p,g,i:g[i]['grade']['points'].__setitem__(0,1),
      'wrong_judge_vector':lambda p,g,i:g[i]['grade'].update(citations=[]),
      'AI_impersonates_human':lambda p,g,i:g[i].update(judgment_kind='human'),
      'missing_sample':lambda p,g,i:p.pop(),
      'duplicate_question':lambda p,g,i:p.__setitem__(1,copy.deepcopy(p[0]))}
    for name,fn in cases.items():check('reject_'+name,lambda fn=fn:reject(fn))
    check('all_original_public_evidence_unchanged',lambda:canonical([predictions,grades])==original)
    gate=None
    if complete:
        gate=verify(ROOT/'reports/answer_evaluation/acceptance/public-inner.json',True,True)
        check('complete_public_delivery_gate',lambda:gate['status']=='PASS')
    return {'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'delivery_gate':gate}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--child',action='store_true');p.add_argument('--complete',action='store_true');p.add_argument('--report');a=p.parse_args()
    if a.child:
        v=child(a.complete);print(json.dumps(v,ensure_ascii=False));return v['status']!='PASS'
    target=ROOT/'.tmp'/('task12-public-'+uuid.uuid4().hex);commit=git('rev-parse','HEAD')
    subprocess.run(['git','worktree','add','--detach',str(target),commit],cwd=ROOT,check=True,capture_output=True)
    env=os.environ.copy();env.update(PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
    command=[sys.executable,'-S','-B','scripts/verify_answer_public.py','--child']+(['--complete'] if a.complete else [])
    proc=subprocess.run(command,cwd=target,env=env,capture_output=True,timeout=600)
    try:value=json.loads(proc.stdout)
    except (ValueError,TypeError):raise RuntimeError(proc.stdout.decode('utf-8')[-1800:]+proc.stderr.decode('utf-8')[-1800:])
    value.update(captured_at=now(),checkout_commit=commit,site_packages_disabled=True,new_model_requests=0,source_sha256=record(__file__)['sha256'])
    write_new(ROOT/a.report,value);print(json.dumps({k:value[k] for k in ('status','passed','total','errors')}));return value['status']!='PASS'


if __name__=='__main__':raise SystemExit(main())
