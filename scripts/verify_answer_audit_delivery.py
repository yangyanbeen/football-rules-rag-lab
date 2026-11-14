"""Current Task12 supplemental engineering gate; human completion is independently required."""
import argparse,io,subprocess,tarfile
from answer_eval_core import *
from answer_audit_v2 import strict_run
import answer_review_v2 as review

BASELINE='cd2e034f85f0018f25ab82024047259e2513c458'
FOLDER=ROOT/'reports/answer_evaluation_audit'
MUTABLE={'README.md','docs/DELIVERY_STATUS.md','docs/PUBLIC_SETUP.md','reports/README.md',
 'docs/EXPERIMENT_LOG.md','reports/all_experiments_summary.csv','reports/resume_evidence.md',
 'data/manifests/experiment_manifest.json','data/manifests/project_file_manifest.json'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True)
    p.add_argument('--public-only',action='store_true');p.add_argument('--require-complete',action='store_true');a=p.parse_args()
    checks={};errors=[]
    def check(name,fn):
        try:
            checks[name]=fn() is True
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as e:checks[name]=False;errors.append({'check':name,'error':type(e).__name__+': '+str(e)})
    raw=subprocess.check_output(['git','archive','--format=tar',BASELINE],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as arc:old={m.name:arc.extractfile(m).read() for m in arc.getmembers() if m.isfile()}
    check('736_previous_public_files_preserved_except_current_navigation',lambda:len(old)==736 and all((ROOT/n).read_bytes()==v for n,v in old.items() if n not in MUTABLE))
    for name in ('docs/EXPERIMENT_LOG.md','reports/resume_evidence.md','reports/all_experiments_summary.csv'):
        check(name+'_append_only',lambda name=name:(ROOT/name).read_bytes().startswith(old[name]))
    registry=read(ROOT/'data/manifests/experiment_manifest.json');previous=json.loads(old['data/manifests/experiment_manifest.json'])
    check('21_prior_experiment_objects_preserved',lambda:len(previous['experiments'])==21 and registry['experiments'][:21]==previous['experiments'])
    check('all21_prior_experiment_artifacts_unchanged',lambda:all(record(ROOT/r['path'])==r for e in previous['experiments'] for r in e.get('artifacts',[])))
    entry=registry['experiments'][-1]
    check('22nd_audit_entry_has_actual_artifacts',lambda:len(registry['experiments'])==22 and entry['id']=='TASK-012-AUDIT' and all(record(ROOT/r['path'])==r for r in entry['artifacts']))
    check('supplement_sources_committed_and_identical',lambda:all(digest(subprocess.check_output(['git','show',entry['source_commit']+':'+n],cwd=ROOT))==h==record(ROOT/n)['sha256'] for n,h in entry['source_sha256'].items()))
    for s in ('dev','test'):check(s+'_strict_unchanged_replay',lambda s=s:strict_run(s,not a.public_only)['samples']==config()['formal_samples'][s])
    def receipt(name):
        v=read(FOLDER/name)
        return v['status']=='PASS' and type(v['passed']) is int and v['passed']==v['total']==len(v['checks']) and all(b is True for b in v['checks'].values())
    for name in ('regression-final.json','http-review-final.json','public-final.json','legacy-contract.json','independent-arithmetic.json','legacy-delivery.json','legacy-public.json'):
        check(name+'_actual_pass',lambda name=name:receipt(name))
    check('regression_bound_to_current_sources',lambda:all(record(ROOT/n)['sha256']==h for n,h in read(FOLDER/'regression-final.json')['source_sha256'].items()))
    check('zero_new_model_requests_in_audit',lambda:all(read(FOLDER/n)['new_model_requests']==0 for n in ('regression-final.json','public-final.json','http-review-final.json')))
    check('public_replay_uses_python_S',lambda:read(FOLDER/'public-final.json')['site_packages_disabled'] is True)
    check('test_ledger_remains_single_completed_run',lambda:[r['event'] for r in rows(DIRECTORY/'test_usage.jsonl')]==['STARTED','COMPLETED'])
    human=read(FOLDER/'human-review-status.json');context=review.review_context()
    check('human_summary_recomputes_without_private_names',lambda:review.validate_public_summary(human,context))
    check('formal_AI_metrics_and_human_results_kept_separate',lambda:read(ROOT/'reports/answer_quality_results.json')['new_human_answer_judgments']==0 and human['judgment_kind']=='human_explicit_form')
    if not a.public_only:
        before=read(ROOT/'.runtime/task12-audit/before.json')
        check('original_corpus_indexes_all180_private_traces_and_old_human_ledger_preserved',lambda:all(digest((ROOT/n).read_bytes())==h for n,h in before['private'].items()))
        check('public_human_receipt_matches_live_private_ledger',lambda:canonical({k:v for k,v in human.items() if k!='captured_at'})==canonical(review.snapshot(context)))
        initial=dict(line.split(' ',1)[::-1] for line in before['tags'].splitlines())
        current=dict(line.split(' ',1)[::-1] for line in git('show-ref','--tags').splitlines())
        check('all21_original_tags_preserved',lambda:len(initial)==21 and all(current.get(k)==v for k,v in initial.items()))
    full=all(checks.values()) and human['status']=='REVIEW_COMPLETE'
    value={'version':'answer-audit-delivery-1.1','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL',
        'passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'new_model_requests':0,
        'source_sha256':record(__file__)['sha256'],'human_review_status':human['status'],
        'reviewed_samples':human['reviewed_samples'],'required_samples':12,'task12_fully_accepted':full,
        'delivery_status':'COMPLETE' if full else 'HUMAN_REVIEW_PENDING' if all(checks.values()) else 'ENGINEERING_FAILED',
        'scope':'Engineering PASS cannot substitute for the original human citation sampling requirement.'}
    write_new(ROOT/a.report,value);print(json.dumps({k:value[k] for k in ('status','passed','total','errors','delivery_status','task12_fully_accepted')},ensure_ascii=False))
    return 1 if value['status']!='PASS' else 2 if a.require_complete and not full else 0


if __name__=='__main__':raise SystemExit(main())
