"""Check equivalent rebuilt indexes after legitimate producer commits change."""
import argparse,copy,json,subprocess,sys,uuid
from pathlib import Path
from bm25_index import ROOT,build,Bm25Index,record,write_new
from bm25_retrieval_eval import validate_index_manifest,snapshots,replay,now

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    report=a.report.resolve()
    if report.exists() or not report.is_relative_to(ROOT/'reports'):raise ValueError('Use new report')
    path=ROOT/'.tmp'/('bm25-restored-'+uuid.uuid4().hex)/'title_body';build(path,'title_body')
    rebuilt=Bm25Index(path);old=ROOT/'data/indexes/bm25/title_body';checks={}
    def rejects(f):
        try:f()
        except (ValueError,KeyError,TypeError):return True
        return False
    checks['index_and_source_map_bytes_identical']=all((path/n).read_bytes()==(old/n).read_bytes() for n in ('index.json','source_map.json'))
    checks['legitimate_producer_commit_changed']=rebuilt.manifest['source_commit']!=json.loads((old/'index_manifest.json').read_text('utf-8'))['source_commit']
    validate_index_manifest(rebuilt.manifest,'title_body',snapshots());checks['equivalent_rebuild_accepted']=True
    bad=copy.deepcopy(rebuilt.manifest);bad['artifacts']['index.json']['sha256']='0'*64
    checks['changed_payload_still_rejected']=rejects(lambda:validate_index_manifest(bad,'title_body',snapshots()))
    bad=copy.deepcopy(rebuilt.manifest);bad['sources']['scripts/bm25_index.py']['sha256']='0'*64
    checks['forged_producer_still_rejected']=rejects(lambda:validate_index_manifest(bad,'title_body',snapshots()))
    output=ROOT/'reports/retrieval'/('bm25-restored-dev-'+uuid.uuid4().hex)
    proc=subprocess.run([sys.executable,'-B','scripts/run_bm25_retrieval.py','dev','--template','title_body',
                         '--index',str(path),'--run-dir',str(output)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=120)
    checks['restored_index_actual_development_run_completed']=proc.returncode==0
    if proc.returncode==0:
        current=replay(output);baseline=replay(ROOT/'reports/retrieval/bm25_b0/development/title_body')
        checks['restored_index_development_metrics_unchanged']=current['quality']['metrics']==baseline['quality']['metrics']
    else:checks['restored_index_development_metrics_unchanged']=False
    raw=(ROOT/'data/manifests/bm25_indexes.json').read_bytes()
    verify=subprocess.run([sys.executable,'-B','scripts/export_bm25_manifests.py'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=60)
    checks['export_verifies_without_rewriting_original_metadata']=verify.returncode==0 and raw==(ROOT/'data/manifests/bm25_indexes.json').read_bytes()
    result={'captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),
            'checks':checks,'rebuilt_index_manifest':record(path/'index_manifest.json'),'actual_development_directory':output.relative_to(ROOT).as_posix(),
            'new_locked_test_requests':0,'scope':'New dev run with equivalent restored postings; original B0 test/source files unchanged',
            'stderr_has_known_jieba_deprecation_warning':'pkg_resources is deprecated' in proc.stderr,
            'failure_stderr':proc.stderr if proc.returncode else None,
            'source_sha256':{p:record(ROOT/'scripts'/p)['sha256'] for p in ('verify_bm25_portability.py','bm25_retrieval_eval.py','run_bm25_retrieval.py','export_bm25_manifests.py')}}
    write_new(report,result);print(json.dumps({k:result[k] for k in ('status','passed','total')}))
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
