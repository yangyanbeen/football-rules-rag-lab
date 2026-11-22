"""Residency safety and unchanged response replay; no inference or heavy weights."""
import copy,json,os,sys,weakref
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import low_memory_runtime as runtime
import task13_engine as engine
from answer_eval_core import read,config
from task13_core import app_config,validate_result


def main():
    model={'name':'pinned:tag','digest':'abc'};other={'name':'other:tag','digest':'other'}
    rows=[dict(model),dict(other)];calls=[]
    class Response:
        def __init__(self,value):self.value=value
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps(self.value).encode()
    class HTTP:
        def open(self,req,timeout):
            calls.append((req.full_url,req.data))
            if req.full_url.endswith('/api/ps'):return Response({'models':copy.deepcopy(rows)})
            payload=json.loads(req.data);assert payload==dict(model=model['name'],prompt='',stream=False,keep_alive=0)
            rows[:]=[r for r in rows if r['name']!=model['name']]
            return Response({'done':True,'done_reason':'unload'})
    with patch.object(runtime.urllib.request,'build_opener',return_value=HTTP()):
        runtime.unload_model('http://127.0.0.1:11434',model,'test')
        assert rows==[other] and len(calls)==3
        calls.clear();runtime.unload_model('http://127.0.0.1:11434',model,'test')
        assert len(calls)==1 and calls[0][1] is None
        rows.append(dict(model,digest='changed'));calls.clear()
        try:runtime.unload_model('http://127.0.0.1:11434',model,'test')
        except ValueError:pass
        else:raise AssertionError('Changed tag was unloaded')
        assert len(calls)==1
    fixture=read(ROOT/'.runtime/phase2/e12-live/single_fact_r2.json')['trace']
    corpus={r['chunk_id']:r for r in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    sequence=[];references=[]
    class Heavy:
        def __init__(self,cfg):sequence.append('reranker_load');references.append(weakref.ref(self))
        def score(self,*args):sequence.append('reranker_score');return True
    class Retriever:
        cfg={};dense=type('Dense',(),{'by_id':corpus})()
        def stage_reranker(self):
            return engine.StageReranker({},lambda:engine.unload_model(None,None,'embedding'))
        def __init__(self):self.reranker=self.stage_reranker()
        def query(self,*args):
            sequence.append('embedding_query');assert self.reranker.score(None,None,None)
            return copy.deepcopy(fixture['retrieval'])
    obj=engine.IntegratedEngine.__new__(engine.IntegratedEngine);obj.cfg=app_config();obj.answer_cfg=config()
    obj.chat=type('Chat',(),{'base_url':'http://127.0.0.1:11434'})();obj.retriever=Retriever()
    obj.prompt=(ROOT/obj.answer_cfg['prompt_file']).read_text('utf8')
    def answer(*args):
        assert obj.retriever.reranker is None and all(r() is None for r in references)
        sequence.append('answer_query');attempts=copy.deepcopy(fixture['attempts'])
        return attempts[-1]['parsed'],attempts,None
    with patch.dict(os.environ,{'FOOTBALL_LOW_MEMORY':'1','FOOTBALL_SOURCE_FACTS':'1',
                               'FOOTBALL_RELEASE_RERANKER':'0','FOOTBALL_JIT_RERANKER':'0'}), \
         patch('bge_reranker.BgeReranker',Heavy),patch.object(engine,'request_json',answer), \
         patch.object(engine,'unload_model',side_effect=lambda url,model,stage:sequence.append(stage+'_unload')):
        with patch.dict(os.environ,{'FOOTBALL_LOW_MEMORY':'0','FOOTBALL_RELEASE_RERANKER':'1'}):
            baseline=obj.answer(fixture['question']);validate_result(baseline,baseline['question'])
        sequence.clear();references.clear();obj.retriever=Retriever()
        for _ in range(2):
            result=obj.answer(fixture['question']);validate_result(result,result['question'])
            for key in ('messages','context','retrieved_ids','answer','citations','selected_ids','status','attempts'):
                assert result[key]==baseline[key],key
        assert sequence==['answer_before_retrieval_unload','embedding_query','embedding_unload',
                          'reranker_load','reranker_score','answer_query','answer_after_generation_unload']*2
        before=list(sequence);gate=obj.answer('某联赛累计三张黄牌停赛几场？')
        validate_result(gate,gate['question']);assert not gate['attempts'] and gate['retrieval'] is None and sequence==before
        obj.retriever.reranker=engine.StageReranker({},lambda:(_ for _ in ()).throw(RuntimeError('unload failed')))
        failed=obj.answer(fixture['question']);assert failed['error'] and not failed['attempts'] and sequence.count('reranker_load')==2
    print(json.dumps(dict(verified=['only_pinned_resident_unloaded','no_load_on_idle_unload','changed_digest_rejected',
        'residency_order','actual_reranker_collected','same_engine_reconstruction','byte_identical_prompt_and_render',
        'D036_zero_calls','unload_failure_prevents_next_load'],new_inference_calls=0)))
if __name__=='__main__':main()
