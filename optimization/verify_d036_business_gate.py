"""Dual-entry boundary checks with captured responses; no real model requests."""
import argparse,copy,json,sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import config,canonical,now
from disciplinary_query_policy import evaluate_suspension_query,refusal_message,PUBLIC_REASON
from rag_langgraph import Flow,Operations
from task13_audit import source_map,request_json,validate_private
from task13_core import app_config
import task13_engine
task13_engine.request_json=request_json

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    read=lambda p:json.loads(p.read_text('utf8'))
    cfg=config();prompt=(ROOT/cfg['prompt_file']).read_text('utf8')
    corpus={r['chunk_id']:r for r in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    raw=read(ROOT/'.runtime/phase2/e4-live90/D036.json')['observations']['model_attempts'][0]['response']
    cases=read(ROOT/'optimization/experiments/D036_business_gate/boundary_cases.json');checks=[]
    class Chat:
        config=cfg
        def __init__(self):self.requests=0;self.queue=[copy.deepcopy(raw)]
        def verify_model(self):pass
        def request(self,path,payload=None):self.requests+=1;return self.queue.pop(0)
    class Ops(Operations):
        @property
        def completed_embeddings(self):return None
        def retrieval(self,*args):self.retrievals+=1;return {}
        def fusion(self,*args):return [{'chunk_id':'L12-09'}]
        def rerank(self,*args):return [{'chunk_id':'L12-09'}]
        def expand(self,ids):return [corpus[cid] for cid in ids]
    results={}
    for case in cases:
        q=case['question'];decision=evaluate_suspension_query(q)
        assert (decision['missing_fields'] if decision else None)==case['missing_fields'],case
        for entry in ('graph','linear'):
            chat=Chat();count=[0]
            if entry=='graph':
                ops=Ops(None,chat,cfg,prompt,source_map());ops.retrievals=0
                r=Flow(ops).invoke(q);retrievals=ops.retrievals
            else:
                engine=task13_engine.IntegratedEngine.__new__(task13_engine.IntegratedEngine)
                engine.cfg=app_config();engine.answer_cfg=cfg;engine.prompt=prompt;engine.chat=chat
                def retrieval(*args):count[0]+=1;return {'results':[{'chunk_id':'L12-09'}]}
                engine.retriever=SimpleNamespace(query=retrieval,dense=SimpleNamespace(by_id=corpus))
                r=engine.answer(q);assert r['error'] is None,r
                retrievals=count[0]
            if decision:
                assert r['status']=='refused' and chat.requests==retrievals==0 and len(chat.queue)==1
                assert r['business_decision']==decision and r['answer']==refusal_message(decision)+'\n'+__import__('answer_eval_core').BOUNDARY
                assert not r['attempts'] and not r['retrieved_ids'] and not r['selected_ids']
                if entry=='linear':validate_private(r,q)
            else:
                assert retrievals==chat.requests==1 and r['status']=='answered',(case,entry,r)
            checks.append(dict(case_id=case['case_id'],entry=entry,question=q,passed=True,
                               status=r['status'],answer_model_calls=chat.requests,retrievals=retrievals,
                               business_decision=decision))
            results[(case['case_id'],entry)]=r
    # Requests already resolved from prior context must retain both parameters.
    for q in ('中超2025赛季累计黄牌：那累计三张停几场？','英超2024-2025赛季累计黄牌：累计五张禁赛多久？'):
        assert evaluate_suspension_query(q) is None
    labels=list(map(json.loads,(ROOT/'data/eval/answer_eval.jsonl').read_text('utf8').splitlines()))
    assert [q['question_id'] for q in labels if evaluate_suspension_query(q['question'])]==['D036']
    checks.append(dict(case_id='formal90_only_intended_hit',entry='shared_policy',passed=True))
    # Both historical model decisions must stay unconsumed in both entries.
    refs={v['question_id']:v for v in read(ROOT/'optimization/baseline/e8b0fd6/trace_manifest.local.json')}
    for origin,path in [('A0',Path(refs['D036']['private_path'])),('A1',ROOT/'.runtime/phase2/e4-live90/D036.json')]:
        raw=read(path)['observations']['model_attempts'][0]['response']
        for entry in ('graph','linear'):
            chat=Chat();q=cases[1]['question']
            if entry=='graph':
                ops=Ops(None,chat,cfg,prompt,source_map());ops.retrievals=0;r=Flow(ops).invoke(q)
                assert ops.retrievals==0
            else:
                engine.chat=chat;r=engine.answer(q)
            assert r['status']=='refused' and chat.requests==0 and chat.queue==[raw]
            checks.append(dict(case_id='unconsumed_'+origin,entry=entry,passed=True,answer_model_calls=0))
    # The existing private contract must reject tampered decisions and fake inference.
    sample=results[('B001','linear')]
    for field in ('business_decision','answer','attempts','selected_ids'):
        broken=copy.deepcopy(sample)
        broken[field]=({'missing_fields':['season']} if field=='business_decision' else
                       'forged refusal' if field=='answer' else [dict(attempt=1)] if field=='attempts' else ['L12-09'])
        try:validate_private(broken,cases[0]['question'])
        except (ValueError,KeyError):pass
        else:raise AssertionError('Tampered refusal accepted: '+field)
        checks.append(dict(case_id='tampered_'+field,entry='private_contract',passed=True))
    value=dict(status='PASS',passed=len(checks),total=len(checks),checks=checks,new_model_requests=0,
               scope='Boundary/branch checks with captured-response adapters; nonblocked answers do not represent semantic accuracy.')
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open('xb') as f:f.write(canonical(value))
    print(json.dumps({k:value[k] for k in ('status','passed','total','new_model_requests')}))
if __name__=='__main__':main()
