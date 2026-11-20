"""A1-controlled capture replay or fresh full Graph regression for the business gate."""
import argparse,copy,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
os.environ['LANGSMITH_TRACING']='false';os.environ['LANGCHAIN_TRACING_V2']='false'
from answer_eval_core import canonical,config,digest,now,questions,read,record
from rag_langgraph import Flow,Operations
from run_langgraph_flow import committed_inputs,new_engine,operations,runtime_identity
from task13_audit import source_map,upstream_clean
from answer_json_chat import generate
from rag_b0 import PinnedChat

def write(p,v):
    with p.open('xb') as f:f.write(canonical(v))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--mode',choices=['live','replay'],required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    cfg=config();assert (ROOT/cfg['prompt_file']).read_bytes()==(ROOT/'optimization/baseline/e8b0fd6/prompt_A.txt').read_bytes()
    control=ROOT/'.runtime/phase2/e4-live90';hashes=read(control/'completed.json')['hashes']
    cases=questions('dev')+questions('test')
    cases=sorted(cases,key=lambda q:({'D036':0,'T027':1,'D016':2}.get(q['question_id'],3),q['question_id']))
    corpus={r['chunk_id']:r for r in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    a.out.mkdir(parents=True,exist_ok=False);commit,inputs=committed_inputs();env=runtime_identity();upstream_clean()
    for name in ('scripts/answer_eval_core.py','scripts/answer_eval_engine.py','scripts/disciplinary_query_policy.py','scripts/task13_core.py','optimization/run_d036_regression.py'):
        inputs[name]=record(ROOT/name)
    frozen=read(ROOT/'optimization/baseline/e8b0fd6/freeze.json')
    for name,ref in frozen['data'].items():assert record(ROOT/name)==ref
    metadata=dict(mode=a.mode,source_commit=commit,source_files=inputs,environment=env,
                  model=cfg['llm'],prompt_variant='A',control=str(control),control_commit=read(control/'metadata.json')['source_commit'],
                  question_count=90,started=now(),holdout_used=False,new_inference=a.mode=='live')
    write(a.out/'metadata.json',metadata)
    class Recording(Operations):
        def retrieval(self,q,depth):
            value=super().retrieval(q,depth);self.obs['channels']=value;return value
        def fusion(self,*args):
            value=super().fusion(*args);self.obs['fused']=value;return value
        def rerank(self,*args):
            value=super().rerank(*args);self.obs['reranked']=value;return value
        def expand(self,ids):
            value=super().expand(ids);self.obs['evidence']=value;return value
        def generate(self,messages,schema):
            item=dict(messages=messages,schema=schema);self.obs['model_attempts'].append(item)
            try:r=super().generate(messages,schema);item['response']=r;return r
            except Exception as exc:
                item['error']=type(exc).__name__+': '+str(exc)
                if hasattr(exc,'response'):item['response']=exc.response
                raise
    class Chat:
        config=cfg
        requests=0
    class Replay(Recording):
        @property
        def completed_embeddings(self):return None
        def retrieval(self,*args):return copy.deepcopy(self.prior['observations'].get('channels',{}))
        def fusion(self,*args):return copy.deepcopy(self.prior['observations']['fused'])
        def rerank(self,*args):return [{'chunk_id':cid} for cid in self.prior['result']['retrieved_ids']]
        def expand(self,ids):return [corpus[cid] for cid in ids]
        def generate(self,messages,schema):
            item=copy.deepcopy(self.queue.pop(0));assert item['messages']==messages and item['schema']==schema
            self.obs['model_attempts'].append(item);self.chat.requests+=1;return item['response']
    engine=None
    if a.mode=='live':
        warm=generate(PinnedChat(cfg),[{'role':'system','content':'只输出一个JSON对象。'},{'role':'user','content':'返回ready为true。'}],{'type':'object','properties':{'ready':{'const':True}},'required':['ready'],'additionalProperties':False})
        write(a.out/'warmup.json',dict(response=warm,excluded=True))
        engine=new_engine();base=operations(engine);ops=Recording(base.retriever,base.chat,base.answer_policy,base.prompt,base.sources)
    else:ops=Replay(None,Chat(),cfg,(ROOT/cfg['prompt_file']).read_text('utf8'),source_map())
    flow=Flow(ops);comparisons=[];finished=[];started=time.perf_counter()
    try:
        for ix,q in enumerate(cases,1):
            qid=q['question_id'];prior=read(control/(qid+'.json'));assert digest((control/(qid+'.json')).read_bytes())==hashes[qid]
            ops.obs={'model_attempts':[]}
            if a.mode=='replay':ops.prior=prior;ops.queue=copy.deepcopy(prior['observations']['model_attempts'])
            r=flow.invoke(q['question']);ats=ops.obs['model_attempts']
            assert r['chat_calls']==len(ats)==len(r['attempts'])==len(r['selection_audits'])<=2
            compared={key:r[key]==prior['result'][key] for key in ('status','selected_ids','citations','answer','reason')}
            if a.mode=='replay':
                if qid=='D036':assert r['status']=='refused' and not ats and len(ops.queue)==1
                else:assert all(compared.values()) and not ops.queue,(qid,compared)
            comparisons.append(dict(question_id=qid,fields_equal_to_A1=compared,business_decision=r.get('business_decision')))
            write(a.out/(qid+'.json'),dict(question_id=qid,question=q['question'],result=r,observations=ops.obs,A1_trace_sha256=hashes[qid],comparison=compared));finished.append(qid)
            print(json.dumps(dict(mode=a.mode,done=ix,qid=qid,status=r['status'],selected=r['selected_ids'],calls=r['chat_calls'],seconds=round(r['wall_ns']/1e9,3)),ensure_ascii=False),flush=True)
    finally:
        if engine is not None:engine.close()
    assert all(record(ROOT/name)==ref for name,ref in inputs.items())
    assert all(record(ROOT/name)==ref for name,ref in frozen['data'].items())
    write(a.out/'completed.json',dict(records=90,hashes={qid:digest((a.out/(qid+'.json')).read_bytes()) for qid in finished},elapsed_seconds=time.perf_counter()-started,finished=now(),inputs_unchanged=True))
    write(a.out/'A1_comparisons.json',comparisons)
    for split,name in [('dev','dev_40.json'),('test','regression_50.json')]:
        view=a.out/('score-'+split);view.mkdir();vhash={}
        write(view/'metadata.json',dict(split=split,variants=['D036_GATE'],dataset_sha256=digest((ROOT/'optimization/datasets'/name).read_bytes()),source_commit=commit,derived_from_mode=a.mode,raw_parent=str(a.out),holdout_used=False))
        for q in questions(split):
            qid=q['question_id'];t=read(a.out/(qid+'.json'));r=t['result'];ats=t['observations']['model_attempts'];rs=[v.get('response',{}) for v in ats]
            v=dict(question_id=qid,variant='D036_GATE',question=q['question'],result=r,offered_ids=r['offered_ids'],retrieved_ids=r['retrieved_ids'],attempts=ats,seconds=r['wall_ns']/1e9,chat_calls=r['chat_calls'],input_tokens=sum(v.get('prompt_eval_count',0) for v in rs),output_tokens=sum(v.get('eval_count',0) for v in rs),pre_generation_guard=not ats,parent_trace_sha256=digest((a.out/(qid+'.json')).read_bytes()))
            file=qid+'-G.json';write(view/file,v);vhash[file]=digest((view/file).read_bytes())
        write(view/'completed.json',dict(records=len(vhash),hashes=vhash))
if __name__=='__main__':main()
