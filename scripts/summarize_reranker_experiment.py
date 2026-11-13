"""Produce the prescribed Task10 report and readable per-question rank changes."""
import json
from eval_dataset import ROOT,EVAL,load_jsonl
from bm25_index import record,write_new
from bm25_retrieval_eval import now
from reranker_eval import DIRECTORY,METHODS,BUDGETS,config,replay


def rank_changes(split):
    questions=load_jsonl(EVAL/('retrieval_'+split+'.jsonl'));rows=load_jsonl(DIRECTORY/split/'predictions.jsonl');result=[]
    for q,row in zip(questions,rows):
        before=row['variants']['no_rerank']['before'];original={r['chunk_id']:r['rank'] for r in before};methods={}
        for method in METHODS:
            p=row['variants'][method];ranked=p['reranker']['results'] if p['reranker'] else p['before']
            after={r['chunk_id']:r for r in ranked}
            methods[method]={'candidate_budget':BUDGETS[method] or 80,'before_top10':[r['chunk_id'] for r in p['before'][:10]],
                'after_top10':[r['chunk_id'] for r in p['results']],
                'labelled_support_rank_changes':[{'chunk_id':cid,'before_rank_within80':original.get(cid),
                    'after_rank_within_candidates':after.get(cid,{}).get('rank'),
                    'excluded_by_prefix':cid in original and original[cid]>(BUDGETS[method] or 80),
                    'reranker_input_truncated':bool(after.get(cid,{}).get('truncated_tokens',0))} for cid in q['expected_chunk_ids']]}
        result.append({'question_id':q['question_id'],'question':q['question'],'answerable':q['answerable'],
                       'labelled_support_chunk_ids':q['expected_chunk_ids'],'methods':methods})
    return {'split':split,'scope':'Readable derivative of raw predictions, not additional model requests. Ranks beyond10 are diagnostic only.','questions':result}


def report_payload():
    dev=replay(DIRECTORY/'dev');test=replay(DIRECTORY/'test')
    grant=json.loads((DIRECTORY/'test_authorization.json').read_text('utf-8'))
    methods=test['methods'];a=methods['top40'];b=methods['top80']
    return {'version':'bge-reranker-report-1.0','config':config(),
        'source_commit':grant['source_commit'],'selected_method_on_dev':grant['selected_method'],
        'development':dev,'test':test,
        'observed_top40_vs_top80':{
            'test_metric_difference':{k:a['quality']['metrics'][k]-b['quality']['metrics'][k] for k in ('Recall@5','Recall@10','MRR@10')},
            'test_rerank_P50_relative_reduction':1-a['latency']['rerank_seconds']['P50_ms']/b['latency']['rerank_seconds']['P50_ms'],
            'scope':'Descriptive paired-query sample across four independently executed methods; not a production speedup guarantee or automatic selection of40.'},
        'truncation_and_ranking_errors':{s:json.loads((DIRECTORY/s/'error_analysis.json').read_text('utf-8'))['counts'] for s in ('dev','test')},
        'artifacts':{s:{n:record(DIRECTORY/s/n) for n in ('run_manifest.json','predictions.jsonl','summary.json','error_analysis.json','rank_changes.json')} for s in ('dev','test')},
        'test_authorization':record(DIRECTORY/'test_authorization.json'),'test_usage':record(DIRECTORY/'test_usage.jsonl'),
        'decision':'Freeze the development-selected method '+grant['selected_method']+' for this experiment. Test is report-only; retain the unchanged Task6 application until a separately authorized integration task.',
        'limitations':['99 fixed Wikipedia-derived Chinese chunks; source/version qualifications remain; not authoritative football advice.',
            '40dev/50test; retrieval quality uses32/40 answerable questions. No answer, citation, refusal accuracy or QPS measured.',
            'This locked test was previously used in Tasks7–9; it is not a new unseen holdout.',
            'One actual measurement per query per method after3warmups per method, rotating order; ordinary desktop CPU, no confidence intervals or isolated production load.',
            'Original Task9 Top10/channel scores are historical context only; Task10 equal-condition control uses new actual Top80/channel.',
            'No graded relevance labels; nDCG is null. Cross-encoder logits are not probabilities.',
            'Public replay recomputes fusion, sorting, metrics, errors and timing; it cannot rederive model logits or private passage tokenization without separately restored pinned model/corpus.']}


def main():
    for split in ('dev','test'):write_new(DIRECTORY/split/'rank_changes.json',rank_changes(split))
    value=report_payload();write_new(ROOT/'reports/reranker_results.json',{'generated_at':now(),**value})
    print(json.dumps({'status':'COMPLETE','selected_on_dev':value['selected_method_on_dev'],
                      'test':{m:r['quality']['metrics'] for m,r in value['test']['methods'].items()}}))


if __name__=='__main__':main()
