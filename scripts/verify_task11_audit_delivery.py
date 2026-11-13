"""Supplemental Task11 proof, preserving original release receipts and test results."""
import argparse,io,json,subprocess,tarfile
from datetime import datetime,timezone
from pathlib import Path
from eval_dataset import ROOT,canonical,digest
from bm25_index import record,write_new
from bm25_retrieval_eval import now,instant,producer_before
import structure_retrieval_eval as ev
from verify_task11_audit import BASE,NAMES
from verify_structure_delivery import MUTABLE as NAVIGATION

DIRECTORY=ROOT/'reports/rechecks/task11-audit-20261113'
MUTABLE=NAVIGATION|set(NAMES)


def valid_receipt(value,n):
    return value['status']=='PASS' and type(value['passed']) is int and type(value['total']) is int and value['passed']==value['total']==len(value['checks'])==n and all(v is True for v in value['checks'].values()) and value.get('errors',[])==[]


def validate_parent_receipt(path,private=False):
    value=json.loads(path.read_text('utf-8'))
    ev.fields(value,('version','started_at','completed_at','source_commit','source_sha256','input_query_receipt','private_output','query_receipt','source_records','results_without_bodies','context_tokens','skipped_ids','actual_new_embedding_queries','answer_llm_requests','scope','checks','status','passed','total'))
    if value['version']!='task11-actual-parent-context-1.1':raise ValueError('Unknown parent receipt')
    producer_before(value['source_commit'],value['started_at'])
    if not instant(value['started_at'])<instant(value['completed_at'])<=datetime.now(timezone.utc):raise ValueError('Invalid parent chronology')
    ev.fields(value['source_records'],ev.SOURCES+('scripts/query_parent_child.py',))
    for p,r in value['source_records'].items():
        blob=subprocess.check_output(['git','show',value['source_commit']+':'+p],cwd=ROOT)
        if r!={'path':p,'size_bytes':len(blob),'sha256':digest(blob)} or r!=record(ROOT/p):raise ValueError('Parent current/producer source differs')
    if value['source_sha256']!=value['source_records']['scripts/query_parent_child.py']['sha256']:raise ValueError('Parent main source differs')
    if value['input_query_receipt'] is not None:
        ref=value['input_query_receipt'];query=ROOT/ref['path'];raw=query.read_bytes();stored=json.loads(raw)
        if record(query)!=ref or value['query_receipt'] is not None:raise ValueError('Replayed parent input differs')
        ev.validate_saved_query(stored,raw);requests=0
    else:
        stored=value['query_receipt'];ev.validate_saved_query(stored);requests=1
        if instant(stored['started_at'])<instant(value['started_at']) or instant(stored['completed_at'])>instant(value['completed_at']):raise ValueError('Nested query chronology differs')
    if type(value['actual_new_embedding_queries']) is not int or value['actual_new_embedding_queries']!=requests or type(value['answer_llm_requests']) is not int or value['answer_llm_requests']!=0:raise ValueError('Parent request count differs')
    m=ev.mapping();seed=stored['packet']['rankings']['child'];selection=ev.budget_contexts(ev.contexts([r['chunk_id'] for r in seed],'parent_child',m),m);expected=[]
    for i,row in enumerate(selection['contexts'],1):
        meta=m['parents'][row['context_id']]
        expected.append({'rank':i,**row,'section_path':meta['section_path'],'content_sha256':meta['content_sha256'],'original_ids':meta['original_ids'],
                         'source_refs':[m['originals'][cid]['source'] for cid in meta['original_ids']],'context_tokens':meta['context_tokens']})
    if not ev.equal(expected,value['results_without_bodies']) or value['context_tokens']!=selection['context_tokens'] or value['skipped_ids']!=selection['skipped_ids']:raise ValueError('Parent metadata/context budget differs')
    ref=value['private_output'];ev.fields(ref,('path','size_bytes','sha256'));local=(ROOT/ref['path']).resolve()
    if not local.is_relative_to(ROOT/'.runtime/task11') or not ev.integer(ref['size_bytes'],1) or not isinstance(ref['sha256'],str) or len(ref['sha256'])!=64:raise ValueError('Private body scope/hash invalid')
    ignored=subprocess.run(['git','check-ignore','--quiet',str(local)],cwd=ROOT).returncode==0
    checks={'at_least_one_real_parent_materialized':bool(expected),'actual_parent_bodies_and_member_sources_match':True,
            'parent_ids_unique':len({r['context_id'] for r in expected})==len(expected),'all_context_tokens_within4096':selection['context_tokens']<=4096,'private_output_not_tracked':ignored}
    if not ev.equal(value['checks'],checks) or not valid_receipt(value,5):raise ValueError('Parent checks do not recompute')
    if private:
        if record(local)!=ref:raise ValueError('Actual local parent body hash differs')
        actual=json.loads(local.read_text('utf-8'))
        if not ev.equal([{k:v for k,v in r.items() if k!='content_zh'} for r in actual['results']],expected):raise ValueError('Actual local parent metadata differs')
        if any(digest(r['content_zh'].encode())!=r['content_sha256'] for r in actual['results']):raise ValueError('Actual local parent text differs')
    return checks


