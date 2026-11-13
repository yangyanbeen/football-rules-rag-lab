"""Task10 audit reproductions/regressions. No model calls or new test retrieval."""
import argparse,contextlib,copy,io,json,subprocess,sys,types,uuid
from pathlib import Path
from unittest.mock import patch
from eval_dataset import ROOT,canonical,digest,load_jsonl
from bm25_index import record,write_new
from bm25_retrieval_eval import now
import reranker_eval as ev
import reranker_live as live
import run_reranker_experiment as runner
from verify_reranker_contract import synthetic

BASE='e24e5c1b37585fe91047a6c6f64c6bdaf7273291'


def historic(name):
    module=types.ModuleType('original_'+Path(name).stem)
    raw=subprocess.check_output(['git','show',BASE+':'+name],cwd=ROOT)
    exec(compile(raw,name+'@'+BASE,'exec'),module.__dict__);return module


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--expect-gaps',action='store_true');a=p.parse_args();output=runner.new_report(a.report)
    temp=ROOT/'.tmp'/('task10-audit-'+uuid.uuid4().hex);temp.mkdir(parents=True)
    checks={};errors=[];observed={};cfg=ev.config();question,known,packets=synthetic()
    target_ev=historic('scripts/reranker_eval.py') if a.expect_gaps else ev
    target_live=historic('scripts/reranker_live.py') if a.expect_gaps else live
    target_runner=historic('scripts/run_reranker_experiment.py') if a.expect_gaps else runner
    def check(name,fn):
        try:checks[name]=bool(fn())
        except Exception as exc:checks[name]=False;errors.append({'check':name,'type':type(exc).__name__,'error':str(exc)})
    def rejects(fn):
        try:fn()
        except (ValueError,TypeError,KeyError,OverflowError,OSError):return True
        return False
    def gap(name,fixed):
        def evaluate():
            value=bool(fixed());observed[name]={'fixed_behavior_observed':value,'expected_original_gap':a.expect_gaps}
            return value is (not a.expect_gaps)
        check(name,evaluate)
    def packet_change(change,method='top20'):
        value=copy.deepcopy(packets[method]);change(value)
        return rejects(lambda:target_ev.validate_packet(value,question,method,known,cfg))
    gap('reject_truncation_below_max_length',lambda:packet_change(lambda v:v['reranker']['results'][0].update(used_tokens=99,truncated_tokens=1)))
    gap('reject_boolean_top10_rank',lambda:packet_change(lambda v:v['results'][0].update(rank=True)))
    gap('reject_boolean_control_rank',lambda:packet_change(lambda v:v['results'][0].update(rank=True),'no_rerank'))
    def bad_model(name):
        bad=copy.deepcopy(cfg);bad['files'][name]['sha256']='0'*64
        with patch.object(Path,'read_text',return_value=json.dumps(bad)):return rejects(target_ev.config)
    for name in ('tokenizer.json','tokenizer_config.json','special_tokens_map.json','config.json'):
        gap('reject_changed_official_'+name,lambda name=name:bad_model(name))
    def bad_channel(channel):
        channels=copy.deepcopy(packets['no_rerank']['channels'])
        if channel=='dense':channels['dense'][0].update(distance=2.,score=-1.)
        else:
            ids=list(known)[:2];channels['bm25']=[{'chunk_id':cid,'rank':i,'score':float(i)} for i,cid in enumerate(ids,1)]
        return rejects(lambda:target_ev.expanded(channels,known))
    gap('reject_unsorted_dense_scores',lambda:bad_channel('dense'))
    gap('reject_unsorted_bm25_scores',lambda:bad_channel('bm25'))
    def constructor_error():
        class Dense:
            def __init__(self,**_):pass
            def close(self):raise RuntimeError('SYNTHETIC_CLEANUP_ERROR')
        stub=types.ModuleType('dense_index');stub.DenseIndex=Dense;stub.PinnedEmbedder=lambda *_:None
        def broken(*_):raise ValueError('SYNTHETIC_MODEL_ERROR')
        with patch.dict(sys.modules,{'dense_index':stub}),patch.object(target_live,'index_files',return_value={}),patch.object(target_live,'Bm25Index',return_value=None),patch.object(target_live,'BgeReranker',side_effect=broken),contextlib.redirect_stderr(io.StringIO()):
            try:target_live.RerankerRetriever(cfg)
            except Exception as exc:return type(exc) is ValueError and str(exc)=='SYNTHETIC_MODEL_ERROR'
        return False
    gap('constructor_keeps_primary_error_when_cleanup_fails',constructor_error)
    def observation_owned():
        obj=object.__new__(target_live.RerankerRetriever);packet=packets['no_rerank']
        rows=[{**r,'metadata':known[r['chunk_id']]} for r in packet['channels']['dense']]
        obj.dense=types.SimpleNamespace(query=lambda *_:{'results':rows,'timing':packet['channel_timing']['dense']})
        obj.bm25=types.SimpleNamespace(query=lambda *_:{'results':[],'timing':packet['channel_timing']['bm25']})
        obs=copy.deepcopy(packet['embedding_observation']);obj.embedder=types.SimpleNamespace(observations=[obs])
        result=obj.query(question,'no_rerank');result['embedding_observation']['inputs']=9
        return obs['inputs']==1
    gap('returned_embedding_observation_is_independent',observation_owned)
    def replay_preflight():
        calls=[];existing=temp/'existing.json';existing.write_text('{}','utf-8')
        with patch.object(sys,'argv',['runner','replay','--run-dir',str(ev.DIRECTORY/'dev'),'--output',str(existing)]),patch.object(target_runner,'replay',side_effect=lambda *_:calls.append('replay') or {'split':'dev'}):
            rejected=rejects(target_runner.main)
        return rejected and not calls
    gap('replay_output_checked_before_loading_data',replay_preflight)
    def wrong_summary():
        grant=json.loads((ev.DIRECTORY/'test_authorization.json').read_text('utf-8'))
        grant['development_summary']=record(ROOT/'reports/retrieval/dense_b0/dev/summary.json')
        return rejects(lambda:target_ev.validate_grant(grant,ev.DIRECTORY/'test'))
    gap('grant_summary_bound_to_development_manifest',wrong_summary)
    def partial_case():
        ids=list(known);q={'question_id':'SYNTHETIC','answerable':True,'expected_chunk_ids':[ids[0],ids[24]]}
        try:result=target_ev.errors_for([q],[{'variants':packets}],'dev',include_partial=True)
        except TypeError:return False
        case=next((c for c in result['cases'] if c['method']=='top20'),None)
        return case is not None and case['flags']['partial_prefix_support_loss'] is True and case['gold_excluded_by_prefix']==[ids[24]]
    gap('partial_prefix_support_loss_not_omitted',partial_case)
    if not a.expect_gaps:
        def variants_bad(field):
            values=copy.deepcopy(packets);row=values['top40']['reranker']['results'][0]
            row[field]='3'*64
            return rejects(lambda:ev.validate_variant_inputs(values))
        check('consistent_cross_budget_model_inputs_pass',lambda:ev.validate_variant_inputs(packets))
        for field in ('query_sha256','passage_sha256','input_ids_sha256'):
            check('reject_cross_budget_'+field,lambda field=field:variants_bad(field))
        def negative_roundoff():
            channels=copy.deepcopy(packets['no_rerank']['channels']);channels['dense'][0].update(distance=-1e-7,score=1.0000001)
            return bool(ev.expanded(channels,known))
        check('tiny_negative_cosine_roundoff_not_rejected',negative_roundoff)
        check('reject_nonfinite_channel_distance',lambda:rejects(lambda:ev.expanded({'dense':[{**r,'distance':float('nan')} for r in packets['no_rerank']['channels']['dense']],'bm25':[]},known)))
        def partial_legacy():
            ids=list(known);q={'question_id':'SYNTHETIC','answerable':True,'expected_chunk_ids':[ids[0],ids[24]]};rows=[{'variants':packets}]
            old=historic('scripts/reranker_eval.py').errors_for([q],rows,'dev');new=ev.errors_for([q],rows,'dev')
            return canonical(old)==canonical(new)
        check('legacy_error_schema_recomputes_byte_equivalent_values',partial_legacy)
        check('new_error_schema1_1_declared',lambda:ev.errors_for([],[],'dev',include_partial=True)['version']=='reranker-errors-1.1')
        check('partial_coverage_incomplete_top5_reported',lambda:ev.errors_for([{'question_id':'SYNTHETIC','answerable':True,'expected_chunk_ids':[list(known)[0],list(known)[24]]}],[{'variants':packets}],'dev',include_partial=True)['counts']['top20']['incomplete_gold_at_5']==1)
    # All original valid packets must still work; these are arithmetic fixtures.
    for method in ev.METHODS:
        check('valid_packet_'+method,lambda method=method:target_ev.validate_packet(packets[method],question,method,known,cfg) is packets[method])
    value={'version':'task10-audit-regressions-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL',
           'passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'observed':observed,
           'expected_original_gaps':a.expect_gaps,'baseline':BASE,'actual_model_requests':0,'new_locked_test_queries':0,
           'scope':'Historic/current module behavior on synthetic packets and in-memory grant copies; no saved evidence modified and no model inference.',
           'source_sha256':{n:record(ROOT/n)['sha256'] for n in ('scripts/verify_task10_audit.py',)+ev.NATIVE}}
    write_new(output,value);print(json.dumps({k:value[k] for k in ('status','passed','total','errors')}));return 0 if value['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
