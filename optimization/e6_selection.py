"""E6: fixed archived contexts, one selection-instruction candidate, paired live calls."""
import argparse,copy,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
os.environ['LANGSMITH_TRACING']='false';os.environ['LANGCHAIN_TRACING_V2']='false'
from answer_eval_core import canonical,config,read,record
from answer_json_chat import generate,selection_schema
from rag_b0 import PinnedChat
from rag_langgraph import Operations,CountingChat
from citation_catalog_guard import safe_render
from e5_second_candidate import inputs,check_refs,module,BASE,RUN
D=ROOT/'optimization/experiments/E6_evidence_selection'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    with p.open('xb') as f:f.write(canonical(v))
def prepare(out):
    out.mkdir(parents=True,exist_ok=False);cfg=config();reviews=read(D/'point_evidence_review.json')
    prompts={v:(D/f'prompt_{v}.txt').read_text('utf8') for v in 'AB'}
    assert (ROOT/cfg['prompt_file']).read_bytes()==prompts['A'].encode()
    assert len(prompts['B'].encode())<=len(prompts['A'].encode())
    assert not subprocess.check_output(['git','diff','5986781','--','scripts','config'],cwd=ROOT)
    items=[]
    for v in reviews:
        path=ROOT/v['source_trace'];assert sha(path)==v['source_sha256'];t=read(path);at=t['observations']['model_attempts'][0]
        ev=json.loads(at['messages'][1]['content'])['evidence'];assert [r['chunk_id'] for r in ev]==v['offered_ids']
        for variant in 'AB':
            msg=copy.deepcopy(at['messages']);msg[0]['content']=prompts[variant]
            assert msg[1:]==at['messages'][1:] and len(canonical(msg))<=6200
            assert at['schema']==selection_schema(v['offered_ids'],3)
        items.append(dict(**v,messages=at['messages'],schema=at['schema'],retrieved_ids=t['result']['retrieved_ids']))
    stress=[v['case_id'] for v in reviews if v['question_id'].startswith('T')]
    dev=[v['case_id'] for v in reviews if v['question_id'].startswith('D')]
    schedule=[]
    for repeat in range(1,5):
        selected_dev=dev if repeat<=2 else [v for v in dev if v.split('-')[0] in ('D004','D009','D017')]
        for pos,key in enumerate(stress+selected_dev):
            for variant in ('AB' if (repeat+pos)%2 else 'BA'):schedule.append(dict(case_id=key,variant=variant,repeat=repeat))
    write(out/'prepared.json',dict(cases=items,schedule=schedule,prompt_hashes={v:sha(D/f'prompt_{v}.txt') for v in 'AB'},
         source_files=inputs(),review_sha256=sha(D/'point_evidence_review.json'),holdout_used=False))
    print(json.dumps(dict(contexts=len(items),invocations=len(schedule),prompt_bytes={v:len(p.encode()) for v,p in prompts.items()})))
def pilot(out,prepared):
    out.mkdir(parents=True,exist_ok=False);data=read(prepared);check_refs(data['source_files']);cfg=config()
    prompts={v:(D/f'prompt_{v}.txt').read_text('utf8') for v in 'AB'}
    assert all(sha(D/f'prompt_{v}.txt')==data['prompt_hashes'][v] for v in 'AB')
    corpus={v['chunk_id']:v for v in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    from run_langgraph_flow import runtime_identity
    from task13_audit import source_map
    graph=module(BASE,'scripts/rag_langgraph.py','e6_fixed_graph')
    chat=CountingChat(PinnedChat(cfg))
    class Frozen(Operations):
        @property
        def completed_embeddings(self):return 0
        def retrieval(self,*args):return copy.deepcopy(self.trace['observations']['channels'])
        def fusion(self,*args):return copy.deepcopy(self.trace['observations']['fused'])
        def rerank(self,*args):
            return copy.deepcopy(self.trace['observations'].get('reranked',[{'chunk_id':c} for c in self.trace['result']['retrieved_ids']]))
        def expand(self,ids):return [corpus[c] for c in ids]
        def generate(self,messages,schema):
            item=dict(messages=messages,schema=schema);self.obs.append(item)
            try:resp=super().generate(messages,schema);item['response']=resp;return resp
            except Exception as exc:
                item['error']=type(exc).__name__+': '+str(exc)
                if hasattr(exc,'response'):item['response']=exc.response
                raise
    ops=Frozen(None,chat,cfg,prompts['A'],source_map());flow=graph.Flow(ops)
    def fixed_pack(q,evidence,cfg,prompt):
        assert q==ops.case['question'] and [v['chunk_id'] for v in evidence]==ops.case['retrieved_ids']
        messages=copy.deepcopy(ops.case['messages']);messages[0]['content']=prompt
        rows=[corpus[c] for c in ops.case['offered_ids']];return rows,messages,len(canonical(messages))
    graph.pack=fixed_pack
    meta=dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),control_commit=BASE,
              prepared_sha256=sha(prepared),pilot_script=record(Path(__file__)),model=cfg['llm'],environment=runtime_identity(),
              schedule=data['schedule'],prompt_hashes=data['prompt_hashes'],holdout_used=False,
              scope='Real answer-model calls with frozen query/body/order/schema; system selection instruction only varies. No fresh retrieval.')
    write(out/'metadata.json',meta)
    warm=generate(chat,[{'role':'system','content':'只输出一个JSON对象。'},{'role':'user','content':'返回ready为true。'}],{'type':'object','properties':{'ready':{'const':True}},'required':['ready'],'additionalProperties':False})
    write(out/'warmup.json',dict(response=warm,excluded=True));hashes={};by={v['case_id']:v for v in data['cases']}
    for ix,item in enumerate(data['schedule'],1):
        ops.case=by[item['case_id']];ops.trace=read(ROOT/ops.case['source_trace']);ops.obs=[];ops.prompt=prompts[item['variant']]
        r=flow.invoke(ops.case['question']);assert r['chat_calls']==len(ops.obs)==len(r['selection_audits'])<=2
        assert ops.obs[0]['messages'][1:]==ops.case['messages'][1:] and ops.obs[0]['schema']==ops.case['schema']
        assert r['offered_ids']==ops.case['offered_ids']
        if r['status']!='failed':assert safe_render(r['selected_ids'],corpus)==(r['answer'],r['citations'])
        name=f"{item['case_id']}-{item['variant']}-r{item['repeat']}.json"
        write(out/name,dict(**item,question_id=ops.case['question_id'],question=ops.case['question'],result=r,observations={'model_attempts':ops.obs},actual_new_embedding_calls=0,actual_new_reranker_calls=0))
        hashes[name]=sha(out/name)
        print(json.dumps(dict(done=ix,total=len(data['schedule']),**item,status=r['status'],selected=r['selected_ids']),ensure_ascii=False),flush=True)
    gates=[]
    for variant in 'AB':
        ops.prompt=prompts[variant];ops.obs=[];before=ops.chat_calls
        r=flow.invoke(read(RUN/'D036.json')['question']);assert r['status']=='refused' and r['chat_calls']==0 and ops.chat_calls==before and not ops.obs
        gates.append(dict(variant=variant,result=r))
    write(out/'D036_zero_call.json',gates);check_refs(data['source_files'])
    assert all(sha(D/f'prompt_{v}.txt')==data['prompt_hashes'][v] for v in 'AB')
    write(out/'completed.json',dict(records=len(hashes),hashes=hashes,inputs_unchanged=True))
def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','pilot']);p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);a=p.parse_args()
    prepare(a.out) if a.mode=='prepare' else pilot(a.out,a.prepared)
if __name__=='__main__':main()
