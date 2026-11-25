"""Integrated rebuilt indexes -> fixed Top40 -> pinned Qwen -> verified source display."""
import os,sys,time,re
from runtime_observation import mark
from task13_core import *
from answer_eval_core import config as answer_config,parse_selection
from answer_eval_engine import pack,request_json,selection_prompt
from generation_decision import (decide as apply_generation_decision,
                                  prompt_for as generation_prompt,
                                  run_selection_audit,
                                  choose_audited_selection)
from citation_catalog_guard import safe_render
from disciplinary_query_policy import evaluate_suspension_query, refusal_message, PUBLIC_REASON
from low_memory_runtime import enabled as low_memory, unload_model


def index_snapshot(cfg):
    return {p.relative_to(ROOT).as_posix():record(p) for k in ('dense_index','bm25_index') for p in (ROOT/cfg[k]).rglob('*') if p.is_file()}


class StageReranker:
    """Own the unchanged pinned cross-encoder only when scoring actually starts."""
    def __init__(self,cfg,before_load=None):self.cfg=cfg;self._owner=None;self.before_load=before_load
    def ensure_loaded(self):
        if self._owner is None:
            if self.before_load is not None:self.before_load()
            from bge_reranker import BgeReranker
            mark('jit_reranker_construction_start')
            self._owner=BgeReranker(self.cfg)
            mark('jit_reranker_construction_end')
        return self._owner
    def score(self,*args,**kwargs):return self.ensure_loaded().score(*args,**kwargs)
    @property
    def session(self):return self.ensure_loaded().session
    @property
    def inputs(self):return self.ensure_loaded().inputs


def retriever(cfg):
    mark('retrieval_import_start')
    from reranker_live import RerankerRetriever
    from reranker_eval import config as reranker_config
    from hybrid_live import index_files
    from bm25_index import Bm25Index
    from dense_index import PinnedEmbedder,DenseIndex
    from bge_reranker import BgeReranker
    mark('retrieval_import_end')
    class RebuiltRetriever(RerankerRetriever):
        def __init__(self):
            self.cfg=reranker_config();self.before=index_files();self.dense=None
            try:
                mark('bm25_construction_start');self.bm25=Bm25Index(ROOT/cfg['bm25_index']);mark('bm25_construction_end')
                if self.bm25.manifest['template']!='title_body':raise ValueError('Expected dev-selected BM25 template')
                mark('dense_construction_start')
                self.embedder=PinnedEmbedder(read(ROOT/'config/dense_index.json'))
                self.dense=DenseIndex(ROOT/cfg['dense_index'],embedder=self.embedder)
                mark('dense_construction_end')
                if low_memory() or os.environ.get('FOOTBALL_JIT_RERANKER','0')=='1':
                    self.reranker=self.stage_reranker();mark('reranker_deferred')
                else:
                    mark('reranker_construction_start')
                    self.reranker=BgeReranker(self.cfg);mark('reranker_construction_end')
            except BaseException:
                if self.dense is not None:self.dense.close()
                raise
        def stage_reranker(self):
            callback=(lambda:unload_model(self.embedder.base_url,self.embedder.cfg['model'],'embedding')) if low_memory() else None
            return StageReranker(self.cfg,callback)
    return RebuiltRetriever()


