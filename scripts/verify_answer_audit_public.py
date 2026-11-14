"""Public-only Task12 supplemental replay from a committed isolated checkout."""
import argparse,json,os,subprocess,sys,uuid
from answer_eval_core import *


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--child',action='store_true');p.add_argument('--report');a=p.parse_args()
    if a.child:
        from verify_answer_audit import verify
        result=verify(False)
        clean=sys.flags.no_site==1 and all(not(ROOT/n).exists() for n in ('.venv','.models','.runtime','data/processed','data/indexes'))
        result['checks']['python_S_without_models_private_corpus_or_traces']=clean
        import answer_review_v2 as review
        summary=read(ROOT/'reports/answer_evaluation_audit/human-review-status.json')
        result['checks']['public_human_summary_recomputes']=review.validate_public_summary(summary,review.review_context())
        result.update(passed=sum(result['checks'].values()),total=len(result['checks']))
        result['status']='PASS' if all(result['checks'].values()) else 'FAIL'
        print(json.dumps(result,ensure_ascii=False));return result['status']!='PASS'
    if not a.report:raise ValueError('--report required')
    source=git('rev-parse','HEAD');target=ROOT/'.tmp'/('task12-audit-public-'+uuid.uuid4().hex)
    subprocess.run(['git','worktree','add','--detach',str(target),source],cwd=ROOT,check=True,capture_output=True)
    env=os.environ.copy();env.update(PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-S','-B','scripts/verify_answer_audit_public.py','--child'],cwd=target,env=env,capture_output=True,timeout=600)
    try:value=json.loads(result.stdout)
    except (ValueError,TypeError):raise RuntimeError(result.stderr.decode('utf-8')[-2000:]+result.stdout.decode('utf-8')[-1000:])
    value.update(checkout_commit=source,captured_at=now(),site_packages_disabled=True,new_model_requests=0)
    write_new(ROOT/a.report,value);print(json.dumps({k:value[k] for k in ('status','passed','total','errors')},ensure_ascii=False))
    return value['status']!='PASS'


if __name__=='__main__':raise SystemExit(main())
