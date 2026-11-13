"""Isolated cold-start/lifecycle regression; mocks make zero model/test requests."""
import argparse,contextlib,hashlib,io,json,sys,types,uuid
from pathlib import Path
from unittest.mock import patch
from eval_dataset import ROOT,digest
from bm25_index import record,write_new
from bm25_retrieval_eval import now
import reranker_eval as ev
import run_reranker_experiment as runner


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--expect-cold-gap',action='store_true');a=p.parse_args()
    output=runner.new_report(a.report);temp=ROOT/'.tmp'/('task10-lifecycle-'+uuid.uuid4().hex);temp.mkdir(parents=True)
    checks={};errors=[];ledger=ev.LEDGER.read_bytes() if ev.LEDGER.exists() else None
    def check(name,fn):
        try:checks[name]=bool(fn())
        except Exception as exc:checks[name]=False;errors.append({'check':name,'type':type(exc).__name__,'error':str(exc)})
    def execute(kind):
        events=[];out=temp/kind
        class Engine:
            def __init__(self,*_):
                events.append(('init',0));self.calls=0;self.before={};self.closed=False
                if kind=='load_failure':raise RuntimeError('SYNTHETIC_LOAD_FAILURE')
            def __enter__(self):return self
            def __exit__(self,*args):self.closed=True;events.append(('close',self.calls));return False
            def environment(self):
                events.append(('environment',self.calls))
                if kind=='cold' and not self.calls:raise RuntimeError('SYNTHETIC_MODEL_NOT_RESIDENT')
                return {}
            def query(self,question,method):
                self.calls+=1;events.append(('query',question))
                if kind=='query_failure' and self.calls==13:raise RuntimeError('SYNTHETIC_QUERY_FAILURE')
                return {'timing':{'total_seconds':.001}}
        synthetic=[{'question_id':'SYNTHETIC','question':'Synthetic lifecycle question, not in evaluation data','answerable':True,'expected_chunk_ids':['synthetic']}]
        stub=types.ModuleType('reranker_live');stub.RerankerRetriever=Engine
        summary={'split':'dev','selected_on_this_split':'top40','methods':{m:{'quality':{'metrics':{}}} for m in ev.METHODS}}
        patches=[patch.dict(sys.modules,{'reranker_live':stub}),patch.object(runner,'run_path',return_value=out),
                 patch.object(runner,'require_release',return_value=None),patch.object(runner,'committed',return_value='a'*40),
                 patch.object(runner,'snapshots',return_value={}),patch.object(runner,'validate_inputs',return_value=None),
                 patch.object(runner,'load_jsonl',return_value=synthetic),patch.object(runner,'summarize',return_value=summary),
                 patch.object(runner,'errors_for',return_value={}),patch.object(runner,'replay',return_value=summary),
                 patch('hybrid_live.index_files',return_value={})]
        error=None
        with contextlib.ExitStack() as stack:
            for value in patches:stack.enter_context(value)
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            try:runner.evaluate(types.SimpleNamespace(mode='dev',run_dir=out,authorization=None))
            except RuntimeError as exc:error=str(exc)
        return {'events':events,'error':error,'out':out}
    cold=execute('cold');load=execute('load_failure');query=execute('query_failure')
    if a.expect_cold_gap:
        check('original_cold_dependency_reproduced_with_mocked_empty_residency',lambda:cold['error']=='SYNTHETIC_MODEL_NOT_RESIDENT')
        check('original_environment_before_first_warmup',lambda:('environment',0) in cold['events'])
    else:
        check('cold_lifecycle_completes_after_warmup',lambda:cold['error'] is None)
        check('environment_after_all12_warmups_before_measurements',lambda:('environment',12) in cold['events'])
        check('all12_warmups_and4_measured_calls_executed',lambda:sum(e[0]=='query' for e in cold['events'])==16)
    check('cold_engine_closed_even_on_failure',lambda:any(e[0]=='close' for e in cold['events']))
    check('primary_load_exception_preserved',lambda:load['error']=='SYNTHETIC_LOAD_FAILURE')
    check('load_failure_phase_and_type_recorded',lambda:(lambda v:v['phase']=='load_models' and v['error_type']=='RuntimeError' and v['error']=='SYNTHETIC_LOAD_FAILURE')(json.loads((load['out']/'failure.json').read_text('utf-8'))))
    check('primary_query_exception_preserved',lambda:query['error']=='SYNTHETIC_QUERY_FAILURE')
    check('query_failure_question_and_phase_recorded',lambda:(lambda v:v['phase']=='measure' and v['question_id']=='SYNTHETIC')(json.loads((query['out']/'failure.json').read_text('utf-8'))))
    check('query_engine_closed_on_failure',lambda:any(e[0]=='close' for e in query['events']))
    check('only_declared_synthetic_or_ad_hoc_text_reaches_query_api',lambda:all(event[1] in (ev.config()['warmup_question'],'Synthetic lifecycle question, not in evaluation data') for run in (cold,load,query) for event in run['events'] if event[0]=='query'))
    def independent_output():
        import reranker_live as live
        from verify_reranker_contract import synthetic
        question,known,variants=synthetic();packet=variants['no_rerank'];obj=object.__new__(live.RerankerRetriever)
        rows=[{**{k:r[k] for k in ('chunk_id','rank','score','distance')},'metadata':known[r['chunk_id']]} for r in packet['channels']['dense']]
        obj.dense=types.SimpleNamespace(query=lambda *_:{'results':rows,'timing':packet['channel_timing']['dense']})
        obj.bm25=types.SimpleNamespace(query=lambda *_:{'results':[],'timing':packet['channel_timing']['bm25']})
        obj.embedder=types.SimpleNamespace(observations=[packet['embedding_observation']])
        output=obj.query(question,'no_rerank');before=output['before'][0]['score'];output['results'][0]['score']=-999.
        return output['before'][0]['score']==before
    check('original_top10_alias_reproduced' if a.expect_cold_gap else 'top10_output_cannot_mutate_before80_ranking',lambda:independent_output() is (False if a.expect_cold_gap else True))
    check('real_test_ledger_untouched',lambda:(ev.LEDGER.read_bytes() if ev.LEDGER.exists() else None)==ledger)
    result={'version':'reranker-lifecycle-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL',
            'passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,
            'expected_original_gap':a.expect_cold_gap,'actual_model_requests':0,'actual_locked_test_queries':0,
            'scope':'In-process mocked lifecycle, not an actual cold model execution or retrieval quality sample.',
            'source_sha256':{n:record(ROOT/n)['sha256'] for n in ('scripts/verify_reranker_lifecycle.py','scripts/run_reranker_experiment.py','scripts/reranker_live.py')}}
    write_new(output,result);print(json.dumps({k:result[k] for k in ('status','passed','total','errors')}));return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
