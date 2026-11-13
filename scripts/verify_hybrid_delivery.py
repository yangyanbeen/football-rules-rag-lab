"""Original Task9 acceptance, independent formula proof and historical preservation."""
import argparse,json,subprocess
from fractions import Fraction
from pathlib import Path
from eval_dataset import ROOT,digest,canonical,load_jsonl
from bm25_index import record,write_new
from bm25_retrieval_eval import now,instant
from hybrid_retrieval_eval import BASE_DIR,BASE,SOURCES,replay,validate_grant
from summarize_hybrid_rrf import report_payload
from rrf import METHODS,CHANNELS
from hybrid_live import validate_live_smoke


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--live-report',type=Path,default=BASE_DIR/'acceptance/live-smoke.json');a=p.parse_args();out=a.report.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'reports'):raise ValueError('Use a new report')
    checks={};errors=[];context={}
    def check(name,fn):
        try:checks[name]=bool(fn())
        except Exception as exc:checks[name]=False;errors.append({'check':name,'type':type(exc).__name__,'error':str(exc)})
    def completed_runs():
        context['dev']=replay(BASE_DIR/'dev');context['test']=replay(BASE_DIR/'test');return True
    check('saved_dev_and_test_replay_with_original_source_proof',completed_runs)
    check('dev_40_questions_32_answerable_8_excluded',lambda:all(v['quality']['questions']==40 and v['quality']['answerable_denominator']==32 and v['quality']['unanswerable_excluded']==8 for v in context['dev']['methods'].values()))
    check('test_50_questions_40_answerable_10_excluded',lambda:all(v['quality']['questions']==50 and v['quality']['answerable_denominator']==40 and v['quality']['unanswerable_excluded']==10 for v in context['test']['methods'].values()))
    rows={s:load_jsonl(BASE_DIR/s/'predictions.jsonl') for s in ('dev','test')}
    check('all_four_methods_equal_top10_output_budget',lambda:all(set(r['results'])==set(METHODS) and all(len(v)<=10 for v in r['results'].values()) and all(len(r['channels'][c]['results'])<=10 for c in CHANNELS) for values in rows.values() for r in values))
    check('270_fusion_measurements_and_all_original_channel_measurements_preserved',lambda:sum(len(r['measurements']) for values in rows.values() for r in values)==270 and all(len(r['channels'][c]['measurements'])==3 for values in rows.values() for r in values for c in CHANNELS))
    def independent_formula():
        for split,values in rows.items():
            k=context[split]['config']['k']
            for row in values:
                score={}
                for channel in CHANNELS:
                    for entry in row['channels'][channel]['results']:
                        cid=entry['chunk_id'];score[cid]=score.get(cid,Fraction())+Fraction(1,k+entry['rank'])
                ids=sorted(score,key=lambda cid:(-score[cid],cid))[:10]
                if ids!=[r['chunk_id'] for r in row['results']['rrf']]:return False
                if any(r['score']!=float(score[r['chunk_id']]) for r in row['results']['rrf']):return False
        return True
    check('independent_rrf_reference_for_all_90_questions',independent_formula)
    grant=json.loads((BASE_DIR/'test_authorization.json').read_text('utf-8'));manifest=json.loads((BASE_DIR/'test/run_manifest.json').read_text('utf-8'))
    check('committed_dev_verification_and_parameters_frozen_before_test',lambda:validate_grant(grant,BASE_DIR/'test') is None and grant['source_commit']==manifest['source_commit'] and instant(grant['prepared_at'])<=instant(manifest['started_at']))
    ledger=load_jsonl(BASE_DIR/'test_usage.jsonl')
    def one_usage():
        common={'run_id':manifest['run_id'],'run_directory':(BASE_DIR/'test').relative_to(ROOT).as_posix(),'template':'rrf-k'+str(grant['config']['k']),
                'source_commit':manifest['source_commit'],'authorization':record(BASE_DIR/'test_authorization.json'),
                'test_sha256':grant['test_sha256'],'scope':'offline rank fusion only','new_channel_retrieval_requests':0}
        if len(ledger)!=2:return False
        for row,event in zip(ledger,('STARTED','COMPLETED')):
            if set(row)!=set(common)|{'event','recorded_at'}|({'run_manifest'} if event=='COMPLETED' else set()):return False
            if row['event']!=event or any(canonical(row[k])!=canonical(v) for k,v in common.items()):return False
        return (ledger[-1]['run_manifest']==record(BASE_DIR/'test/run_manifest.json') and
                instant(manifest['started_at'])<=instant(ledger[0]['recorded_at'])<=instant(manifest['completed_at'])<=instant(ledger[-1]['recorded_at']))
    check('one_offline_formal_fusion_started_and_completed_exact_identity',one_usage)
    check('test_error_analysis_aggregate_only',lambda:json.loads((BASE_DIR/'test/error_analysis.json').read_text('utf-8'))['development_cases'] is None)
    check('no_offline_channel_retrieval_or_answer_calls',lambda:all(s['new_channel_retrieval_requests']==s['llm_requests']==0 for s in (context['dev'],context['test'])))
    check('nDCG_not_fabricated_without_graded_labels',lambda:all(v['quality']['nDCG@10'] is None for s in ('dev','test') for v in context[s]['methods'].values()))
    current=json.loads((ROOT/'reports/hybrid_rrf_results.json').read_text('utf-8'))
    check('prescribed_report_exactly_recomputes',lambda:canonical({k:v for k,v in current.items() if k!='generated_at'})==canonical(report_payload()))
    check('result_explicitly_records_negative_MRR_vs_BM25',lambda:context['test']['rrf_vs_single_channels']['bm25']['verdict']=='inferior' and context['test']['rrf_vs_single_channels']['bm25']['per_metric']['MRR@10']=='lower')
    check('unranked_union_coverage_separate_from_top10_MRR',lambda:all(context[s]['full_union_diagnostic']['MRR'] is None and context[s]['full_union_diagnostic']['ranked'] is False for s in ('dev','test')))
    receipt=json.loads((BASE_DIR/'acceptance/contract-development.json').read_text('utf-8'))
    check('56_development_contract_checks_pass',lambda:receipt['status']=='PASS' and receipt['passed']==receipt['total']==56 and len(receipt['checks'])==56 and all(v is True for v in receipt['checks'].values()))
    smoke=json.loads(a.live_report.read_text('utf-8'))
    check('17_actual_query_checks_recompute_and_sources_match_producer',lambda:len(validate_live_smoke(smoke))==17)
    check('four_actual_embedding_queries_zero_original_test_queries_zero_answer_calls',lambda:smoke['actual_embedding_queries']==4 and smoke['new_locked_test_queries']==smoke['answer_llm_requests']==0 and smoke['is_accuracy_evaluation'] is False)
    check('actual_query_sources_and_timing_fields_present',lambda:len(smoke['queries'])==4 and all(set(r['channels'])==set(CHANNELS) and set(r['results'])==set(METHODS) and r['timing']['total_seconds']>0 for r in smoke['queries']))
    public=json.loads((BASE_DIR/'acceptance/public-only-replay.json').read_text('utf-8'))
    check('public_only_without_corpus_indexes_or_third_party_replays_two_runs',lambda:public['status']=='PASS' and public['passed']==public['total']==7 and all(v is True for v in public['checks'].values()))
    oldgate=json.loads((BASE_DIR/'acceptance/previous-task8.json').read_text('utf-8'))
    check('previous_task8_original_35_checks_pass',lambda:oldgate['status']=='PASS' and oldgate['passed']==oldgate['total']==35 and all(v is True for v in oldgate['checks'].values()))
    env=json.loads((BASE_DIR/'acceptance/environment.json').read_text('utf-8'))
    check('environment_and_retrospective_capture_scope_recorded',lambda:env['python']=='3.10.22' and env['logical_cpus']>0 and 'after' in env['scope'] and env['producer_sha256']==record(ROOT/'scripts/collect_hybrid_environment.py')['sha256'])
    before=json.loads((ROOT/'.runtime/task9/before.json').read_text('utf-8'))
    mutable={'README.md','docs/DELIVERY_STATUS.md','docs/PUBLIC_SETUP.md','docs/EXPERIMENT_LOG.md','reports/README.md',
             'reports/resume_evidence.md','reports/all_experiments_summary.csv','data/manifests/experiment_manifest.json','data/manifests/project_file_manifest.json'}
    check('all_480_original_files_except_declared_current_indexes_unchanged',lambda:len(before['tracked'])==480 and all(digest((ROOT/p).read_bytes())==v for p,v in before['tracked'].items() if p not in mutable))
    check('22_original_private_index_files_unchanged',lambda:len(before['indexes'])==22 and all(digest((ROOT/p).read_bytes())==v for p,v in before['indexes'].items()))
    check('original_human_review_ledger_unchanged',lambda:digest((ROOT/'.runtime/eval_review/reviews.jsonl').read_bytes())==before['ledger_sha256'])
    local=json.loads((ROOT/'data/manifests/local_data_files.json').read_text('utf-8'))['files']
    check('61_local_corpus_files_unchanged',lambda:len(local)==61 and all(digest((ROOT/r['path']).read_bytes())==r['sha256'] for r in local))
    old=json.loads(subprocess.check_output(['git','show',BASE+':data/manifests/experiment_manifest.json'],cwd=ROOT))
    registry=json.loads((ROOT/'data/manifests/experiment_manifest.json').read_text('utf-8'))
    check('14_original_experiment_objects_preserved',lambda:len(old['experiments'])==14 and registry['experiments'][:14]==old['experiments'])
    prefix=subprocess.check_output(['git','show',BASE+':docs/EXPERIMENT_LOG.md'],cwd=ROOT)
    check('original_experiment_log_prefix_preserved',lambda:(ROOT/'docs/EXPERIMENT_LOG.md').read_bytes().startswith(prefix))
    check('all_original_reports_except_three_current_indexes_unchanged',lambda:all(digest((ROOT/p).read_bytes())==v for p,v in before['tracked'].items() if p.startswith('reports/') and p not in mutable))
    required=('scripts/rrf.py','scripts/run_hybrid_retrieval.py','reports/hybrid_rrf_results.json','docs/RRF_EXPERIMENT.md','reports/TASK_09_DELIVERY.md')
    check('all_original_task9_deliverables_exist',lambda:all((ROOT/p).is_file() for p in required))
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    check('no_private_corpus_index_runtime_or_dependencies_tracked',lambda:not any(p.startswith(('data/raw/','data/processed/','data/indexes/','.runtime/','.tmp/','.venv/')) for p in tracked))
    result={'version':'hybrid-delivery-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL',
            'passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'baseline':BASE,
            'original_criteria':'Task9 and Technical5.2 unchanged; extra engineering checks reported separately',
            'new_original_channel_test_queries':0,'new_offline_fusion_test_runs':1,'source_sha256':record(__file__)['sha256']}
    write_new(out,result);print(json.dumps({k:result[k] for k in ('status','passed','total','errors')}))
    return 0 if all(checks.values()) else 1


if __name__=='__main__':raise SystemExit(main())
