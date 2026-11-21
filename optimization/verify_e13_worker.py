"""Run the actual Worker answer/validator around archived dependency responses."""
import copy,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,config
from task13_core import app_config,validate_result
import task13_engine as engine

def main():
    fixture=read(ROOT/'.runtime/phase2/e12-live/single_fact_r2.json')['trace']
    corpus={r['chunk_id']:r for r in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    class Retriever:
        dense=type('Dense',(),{'by_id':corpus})()
        calls=0
        def query(self,q,mode):
            assert q==fixture['question'] and mode=='top40';self.calls+=1;return copy.deepcopy(fixture['retrieval'])
    original=engine.request_json;calls=[]
    def frozen(*args):
        calls.append(1);ats=copy.deepcopy(fixture['attempts'])
        return ats[-1]['parsed'],ats,None
    obj=engine.IntegratedEngine.__new__(engine.IntegratedEngine)
    obj.cfg=app_config();obj.answer_cfg=config();obj.retriever=Retriever();obj.chat=None
    obj.prompt=(ROOT/obj.answer_cfg['prompt_file']).read_text('utf8')
    prior=os.environ.get('FOOTBALL_SOURCE_FACTS');engine.request_json=frozen;results={}
    try:
        for flag in ('0','1'):
            os.environ['FOOTBALL_SOURCE_FACTS']=flag
            result=obj.answer(fixture['question']);validate_result(result,result['question']);results[flag]=result
        assert results['0']['status']=='refused' and results['1']['status']=='answered'
        assert results['1']['selected_ids']==['L01-01'] and results['1']['fact_recovery']['applied']
        assert results['0']['attempts']==results['1']['attempts'] and len(calls)==2
        assert results['1']['attempts'][-1]['parsed']['answerable'] is False
        checks=0
        for mutate in ('drop_proof','forge_fact','unoffered_id','rewritten_subject'):
            value=copy.deepcopy(results['1'])
            if mutate=='drop_proof':value.pop('fact_recovery')
            elif mutate=='forge_fact':value['fact_recovery']['fact_ids']=['adult_ball_pressure_kpa']
            elif mutate=='unoffered_id':value['selected_ids']=['L12-09']
            else:value['query_resolution']=dict(outcome='rewritten',original_question_sha256='0'*64)
            try:validate_result(value,value['question'])
            except (ValueError,KeyError):checks+=1
            else:raise AssertionError(mutate+' was accepted')
        obj.fact_recovery_allowed=False
        history_result=obj.answer(fixture['question']);validate_result(history_result,history_result['question'])
        assert history_result['status']=='refused' and 'fact_recovery' not in history_result
        before=len(calls);retrieved=obj.retriever.calls
        gate=obj.answer('某联赛队员累计三张黄牌一定停赛几场？没有给联赛和赛季。')
        validate_result(gate,gate['question'])
        assert gate['status']=='refused' and not gate['attempts'] and gate['retrieval'] is None and len(calls)==before and obj.retriever.calls==retrieved
        print(json.dumps(dict(passed=10,proof_tamper_checks=checks,default_off=True,model_response_preserved=True,
            same_original_generation_flow=True,rewritten_subject_blocked=True,D036_zero_calls=True,actual_model_calls=0)))
    finally:
        engine.request_json=original
        if prior is None:os.environ.pop('FOOTBALL_SOURCE_FACTS',None)
        else:os.environ['FOOTBALL_SOURCE_FACTS']=prior
if __name__=='__main__':main()