def verify(output,public_only=False,complete=False):
    checks={};errors=[]
    def check(name,fn):
        try:
            checks[name]=bool(fn())
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error':str(exc),'type':type(exc).__name__})
    raw=subprocess.check_output(['git','archive','--format=tar',BASE],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:old={m.name:archive.extractfile(m).read() for m in archive.getmembers() if m.isfile()}
    check('643_original_public_files_except_declared_repairs_and_navigation_preserved',lambda:len(old)==643 and all((ROOT/p).read_bytes()==raw for p,raw in old.items() if p not in MUTABLE))
    registry=json.loads((ROOT/'data/manifests/experiment_manifest.json').read_text('utf-8'));prior=json.loads(old['data/manifests/experiment_manifest.json'])
    check('19_original_experiment_objects_preserved',lambda:len(prior['experiments'])==19 and registry['experiments'][:19]==prior['experiments'])
    for p in ('docs/EXPERIMENT_LOG.md','reports/resume_evidence.md','reports/all_experiments_summary.csv'):check(p+'_append_only',lambda p=p:(ROOT/p).read_bytes().startswith(old[p]))
    summaries={}
    def replay(split):summaries[split]=ev.replay(ev.DIRECTORY/split);return True
    for s in ('dev','test'):check(s+'_original_metrics_ranks_and_errors_replay_with_fixed_code',lambda s=s:replay(s))
    def result():
        final=json.loads((ROOT/'reports/chunking_comparison.json').read_text('utf-8'))
        return ev.equal(final['development'],summaries['dev']) and ev.equal(final['test'],summaries['test']) and final['selected_on_dev']==summaries['dev']['selected_on_this_split']=='parent_child' and summaries['test']['selected_on_this_split'] is None
    check('original_result_and_dev_only_selection_unchanged',result)
    check('formal_test_ledger_original_two_events_only',lambda:[r['event'] for r in ev.load_jsonl(ev.LEDGER)]==['STARTED','COMPLETED'])
    def current(name,n,names):
        v=json.loads((DIRECTORY/name).read_text('utf-8'))
        return valid_receipt(v,n) and all(v['source_sha256'][p]==record(ROOT/p)['sha256'] for p in names)
    check('21_original_checks_reproduce17_gaps_and4_controls',lambda:current('reproduction-final-v2.json',21,('scripts/verify_task11_audit.py',)))
    check('32_current_regressions_bound_to_repaired_code',lambda:current('regressions-complete.json',32,NAMES+('scripts/verify_task11_audit.py',)))
    check('46_original_contract_checks_bound_to_current_native_code',lambda:current('contract-current.json',46,ev.NATIVE))
    check('actual_current_query_receipt_producer_and_packet_valid',lambda:ev.validate_saved_query(json.loads((DIRECTORY/'query-current.json').read_text('utf-8'))))
    for name in ('parent-from-current.json','parent-from-legacy.json','parent-fresh.json'):
        check(name+'_five_real_parent_checks_recompute',lambda name=name:len(validate_parent_receipt(DIRECTORY/name))==5)
    def public(name,n,historical):
        v=json.loads((DIRECTORY/name).read_text('utf-8'))
        return valid_receipt(v,n) and v['historical_release'] is historical and v['site_packages_disabled'] is True and v['new_model_requests']==0 and v['source_sha256']==record(ROOT/'scripts/verify_task11_public_audit.py')['sha256']
    check('original_release25_public_checks_pass_at_original_commit',lambda:public('historical-public.json',25,True))
    check('current_independent_public_replay_and_mutations_pass',lambda:public('public-current.json',16,False))
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    check('no_private_corpus_index_model_dependencies_or_runtime_tracked',lambda:not any(p.startswith(('.runtime/','.tmp/','.venv/','.models/','data/indexes/','data/raw/','data/processed/','third_party/')) for p in tracked))
    if not public_only:
        before=json.loads((ROOT/'.runtime/task11-audit/before.json').read_text('utf-8'))
        check('25_private_index_files_preserved',lambda:len(before['indexes'])==25 and all(digest((ROOT/p).read_bytes())==v for p,v in before['indexes'].items()))
        check('derived_parent_child_corpus_preserved',lambda:digest((ROOT/'data/processed/rag_chunks_parent_child.jsonl').read_bytes())==before['derived_corpus'])
        check('original_human_review_ledger_preserved',lambda:digest((ROOT/'.runtime/eval_review/reviews.jsonl').read_bytes())==before['human_review_sha256'])
        corpus=json.loads((ROOT/'data/manifests/local_data_files.json').read_text('utf-8'))['files']
        check('61_original_corpus_files_preserved',lambda:len(corpus)==61 and all(digest((ROOT/r['path']).read_bytes())==r['sha256'] for r in corpus))
        for name in ('parent-from-current.json','parent-from-legacy.json','parent-fresh.json'):check(name+'_actual_private_bodies_match',lambda name=name:len(validate_parent_receipt(DIRECTORY/name,True))==5)
    if complete:
        for p in ('docs/TASK_11_AUDIT.md','reports/TASK_11_SUPPLEMENT.md'):check(p+'_delivered',lambda p=p:(ROOT/p).stat().st_size>100)
        check('20th_audit_experiment_registered',lambda:len(registry['experiments'])==20 and registry['experiments'][-1]['id']=='TASK-011-AUDIT')
        check('audit_registered_artifact_hashes_match',lambda:all(record(ROOT/r['path'])==r for r in registry['experiments'][-1]['artifacts']))
        code=NAMES+('scripts/verify_task11_audit.py','scripts/verify_task11_audit_delivery.py')
        def registered_source():
            entry=registry['experiments'][-1]
            return entry['source_sha256']=={p:record(ROOT/p)['sha256'] for p in code} and all(entry['source_sha256'][p]==digest(subprocess.check_output(['git','show',entry['source_commit']+':'+p],cwd=ROOT)) for p in code)
        check('audit_registered_source_matches_frozen_commit',registered_source)
    value={'version':'task11-audit-delivery-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,
           'public_only':public_only,'complete':complete,'new_model_requests':0,'new_test_queries':0,'source_sha256':record(__file__)['sha256']}
    write_new(output,value);return value


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--public-only',action='store_true');p.add_argument('--complete',action='store_true');a=p.parse_args()
    from run_structure_comparison import output_path
    value=verify(output_path(a.report),a.public_only,a.complete);print(json.dumps({k:value[k] for k in ('status','passed','total','errors')}));return 0 if value['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
