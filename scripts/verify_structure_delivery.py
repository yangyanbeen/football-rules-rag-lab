"""Task11 delivery, full private preservation or standard-library public replay."""
import argparse,io,json,subprocess,tarfile
from pathlib import Path
from eval_dataset import ROOT,canonical,digest,load_jsonl
from bm25_index import record,write_new
from bm25_retrieval_eval import now,instant
from structure_aware_chunking import DATA,MAP,STATS,AUDIT,derive,describe,tokenizer,config
import structure_retrieval_eval as ev

MUTABLE={'README.md','docs/DELIVERY_STATUS.md','docs/PUBLIC_SETUP.md','docs/EXPERIMENT_LOG.md','reports/README.md',
         'reports/resume_evidence.md','reports/all_experiments_summary.csv','data/manifests/experiment_manifest.json','data/manifests/project_file_manifest.json'}


def verify(output,public_only=False,complete=False):
    checks={};errors=[]
    def check(name,fn):
        try:
            checks[name]=bool(fn())
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error':str(exc),'type':type(exc).__name__})
    raw=subprocess.check_output(['git','archive','--format=tar',ev.BASE],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:old={m.name:archive.extractfile(m).read() for m in archive.getmembers() if m.isfile()}
    check('603_original_files_except_current_indexes_byte_preserved',lambda:len(old)==603 and all((ROOT/p).read_bytes()==raw for p,raw in old.items() if p not in MUTABLE))
    registry=json.loads((ROOT/'data/manifests/experiment_manifest.json').read_text('utf-8'));original=json.loads(old['data/manifests/experiment_manifest.json'])
    check('18_original_experiment_objects_preserved',lambda:len(original['experiments'])==18 and registry['experiments'][:18]==original['experiments'])
    for p in ('docs/EXPERIMENT_LOG.md','reports/resume_evidence.md','reports/all_experiments_summary.csv'):
        check(p+'_append_only',lambda p=p:(ROOT/p).read_bytes().startswith(old[p]))
    m=ev.mapping();stats=json.loads((ROOT/STATS).read_text('utf-8'));audit=json.loads((ROOT/AUDIT).read_text('utf-8'))
    for group,layer in [('base','originals'),('child','children'),('parent','parents')]:
        check(group+'_characters_tokens_duplicates_recompute',lambda group=group,layer=layer:canonical(stats[group])==canonical(describe(m[layer])))
    check('99_lossless_structural_checks_all_pass',lambda:len(audit['samples'])==99 and audit['status']=='PASS' and all(x is True for x in audit['checks'].values()) and all(r['lossless'] is True and r['table_atomic'] is True and r['conditions_and_exceptions_counts']==r['reassembled_marker_counts'] for r in audit['samples']))
    check('source_tokenizer_exactly_pinned_and_no_special_tokens',lambda:m['tokenizer']=={k:config()[k] for k in ('tokenizer_model','tokenizer_revision','tokenizer_json_sha256','tokenizers_version','special_tokens')} and m['tokenizer']['special_tokens'] is False)
    dev=ev.replay(ev.DIRECTORY/'dev');test=ev.replay(ev.DIRECTORY/'test')
    check('dev_and_test_all_rankings_span_metrics_errors_recompute',lambda:dev['split']=='dev' and test['split']=='test')
    check('dev32_test40_answerable_fixed_denominators',lambda:all(s['methods'][method]['budgeted']['answerable_denominator']==n for s,n in [(dev,32),(test,40)] for method in ev.METHODS))
    check('dev40_test50_measured_embedding_counts',lambda:dev['actual_measured_embedding_queries']==40 and test['actual_measured_embedding_queries']==50)
    check('all_contexts_obey_common4096_budget',lambda:all(r['context_tokens']<=4096 for s in (dev,test) for v in s['methods'].values() for r in v['budgeted']['context_per_question']))
    check('test_not_used_to_select_method',lambda:dev['selected_on_this_split'] in ev.METHODS and test['selected_on_this_split'] is None)
    check('ndcg_not_invented',lambda:all(v['budgeted']['nDCG@10'] is None for s in (dev,test) for v in s['methods'].values()))
    def ledger():
        rows=load_jsonl(ev.LEDGER);manifest=json.loads((ev.DIRECTORY/'test/run_manifest.json').read_text('utf-8'))
        return (len(rows)==2 and [r['event'] for r in rows]==['STARTED','COMPLETED']
                and all(rows[0][k]==rows[1][k] for k in ('run_id','run_directory','source_commit','authorization','test_sha256'))
                and rows[0]['run_id']==manifest['run_id'] and rows[0]['authorization']==manifest['authorization']
                and rows[1]['run_manifest']==record(ev.DIRECTORY/'test/run_manifest.json')
                and instant(manifest['started_at'])<=instant(rows[0]['recorded_at'])<instant(manifest['completed_at'])<instant(rows[1]['recorded_at']))
    check('one_exclusive_completed_task11_test_ledger',ledger)
    proof=json.loads((ev.DIRECTORY/'acceptance/contract-final.json').read_text('utf-8'))
    check('current_contract_all_pass_and_native_sha_bound',lambda:proof['status']=='PASS' and proof['passed']==proof['total']==len(proof['checks']) and proof['total']>=40 and all(v is True for v in proof['checks'].values()) and proof['source_sha256']=={p:record(ROOT/p)['sha256'] for p in ev.NATIVE})
    index=json.loads((ROOT/ev.INDEX).read_text('utf-8'))
    check('index_source_and_model_runtime_bound',lambda:index['embedding_config']==record(ROOT/'config/dense_index.json') and index['model_runtime']['size_vram']==0 and index['model_runtime']['digest']==json.loads((ROOT/'config/dense_index.json').read_text('utf-8'))['model']['digest'] and all(index['source_sha256'][p]==digest(subprocess.check_output(['git','show',index['source_commit']+':'+p],cwd=ROOT)) for p in ev.SOURCES))
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    check('no_private_corpus_vectors_models_dependencies_or_runtime_tracked',lambda:not any(p.startswith(('.runtime/','.tmp/','.venv/','.models/','data/indexes/','data/processed/','data/raw/','third_party/')) for p in tracked))
    if not public_only:
        before=json.loads((ROOT/'.runtime/task11/before.json').read_text('utf-8'))
        check('22_original_index_files_preserved',lambda:len(before['indexes'])==22 and all(digest((ROOT/p).read_bytes())==v for p,v in before['indexes'].items()))
        check('original_human_review_ledger_preserved',lambda:digest((ROOT/'.runtime/eval_review/reviews.jsonl').read_bytes())==before['human_review_sha256'])
        corpus_records=json.loads((ROOT/'data/manifests/local_data_files.json').read_text('utf-8'))['files']
        check('61_original_corpus_files_preserved',lambda:len(corpus_records)==61 and all(record(ROOT/r['path'])['sha256']==r['sha256'] for r in corpus_records))
        check('derived_jsonl_local_hash_matches_public_map',lambda:record(ROOT/DATA)==m['derived_corpus'])
        def structure():
            from bm25_index import corpus
            private,mp,st,au=derive(corpus(),tokenizer(),config())
            return ((ROOT/DATA).read_bytes()==b''.join(canonical(r)+b'\n' for r in private)
                    and all(canonical(mp[k])==canonical(m[k]) for k in mp) and canonical(st)==canonical(stats) and canonical(au)==canonical(audit))
        check('actual_tokenizer_rebuild_and_all_conditions_table_bytes_match',structure)
        check('independent_private_index_artifacts_match',lambda:all(record(ROOT/p)==r for p,r in index['artifact_files'].items()))
    if complete:
        result=json.loads((ROOT/'reports/chunking_comparison.json').read_text('utf-8'))
        check('prescribed_comparison_result_recomputes',lambda:canonical(result['development'])==canonical(dev) and canonical(result['test'])==canonical(test) and result['selected_on_dev']==dev['selected_on_this_split'] and canonical(result['structure'])==canonical(stats))
        for name in ('docs/CHUNKING_STRATEGY.md','reports/TASK_11_DELIVERY.md'):
            check(name+'_delivered',lambda name=name:(ROOT/name).stat().st_size>100)
        check('19th_task11_experiment_registered',lambda:len(registry['experiments'])==19 and registry['experiments'][-1]['id']=='TASK-011-STRUCTURE-PARENT-CHILD')
        check('new_registered_artifacts_and_code_hashes_match',lambda:all(record(ROOT/r['path'])==r for r in registry['experiments'][-1]['artifacts']) and registry['experiments'][-1]['source_sha256']=={p:record(ROOT/p)['sha256'] for p in ev.NATIVE})
    value={'version':'structure-delivery-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),
           'checks':checks,'errors':errors,'public_only':public_only,'complete':complete,'new_model_requests':0,'source_sha256':record(__file__)['sha256']}
    write_new(output,value);return value


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--public-only',action='store_true');p.add_argument('--complete',action='store_true');a=p.parse_args()
    from run_structure_comparison import output_path
    value=verify(output_path(a.report),a.public_only,a.complete);print(json.dumps({k:value[k] for k in ('status','passed','total','errors')}));return 0 if value['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
