"""Task10 arithmetic/adversarial checks; synthetic cases are not metric samples."""
import argparse,copy,json,math,uuid
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from eval_dataset import ROOT,EVAL,canonical,digest,load_jsonl
from bm25_index import record,write_new
from bm25_retrieval_eval import now,statistics
from retrieval_metrics import compute_metrics
from rrf import fuse,SOURCE_FIELDS
import reranker_eval as ev
import run_reranker_experiment as runner
from run_bm25_retrieval import reserve_test_usage,finish_test_usage


def synthetic():
    known=json.loads((ROOT/'reports/retrieval/dense_b0/dev/source_map.json').read_text('utf-8'))
    mapping={r['chunk_id']:r for r in known}
    channels={'dense':[{'chunk_id':r['chunk_id'],'rank':i,'score':1-i/100,'distance':i/100} for i,r in enumerate(known[:80],1)],'bm25':[]}
    before=[{k:r[k] for k in ('chunk_id','rank','score')} for r in fuse(ev.expanded(channels,mapping),60,80)['rrf']]
    question='合成算术例子，非评测题';query=ev.normalize_query(question)
    variants={}
    for method in ev.METHODS:
        budget=ev.BUDGETS[method];reranker=None;rerank_seconds=0.
        if budget:
            records=[{'chunk_id':r['chunk_id'],'before_rank':i,'rank':i,'score':float(budget-i),
                      'query_sha256':digest(query.encode()),'passage_sha256':'1'*64,'input_ids_sha256':'2'*64,
                      'original_tokens':100,'used_tokens':100,'truncated_tokens':0} for i,r in enumerate(before[:budget],1)]
            batches=[{'offset':i,'size':min(8,budget-i),'padded_length':100,'tokenization_and_tensor_seconds':.001,'inference_seconds':.01} for i in range(0,budget,8)]
            token=sum(b['tokenization_and_tensor_seconds'] for b in batches);infer=sum(b['inference_seconds'] for b in batches)
            rerank_seconds=token+infer+.002
            reranker={'results':records,'batches':batches,'timing':{'tokenization_and_tensor_seconds':token,'inference_seconds':infer,'other_seconds':.001,'total_seconds':token+infer+.001}}
            results=[{k:r[k] for k in ('chunk_id','rank','score')} for r in records[:10]]
        else:results=before[:10]
        variants[method]={'method':method,'query':query,'channels':copy.deepcopy(channels),'before':copy.deepcopy(before),
             'reranker':reranker,'results':copy.deepcopy(results),
             'timing':{'normalization_seconds':.001,'dense_seconds':.2,'bm25_seconds':.01,'fusion_seconds':.002,'rerank_seconds':rerank_seconds,'total_seconds':.213+rerank_seconds},
             'channel_timing':{'dense':{'query_embedding_seconds':.18,'vector_search_seconds':.01},
                              'bm25':{'normalization_seconds':.001,'tokenization_seconds':.001,'scoring_seconds':.001,'total_seconds':.003}},
             'embedding_observation':{'inputs':1,'elapsed_seconds':.17,'prompt_eval_count':10,'server_load_duration_ns':1000,'server_total_duration_ns':160000000}}
    return question,mapping,variants


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--development-run',type=Path)
    a=p.parse_args();out=runner.new_report(a.report);temp=ROOT/'.tmp'/('task10-contract-'+uuid.uuid4().hex);temp.mkdir(parents=True)
    cfg=ev.config();question,known,variants=synthetic();checks={};errors=[]
    def check(name,fn):
        try:checks[name]=bool(fn())
        except Exception as exc:checks[name]=False;errors.append({'check':name,'type':type(exc).__name__,'error':str(exc)})
    def rejects(fn):
        try:fn()
        except (ValueError,KeyError,TypeError,OSError):return True
        return False
    for method in ev.METHODS:check('valid_'+method,lambda method=method:ev.validate_packet(variants[method],question,method,known,cfg) is variants[method])
    check('actual_80_before_candidates_each_variant',lambda:all(len(p['before'])==80 for p in variants.values()))
    check('hand_rrf_first_score',lambda:variants['no_rerank']['before'][0]['score']==1/61)
    check('discrete_budget20_40_80',lambda:[len(variants[m]['reranker']['results']) for m in ev.METHODS[1:]]==[20,40,80])
    check('last_inference_batch20_is4',lambda:variants['top20']['reranker']['batches'][-1]['size']==4)
    check('no_rerank_has_no_model_scores_or_cost',lambda:variants['no_rerank']['reranker'] is None and variants['no_rerank']['timing']['rerank_seconds']==0)
    def bad(method,mutate):
        packet=copy.deepcopy(variants[method]);mutate(packet);return rejects(lambda:ev.validate_packet(packet,question,method,known,cfg))
    mutations=[
      ('extra_fulltext',lambda p:p.update(content_zh='forbidden')),
      ('wrong_query',lambda p:p.update(query='other')),
      ('unknown_method',lambda p:p.update(method='top99')),
      ('wrong_budget',lambda p:p['reranker']['results'].pop()),
      ('duplicate_candidate',lambda p:p['reranker']['results'][1].update(chunk_id=p['reranker']['results'][0]['chunk_id'])),
      ('unknown_id',lambda p:p['reranker']['results'][0].update(chunk_id='missing')),
      ('nan_logit',lambda p:p['reranker']['results'][0].update(score=math.nan)),
      ('boolean_logit',lambda p:p['reranker']['results'][0].update(score=True)),
      ('infinite_logit',lambda p:p['reranker']['results'][0].update(score=math.inf)),
      ('wrong_before_rank',lambda p:p['reranker']['results'][0].update(before_rank=2)),
      ('boolean_rank',lambda p:p['reranker']['results'][0].update(rank=True)),
      ('sort_wrong',lambda p:p['reranker']['results'].reverse()),
      ('rank_gap',lambda p:p['reranker']['results'][0].update(rank=0)),
      ('missing_batch',lambda p:p['reranker']['batches'].pop()),
      ('batch_offset',lambda p:p['reranker']['batches'][0].update(offset=1)),
      ('batch_size',lambda p:p['reranker']['batches'][0].update(size=7)),
      ('padding_mismatch',lambda p:p['reranker']['batches'][0].update(padded_length=512)),
      ('batch_nan_timing',lambda p:p['reranker']['batches'][0].update(inference_seconds=math.nan)),
      ('batch_sum',lambda p:p['reranker']['timing'].update(inference_seconds=100.)),
      ('rerank_outer_omits_work',lambda p:p['timing'].update(rerank_seconds=.00001)),
      ('chain_stage_sum',lambda p:p['timing'].update(total_seconds=10.)),
      ('negative_chain',lambda p:p['timing'].update(dense_seconds=-1.)),
      ('token_noninteger',lambda p:p['reranker']['results'][0].update(used_tokens=True)),
      ('token_over512',lambda p:p['reranker']['results'][0].update(used_tokens=513)),
      ('token_negative',lambda p:p['reranker']['results'][0].update(truncated_tokens=-1)),
      ('token_accounting',lambda p:p['reranker']['results'][0].update(original_tokens=101)),
      ('query_input_hash',lambda p:p['reranker']['results'][0].update(query_sha256='0'*64)),
      ('missing_input_hash',lambda p:p['reranker']['results'][0].pop('input_ids_sha256')),
      ('passage_hash',lambda p:p['reranker']['results'][0].update(passage_sha256='x')),
      ('top10_tamper',lambda p:p['results'].reverse()),
      ('before_rrf_score',lambda p:p['before'][0].update(score=.5)),
      ('before_candidate_drop',lambda p:p['before'].pop()),
      ('channel80_required',lambda p:p['channels']['dense'].pop()),
      ('channel_missing',lambda p:p['channels'].pop('bm25')),
      ('channel_rank_gap',lambda p:p['channels']['dense'][0].update(rank=0)),
      ('channel_unknown_id',lambda p:p['channels']['dense'][0].update(chunk_id='unknown')),
      ('source_fulltext_injection',lambda p:p['channels']['dense'][0].update(content_zh='forbidden')),
      ('embedding_call_count',lambda p:p['embedding_observation'].update(inputs=2)),
      ('embedding_timing',lambda p:p['embedding_observation'].update(elapsed_seconds=5.)),
      ('embedding_model_counters',lambda p:p['embedding_observation'].update(server_total_duration_ns=-1)),
      ('bm25_stage_containment',lambda p:p['channel_timing']['bm25'].update(total_seconds=10.))]
    for name,mutate in mutations:check('reject_'+name,lambda mutate=mutate:bad('top20',mutate))
    check('reject_control_model_cost',lambda:bad('no_rerank',lambda p:p['timing'].update(rerank_seconds=.01)))
    check('reject_control_top10_reorder',lambda:bad('no_rerank',lambda p:p['results'].reverse()))
    for value in ('',None,'x'*1201):check('reject_invalid_query_'+str(type(value).__name__)+str(len(str(value))),lambda value=value:rejects(lambda:ev.normalize_query(value)))
    check('reject_output_escape_before_models',lambda:rejects(lambda:runner.run_path(ROOT.parent/'outside-task10')))
    check('reject_existing_run_before_models',lambda:rejects(lambda:runner.run_path(ROOT/'reports/retrieval/dense_b0/dev')))
    check('reject_existing_report',lambda:rejects(lambda:runner.new_report(ROOT/'reports/hybrid_rrf_results.json')))
    # Independent metric arithmetic: first relevant at rank2; one miss; unanswerable excluded.
    qs=[{'question_id':'a','answerable':True,'expected_chunk_ids':['good']},
        {'question_id':'b','answerable':True,'expected_chunk_ids':['absent']},
        {'question_id':'u','answerable':False,'expected_chunk_ids':[]}]
    ps=[{'question_id':q['question_id'],'results':[{'chunk_id':'bad','rank':1},{'chunk_id':'good','rank':2}]} for q in qs]
    metrics=compute_metrics(qs,ps)
    check('hand_recall_half',lambda:metrics['metrics']['Recall@5']==.5 and metrics['metrics']['Recall@10']==.5)
    check('hand_mrr_quarter',lambda:metrics['metrics']['MRR@10']==.25)
    check('unanswerable_not_quality_denominator',lambda:metrics['answerable_denominator']==2 and metrics['unanswerable_excluded']==1)
    check('ndcg_null_without_graded_labels',lambda:metrics['nDCG@10'] is None)
    check('overflowing_counter_rejected',lambda:ev.number(10**1000) is False)
    check('warmup_is_not_dev_or_test_question',lambda:not any(digest(q['question'].encode())==digest(cfg['warmup_question'].encode()) for split in ('dev','test') for q in load_jsonl(EVAL/('retrieval_'+split+'.jsonl'))))
    check('linear_p50_p95',lambda:statistics([1.,2.,3.,4.])['P50_ms']==2500. and abs(statistics([1.,2.,3.,4.])['P95_ms']-3850.)<1e-8)
    # Support at rank30 is lost only by20; rank70 only by20/40; rank90 outside80.
    def truncation():
        row={'variants':variants};qs=[];rows=[]
        ids=list(known)
        for i,pos in enumerate((29,69,89)):
            qs.append({'question_id':str(i),'answerable':True,'expected_chunk_ids':[ids[pos]]});rows.append(row)
        error=ev.errors_for(qs,rows,'dev')['counts']
        return error['top20']['gold_lost_vs_top80']==2 and error['top40']['gold_lost_vs_top80']==1 and error['top80']['gold_lost_vs_top80']==0 and error['top80']['no_gold_in_candidates']==1
    check('truncation_loss_distinguished_from_top80_miss',truncation)
    path=temp/'ledger.jsonl';usage={'run_id':'synthetic','template':'synthetic','authorization':None,'run_directory':'synthetic','test_sha256':'0'*64,'source_commit':'1'*40}
    def reserve():
        try:reserve_test_usage(path,{**usage,'event':'STARTED'});return True
        except FileExistsError:return False
    with ThreadPoolExecutor(2) as pool:winners=list(pool.map(lambda _:reserve(),range(2)))
    check('exclusive_test_reservation_one_winner',lambda:winners.count(True)==1)
    check('wrong_run_cannot_finish',lambda:rejects(lambda:finish_test_usage(path,{**usage,'run_id':'wrong','event':'COMPLETED'})))
    finish_test_usage(path,{**usage,'event':'FAILED'})
    check('failure_consumes_own_reservation',lambda:[r['event'] for r in load_jsonl(path)]==['STARTED','FAILED'])
    check('finished_test_cannot_finish_again',lambda:rejects(lambda:finish_test_usage(path,{**usage,'event':'COMPLETED'})))
    development_manifest=None
    if a.development_run:
        summary=ev.replay(a.development_run);development_manifest=record(a.development_run/'run_manifest.json')
        check('saved_dev_full_replay',lambda:summary['split']=='dev' and summary['new_embedding_queries']==160 and summary['new_reranker_pairs']==5600)
        check('all_four_dev_latency_samples40',lambda:all(v['latency']['total_seconds']['samples']==40 and v['latency']['rerank_seconds']['samples']==40 for v in summary['methods'].values()))
        check('selection_restricted_to_dev',lambda:summary['selected_on_this_split'] in ev.METHODS)
        check('dev_no_answer_llm_requests',lambda:summary['answer_llm_requests']==0)
    result={'version':'reranker-contract-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL',
            'passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,
            'development_manifest':development_manifest,'source_sha256':{p:record(ROOT/p)['sha256'] for p in ev.NATIVE},
            'scope':'Synthetic contract checks and saved-development recomputation; no new test queries or model calls'}
    write_new(out,result);print(json.dumps({k:result[k] for k in ('status','passed','total','errors')}));return 0 if all(checks.values()) else 1


if __name__=='__main__':raise SystemExit(main())
