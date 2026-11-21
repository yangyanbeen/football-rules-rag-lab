"""Actual answer/validation contract with frozen dependency responses, no inference."""
import copy,gc,json,os,sys,weakref
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,config,canonical
from task13_core import app_config,validate_result
import task13_engine as engine
import bge_reranker

def main():
    fixture=read(ROOT/'.runtime/phase2/e12-live/single_fact_r2.json')['trace'];corpus={r['chunk_id']:r for r in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    class Heavy:pass
    class Retriever:
        dense=type('Dense',(),{'by_id':corpus})()
        cfg={}
        def __init__(self):self.reranker=Heavy();self.reference=weakref.ref(self.reranker);self.queries=0
        def query(self,q,method):
            assert self.reranker is not None;self.reference=weakref.ref(self.reranker);self.queries+=1;return copy.deepcopy(fixture['retrieval'])
    previous={k:os.environ.get(k) for k in ('FOOTBALL_RELEASE_RERANKER','FOOTBALL_SOURCE_FACTS')};original=engine.request_json;factory=bge_reranker.BgeReranker;values={};invocations=[];restores=[]
    def restore(cfg):restores.append(1);return Heavy()
    bge_reranker.BgeReranker=restore
    try:
        os.environ['FOOTBALL_SOURCE_FACTS']='1'
        for flag in ('0','1'):
            os.environ['FOOTBALL_RELEASE_RERANKER']=flag
            obj=engine.IntegratedEngine.__new__(engine.IntegratedEngine);obj.cfg=app_config();obj.answer_cfg=config();obj.retriever=Retriever();obj.chat=None
            obj.prompt=(ROOT/obj.answer_cfg['prompt_file']).read_text('utf8')
            def frozen(chat,messages,cfg,parser,schema):
                assert messages==fixture['messages']
                assert (obj.retriever.reranker is None)==(flag=='1')
                if flag=='1':assert obj.retriever.reference() is None
                invocations.append(flag);ats=copy.deepcopy(fixture['attempts']);return ats[-1]['parsed'],ats,None
            engine.request_json=frozen;r=obj.answer(fixture['question']);validate_result(r,r['question']);values[flag]=r
            queries=obj.retriever.queries;calls=len(invocations)
            gate=obj.answer('某联赛累计三张黄牌停赛几场？');validate_result(gate,gate['question'])
            assert gate['status']=='refused' and not gate['attempts'] and gate['retrieval'] is None and queries==obj.retriever.queries and len(invocations)==calls
            if flag=='1':
                again=obj.answer(fixture['question']);validate_result(again,again['question']);assert len(restores)==1 and obj.retriever.queries==queries+1
        for key in ('context','messages','retrieval','selected_ids','answer','citations','attempts'):
            assert canonical(values['0'][key])==canonical(values['1'][key]),key
        assert len(invocations)==3
        from runtime_memory_snapshot import snapshot
        memory=snapshot();assert all(memory[k]>0 for k in ('available','total','rss','private','native_peak_rss'))
        print(json.dumps(dict(before_model_collection=True,byte_identical_inputs_and_outputs=True,D036_zero_calls=True,repeated_engine_reconstructs=True,default_off=True,real_model_calls=0,stage_counter_snapshot=memory)))
    finally:
        engine.request_json=original
        bge_reranker.BgeReranker=factory
        for k,v in previous.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v
if __name__=='__main__':main()
