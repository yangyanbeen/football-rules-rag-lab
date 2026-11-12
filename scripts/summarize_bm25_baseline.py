"""Publish a recomputed task 8 report; selection remains development-only."""
import json
from bm25_index import ROOT,RESOURCES,record,write_new
from bm25_retrieval_eval import replay,choose,now
from dense_retrieval_eval import replay as replay_dense


def main():
    base=ROOT/'reports/retrieval/bm25_b0'
    selected=json.loads((base/'selection.json').read_text('utf-8'))
    if selected!=choose(base/'development'):raise ValueError('Frozen selection differs')
    development={t:replay(base/'development'/t) for t in ('body','title_body','path_body')}
    test=replay(base/'test')
    dense={s:replay_dense(ROOT/'reports/retrieval/dense_b0'/s) for s in ('dev','test')}
    test_manifest=json.loads((base/'test/run_manifest.json').read_text('utf-8'))
    comparison={key:{'BM25':test['quality']['metrics'][key],'Dense':dense['test']['quality']['metrics'][key],
                      'difference':test['quality']['metrics'][key]-dense['test']['quality']['metrics'][key]}
                for key in ('Recall@5','Recall@10','MRR@10','all_gold_coverage@5')}
    report={'version':'bm25-baseline-report-1.0','status':'COMPLETE','generated_at':now(),
            'scope':'Task8 single-channel lexical baseline; fixed corpus and same human-reviewed dev/test as Dense',
            'selected_template':selected['selected_template'],'selection_policy':selected['policy'],
            'source_commit':test_manifest['source_commit'],'resources':{p:record(ROOT/p) for p in RESOURCES},
            'tokenizer':{**json.loads((ROOT/'config/bm25_b0.json').read_text('utf-8'))['tokenizer'],
                         **test_manifest['index_manifest']['dependency']},
            'corpus_records':99,'k1':1.5,'b':.75,'positive_scores_only':True,
            'development':{t:{'quality':s['quality'],'latency':s['latency'],'manifest':record(base/'development'/t/'run_manifest.json')} for t,s in development.items()},
            'test':{'quality':test['quality'],'latency':test['latency'],'manifest':record(base/'test/run_manifest.json')},
            'dense_original_test':{'metrics':dense['test']['quality']['metrics'],'summary':record(ROOT/'reports/retrieval/dense_b0/test/summary.json')},
            'same_test_quality_comparison':comparison,'new_formal_bm25_test_experiments':1,
            'test_parameter_selection':False,'answer_llm_requests':0,
            'limitations':['Small fixed Wikipedia snapshot; no referee expert certification or generated-answer accuracy claim.',
              'BM25 query CPU timing excludes index/trie loading; Dense includes embedding HTTP and integrity checks. Timing differences are not production QPS or end-to-end optimization claims.',
              'No graded relevance labels; nDCG not reported. All three repeats contribute to latency; only first ranks contribute to quality.',
              'Original failed development run retained separately; successful development set is development/, not dev/body/.'],
            'artifacts':{'selection':record(base/'selection.json'),'authorization':record(base/'test_authorization.json'),
                         'test_usage':record(base/'test_usage.jsonl'),'verification':record(base/'acceptance/contract-final.json'),
                         'probes':record(base/'development_probes.json')}}
    write_new(ROOT/'reports/bm25_baseline.json',report)
    print(json.dumps({'status':'COMPLETE','selected_template':report['selected_template'],'test_metrics':test['quality']['metrics']}))

if __name__=='__main__':main()
