"""Task10 delivery gate; --public-only replays without private data or packages."""
import argparse,json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from eval_dataset import ROOT,EVAL,canonical,digest,load_jsonl
from bm25_index import record,write_new
from bm25_retrieval_eval import now,instant
import reranker_eval as ev

MUTABLE={'README.md','docs/DELIVERY_STATUS.md','docs/PUBLIC_SETUP.md','docs/EXPERIMENT_LOG.md',
         'reports/README.md','reports/resume_evidence.md','reports/all_experiments_summary.csv',
         'data/manifests/experiment_manifest.json','data/manifests/project_file_manifest.json'}


def git_bytes(commit,name):return subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)


def strong_manifest(directory):
    """Check independently pinned original artifact hashes, clocks and CPU model."""
    m=json.loads((directory/'run_manifest.json').read_text('utf-8'))
    if not instant(m['started_at'])<instant(m['completed_at'])<=datetime.now(timezone.utc):raise ValueError('Future/backward run')
    wall=(instant(m['completed_at'])-instant(m['started_at'])).total_seconds()
    if abs(m['wall_seconds']-wall)>.5:raise ValueError('Monotonic and UTC wall duration disagree')
    if m['load_seconds']>=m['wall_seconds']:raise ValueError('Load interval invalid')
    dense=json.loads((ROOT/'data/manifests/dense_index_manifest.json').read_text('utf-8'))
    bm=json.loads((ROOT/'data/manifests/bm25_indexes.json').read_text('utf-8'))['indexes']['title_body']
    expected={**{'data/indexes/dense/'+p:v for p,v in dense['artifact_files'].items()},
              **{'data/indexes/bm25/title_body/'+p:v for p,v in bm['artifacts'].items()},
              'data/indexes/dense/index_manifest.json':{'sha256':dense['local_manifest_sha256']},
              'data/indexes/bm25/title_body/index_manifest.json':{'sha256':digest((json.dumps(bm,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode())}}
    for snapshot in m['index_snapshots'].values():
        if set(snapshot)!=set(expected):raise ValueError('Index snapshot paths not original')
        for p,item in snapshot.items():
            ev.fields(item,('path','size_bytes','sha256'),'original index snapshot')
            if item['path']!=p or type(item['size_bytes']) is not int or item['size_bytes']<1 or not ev.sha(item['sha256']):raise ValueError('Invalid snapshot entry')
            if any(item[k]!=v for k,v in expected[p].items()):raise ValueError('Index identity differs from original artifact')
    env=m['environment'];cfg=json.loads((ROOT/'config/dense_index.json').read_text('utf-8'));runtime=env['embedding_runtime']
    ev.fields(runtime,('name','digest','size','size_vram','context_length','runner'),'pinned embedding runtime')
    if runtime['name']!=cfg['model']['name'] or runtime['digest']!=cfg['model']['digest'] or runtime['runner']!='llamacpp':raise ValueError('Embedding model not pinned')
    if (type(runtime['size_vram']) is not int or runtime['size_vram']!=0 or type(runtime['size']) is not int or runtime['size']<1
        or type(runtime['context_length']) is not int or runtime['context_length']!=8192):raise ValueError('Embedding device/context differs')
    if env['python']!='3.10.22' or type(env['logical_cpus']) is not int or env['logical_cpus']<1 or type(env['physical_memory_bytes']) is not int or env['physical_memory_bytes']<1:raise ValueError('Host observation invalid')
    return True


def validate_ledger():
    rows=load_jsonl(ev.LEDGER);m=json.loads((ev.DIRECTORY/'test/run_manifest.json').read_text('utf-8'))
    if len(rows)!=2 or [r['event'] for r in rows]!=['STARTED','COMPLETED']:raise ValueError('Test ledger not one completed run')
    for k in ('run_id','run_directory','template','source_commit','authorization','test_sha256'):
        if rows[0][k]!=rows[1][k]:raise ValueError('Test ledger identity changed')
    if rows[0]['run_id']!=m['run_id'] or rows[0]['source_commit']!=m['source_commit'] or rows[0]['authorization']!=m['authorization']:raise ValueError('Ledger not bound to test')
    if rows[0]['run_directory']!='reports/retrieval/bge_reranker_b0/test' or rows[0]['test_sha256']!=digest((EVAL/'retrieval_test.jsonl').read_bytes()):raise ValueError('Ledger scope differs')
    if rows[1]['run_manifest']!=record(ev.DIRECTORY/'test/run_manifest.json'):raise ValueError('Completion does not bind manifest')
    if not instant(m['started_at'])<=instant(rows[0]['recorded_at'])<instant(m['completed_at'])<instant(rows[1]['recorded_at']):raise ValueError('Ledger chronology invalid')
    return True


def verify(report,public_only=False,complete=False):
    checks={};errors=[];summaries={}
    def check(name,fn):
        try:checks[name]=bool(fn())
        except Exception as exc:checks[name]=False;errors.append({'check':name,'type':type(exc).__name__,'error':str(exc)})
    def replay(split):summaries[split]=ev.replay(ev.DIRECTORY/split);return True
    check('fixed_original_task10_policy',lambda:ev.config()['methods']==list(ev.METHODS))
    for split in ('dev','test'):
        check(split+'_all_metrics_rankings_batches_and_raw_timings_recompute',lambda split=split:replay(split))
        check(split+'_original_indexes_cpu_runtime_and_clocks_bound',lambda split=split:strong_manifest(ev.DIRECTORY/split))
    check('one_frozen_test_matrix_and_two_owned_ledger_events',validate_ledger)
    def grant():
        g=json.loads((ev.DIRECTORY/'test_authorization.json').read_text('utf-8'));ev.validate_grant(g,ev.DIRECTORY/'test')
        proof=json.loads((ROOT/g['verification']['path']).read_text('utf-8'))
        return (all(proof['source_sha256'][p]==digest(git_bytes(g['source_commit'],p)) for p in ev.NATIVE)
                and proof['passed']==proof['total']==len(proof['checks']) and proof['total']>=72)
    check('committed_dev_verification_before_frozen_test',grant)
    check('dev_selection_frozen_no_test_selection',lambda:summaries['dev']['selected_on_this_split'] in ev.METHODS and summaries['test']['selected_on_this_split'] is None)
    check('same99_original_source_map_no_text',lambda:all(json.loads((ev.DIRECTORY/s/'source_map.json').read_text('utf-8'))==json.loads((ROOT/'reports/retrieval/dense_b0/dev/source_map.json').read_text('utf-8')) for s in ('dev','test')))
    check('dev32_and_test40_quality_denominators',lambda:all(summaries[s]['methods'][m]['quality']['answerable_denominator']==n for s,n in [('dev',32),('test',40)] for m in ev.METHODS))
    check('all_query_latency_samples40_and50_including_unanswerable',lambda:all(summaries[s]['methods'][m]['latency'][clock]['samples']==n for s,n in [('dev',40),('test',50)] for m in ev.METHODS for clock in ('rerank_seconds','total_seconds')))
    check('actual_distinct_candidates20_40_80',lambda:all(summaries[s]['methods'][m]['scored_pairs']==n*ev.BUDGETS[m] for s,n in [('dev',40),('test',50)] for m in ev.METHODS))
    check('ndcg_not_fabricated',lambda:all(summaries[s]['nDCG@10'] is None for s in ('dev','test')))
    check('no_answer_model_requests',lambda:all(summaries[s]['answer_llm_requests']==0 for s in ('dev','test')))
    def preserved():
        names=subprocess.check_output(['git','ls-tree','-r','--name-only',ev.BASE],cwd=ROOT,text=True).splitlines()
        return len(names)==534 and all((ROOT/p).read_bytes()==git_bytes(ev.BASE,p) for p in names if p not in MUTABLE)
    check('534_original_public_files_except_current_indexes_byte_preserved',preserved)
    old=json.loads(git_bytes(ev.BASE,'data/manifests/experiment_manifest.json'))
    current=json.loads((ROOT/'data/manifests/experiment_manifest.json').read_text('utf-8'))
    check('16_original_experiment_objects_preserved',lambda:len(old['experiments'])==16 and current['experiments'][:16]==old['experiments'])
    for name in ('docs/EXPERIMENT_LOG.md','reports/all_experiments_summary.csv','reports/resume_evidence.md'):
        check(name+'_original_prefix_preserved',lambda name=name:(ROOT/name).read_bytes().startswith(git_bytes(ev.BASE,name)))
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    check('no_corpus_models_indexes_or_dependencies_tracked',lambda:not any(p.startswith(('.runtime/','.models/','.venv/','.tmp/','data/indexes/','data/raw/','data/processed/','third_party/')) for p in tracked))
    if not public_only:
        before=json.loads((ROOT/'.runtime/task10/before.json').read_text('utf-8'))
        check('22_private_index_files_preserved',lambda:len(before['indexes'])==22 and all(digest((ROOT/p).read_bytes())==v for p,v in before['indexes'].items()))
        check('private90_human_review_ledger_preserved',lambda:digest((ROOT/'.runtime/eval_review/reviews.jsonl').read_bytes())==before['human_review_sha256'])
        corpus=json.loads((ROOT/'data/manifests/local_data_files.json').read_text('utf-8'))['files']
        check('61_private_corpus_files_preserved',lambda:len(corpus)==61 and all(digest((ROOT/r['path']).read_bytes())==r['sha256'] for r in corpus))
        def model():
            from bge_reranker import HOME,file_sha
            return all((HOME/n).stat().st_size==r['size_bytes'] and file_sha(HOME/n)==r['sha256'] for n,r in ev.config()['files'].items())
        check('official_model_weights_and_tokenizer_sha256_match',model)
    if complete:
        final=json.loads((ROOT/'reports/reranker_results.json').read_text('utf-8'))
        check('final_result_dev_test_equal_independent_replay',lambda:canonical(final['development'])==canonical(summaries['dev']) and canonical(final['test'])==canonical(summaries['test']))
        check('final_result_selection_from_dev_not_test',lambda:final['selected_method_on_dev']==summaries['dev']['selected_on_this_split'])
        from summarize_reranker_experiment import report_payload,rank_changes
        check('prescribed_full_report_recomputes',lambda:canonical({k:v for k,v in final.items() if k!='generated_at'})==canonical(report_payload()))
        for split in ('dev','test'):
            check(split+'_readable_before_after_rank_changes_recompute',lambda split=split:canonical(rank_changes(split))==canonical(json.loads((ev.DIRECTORY/split/'rank_changes.json').read_text('utf-8'))))
        for name in ('docs/RERANKER_EXPERIMENT.md','reports/TASK_10_DELIVERY.md','scripts/install_reranker_model.py'):
            check(name+'_delivered',lambda name=name:(ROOT/name).is_file() and (ROOT/name).stat().st_size>100)
        check('17th_experiment_registered',lambda:len(current['experiments'])==17 and current['experiments'][-1]['id']=='TASK-010-BGE-RERANKER')
        check('registered_artifact_hashes_match',lambda:all(record(ROOT/r['path'])==r for r in current['experiments'][-1]['artifacts']))
        def registered_code():
            c=current['experiments'][-1]['code']
            return (c['formal_test_source_commit']==final['source_commit']
                    and c['formal_test_source_sha256']=={p:digest(git_bytes(c['formal_test_source_commit'],p)) for p in ev.NATIVE}
                    and c['delivery_source_sha256']=={p:record(ROOT/p)['sha256'] for p in ev.NATIVE}
                    and c['delivery_source_sha256']=={p:digest(git_bytes(c['delivery_source_commit'],p)) for p in ev.NATIVE})
        check('formal_and_delivered_source_identities_separate_and_bound',registered_code)
        def public_receipt():
            r=json.loads((ev.DIRECTORY/'acceptance/public-final.json').read_text('utf-8'))
            return r['status']=='PASS' and r['passed']==r['total']==35 and len(r['checks'])==35 and all(v is True for v in r['checks'].values()) and r['includes_test'] is True and r['new_model_requests']==0 and r['source_sha256']==record(ROOT/'scripts/verify_reranker_public_replay.py')['sha256']
        check('independent_public_replay_and25_bad_copies_rejected',public_receipt)
        def current_receipt(name,total,names):
            r=json.loads((ev.DIRECTORY/'acceptance'/name).read_text('utf-8'))
            return r['status']=='PASS' and r['passed']==r['total']==len(r['checks'])==total and all(v is True for v in r['checks'].values()) and all(r['source_sha256'][p]==record(ROOT/p)['sha256'] for p in names)
        check('current74_contract_checks_bind_delivered_native_code',lambda:current_receipt('contract-current.json',74,ev.NATIVE))
        check('current12_cold_start_and_output_regressions_pass',lambda:current_receipt('cold-start-regressions.json',12,('scripts/run_reranker_experiment.py','scripts/verify_reranker_lifecycle.py','scripts/reranker_live.py')))
        from verify_reranker_cold_start import validate as validate_cold
        check('actual8_isolated_cold_start_checks_recompute',lambda:len(validate_cold(json.loads((ev.DIRECTORY/'acceptance/cold-start-actual.json').read_text('utf-8'))))==8)
    result={'version':'reranker-delivery-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL',
            'passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'public_only':public_only,
            'complete_delivery':complete,'new_model_requests':0,'source_sha256':record(__file__)['sha256']}
    write_new(report,result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--public-only',action='store_true');p.add_argument('--complete',action='store_true');a=p.parse_args()
    from run_reranker_experiment import new_report
    result=verify(new_report(a.report),a.public_only,a.complete);print(json.dumps({k:result[k] for k in ('status','passed','total','errors')}));return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
