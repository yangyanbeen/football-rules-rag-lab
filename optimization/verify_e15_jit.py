"""Check exact construction/deletion sequence without backend or heavy weights."""
import copy,json,os,sys,weakref
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,config
from task13_core import app_config,validate_result
import task13_engine as engine
import bge_reranker

def main():
    fixture=read(ROOT/'.runtime/phase2/e12-live/single_fact_r2.json')['trace'];corpus={r['chunk_id']:r for r in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    order=[];references=[]
    class FakeHeavy:
        session='pinned-session';inputs=['input_ids','attention_mask']
        def __init__(self,cfg):order.append('construct');references.append(weakref.ref(self))
        def score(self,*args):order.append('score');return {'delegated':True}
    class Retriever:
        cfg={};dense=type('Dense',(),{'by_id':corpus})()
        def __init__(self):self.reranker=engine.StageReranker(self.cfg)
        def query(self,q,method):
            order.append('dense_complete');assert len(references)==order.count('answer')
            assert self.reranker.score(None,None,None)=={'delegated':True}
            return copy.deepcopy(fixture['retrieval'])
    obj=engine.IntegratedEngine.__new__(engine.IntegratedEngine);obj.cfg=app_config();obj.answer_cfg=config();obj.chat=None
    obj.prompt=(ROOT/obj.answer_cfg['prompt_file']).read_text('utf8')
    original=engine.request_json;factory=bge_reranker.BgeReranker
    prior={k:os.environ.get(k) for k in ('FOOTBALL_SOURCE_FACTS','FOOTBALL_RELEASE_RERANKER','FOOTBALL_JIT_RERANKER')}
    def model(chat,messages,*args):
        assert messages==fixture['messages'] and obj.retriever.reranker is None and all(r() is None for r in references)
        order.append('answer');ats=copy.deepcopy(fixture['attempts']);return ats[-1]['parsed'],ats,None
    try:
        bge_reranker.BgeReranker=FakeHeavy;engine.request_json=model
        for k in prior:os.environ[k]='1'
        obj.retriever=Retriever();assert not references
        for _ in range(2):
            r=obj.answer(fixture['question']);validate_result(r,r['question']);assert r['selected_ids']==['L01-01']
        assert order==['dense_complete','construct','score','answer']*2
        before=list(order);gate=obj.answer('某联赛累计三张黄牌停赛几场？');validate_result(gate,gate['question'])
        assert not gate['attempts'] and gate['retrieval'] is None and order==before
        # Readiness explicitly loads the lazy owner and exposes the same interface.
        ready=engine.StageReranker({});ready.ensure_loaded();assert ready.session=='pinned-session' and ready.inputs==['input_ids','attention_mask']
        print(json.dumps(dict(sequence_verified=True,actual_owner_collected_before_model=True,repeated_engine=True,readiness_pinned_interface=True,D036_zero_calls=True,new_model_calls=0)))
    finally:
        engine.request_json=original;bge_reranker.BgeReranker=factory
        for k,v in prior.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v
if __name__=='__main__':main()
