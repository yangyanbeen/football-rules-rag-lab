"""Task9 isolated regression/reproduction; no original test inference or fusion."""
import argparse,contextlib,copy,io,json,sys,uuid
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from eval_dataset import ROOT,canonical
from bm25_index import write_new,record
from bm25_retrieval_eval import now
import rrf,hybrid_live as live,run_hybrid_retrieval as runner

BASE='8553f390107fc9f38cdefb927fa4f016b996f4bc'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--expect-gaps',action='store_true');p.add_argument('--live-report',type=Path);a=p.parse_args()
    report=runner.new_report(a.report);temp=ROOT/'.tmp'/('task9-audit-'+uuid.uuid4().hex);temp.mkdir(parents=True)
    checks={};errors=[]
    def check(name,fn):
        try:checks[name]=bool(fn())
        except Exception as exc:checks[name]=False;errors.append({'check':name,'type':type(exc).__name__,'error':str(exc)})
    packet=json.loads((ROOT/'reports/retrieval/hybrid_rrf_b0/dev/predictions.jsonl').read_text('utf-8').splitlines()[0])
    channels={c:packet['channels'][c]['results'] for c in rrf.CHANNELS}
    def isolated_input():
        values=copy.deepcopy(channels);old=canonical(values);result=rrf.fuse(values)
        result['rrf'][0]['source_lines'][0]=999999
        return canonical(values)==old
    def isolated_methods():
        result=rrf.fuse(channels);old=canonical({k:v for k,v in result.items() if k!='rrf'})
        result['rrf'][0]['sources'][next(iter(result['rrf'][0]['sources']))]['rank']=999
        return canonical({k:v for k,v in result.items() if k!='rrf'})==old
    def cli_preflight(kind):
        calls=[]
        class Engine:
            def __init__(self,*args):calls.append('init')
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def query(self,q):calls.append('query');return {}
        existing=temp/'existing.json';existing.write_text('{}','utf-8')
        argv=['run_hybrid_retrieval.py','query','--question','synthetic']
        if kind=='existing':argv+=['--output',str(existing)]
        elif kind=='outside':argv+=['--output',str(temp/'outside.txt')]
        elif kind=='blank':argv=['run_hybrid_retrieval.py','query','--question',' ']
        with patch.object(sys,'argv',argv),patch.object(live,'HybridRetriever',Engine),contextlib.redirect_stdout(io.StringIO()):
            try:runner.main()
            except (ValueError,SystemExit):pass
        return not calls
    def cleanup_primary():
        engine=live.HybridRetriever.__new__(live.HybridRetriever);engine.before={}
        class Dense:
            def close(self):raise RuntimeError('synthetic primary cleanup')
        engine.dense=Dense()
        with patch.object(live,'index_files',return_value={'changed':True}):
            try:engine.close()
            except Exception as exc:return type(exc) is RuntimeError and str(exc)=='synthetic primary cleanup'
        return False
    cases={'returned_metadata_does_not_alias_input':isolated_input,'different_methods_have_independent_sources':isolated_methods,
           'existing_query_output_rejected_before_engine':lambda:cli_preflight('existing'),
           'invalid_query_output_rejected_before_engine':lambda:cli_preflight('outside'),
           'blank_query_rejected_before_engine':lambda:cli_preflight('blank'),'cleanup_preserves_first_exception':cleanup_primary}
    for name,fn in cases.items():check(name,(lambda fn=fn:not fn()) if a.expect_gaps else fn)
    if not a.expect_gaps:
        receipt=json.loads((ROOT/'reports/retrieval/hybrid_rrf_b0/acceptance/live-smoke.json').read_text('utf-8'))
        check('original_live_receipt_validates_historically',lambda:live.validate_live_smoke(receipt) is not None)
        mutations=[('wrong_fusion_score',lambda r:r['queries'][0]['results']['rrf'][0].update(score=0)),
                   ('wrong_source_lines',lambda r:r['queries'][0]['channels']['dense']['results'][0].update(source_lines=[1,2])),
                   ('negative_stage',lambda r:r['queries'][0]['timing'].update(dense_seconds=-1)),
                   ('boolean_gpu_size',lambda r:r['embedding_runtime'].update(size_vram=False)),
                   ('wrong_model_digest',lambda r:r['embedding_runtime'].update(digest='0'*64)),
                   ('wrong_observation_count',lambda r:r['queries'][0]['embedding_observation'].update(inputs=2)),
                   ('missing_source_coverage',lambda r:r.update(source_sha256={})),
                   ('wrong_source_hash',lambda r:r['source_sha256'].__setitem__('scripts/rrf.py','0'*64)),
                   ('missing_query',lambda r:r['queries'].pop()),
                   ('wrong_k',lambda r:r['queries'][0].update(k=20)),
                   ('wrong_scope',lambda r:r.update(is_accuracy_evaluation=True)),
                   ('wrong_check_flag',lambda r:r['checks'].__setitem__(next(iter(r['checks'])),False)),
                   ('future_start',lambda r:r.update(started_at='2099-01-01T00:00:00+00:00')),
                   ('extra_body',lambda r:r['queries'][0]['channels']['dense']['results'][0].update(content_zh='synthetic body'))]
        for name,mutate in mutations:
            def rejects(mutate=mutate):
                bad=copy.deepcopy(receipt);mutate(bad)
                try:live.validate_live_smoke(bad)
                except (ValueError,KeyError,TypeError):return True
                return False
            check('live_rejects_'+name,rejects)
        check('rrf_values_unchanged_for_original_dev_packet',lambda:canonical(rrf.fuse(channels))==canonical(packet['results']))
        if a.live_report:
            fresh=json.loads(a.live_report.read_text('utf-8'))
            check('new_live_receipt_validates_with_producer_and_index_snapshots',lambda:len(live.validate_live_smoke(fresh))==17)
            def both_snapshots(r):
                key=next(iter(r['index_snapshots']['before']))
                for side in ('before','after'):r['index_snapshots'][side][key]['sha256']='0'*64
            def renamed_snapshot(r):
                key=next(iter(r['index_snapshots']['before']))
                for side in ('before','after'):
                    entry=r['index_snapshots'][side].pop(key);entry['path']=key+'-fake';r['index_snapshots'][side][key+'-fake']=entry
            for name,mutate in [('changed_after_snapshot',lambda r:r['index_snapshots']['after'].clear()),
                                ('same_forged_before_after',both_snapshots),('invented_index_path',renamed_snapshot),
                                ('wrong_declared_producer',lambda r:r.update(source_commit=live.ORIGINAL_SMOKE_SOURCE)),
                                ('boolean_request_count',lambda r:r.update(actual_embedding_queries=True)),
                                ('boolean_observation_count',lambda r:r['queries'][0]['embedding_observation'].update(inputs=True))]:
                def rejects_new(mutate=mutate):
                    bad=copy.deepcopy(fresh);mutate(bad)
                    try:live.validate_live_smoke(bad)
                    except (ValueError,KeyError,TypeError):return True
                    return False
                check('new_live_rejects_'+name,rejects_new)
    value={'version':'task9-audit-regression-1.0','captured_at':now(),'baseline':BASE,
           'status':('GAPS_REPRODUCED' if a.expect_gaps else 'PASS') if all(checks.values()) else 'FAIL',
           'passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,
           'new_locked_test_queries':0,'new_test_fusion_runs':0,'source_sha256':record(__file__)['sha256']}
    write_new(report,value);print(json.dumps({k:value[k] for k in ('status','passed','total','errors')}))
    return 0 if all(checks.values()) else 1


if __name__=='__main__':raise SystemExit(main())
