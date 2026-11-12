"""Original task 8 delivery and local preservation gate; no new test retrieval."""
from __future__ import annotations
import argparse,json,subprocess,uuid
from pathlib import Path
from bm25_index import ROOT,TEMPLATES,Bm25Index,build,record,write_new
from bm25_retrieval_eval import replay,choose,validate_grant,instant,now
from eval_dataset import digest,load_jsonl
from validate_eval_dataset import validate


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    report=a.report.resolve()
    if report.exists() or report.suffix!='.json' or not report.is_relative_to(ROOT/'reports'):raise ValueError('Use a new reports JSON')
    base=ROOT/'reports/retrieval/bm25_b0';checks={};errors=[];context={}
    def check(name,callback):
        try:checks[name]=bool(callback())
        except Exception as exc:checks[name]=False;errors.append({'check':name,'type':type(exc).__name__,'error':str(exc)})
    def rejects(callback):
        try:callback()
        except (ValueError,OSError,KeyError,TypeError):return True
        return False
    def runs():
        context.update(dev={t:replay(base/'development'/t) for t in TEMPLATES},test=replay(base/'test'))
        return True
    check('three_development_and_one_test_replay_without_model_calls',runs)
    check('fixed_development_counts_40_32_8',lambda:all(s['quality']['questions']==40 and s['quality']['answerable_denominator']==32 and s['quality']['unanswerable_excluded']==8 for s in context['dev'].values()))
    check('fixed_test_counts_50_40_10',lambda:(lambda q:q['questions']==50 and q['answerable_denominator']==40 and q['unanswerable_excluded']==10)(context['test']['quality']))
    selection=json.loads((base/'selection.json').read_text('utf-8'));grant=json.loads((base/'test_authorization.json').read_text('utf-8'))
    check('selection_exactly_recomputes_from_all_three_dev_runs',lambda:selection==choose(base/'development'))
    check('test_uses_only_selected_template',lambda:context['test']['template']==selection['selected_template']==grant['template'])
    def authorization():validate_grant(grant,base/'test');return True
    check('authorization_binds_source_data_selection_and_verification',authorization)
    check('test_source_frozen_before_authorization',lambda:subprocess.check_output(['git','show','-s','--format=%cI',grant['source_commit']],cwd=ROOT,text=True).strip() and
          instant(subprocess.check_output(['git','show','-s','--format=%cI',grant['source_commit']],cwd=ROOT,text=True).strip())<=instant(grant['prepared_at']))
    check('development_and_contract_predate_authorization',lambda:all(instant(json.loads((ROOT/r['run_manifest']['path']).read_text('utf-8'))['completed_at'])<=instant(grant['prepared_at']) for r in selection['development_runs']) and instant(json.loads((ROOT/grant['verification']['path']).read_text('utf-8'))['captured_at'])<=instant(grant['prepared_at']))
    ledger=load_jsonl(base/'test_usage.jsonl');test_manifest=json.loads((base/'test/run_manifest.json').read_text('utf-8'))
    check('one_formal_test_with_started_completed_events',lambda:len(ledger)==2 and [r['event'] for r in ledger]==['STARTED','COMPLETED'] and all(r['run_id']==test_manifest['run_id'] and r['authorization']==record(base/'test_authorization.json') and r['test_sha256']==grant['test_sha256'] for r in ledger))
    check('test_completion_binds_exact_original_run_manifest',lambda:ledger[-1]['run_manifest']==record(base/'test/run_manifest.json'))
    check('all_510_successful_measurements_present',lambda:sum(v['latency']['all']['total_seconds']['samples'] for v in context['dev'].values())==360 and context['test']['latency']['all']['total_seconds']['samples']==150)
    check('74_contract_checks_passed_before_test',lambda:(lambda r:r['status']=='PASS' and r['passed']==r['total']==74 and all(r['checks'].values()) and r['development_replay_checked'] is True)(json.loads((base/'acceptance/contract-final.json').read_text('utf-8'))))
    check('current_contract_checks_pass',lambda:(lambda r:r['status']=='PASS' and r['passed']==r['total']==74)(json.loads((base/'acceptance/contract-current.json').read_text('utf-8'))))
    check('restored_index_eight_regressions_and_actual_dev_pass',lambda:(lambda r:r['status']=='PASS' and r['passed']==r['total']==8 and r['new_locked_test_requests']==0)(json.loads((base/'acceptance/portability.json').read_text('utf-8'))))
    check('failed_initial_development_run_still_rejected',lambda:(base/'dev/body/failure.json').exists() and rejects(lambda:replay(base/'dev/body')))
    public=json.loads((ROOT/'data/manifests/bm25_indexes.json').read_text('utf-8'))
    indexes={t:Bm25Index(ROOT/'data/indexes/bm25'/t) for t in TEMPLATES}
    check('all_three_persisted_indexes_validate_99_original_units',lambda:all(len(v.sources)==99 and v.manifest==public['indexes'][t] for t,v in indexes.items()))
    fixture=ROOT/'.tmp'/('task8-rebuild-'+uuid.uuid4().hex)
    def rebuild():
        rebuilt=[]
        for template in TEMPLATES:
            target=fixture/template;result=build(target,template)
            same=all((target/n).read_bytes()==(indexes[template].path/n).read_bytes() for n in ('index.json','source_map.json'))
            rebuilt.append({'template':template,'build_seconds':result['build_seconds'],'payload_and_source_map_identical':same})
        context['rebuild']=rebuilt;return all(r['payload_and_source_map_identical'] for r in rebuilt)
    check('three_fresh_rebuild_payloads_byte_identical',rebuild)
    report_data=json.loads((ROOT/'reports/bm25_baseline.json').read_text('utf-8'))
    check('prescribed_report_recomputed_from_original_predictions',lambda:report_data['test']['quality']==context['test']['quality'] and report_data['test']['latency']==context['test']['latency'] and all(report_data['development'][t]['quality']==s['quality'] for t,s in context['dev'].items()))
    check('test_error_analysis_only_aggregate',lambda:json.loads((base/'test/error_analysis.json').read_text('utf-8'))['development_cases'] is None)
    probes=json.loads((base/'development_probes.json').read_text('utf-8'))
    check('rule_decimal_terminology_diagnostics_present',lambda:{r['kind'] for r in probes['probes']}=={'rule_number','decimal','term'})
    check('rule_number_and_decimals_preserved_in_probes',lambda:'rule:11' in probes['probes'][0]['tokens'] and all(v in probes['probes'][1]['tokens'] for v in ('7.32','2.44')))
    def segmentation():
        from compare_bm25_segmentation import replay_comparison
        s=replay_comparison(base/'segmentation-dev')
        return s['quality']['questions']==40 and s['quality']['answerable_denominator']==32 and s['latency']['all']['total_seconds']['samples']==120
    check('accurate_search_mode_dev_comparison_replays',segmentation)
    check('supplement_timestamp_after_original_test_declared',lambda:instant(json.loads((base/'segmentation-dev/manifest.json').read_text('utf-8'))['started_at'])>instant(test_manifest['completed_at']))
    check('supplement_did_not_rewrite_original_test_or_usage_ledger',lambda:all(record(ROOT/report_data['artifacts'][n]['path'])==report_data['artifacts'][n] for n in ('authorization','test_usage')) and record(base/'test/run_manifest.json')==report_data['test']['manifest'])
    check('required_original_task8_files_delivered',lambda:all((ROOT/p).is_file() for p in ('scripts/build_bm25_index.py','scripts/run_bm25_retrieval.py','reports/bm25_baseline.json','docs/BM25_RETRIEVAL.md','reports/TASK_08_DELIVERY.md')))
    check('original_task4_human_delivery_unchanged',lambda:(lambda r:r['status']=='PASS' and r['human_review']['approved']==90)(validate(phase='delivery')))
    before=json.loads((ROOT/'.runtime/task8/before.json').read_text('utf-8'))
    check('authority_docs_and_original_eval_validator_unchanged',lambda:all(digest((ROOT/p).read_bytes())==before['tracked'][p] for p in ('docs/TECHNICAL_DESIGN.md','docs/DEVELOPMENT_PLAN_AND_REPORT.md','docs/UPSTREAM_VERSION.md','scripts/validate_eval_dataset.py')))
    exempt={'reports/README.md','reports/resume_evidence.md','reports/all_experiments_summary.csv'}
    check('all_original_eval_and_historical_report_bytes_unchanged',lambda:all(digest((ROOT/p).read_bytes())==v for p,v in before['tracked'].items() if p.startswith(('reports/','data/eval/')) and p not in exempt))
    check('formal_dense_index_all_files_unchanged',lambda:before['index']=={p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in (ROOT/'data/indexes/dense').rglob('*') if p.is_file()})
    check('original_private_human_review_ledger_unchanged',lambda:before['ledger_sha256']==digest((ROOT/'.runtime/eval_review/reviews.jsonl').read_bytes()))
    lock=json.loads((ROOT/'data/manifests/task1_task2_baseline_lock.json').read_text('utf-8'))
    check('ten_frozen_files_unchanged',lambda:len(lock['files'])==10 and all(digest((ROOT/r['path']).read_bytes())==r['sha256'] for r in lock['files']))
    check('four_historical_prefixes_unchanged',lambda:all(digest((ROOT/r['path']).read_bytes()[:r['original_size_bytes']])==r['original_prefix_sha256'] for r in lock['append_only_files']))
    local=json.loads((ROOT/'data/manifests/local_data_files.json').read_text('utf-8'))['files']
    check('61_local_corpus_files_unchanged',lambda:len(local)==61 and all(digest((ROOT/r['path']).read_bytes())==r['sha256'] for r in local))
    old=json.loads(subprocess.check_output(['git','show',before['base_commit']+':data/manifests/experiment_manifest.json'],cwd=ROOT))
    check('all_11_original_experiment_objects_preserved',lambda:json.loads((ROOT/'data/manifests/experiment_manifest.json').read_text('utf-8'))['experiments'][:11]==old['experiments'])
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    check('bm25_indexes_dependency_and_corpus_not_public',lambda:not any(p.startswith(('data/indexes/','.runtime/','data/processed/')) for p in tracked))
    result={'captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),
            'checks':checks,'errors':errors,'selected_template':selection['selected_template'],'rebuilds':context.get('rebuild'),
            'new_locked_test_retrievals_in_this_gate':0,'test_individual_results_exposed_by_gate':False,
            'scope':'Original Task8 acceptance plus independent saved-result replay, private index rebuild and preservation. Test retrieval is not rerun.',
            'source_sha256':record(Path(__file__))['sha256']}
    write_new(report,result);print(json.dumps({k:result[k] for k in ('status','passed','total','errors')}))
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
