"""Frozen E7 requirements, single-paragraph real verification, original selector.

Inference inputs contain no reviewed requirements, labels, reference answers,
or source-audit relation judgments. Source scoring is a separate process.
"""
import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
os.environ['LANGSMITH_TRACING']='false';os.environ['LANGCHAIN_TRACING_V2']='false'
from answer_eval_core import canonical,read,record,config
from answer_json_chat import generate
from rag_b0 import PinnedChat
from rag_langgraph import CountingChat,Operations
from citation_catalog_guard import safe_render
from disciplinary_query_policy import evaluate_suspension_query,refusal_message,PUBLIC_REASON
from e7_evidence_map import parse_mapping
from e8_pair_verifier import SCHEMA,make_messages,parse_verdict

D=ROOT/'optimization/experiments/E8_pair_verification'
E7_PREP=ROOT/'.runtime/phase2/e7-prepared-final/prepared.json'
E7_RUN=ROOT/'.runtime/phase2/e7-pilot'
REPAIR={'role':'user','content':'上次JSON或短引校验未通过。重新核验同一要点与同一原文，只输出规定JSON。短引须逐字来自本段，不要省略或拼接，不改变原始要点和证据。'}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    with p.open('xb') as f:f.write(canonical(v))
def verify_refs(refs):assert all(record(ROOT/n)==v for n,v in refs.items())

def business_gate(question):
    decision=evaluate_suspension_query(question)
    if decision:
        return dict(status='refused',reason=PUBLIC_REASON,business_decision=decision,
            answer=refusal_message(decision),retrieval_calls=0,answer_calls=0,verification_calls=0)
    return None

