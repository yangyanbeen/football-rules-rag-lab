"""Task9 audit aggregate and historical byte preservation; no new test run."""
import argparse,json,subprocess
from pathlib import Path
from eval_dataset import ROOT,digest,canonical
from bm25_index import record,write_new
from bm25_retrieval_eval import now
from hybrid_retrieval_eval import replay
from hybrid_live import validate_live_smoke

BASE='8553f390107fc9f38cdefb927fa4f016b996f4bc'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);a=p.parse_args();out=a.report.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'reports'):raise ValueError('Use a new reports file')
    before=json.loads((ROOT/'.runtime/task9-audit/before.json').read_text('utf-8'));checks={};errors=[]
    def check(name,fn):
        try:checks[name]=bool(fn())
        except Exception as exc:checks[name]=False;errors.append({'check':name,'type':type(exc).__name__,'error':str(exc)})
    mutable={'README.md','docs/DELIVERY_STATUS.md','docs/PUBLIC_SETUP.md','docs/RRF_EXPERIMENT.md','docs/EXPERIMENT_LOG.md',
             'reports/README.md','reports/resume_evidence.md','reports/all_experiments_summary.csv',
             'data/manifests/project_file_manifest.json','data/manifests/experiment_manifest.json',
             'scripts/rrf.py','scripts/run_hybrid_retrieval.py','scripts/hybrid_live.py','scripts/verify_hybrid_live.py','scripts/verify_hybrid_delivery.py'}
    check('514_original_files_present',lambda:len(before['tracked'])==514 and all((ROOT/p).is_file() for p in before['tracked']))
    check('original_files_outside_declared_changes_byte_identical',lambda:all(digest((ROOT/p).read_bytes())==v for p,v in before['tracked'].items() if p not in mutable))
    check('all_original_reports_except_three_current_indexes_identical',lambda:all(digest((ROOT/p).read_bytes())==v for p,v in before['tracked'].items() if p.startswith('reports/') and p not in mutable))
    check('original_task9_authorization_and_two_usage_events_identical',lambda:all(digest((ROOT/p).read_bytes())==before['tracked'][p] for p in ('reports/retrieval/hybrid_rrf_b0/test_authorization.json','reports/retrieval/hybrid_rrf_b0/test_usage.jsonl')))
    check('all_22_original_index_files_identical',lambda:len(before['indexes'])==22 and all(digest((ROOT/p).read_bytes())==v for p,v in before['indexes'].items()))
    check('private_human_review_ledger_identical',lambda:digest((ROOT/'.runtime/eval_review/reviews.jsonl').read_bytes())==before['ledger_sha256'])
    files=json.loads((ROOT/'data/manifests/local_data_files.json').read_text('utf-8'))['files']
    check('61_local_corpus_files_identical',lambda:len(files)==61 and all(digest((ROOT/r['path']).read_bytes())==r['sha256'] for r in files))
    old=json.loads(subprocess.check_output(['git','show',BASE+':data/manifests/experiment_manifest.json'],cwd=ROOT))
    current=json.loads((ROOT/'data/manifests/experiment_manifest.json').read_text('utf-8'))
    check('15_original_experiment_objects_preserved',lambda:len(old['experiments'])==15 and current['experiments'][:15]==old['experiments'])
    prefix=subprocess.check_output(['git','show',BASE+':docs/EXPERIMENT_LOG.md'],cwd=ROOT)
    check('original_experiment_log_prefix_preserved',lambda:(ROOT/'docs/EXPERIMENT_LOG.md').read_bytes().startswith(prefix))
    base=ROOT/'reports/rechecks/task9-audit-20261113'
    for name,total in [('regressions-final.json',29),('contract-current.json',56),('delivery-current.json',30)]:
        check(name,lambda name=name,total=total:(lambda r:r['status']=='PASS' and r['passed']==r['total']==len(r['checks'])==total and all(v is True for v in r['checks'].values()))(json.loads((base/name).read_text('utf-8'))))
    check('new_live_receipt_fully_recomputes',lambda:len(validate_live_smoke(json.loads((base/'live-smoke.json').read_text('utf-8'))))==17)
    def dev():
        current=replay(ROOT/'reports/retrieval/task9-audit-20261113/dev');old=replay(ROOT/'reports/retrieval/hybrid_rrf_b0/dev')
        return canonical(current['methods'])==canonical(old['methods']) and current['latency']['fusion_only']['samples']==120
    check('new_dev_40_queries_same_four_method_quality',dev)
    check('forged_live_receipt_rejected_by_full_gate',lambda:json.loads((base/'negative-case-proof.json').read_text('utf-8'))['expected_invalid_receipt_rejected'] is True)
    public=json.loads((base/'public-only-replay.json').read_text('utf-8'))
    check('public_only_three_rank_runs_two_live_receipts_recompute',lambda:public['status']=='PASS' and public['passed']==public['total']==10 and all(v is True for v in public['checks'].values()))
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    check('no_private_data_indexes_dependencies_or_runtime_tracked',lambda:not any(p.startswith(('.runtime/','.tmp/','.venv/','data/indexes/','data/raw/','data/processed/')) for p in tracked))
    value={'version':'task9-audit-preservation-1.0','captured_at':now(),'baseline':BASE,'status':'PASS' if all(checks.values()) else 'FAIL',
           'passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'new_test_fusion_runs':0,'new_locked_test_queries':0,
           'new_development_fusion_measurements':120,'new_ad_hoc_embedding_queries':4,'source_sha256':record(__file__)['sha256']}
    write_new(out,value);print(json.dumps({k:value[k] for k in ('status','passed','total','errors')}))
    return 0 if all(checks.values()) else 1


if __name__=='__main__':raise SystemExit(main())
