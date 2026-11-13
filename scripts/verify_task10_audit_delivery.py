"""Supplemental Task10 gate, preserving the original release and its receipts."""
import argparse,io,json,subprocess,tarfile
from pathlib import Path
from eval_dataset import ROOT,canonical,digest
from bm25_index import record,write_new
from bm25_retrieval_eval import now
import reranker_eval as ev
from verify_reranker_delivery import MUTABLE as INDEXES,strong_manifest,validate_ledger

BASE='e24e5c1b37585fe91047a6c6f64c6bdaf7273291'
DIRECTORY=ROOT/'reports/rechecks/task10-audit-20261113'
MUTABLE=INDEXES|{'scripts/reranker_eval.py','scripts/reranker_live.py','scripts/run_reranker_experiment.py'}


def baseline():
    raw=subprocess.check_output(['git','archive','--format=tar',BASE],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {m.name:archive.extractfile(m).read() for m in archive.getmembers() if m.isfile()}


def accepted(value,total):
    return (value['status']=='PASS' and type(value['passed']) is int and type(value['total']) is int
            and value['passed']==value['total']==len(value['checks'])==total
            and all(v is True for v in value['checks'].values()) and value.get('errors',[])==[])


def receipt(name,total,names):
    value=json.loads((DIRECTORY/name).read_text('utf-8'))
    return accepted(value,total) and all(value['source_sha256'][p]==record(ROOT/p)['sha256'] for p in names)


def verify(output,public_only=False,complete=False):
    checks={};errors=[];old=baseline();summaries={}
    def check(name,fn):
        try:
            checks[name]=bool(fn())
            if not checks[name]:errors.append({'check':name,'error':'Predicate returned false'})
        except Exception as exc:checks[name]=False;errors.append({'check':name,'type':type(exc).__name__,'error':str(exc)})
    check('578_original_files_except_declared_code_and_current_indexes_preserved',lambda:len(old)==578 and all((ROOT/p).read_bytes()==raw for p,raw in old.items() if p not in MUTABLE))
    old_registry=json.loads(old['data/manifests/experiment_manifest.json'])
    registry=json.loads((ROOT/'data/manifests/experiment_manifest.json').read_text('utf-8'))
    check('17_original_experiment_objects_preserved',lambda:len(old_registry['experiments'])==17 and registry['experiments'][:17]==old_registry['experiments'])
    for name in ('docs/EXPERIMENT_LOG.md','reports/all_experiments_summary.csv','reports/resume_evidence.md'):
        check(name+'_original_prefix_preserved',lambda name=name:(ROOT/name).read_bytes().startswith(old[name]))
    def replay(split):summaries[split]=ev.replay(ev.DIRECTORY/split);return True
    from analyze_reranker_support import payload
    for split in ('dev','test'):
        check(split+'_original_ranks_metrics_timings_recompute',lambda split=split:replay(split))
        check(split+'_original_cpu_indexes_and_chronology_bound',lambda split=split:strong_manifest(ev.DIRECTORY/split))
        check(split+'_new_partial_support_diagnostics_recompute',lambda split=split:canonical(payload(split))==canonical(json.loads((DIRECTORY/(split+'_support_diagnostics.json')).read_text('utf-8'))))
    check('one_completed_original_test_matrix_no_new_reservation',validate_ledger)
    def original_final():
        final=json.loads((ROOT/'reports/reranker_results.json').read_text('utf-8'))
        return all(canonical(final[key])==canonical(summaries[split]) for key,split in [('development','dev'),('test','test')]) and final['selected_method_on_dev']==summaries['dev']['selected_on_this_split']=='top40' and summaries['test']['selected_on_this_split'] is None
    check('original_result_and_dev_only_selection_unchanged',original_final)
    check('original18_checks_reproduce14_gaps_and4_valid_controls',lambda:receipt('reproduction-final.json',18,('scripts/verify_task10_audit.py',)))
    check('current27_new_regressions_bind_native_code',lambda:receipt('regressions-final.json',27,ev.NATIVE+('scripts/verify_task10_audit.py',)))
    check('current74_original_contract_checks_bind_native_code',lambda:receipt('contract-final.json',74,ev.NATIVE))
    check('current12_lifecycle_checks_bind_producers',lambda:receipt('lifecycle-final.json',12,('scripts/run_reranker_experiment.py','scripts/reranker_live.py','scripts/verify_reranker_lifecycle.py')))
    def public_receipt(name,total,historical):
        value=json.loads((DIRECTORY/name).read_text('utf-8'))
        ancestor=subprocess.run(['git','merge-base','--is-ancestor',value['checkout_commit'],'HEAD'],cwd=ROOT).returncode==0
        identity=value['checkout_commit']==BASE if historical else value['checkout_commit']!=BASE
        return (accepted(value,total) and value['historical_release'] is historical and value['site_packages_disabled'] is True
                and value['new_model_requests']==value['new_locked_test_queries']==0 and ancestor and identity
                and value['source_sha256']==record(ROOT/'scripts/verify_task10_public_audit.py')['sha256'])
    check('independent_public14_checks_and_rehashed_mutations_rejected',lambda:public_receipt('public-current.json',14,False))
    check('original_release_public35_checks_remain_valid',lambda:public_receipt('historical-release-gate.json',35,True))
    def live_receipt(name,module):
        value=json.loads((DIRECTORY/name).read_text('utf-8'))
        return len(module.validate(value))==8 and all(value['source_sha256'][p]==record(ROOT/p)['sha256'] for p in ev.NATIVE)
    import verify_task10_live_audit as live
    import verify_reranker_cold_start as cold
    check('actual_four_budget_live8_checks_recompute',lambda:live_receipt('live-current.json',live))
    check('actual_isolated_cold8_checks_recompute',lambda:live_receipt('cold-current.json',cold))
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    check('no_private_runtime_models_indexes_corpus_or_dependencies_tracked',lambda:not any(p.startswith(('.runtime/','.models/','.venv/','.tmp/','data/indexes/','data/raw/','data/processed/','third_party/')) for p in tracked))
    if not public_only:
        before=json.loads((ROOT/'.runtime/task10-audit/before.json').read_text('utf-8'))
        check('22_private_index_files_preserved',lambda:len(before['indexes'])==22 and all(digest((ROOT/p).read_bytes())==v for p,v in before['indexes'].items()))
        check('original_human_review_ledger_preserved',lambda:digest((ROOT/'.runtime/eval_review/reviews.jsonl').read_bytes())==before['human_review_sha256'])
        corpus=json.loads((ROOT/'data/manifests/local_data_files.json').read_text('utf-8'))['files']
        check('61_private_corpus_files_preserved',lambda:len(corpus)==61 and all(digest((ROOT/r['path']).read_bytes())==r['sha256'] for r in corpus))
        def model():
            from bge_reranker import HOME,file_sha
            return all((HOME/n).stat().st_size==r['size_bytes'] and file_sha(HOME/n)==r['sha256'] for n,r in ev.config()['files'].items())
        check('five_official_model_files_sha256_match',model)
    if complete:
        for name in ('docs/TASK_10_AUDIT.md','reports/TASK_10_SUPPLEMENT.md'):
            check(name+'_delivered',lambda name=name:(ROOT/name).is_file() and (ROOT/name).stat().st_size>100)
        check('18th_audit_experiment_registered',lambda:len(registry['experiments'])==18 and registry['experiments'][-1]['id']=='TASK-010-AUDIT')
        check('audit_artifact_hashes_match',lambda:all(record(ROOT/r['path'])==r for r in registry['experiments'][-1]['artifacts']))
        def code_identity():
            code=registry['experiments'][-1]['code'];names=ev.NATIVE+('scripts/verify_task10_audit_delivery.py',)
            return code['source_sha256']=={p:record(ROOT/p)['sha256'] for p in names} and code['source_sha256']=={p:digest(subprocess.check_output(['git','show',code['source_commit']+':'+p],cwd=ROOT)) for p in names}
        check('registered_current_source_matches_frozen_commit',code_identity)
    value={'version':'task10-audit-delivery-1.0','captured_at':now(),'baseline_commit':BASE,
           'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),
           'checks':checks,'errors':errors,'public_only':public_only,'complete':complete,
           'source_sha256':record(__file__)['sha256'],'new_model_requests':0,'new_locked_test_queries':0,
           'scope':'Supplemental invariants, receipt replay and preservation; original release gate remains tied to its historical checkout.'}
    write_new(output,value);return value


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--public-only',action='store_true');p.add_argument('--complete',action='store_true');a=p.parse_args()
    from run_reranker_experiment import new_report
    value=verify(new_report(a.report),a.public_only,a.complete);print(json.dumps({k:value[k] for k in ('status','passed','total','errors')}));return 0 if value['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
