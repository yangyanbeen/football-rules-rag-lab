"""Integrated rebuilt indexes -> fixed Top40 -> pinned Qwen -> verified source display."""
import sys,time,re
from task13_core import *
from answer_eval_core import config as answer_config,parse_selection
from answer_eval_engine import pack,request_json
from citation_catalog_guard import safe_render


def index_snapshot(cfg):
    return {p.relative_to(ROOT).as_posix():record(p) for k in ('dense_index','bm25_index') for p in (ROOT/cfg[k]).rglob('*') if p.is_file()}


def retriever(cfg):
    from reranker_live import RerankerRetriever
    from reranker_eval import config as reranker_config
    from hybrid_live import index_files
    from bm25_index import Bm25Index
    from dense_index import PinnedEmbedder,DenseIndex
    from bge_reranker import BgeReranker
    class RebuiltRetriever(RerankerRetriever):
        def __init__(self):
            self.cfg=reranker_config();self.before=index_files();self.dense=None
            try:
                self.bm25=Bm25Index(ROOT/cfg['bm25_index'])
                if self.bm25.manifest['template']!='title_body':raise ValueError('Expected dev-selected BM25 template')
                self.embedder=PinnedEmbedder(read(ROOT/'config/dense_index.json'))
                self.dense=DenseIndex(ROOT/cfg['dense_index'],embedder=self.embedder)
                self.reranker=BgeReranker(self.cfg)
            except BaseException:
                if self.dense is not None:self.dense.close()
                raise
    return RebuiltRetriever()


class IntegratedEngine:
    def __init__(self):
        from rag_b0 import PinnedChat
        self.cfg=app_config();self.answer_cfg=answer_config();self.retriever=None;self.closed=False
        self.before=index_snapshot(self.cfg)
        try:
            self.retriever=retriever(self.cfg);self.chat=PinnedChat(self.answer_cfg)
            self.chat.verify_model();self.prompt=(ROOT/'config/answer_evaluation_system.txt').read_text('utf-8')
        except BaseException:
            if self.retriever is not None:
                try:self.retriever.close()
                except BaseException as e:print('Secondary cleanup error: '+type(e).__name__,file=sys.stderr)
            raise

    def close(self):
        if self.closed:return
        self.closed=True
        try:
            if self.retriever is not None:self.retriever.close()
        finally:
            if index_snapshot(self.cfg)!=self.before:raise ValueError('Integrated query changed rebuilt indexes')

    def __enter__(self):return self
    def __exit__(self,typ,*_):
        try:self.close()
        except Exception as exc:
            if typ:print('Secondary cleanup error: '+type(exc).__name__,file=sys.stderr)
            else:raise

    def answer(self,question):
        question=normalize_question(question);start=time.perf_counter()
        r={'profile':self.cfg['version'],'trace_id':uuid.uuid4().hex,'captured_at':now(),'question':question,
            'status':'refused','answer':REFUSAL+'\n'+BOUNDARY,'citations':[],'selected_ids':[],'offered_ids':[],
            'retrieved_ids':[],'retrieval':None,'context':[],'messages':[],'attempts':[],'refusal_reason':None,
            'error':None,'prompt_utf8_bytes':0,'configuration':source_identity(),
            'indexes':{n:record(ROOT/self.cfg[n]/'index_manifest.json') for n in ('dense_index','bm25_index')},
            'timing':{'retrieval_seconds':0.,'generation_seconds':0.}}
        try:
            if re.search(r'官方|现行|最新|IFAB',question,re.I) and re.search(r'赛季|20\d{2}|规则',question):
                r['refusal_reason']='version_unverified';return r
            t=time.perf_counter()
            try:r['retrieval']=self.retriever.query(question,'top40')
            finally:r['timing']['retrieval_seconds']=time.perf_counter()-t
            evidence=[self.retriever.dense.by_id[v['chunk_id']] for v in r['retrieval']['results']]
            context,messages,size=pack(question,evidence,self.answer_cfg,self.prompt)
            r.update(retrieved_ids=[v['chunk_id'] for v in evidence],context=context,messages=messages,
                offered_ids=[v['chunk_id'] for v in context],prompt_utf8_bytes=size)
            if not context:r['refusal_reason']='no_whole_evidence_within_budget';return r
            from answer_json_chat import selection_schema
            t=time.perf_counter()
            try:
                selection,attempts,error=request_json(self.chat,messages,self.answer_cfg,
                    lambda s:parse_selection(s,r['offered_ids'],self.answer_cfg),selection_schema(r['offered_ids'],3))
                r['attempts']=attempts
            finally:r['timing']['generation_seconds']=time.perf_counter()-t
            if error:raise ValueError(error)
            if selection['answerable']:
                answer,cites=safe_render(selection['chunk_ids'],{v['chunk_id']:v for v in context})
                r.update(status='answered',answer=answer,citations=cites,selected_ids=selection['chunk_ids'])
            else:r['refusal_reason']=selection['reason']
        except (ValueError,KeyError,TypeError,OSError,RuntimeError,TimeoutError) as exc:
            r.update(error=type(exc).__name__+': '+str(exc),refusal_reason='runtime_or_validation_error')
        finally:r['timing']['total_seconds']=time.perf_counter()-start
        return r
