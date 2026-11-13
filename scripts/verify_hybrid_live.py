"""Actual four-query hybrid smoke; no answer model and no accuracy claim."""
import argparse,json
from pathlib import Path
from eval_dataset import ROOT,EVAL,load_jsonl,digest,canonical
from bm25_index import record,write_new
from bm25_retrieval_eval import now
from hybrid_retrieval_eval import SOURCES
from hybrid_live import HybridRetriever
from rrf import fuse,CHANNELS


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    out=a.report.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'reports'):raise ValueError('Use a new reports file')
    questions=['请检索第十一条下关于越位的资料段落。','请查找同时包含7.32米与2.44米的球门尺寸资料。',
               '请检索和“间接任意球”有关的规则段落。','zzzzunknownlexicaltoken987654321']
    test_hashes={digest(q['question'].encode()) for q in load_jsonl(EVAL/'retrieval_test.jsonl')}
    if any(digest(q.encode()) in test_hashes for q in questions):raise ValueError('Do not run original test questions as smoke queries')
    checks={};rows=[];started=now()
    with HybridRetriever() as engine:
        for i,q in enumerate(questions,1):
            row=engine.query(q);rows.append(row)
            checks['query_'+str(i)+'_fusion_recomputes']=canonical(row['results'])==canonical(fuse({c:row['channels'][c]['results'] for c in CHANNELS}))
            checks['query_'+str(i)+'_positive_total_and_stages']=row['timing']['total_seconds']>0 and abs(row['timing']['total_seconds']-sum(v for k,v in row['timing'].items() if k!='total_seconds'))<1e-8
            checks['query_'+str(i)+'_top10_budget_and_unique']=all(len(v)<=10 and len({r['chunk_id'] for r in v})==len(v) for v in row['results'].values())
        runtime=engine.embedder.runtime()
    checks['all_four_queries_completed']=len(rows)==4
    checks['oov_bm25_empty_no_zero_fill']=not rows[-1]['channels']['bm25']['results']
    checks['oov_rrf_falls_to_dense_ranks']=([r['chunk_id'] for r in rows[-1]['results']['rrf']]==[r['chunk_id'] for r in rows[-1]['channels']['dense']['results']])
    checks['pinned_embedding_cpu']=runtime['size_vram']==0
    checks['original_index_files_unchanged']=True # close() raises on any byte change
    result={'version':'hybrid-live-smoke-1.0','status':'PASS' if all(checks.values()) else 'FAIL','captured_at':now(),'started_at':started,
            'passed':sum(checks.values()),'total':len(checks),'checks':checks,'queries':rows,'embedding_runtime':runtime,
            'actual_embedding_queries':4,'new_locked_test_queries':0,'answer_llm_requests':0,'is_accuracy_evaluation':False,
            'source_sha256':{p:record(ROOT/p)['sha256'] for p in SOURCES+('scripts/verify_hybrid_live.py',)},
            'scope':'Four ad-hoc actual dual-channel queries; not new accuracy or latency benchmark samples'}
    write_new(out,result);print(json.dumps({k:result[k] for k in ('status','passed','total')}))
    return 0 if all(checks.values()) else 1


if __name__=='__main__':raise SystemExit(main())
