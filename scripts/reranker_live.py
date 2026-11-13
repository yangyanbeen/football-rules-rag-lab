"""Task10 actual deep retrieval + optional cross encoder; index/corpus read only."""
import ctypes,importlib.metadata,os,platform,sys,time
from eval_dataset import ROOT
from bm25_index import Bm25Index
from bm25_retrieval_eval import now
from dense_retrieval_eval import normalize_query
from hybrid_live import index_files
from rrf import fuse,SOURCE_FIELDS
from bge_reranker import BgeReranker
from reranker_eval import METHODS,BUDGETS


class RerankerRetriever:
    def __init__(self,cfg):
        from dense_index import DenseIndex,PinnedEmbedder
        import json
        self.cfg=cfg;self.before=index_files();self.dense=None
        try:
            self.bm25=Bm25Index(ROOT/'data/indexes/bm25/title_body')
            self.embedder=PinnedEmbedder(json.loads((ROOT/'config/dense_index.json').read_text('utf-8')))
            self.dense=DenseIndex(embedder=self.embedder);self.reranker=BgeReranker(cfg)
        except BaseException:
            if self.dense is not None:self.dense.close()
            raise

    def query(self,question,method):
        if method not in METHODS:raise ValueError('Unknown rerank method')
        start=time.perf_counter_ns();query=normalize_query(question);a=time.perf_counter_ns()
        dense=self.dense.query(query,80);b=time.perf_counter_ns()
        bm25=self.bm25.query(question,80);c=time.perf_counter_ns()
        channels={'dense':[{**{p:r['metadata'][p] for p in SOURCE_FIELDS},**{p:r[p] for p in ('rank','score','distance')}} for r in dense['results']],
                  'bm25':bm25['results']}
        ranked=fuse(channels,60,80)['rrf'];before=[{k:r[k] for k in ('chunk_id','rank','score')} for r in ranked]
        raw={name:[{k:v for k,v in r.items() if k not in SOURCE_FIELDS or k=='chunk_id'} for r in rows] for name,rows in channels.items()}
        budget=BUDGETS[method]
        # Control has no score-model invocation; both branches include preparation/output adapter costs.
        if budget:
            d=time.perf_counter_ns();reranker=self.reranker.score(query,ranked[:budget],self.dense.by_id)
            results=[{k:r[k] for k in ('chunk_id','rank','score')} for r in reranker['results'][:10]]
            end=time.perf_counter_ns();rerank_seconds=(end-d)/1e9;fusion_seconds=(d-c)/1e9
        else:
            reranker=None;results=before[:10];end=time.perf_counter_ns();rerank_seconds=0.;fusion_seconds=(end-c)/1e9
        return {'method':method,'query':query,'channels':raw,'before':before,'reranker':reranker,'results':results,
                'timing':{'normalization_seconds':(a-start)/1e9,'dense_seconds':(b-a)/1e9,'bm25_seconds':(c-b)/1e9,
                          'fusion_seconds':fusion_seconds,'rerank_seconds':rerank_seconds,'total_seconds':(end-start)/1e9},
                'channel_timing':{'dense':dense['timing'],'bm25':bm25['timing']},'embedding_observation':self.embedder.observations[-1]}

    def environment(self):
        memory=None
        if os.name=='nt':
            class Memory(ctypes.Structure):
                _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ('total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','avail_extended')]
            m=Memory();m.length=ctypes.sizeof(m)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):memory=m.total_phys
        return {'captured_at':now(),'python':platform.python_version(),'system':platform.platform(),'machine':platform.machine(),
                'processor':platform.processor(),'logical_cpus':os.cpu_count(),'physical_memory_bytes':memory,
                'packages':{p:importlib.metadata.version(p) for p in self.cfg['packages']},
                'providers':self.reranker.session.get_providers(),'model_inputs':self.reranker.inputs,'embedding_runtime':self.embedder.runtime()}

    def close(self):
        primary=None
        try:
            if self.dense is not None:self.dense.close()
        except BaseException as exc:primary=exc
        try:
            if index_files()!=self.before:raise ValueError('Task10 changed original indexes')
        except BaseException:
            if primary is None:raise
            print('Index cleanup additionally failed',file=sys.stderr)
        if primary is not None:raise primary

    def __enter__(self):return self
    def __exit__(self,*_):
        primary=sys.exc_info()[0] is not None
        try:self.close()
        except Exception as exc:
            if primary:print('Cleanup additionally failed: '+type(exc).__name__,file=sys.stderr)
            else:raise
