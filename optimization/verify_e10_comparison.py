"""Model-free checks for fixed packets, normal gates and original Graph guards."""
import copy,json
from e10_model_comparison import ROOT,read,config,build,normal_gates

def main():
    frozen=read(ROOT/'.runtime/phase2/e10-frozen/inputs.json');case=frozen['cases'][0]
    corpus={v['chunk_id']:v for v in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    packets=[];count=0
    for variant in 'AB':
        cfg=config()
        if variant=='B':cfg=copy.deepcopy(cfg);cfg['llm'].update(name='test-candidate:fixture',digest='0'*64)
        ops,flow=build(cfg,corpus,'test_'+variant);ops.case=case;ops.trace=read(ROOT/case['source_trace'])
        def fake(messages,schema):
            ops.chat.requests+=1
            response={'message':{'content':json.dumps(dict(answerable=True,chunk_ids=['L12-06'],reason=None))}}
            ops.obs.append(dict(messages=messages,schema=schema,response=response));return response
        ops.generate=fake
        result=flow.invoke(case['question'])
        assert result['status']=='answered' and result['selected_ids']==['L12-06'] and result['chat_calls']==1
        packets.append(ops.obs[0]);count+=1
        gates=normal_gates(ops,flow,cfg)
        assert gates['graph']['chat_calls']==0 and not gates['linear']['attempts'];count+=2
        old=corpus['L12-06']['content_zh'];before=ops.chat_calls
        corpus['L12-06']['content_zh']=old+'篡改'
        result=flow.invoke(case['question']);assert result['status']=='failed' and ops.chat_calls==before
        corpus['L12-06']['content_zh']=old;count+=1
    assert packets[0]==packets[1];count+=1
    assert len(frozen['schedule'])==36 and all(sum(v['case_id']==c['case_id'] for v in frozen['schedule'])==(6 if c['case_id'] in ('T026-expanded','T034-expanded','D017-native','D021-native') else 2) for c in frozen['cases']);count+=1
    print(json.dumps(dict(passed=count,model_inference_calls=0,fixed_payload_and_gates_verified=True)))
if __name__=='__main__':main()