def prepare(out,stage):
    out.mkdir(parents=True,exist_ok=False)
    cfg=config();prompt=(D/'verifier_prompt.txt').read_text('utf8')
    prep=read(E7_PREP);by={c['case_id']:c for c in prep['cases']}
    keys=['T026-expanded'] if stage=='minimal' else [q+'-native' for q in ('D001','D002','D003','D012','D021')]
    corpus={r['chunk_id']:r for r in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    cases=[];pairs=[];budgets=[]
    for rep in range(1,5):
        for key in keys:
            c=by[key];path=E7_RUN/f'{key}-B-r{rep}.json';trace=read(path)
            reqs=trace['observations']['model_attempts'][-1]['mapping_validation']['requirements']
            ev=json.loads(c['messages'][1]['content'])['evidence']
            for row in ev:
                assert row['content_zh']==corpus[row['chunk_id']]['content_zh']
                assert hashlib.sha256(row['content_zh'].encode()).hexdigest()==corpus[row['chunk_id']]['content_zh_sha256']
            cases.append(dict(case_id=key,repeat=rep,question=c['question'],offered_ids=c['offered_ids'],
                requirements=reqs,original_selected_ids=trace['result']['selected_ids'],source_trace=path.relative_to(ROOT).as_posix(),source_sha256=sha(path)))
            for i,req in enumerate(reqs):
                for row in ev:
                    paragraph={k:row[k] for k in ('chunk_id','content_zh')}
                    messages=make_messages(req['requirement'],paragraph,prompt)
                    size=len(canonical(messages));repair_size=len(canonical([*messages,REPAIR]))
                    assert size<=6200 and repair_size<=6200
                    pair_id=f"{key}-r{rep}-p{i}-{row['chunk_id']}"
                    pairs.append(dict(pair_id=pair_id,case_id=key,repeat=rep,requirement_index=i,
                        requirement=req['requirement'],paragraph=paragraph,body_sha256=hashlib.sha256(row['content_zh'].encode()).hexdigest()))
                    budgets.append(dict(pair_id=pair_id,message_bytes=size,retry_bytes=repair_size,schema_bytes=len(canonical(SCHEMA))))
    refs={**prep['source_files'],**prep['candidate_files']}
    for p in [Path(__file__),ROOT/'optimization/e8_pair_verifier.py',ROOT/'optimization/verify_e8_pair_verifier.py',D/'verifier_prompt.txt',D/'manifest.json']:
        refs[p.relative_to(ROOT).as_posix()]=record(p)
    manifest=dict(stage=stage,cases=cases,pairs=pairs,prompt_sha256=sha(D/'verifier_prompt.txt'),
        schema=SCHEMA,model=cfg['llm'],source_files=refs,control='Frozen archived E7-B mapping, original selector and renderer',
        no_gold_in_model_input=True,no_requirement_generation=True,holdout_used=False)
    write(out/'prepared.json',manifest)
    write(out/'budget_preflight.json',dict(stage=stage,pairs=len(pairs),rows=budgets,evidence_trimmed=False,overflow=[]))
    print(json.dumps(dict(stage=stage,case_observations=len(cases),pair_calls_without_retry=len(pairs),maximum_messages_bytes=max(v['message_bytes'] for v in budgets)),ensure_ascii=False))

def pair_call(chat,pair,prompt,cfg):
    attempts=[];verdict=None
    messages=make_messages(pair['requirement'],pair['paragraph'],prompt)
    before=chat.requests;start=time.perf_counter()
    for attempt in range(1,3):
        current=messages if attempt==1 else [*messages,REPAIR]
        assert len(canonical(current))<=6200
        at=dict(attempt=attempt,messages=current,schema=SCHEMA,response=None,error=None)
        attempts.append(at);before_attempt=chat.requests;at_start=time.perf_counter()
        try:
            response=generate(chat,current,SCHEMA);at['response']=response
            verdict=parse_verdict(response['message']['content'],pair['paragraph']['content_zh'])
            at['verdict']=verdict
            break
        except (ValueError,TypeError,KeyError,OSError,RuntimeError,TimeoutError) as exc:
            at['error']=type(exc).__name__+': '+str(exc)
            if hasattr(exc,'response'):at['response']=exc.response
            retry=(chat.requests-before_attempt==1 and getattr(exc,'retryable',True) is True
                   and not isinstance(exc,(OSError,RuntimeError,TimeoutError)))
            if not retry:break
        finally:at['seconds']=time.perf_counter()-at_start
    return dict(**pair,verdict=verdict,attempts=attempts,model_calls=chat.requests-before,seconds=time.perf_counter()-start,
        status='accepted' if verdict else 'failed',semantics_not_filtered_with_gold=True)

def run(out,prepared):
    out.mkdir(parents=True,exist_ok=False)
    data=read(prepared);verify_refs(data['source_files'])
    assert not subprocess.check_output(['git','diff','5986781','--','scripts','config'],cwd=ROOT)
    cfg=config();assert cfg['llm']==data['model']
    prompt=(D/'verifier_prompt.txt').read_text('utf8');assert sha(D/'verifier_prompt.txt')==data['prompt_sha256']
    chat=CountingChat(PinnedChat(cfg))
    from run_langgraph_flow import runtime_identity
    write(out/'metadata.json',dict(stage=data['stage'],source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        prepared_sha256=sha(prepared),source_files=data['source_files'],model=cfg['llm'],environment=runtime_identity(),
        pair_count=len(data['pairs']),holdout_used=False,actual_new_retrieval_calls=0,
        protocol='Each request contains exactly one frozen E7 requirement and one complete offered paragraph; no oracle labels or original support mapping.',
        no_new_mapping_model_calls=True,no_additional_answer_synthesis_calls=True))
    # Exercise the actual shared business policy and original Graph before
    # constructing verification requests. No retriever exists for this probe.
    q=read(ROOT/'.runtime/phase2/d036-gate-live90-final/D036.json')['question']
    before=chat.requests;entry=business_gate(q);assert entry and chat.requests==before
    from task13_audit import source_map
    from rag_langgraph import Flow
    sources=source_map();ops=Operations(None,chat,cfg,(ROOT/cfg['prompt_file']).read_text('utf8'),sources)
    graph_result=Flow(ops).invoke(q)
    assert graph_result['status']=='refused' and graph_result['chat_calls']==0 and not graph_result['retrieved_ids'] and graph_result['embedding_queries']==0
    assert chat.requests==before
    write(out/'D036_zero_call.json',dict(experimental_entry=entry,original_graph=graph_result))
    warm=generate(chat,[{'role':'system','content':'只输出一个JSON对象。'},{'role':'user','content':'返回ready为true。'}],
                  {'type':'object','properties':{'ready':{'const':True}},'required':['ready'],'additionalProperties':False})
    write(out/'warmup.json',dict(response=warm,excluded=True));hashes={};results=[]
    for ix,pair in enumerate(data['pairs'],1):
        case=next(c for c in data['cases'] if c['case_id']==pair['case_id'] and c['repeat']==pair['repeat'])
        assert business_gate(case['question']) is None
        result=pair_call(chat,pair,prompt,cfg)
        assert result['model_calls']<=2
        name=pair['pair_id']+'.json';write(out/name,result);hashes[name]=sha(out/name);results.append(result)
        print(json.dumps(dict(done=ix,total=len(data['pairs']),pair_id=pair['pair_id'],relation=result['verdict']['relation'] if result['verdict'] else None,calls=result['model_calls'],seconds=round(result['seconds'],3)),ensure_ascii=False),flush=True)
    corpus={r['chunk_id']:r for r in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    for c in data['cases']:
        rs=[r for r in results if r['case_id']==c['case_id'] and r['repeat']==c['repeat']]
        assert len(rs)==len(c['requirements'])*len(c['offered_ids'])
        if any(r['verdict'] is None for r in rs):
            value=dict(case_id=c['case_id'],repeat=c['repeat'],status='failed',selected_ids=[],requirements=None,
                answer=None,citations=[],reason='verification_protocol_failure')
        else:
            requirements=[dict(requirement=req['requirement'],supporting_ids=[r['paragraph']['chunk_id'] for r in rs
                if r['requirement_index']==i and r['verdict']['relation']=='direct_support']) for i,req in enumerate(c['requirements'])]
            assert [r['requirement'] for r in requirements]==[r['requirement'] for r in c['requirements']]
            selection,audit=parse_mapping(json.dumps({'requirements':requirements},ensure_ascii=False),c['offered_ids'],3)
            ids=selection['chunk_ids'];answer,cites=safe_render(ids,corpus)
            assert all(canonical(cite)==canonical(sources[cite['chunk_id']]) for cite in cites)
            value=dict(case_id=c['case_id'],repeat=c['repeat'],status='answered' if ids else 'refused',
                requirements=requirements,selected_ids=ids,answer=answer,citations=cites,selection_audit=audit)
        value.update(control_selected_ids=c['original_selected_ids'],new_mapping_calls=0,new_answer_synthesis_calls=0,
            verifier_calls=sum(r['model_calls'] for r in rs),verifier_seconds=sum(r['seconds'] for r in rs))
        name=f"result-{c['case_id']}-r{c['repeat']}.json";write(out/name,value);hashes[name]=sha(out/name)
    verify_refs(data['source_files'])
    write(out/'completed.json',dict(stage=data['stage'],pair_records=len(results),case_records=len(data['cases']),
        model_calls=sum(r['model_calls'] for r in results),hashes=hashes,inputs_unchanged=True))

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','run']);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--prepared',type=Path);p.add_argument('--stage',choices=['minimal','expansion'],default='minimal');a=p.parse_args()
    prepare(a.out,a.stage) if a.mode=='prepare' else run(a.out,a.prepared)
if __name__=='__main__':main()