class IntegratedEngine:
    def __init__(self):
        from rag_b0 import PinnedChat
        self.cfg=app_config();self.answer_cfg=answer_config();self.retriever=None;self.closed=False
        self.before=index_snapshot(self.cfg)
        try:
            if not low_memory() and os.environ.get('FOOTBALL_LAZY_RETRIEVAL','0')!='1':self.retriever=retriever(self.cfg)
            self.chat=PinnedChat(self.answer_cfg)
            mark('chat_identity_validation_start')
            self.chat.verify_model();self.prompt=generation_prompt((ROOT/'config/answer_evaluation_system.txt').read_text('utf-8'))
            mark('chat_identity_validation_end')
        except BaseException:
            if self.retriever is not None:
                try:self.retriever.close()
                except BaseException as e:print('Secondary cleanup error: '+type(e).__name__,file=sys.stderr)
            raise

    def ensure_retriever(self):
        if self.retriever is None:
            mark('lazy_retrieval_construction_start')
            self.retriever=retriever(self.cfg)
            mark('lazy_retrieval_construction_end')
        elif ((low_memory() or os.environ.get('FOOTBALL_RELEASE_RERANKER','0')=='1')
              and hasattr(self.retriever,'reranker') and self.retriever.reranker is None):
            from bge_reranker import BgeReranker
            mark('reranker_reconstruction_start')
            if low_memory():self.retriever.reranker=self.retriever.stage_reranker()
            elif os.environ.get('FOOTBALL_JIT_RERANKER','0')=='1':self.retriever.reranker=StageReranker(self.retriever.cfg)
            else:self.retriever.reranker=BgeReranker(self.retriever.cfg)
            mark('reranker_reconstruction_end')
        return self.retriever

    def release_reranker(self):
        """Drop only the finished cross-encoder; preserve ranked data and sources."""
        if self.retriever is None or getattr(self.retriever,'reranker',None) is None:return
        import gc,weakref
        mark('reranker_release_start')
        # For the stage owner, verify collection of the actual cross-encoder.
        owner=getattr(self.retriever.reranker,'_owner',self.retriever.reranker)
        observed=weakref.ref(owner) if owner is not None else None
        del owner
        self.retriever.reranker=None
        gc.collect()
        # This says whether the Python owner is gone; OS memory is measured
        # independently and is never inferred from object collection.
        mark('reranker_release_end',object_collected=observed is None or observed() is None)

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
            decision=evaluate_suspension_query(question)
            if decision:
                r.update(business_decision=decision,refusal_reason=PUBLIC_REASON,
                         answer=refusal_message(decision)+'\n'+BOUNDARY)
                return r
            if re.search(r'官方|现行|最新|IFAB',question,re.I) and re.search(r'赛季|20\d{2}|规则',question):
                r['refusal_reason']='version_unverified';return r
            if low_memory():unload_model(self.chat.base_url,self.answer_cfg['llm'],'answer_before_retrieval')
            self.ensure_retriever()
            t=time.perf_counter()
            try:
                mark('retrieval_query_start');r['retrieval']=self.retriever.query(question,'top40');mark('retrieval_query_end')
            finally:r['timing']['retrieval_seconds']=time.perf_counter()-t
            evidence=[self.retriever.dense.by_id[v['chunk_id']] for v in r['retrieval']['results']]
            context,messages,size=pack(question,evidence,self.answer_cfg,self.prompt)
            r.update(retrieved_ids=[v['chunk_id'] for v in evidence],context=context,messages=messages,
                offered_ids=[v['chunk_id'] for v in context],prompt_utf8_bytes=size)
            mark('context_packed')
            if low_memory() or os.environ.get('FOOTBALL_RELEASE_RERANKER','0')=='1':self.release_reranker()
            if not context:r['refusal_reason']='no_whole_evidence_within_budget';return r
            from answer_json_chat import selection_schema
            t=time.perf_counter()
            try:
                mark('answer_model_start')
                selection,attempts,error=request_json(self.chat,messages,self.answer_cfg,
                    lambda s:parse_selection(s,r['offered_ids'],self.answer_cfg),selection_schema(r['offered_ids'],3))
                mark('answer_model_end')
                r['attempts']=attempts
            finally:
                if low_memory():unload_model(self.chat.base_url,self.answer_cfg['llm'],'answer_after_generation')
                r['timing']['generation_seconds']=time.perf_counter()-t
            if error:raise ValueError(error)
            audit = run_selection_audit(
                self.chat, messages, self.answer_cfg,
                lambda s: parse_selection(s, r['offered_ids'], self.answer_cfg),
                selection_schema(r['offered_ids'], 3), request_json)
            if audit is not None:
                selection = choose_audited_selection(selection, audit)
                r['selection_audit'] = audit
            decision=apply_generation_decision(
                question,selection,context,messages,
                recovery_allowed=getattr(self,'fact_recovery_allowed',True))
            r['generation_decision']=decision['trace']
            recovery=decision['recovery']
            if recovery is not None:
                r['fact_recovery']=recovery
                if recovery['applied']:
                    mark('fact_binding_start');answer,cites=safe_render(
                        recovery['selected_ids'],{v['chunk_id']:v for v in context});mark('fact_binding_end')
                    r.update(status='answered',answer=answer,citations=cites,
                             selected_ids=recovery['selected_ids'],refusal_reason=None)
                    return r
            if selection['answerable']:
                answer,cites=safe_render(selection['chunk_ids'],{v['chunk_id']:v for v in context})
                r.update(status='answered',answer=answer,citations=cites,selected_ids=selection['chunk_ids'])
            else:r['refusal_reason']=selection['reason']
        except (ValueError,KeyError,TypeError,OSError,RuntimeError,TimeoutError) as exc:
            r.update(error=type(exc).__name__+': '+str(exc),refusal_reason='runtime_or_validation_error')
        finally:r['timing']['total_seconds']=time.perf_counter()-start
        return r
