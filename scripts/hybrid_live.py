"""Read-only actual Dense + fixed accurate BM25 query; no answer generation."""
import json,time,sys
from pathlib import Path
from eval_dataset import ROOT
from bm25_index import Bm25Index,record
from dense_retrieval_eval import normalize_query
from rrf import fuse,SOURCE_FIELDS


def index_files():
    return {p.relative_to(ROOT).as_posix():record(p) for folder in ('dense','bm25/title_body')
            for p in (ROOT/'data/indexes'/folder).rglob('*') if p.is_file()}


class HybridRetriever:
    def __init__(self,k=60):
        from dense_index import DenseIndex,PinnedEmbedder
        from rrf import parameters
        parameters(k,10);self.k=k;self.dense=None;self.before=index_files()
        try:
            self.bm25=Bm25Index(ROOT/'data/indexes/bm25/title_body')
            cfg=json.loads((ROOT/'config/dense_index.json').read_text('utf-8'))
            self.embedder=PinnedEmbedder(cfg)
            self.dense=DenseIndex(embedder=self.embedder)
        except BaseException:
            if self.dense is not None:self.dense.close()
            raise

    def query(self,question):
        start=time.perf_counter_ns();query=normalize_query(question);a=time.perf_counter_ns()
        dense=self.dense.query(query,10);b=time.perf_counter_ns()
        bm25=self.bm25.query(question,10);c=time.perf_counter_ns()
        dense_rows=[{**{p:r['metadata'][p] for p in SOURCE_FIELDS},**{p:r[p] for p in ('rank','score','distance')}} for r in dense['results']]
        channels={'dense':{'query':query,'results':dense_rows,'timing':dense['timing']},
                  'bm25':{'query':bm25['query'],'tokens':bm25['tokens'],'results':bm25['results'],'timing':bm25['timing']}}
        result=fuse({name:row['results'] for name,row in channels.items()},self.k,10);end=time.perf_counter_ns()
        return {'question':question,'k':self.k,'channels':channels,'results':result,
                'timing':dict(zip(('normalization_seconds','dense_seconds','bm25_seconds','fusion_and_adapter_seconds','total_seconds'),
                                 ((a-start)/1e9,(b-a)/1e9,(c-b)/1e9,(end-c)/1e9,(end-start)/1e9))),
                'embedding_observation':self.embedder.observations[-1],
                'quality_evaluation':False,'llm_generation_requests':0}

    def close(self):
        try:
            if self.dense is not None:self.dense.close()
        finally:
            if index_files()!=self.before:raise ValueError('Original indexes changed during actual hybrid query')

    def __enter__(self):return self
    def __exit__(self,*_):
        primary=sys.exc_info()[0] is not None
        try:self.close()
        except Exception as exc:
            if primary:print('Hybrid cleanup also failed: '+type(exc).__name__,file=sys.stderr)
            else:raise
