"""Prescribed Task9 report from saved predictions; no retrieval or tuning."""
import json
from eval_dataset import ROOT
from bm25_index import record,write_new
from bm25_retrieval_eval import now
from hybrid_retrieval_eval import replay,BASE_DIR,BASE,CONFIG


def report_payload():
    dev=replay(BASE_DIR/'dev');test=replay(BASE_DIR/'test')
    grant=json.loads((BASE_DIR/'test_authorization.json').read_text('utf-8'))
    return {'version':'hybrid-rrf-results-1.0','status':'COMPLETE','baseline_commit':BASE,'source_commit':grant['source_commit'],
            'config':grant['config'],'data_records':99,'development':dev,'test':test,
            'decision':'RRF improves over Dense but ties BM25 recall and lowers BM25 MRR on this fixed test. Keep as an explicit candidate-generation option, not the best single ranking baseline.',
            'new_channel_test_retrieval_requests':0,'new_formal_offline_test_fusion_runs':1,'answer_llm_requests':0,
            'test_used_for_parameter_selection':False,'artifacts':{key:record(BASE_DIR/path) for key,path in
               [('development_manifest','dev/run_manifest.json'),('test_manifest','test/run_manifest.json'),
                ('authorization','test_authorization.json'),('test_usage','test_usage.jsonl'),
                ('verification','acceptance/contract-development.json'),('actual_query_smoke','acceptance/live-smoke.json')]},
            'limitations':['The locked questions were previously reported in Task7/8; this is not a new unseen holdout.',
                'Saved original Top10 per channel; no evidence about deeper Top20/40/80 candidates.',
                'Four methods have the same Top10 output cap; unranked union of at most20 is a separate coverage diagnostic.',
                'New fusion timings include validation/adapters and all four output constructions; historical channel timings are not added into a fake end-to-end measurement.',
                'No graded relevance, answer accuracy, QPS, production SLA or universal fusion benefit claim.',
                'Environment metadata collected after the two fusion runs on the same host; original channel environment remains in original manifests.']}


def main():
    value=report_payload();value['generated_at']=now();write_new(ROOT/'reports/hybrid_rrf_results.json',value)
    print(json.dumps({'status':'COMPLETE','test':{m:v['quality']['metrics'] for m,v in value['test']['methods'].items()},
                      'comparison':value['test']['rrf_vs_single_channels']},ensure_ascii=False))


if __name__=='__main__':main()
