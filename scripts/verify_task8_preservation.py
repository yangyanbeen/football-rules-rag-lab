"""Task8 audit preservation and evidence aggregate, without new test retrieval."""
import argparse,json,subprocess
from pathlib import Path
from bm25_index import ROOT,record,write_new
from bm25_retrieval_eval import now,replay
from compare_bm25_segmentation import replay_comparison
from eval_dataset import digest,load_jsonl


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    out=a.report.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'reports'):raise ValueError('Use new reports JSON')
    before=json.loads((ROOT/'.runtime/task8-audit/before.json').read_text('utf-8'))
    checks={};errors=[]
    def check(name,fn):
        try:checks[name]=bool(fn())
        except Exception as exc:checks[name]=False;errors.append({'check':name,'type':type(exc).__name__,'error':str(exc)})
    def unchanged(path):return digest((ROOT/path).read_bytes())==before['tracked'][path]
    mutable={'README.md','docs/DELIVERY_STATUS.md','docs/PUBLIC_SETUP.md','docs/BM25_RETRIEVAL.md',
             'docs/EXPERIMENT_LOG.md','reports/README.md','reports/resume_evidence.md','reports/all_experiments_summary.csv',
             'data/manifests/experiment_manifest.json','data/manifests/project_file_manifest.json',
             'scripts/bm25_retrieval_eval.py','scripts/run_bm25_retrieval.py','scripts/compare_bm25_segmentation.py','scripts/verify_bm25_delivery.py'}
    check('all_original_files_present',lambda:len(before['tracked'])==446 and all((ROOT/p).is_file() for p in before['tracked']))
    check('all_original_files_outside_declared_changes_unchanged',lambda:all(unchanged(p) for p in before['tracked'] if p not in mutable))
    check('authority_documents_and_original_validator_unchanged',lambda:all(unchanged(p) for p in ('docs/TECHNICAL_DESIGN.md','docs/DEVELOPMENT_PLAN_AND_REPORT.md','docs/UPSTREAM_VERSION.md','scripts/validate_eval_dataset.py')))
    report_exceptions={'reports/README.md','reports/resume_evidence.md','reports/all_experiments_summary.csv'}
    check('all_original_reports_and_evaluation_bytes_unchanged',lambda:all(unchanged(p) for p in before['tracked'] if p.startswith(('reports/','data/eval/')) and p not in report_exceptions))
    check('all_original_task8_scope_and_resources_unchanged',lambda:all(unchanged(p) for p in before['tracked'] if p.startswith('config/bm25_') or p in ('docs/TASK_08_SCOPE.md','docs/TASK_08_SEGMENTATION_SUPPLEMENT.md','data/manifests/bm25_indexes.json')))
    check('20_original_private_index_files_unchanged',lambda:len(before['indexes'])==20 and all(digest((ROOT/p).read_bytes())==v for p,v in before['indexes'].items()))
    check('private_human_review_ledger_unchanged',lambda:digest((ROOT/'.runtime/eval_review/reviews.jsonl').read_bytes())==before['ledger_sha256'])
    local=json.loads((ROOT/'data/manifests/local_data_files.json').read_text('utf-8'))['files']
    check('61_local_corpus_files_unchanged',lambda:len(local)==61 and all(record(ROOT/r['path'])=={k:r[k] for k in ('path','size_bytes','sha256')} for r in local))
    old=json.loads(subprocess.check_output(['git','show',before['base_commit']+':data/manifests/experiment_manifest.json'],cwd=ROOT))
    current=json.loads((ROOT/'data/manifests/experiment_manifest.json').read_text('utf-8'))
    check('13_original_experiment_objects_preserved',lambda:len(old['experiments'])==13 and current['experiments'][:13]==old['experiments'])
    prefix=subprocess.check_output(['git','show',before['base_commit']+':docs/EXPERIMENT_LOG.md'],cwd=ROOT)
    check('original_experiment_log_prefix_preserved',lambda:(ROOT/'docs/EXPERIMENT_LOG.md').read_bytes().startswith(prefix))
    ledger=ROOT/'reports/retrieval/bm25_b0/test_usage.jsonl'
    check('original_test_ledger_two_events_and_exact_bytes',lambda:unchanged(ledger.relative_to(ROOT).as_posix()) and [r['event'] for r in load_jsonl(ledger)]==['STARTED','COMPLETED'])
    acceptance=ROOT/'reports/rechecks/task8-audit-20261112'
    for name,total in [('regressions-current.json',32),('contract.json',74),('portability.json',8),('delivery-restored-current.json',35)]:
        check(name,lambda name=name,total=total:(lambda r:r['status']=='PASS' and r['passed']==r['total']==total and all(v is True for v in r['checks'].values()))(json.loads((acceptance/name).read_text('utf-8'))))
    port=json.loads((acceptance/'portability.json').read_text('utf-8'))
    def development():
        current=replay(ROOT/port['actual_development_directory'])
        original=replay(ROOT/'reports/retrieval/bm25_b0/development/title_body')
        return current['quality']['metrics']==original['quality']['metrics'] and current['latency']['all']['total_seconds']['samples']==120
    check('actual_restored_dev_40_questions_same_quality',development)
    segroot=ROOT/'reports/retrieval/task8-audit-20261112'
    def segmentation():
        runs=[replay_comparison(segroot/('segmentation-dev-'+str(n))) for n in (1,2)]
        old=replay_comparison(ROOT/'reports/retrieval/bm25_b0/segmentation-dev')
        manifests=[json.loads((segroot/('segmentation-dev-'+str(n))/'manifest.json').read_text('utf-8')) for n in (1,2)]
        return (all(s['quality']['metrics']==old['quality']['metrics'] and s['quality']['questions']==40 and s['latency']['all']['total_seconds']['samples']==120 for s in runs)
                and len({m['index']['path'] for m in manifests})==2)
    check('two_repeatable_segmentation_dev_runs_same_quality_distinct_indexes',segmentation)
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    check('no_private_indexes_dependencies_or_corpus_tracked',lambda:not any(p.startswith(('.runtime/','.tmp/','.venv/','data/indexes/','data/processed/','data/raw/')) for p in tracked))
    result={'version':'task8-audit-preservation-1.0','captured_at':now(),'baseline':before['base_commit'],
            'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),
            'checks':checks,'errors':errors,'new_locked_test_retrievals':0,'new_development_runs':3,
            'new_development_measurements':360,'source_sha256':record(Path(__file__))['sha256']}
    write_new(out,result);print(json.dumps({k:result[k] for k in ('status','passed','total','errors')}))
    return 0 if all(checks.values()) else 1


if __name__=='__main__':raise SystemExit(main())
