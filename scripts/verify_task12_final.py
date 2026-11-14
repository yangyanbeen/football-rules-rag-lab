"""Task12 current final gate, preserving original evaluations and real human judgments."""
import argparse,io,tarfile
from answer_acceptance import *
from answer_audit_v2 import strict_run

BASELINE='c6cf77c5c0ccab92b097b9bda700dff12219b859'
FOLDER=ROOT/'reports/answer_evaluation_acceptance'
MUTABLE={'README.md','docs/DELIVERY_STATUS.md','docs/PUBLIC_SETUP.md','docs/EXPERIMENT_LOG.md','reports/README.md',
    'reports/all_experiments_summary.csv','reports/resume_evidence.md','data/manifests/experiment_manifest.json','data/manifests/project_file_manifest.json'}


def verify(public_only=False):
    checks={};errors=[]
    def check(name,fn):
        try:
            checks[name]=fn() is True
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as e:checks[name]=False;errors.append({'check':name,'error':type(e).__name__+': '+str(e)})
    with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive','--format=tar',BASELINE],cwd=ROOT))) as arc:
        old={m.name:arc.extractfile(m).read() for m in arc.getmembers() if m.isfile()}
    check('764_previous_public_files_preserved_except_current_navigation',lambda:len(old)==764 and all((ROOT/n).read_bytes()==b for n,b in old.items() if n not in MUTABLE))
    for n in ('docs/EXPERIMENT_LOG.md','reports/resume_evidence.md','reports/all_experiments_summary.csv'):
        check(n+'_append_only',lambda n=n:(ROOT/n).read_bytes().startswith(old[n]))
    registry=read(ROOT/'data/manifests/experiment_manifest.json');previous=json.loads(old['data/manifests/experiment_manifest.json'])
    check('all22_existing_experiment_objects_preserved',lambda:len(previous['experiments'])==22 and registry['experiments'][:22]==previous['experiments'])
    entry=registry['experiments'][-1]
    check('23rd_real_human_acceptance_registered',lambda:len(registry['experiments'])==23 and entry['id']=='TASK-012-HUMAN-ACCEPTANCE' and all(record(ROOT/r['path'])==r for r in entry['artifacts']))
    check('current_supplement_source_is_committed_and_identical',lambda:all(digest(subprocess.check_output(['git','show',entry['source_commit']+':'+n],cwd=ROOT))==h==record(ROOT/n)['sha256'] for n,h in entry['source_sha256'].items()))
    human=read(ROOT/HUMAN);context=strict_human(human)
    check('twelve_explicit_reviews_no_missing_or_uncertain',lambda:human['status']=='REVIEW_COMPLETE' and human['reviewed_samples']==12 and not human['missing_ids'] and not human['unresolved_ids'])
    check('new_human_sample_analysis_independently_recomputes',lambda:canonical(analyze(human))==canonical(read(ROOT/ANALYSIS)))
    check('human_five_metric_denominators_and_zero_refusal_guard',lambda:set(read(ROOT/ANALYSIS)['human_semantic_metrics'])=={'answer_point_coverage','citation_correctness','condition_exception_retention'} and set(read(ROOT/ANALYSIS)['label_based_refusal_metrics'])=={'correct_refusal_rate','false_refusal_rate'} and read(ROOT/ANALYSIS)['label_based_refusal_metrics']['correct_refusal_rate']['value'] is None)
    check('AI_assistance_and_error_biased_sample_disclosed',lambda:'AI supplied' in read(ROOT/ANALYSIS)['review_assistance'] and 'error-prioritized' in read(ROOT/ANALYSIS)['interpretation'])
    old_gate=read(FOLDER/'prior-full-acceptance.json')
    check('original_strict_full_acceptance_ACTUALLY_completed',lambda:old_gate['status']=='PASS' and old_gate['passed']==old_gate['total']==26 and all(v is True for v in old_gate['checks'].values()) and old_gate['task12_fully_accepted'] is True and old_gate['delivery_status']=='COMPLETE' and old_gate['human_receipt']==record(ROOT/HUMAN) and old_gate['source_sha256']==record(ROOT/'scripts/verify_answer_audit_delivery.py')['sha256'])
    for split in ('dev','test'):check(split+'_original_answers_judges_and_metrics_replayed',lambda split=split:strict_run(split,not public_only)['samples']==config()['formal_samples'][split])
    check('original_formal_test_ledger_still_single_completed_run',lambda:[r['event'] for r in rows(DIRECTORY/'test_usage.jsonl')]==['STARTED','COMPLETED'])
    for name in ('cases-final.json','prior-regression.json','public-cases.json'):
        def receipt(name=name):
            v=read(FOLDER/name)
            return v['status']=='PASS' and type(v['passed']) is int and v['passed']==v['total']==len(v['checks']) and all(b is True for b in v['checks'].values()) and v['new_model_requests']==0
        check(name+'_all_actual_checks_pass',receipt)
    check('new_regression_bound_to_current_source_hashes',lambda:all(record(ROOT/n)['sha256']==h for n,h in read(FOLDER/'cases-final.json')['source_sha256'].items()))
    check('public_cases_run_with_python_S',lambda:read(FOLDER/'public-cases.json')['site_packages_disabled'] is True)
    check('catalog_policy_bound_to_frozen_record_and_body_hashes',lambda:all(any(r['chunk_id']==cid and r['record_sha256']==note['record_sha256'] and r['content_zh_sha256']==note['content_zh_sha256'] for r in read(ROOT/'data/manifests/dense_chunk_ids.json')) for cid,note in load_policy().items()))
    check('AI_results_and_human_sample_not_overwritten_or_mixed',lambda:read(ROOT/'reports/answer_quality_results.json')['new_human_answer_judgments']==0 and read(ROOT/ANALYSIS)['human_reviewed_questions']==12)
    if not public_only:
        before=read(ROOT/'.runtime/task12-acceptance/before.json')
        check('all_original_private_corpus_indexes_traces_and_actual_human_ledger_preserved',lambda:all(digest((ROOT/n).read_bytes())==h for n,h in before['private'].items()))
        check('actual_local_ledger_matches_new_public_human_snapshot',lambda:canonical({k:v for k,v in human.items() if k!='captured_at'})==canonical(review.snapshot(context)))
        check('all22_previous_tags_unchanged',lambda:all(line in git('show-ref','--tags').splitlines() for line in before['tags'].splitlines()) and len(before['tags'].splitlines())==22)
        def preview():
            p=ROOT/'.runtime/task12-acceptance/T006-display-final.json';v=read(p)
            from citation_catalog_guard import make_preview
            return canonical(v)==canonical(make_preview('T006')) and v['new_model_requests']==0
        check('actual_derived_catalog_display_preview_verified',preview)
    value={'version':'task12-final-acceptance-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL',
        'passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,
        'task12_fully_accepted':all(checks.values()),'human_reviews':human['reviewed_samples'],'human_ledger_entries':human['ledger_entries'],
        'human_receipt':record(ROOT/HUMAN),'human_quality_analysis':record(ROOT/ANALYSIS),'public_only':public_only,
        'new_model_requests':0,'new_human_judgments':0,'source_sha256':record(__file__)['sha256'],
        'scope':'Task12 evaluation artifacts and genuine human sampling complete; does not assert all answers correct. No corpus/test rewriting or quality gain claim.'}
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--public-only',action='store_true');p.add_argument('--report',required=True);a=p.parse_args()
    v=verify(a.public_only);write_new(ROOT/a.report,v);print(json.dumps({k:v[k] for k in ('status','passed','total','errors','task12_fully_accepted')},ensure_ascii=False));raise SystemExit(v['status']!='PASS')
