"""Frozen-candidate E5 refill audit and interleaved real-answer-model pilot."""
import argparse,copy,csv,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from types import ModuleType
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
os.environ['LANGSMITH_TRACING']='false';os.environ['LANGCHAIN_TRACING_V2']='false'
from answer_eval_core import canonical,config,parse_selection,read,record
from disciplinary_query_policy import evaluate_suspension_query
from citation_catalog_guard import safe_render
from answer_json_chat import generate
from rag_b0 import PinnedChat
from rag_langgraph import Operations,CountingChat
from run_langgraph_flow import runtime_identity

BASE='59867813e8eb16709b0be1946708d8c03a33b9cb'
FORMAL='86a01e938067f89bcc7dbbb1524d7e53426116f4'
RUN=ROOT/'.runtime/phase2/d036-gate-live90-final'
PRIMARY=['T034','T026','T014'];CONTROLS=['D013','T002','T013']

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    with p.open('xb') as f:f.write(canonical(v))
def module(commit,path,name):
    m=ModuleType(name);m.__file__=str(ROOT/path);sys.modules[name]=m
    exec(compile(subprocess.check_output(['git','show',commit+':'+path],cwd=ROOT),m.__file__,'exec'),m.__dict__)
    return m
def inputs():
    names=subprocess.check_output(['git','ls-files','scripts','config'],cwd=ROOT,text=True).splitlines()
    refs={n:record(ROOT/n) for n in names}
    refs.update(read(ROOT/'optimization/baseline/e8b0fd6/freeze.json')['data'])
    for row in read(ROOT/'optimization/datasets/freeze_manifest.json')['files']:
        p=ROOT/'optimization'/row['path'];assert sha(p)==row['sha256'];refs[p.relative_to(ROOT).as_posix()]=record(p)
    return refs
def check_refs(refs):assert all(record(ROOT/n)==v for n,v in refs.items())
def packers():
    from answer_eval_engine import pack
    return {'control':module(BASE,'scripts/answer_eval_engine.py','e5_refill_control_pack').pack,'candidate':pack}
def audit(out):
    out.mkdir(parents=True,exist_ok=False);cfg=config();prompt=(ROOT/cfg['prompt_file']).read_text('utf8');packs=packers();before=inputs()
    assert not subprocess.check_output(['git','diff','--name-only',FORMAL,BASE,'--','scripts','config'],cwd=ROOT)
    meta=read(RUN/'metadata.json');assert meta['source_commit']==FORMAL
    for name,ref in meta['source_files'].items():
        # Only the candidate pack differs from the full frozen D036 runtime.
        if name!='scripts/answer_eval_engine.py':assert record(ROOT/name)==ref
    rows=[];legacy=module('ba48ba1','scripts/answer_eval_engine.py','e5_prior_scan').pack
    for qid,h in sorted(read(RUN/'completed.json')['hashes'].items()):
        path=RUN/(qid+'.json');assert sha(path)==h;t=read(path);r=t['result'];ev=t['observations'].get('evidence',[])
        if not t['observations']['model_attempts']:
            rows.append(dict(question_id=qid,question=t['question'],bypassed=True,reason=r['reason'],business_decision=r.get('business_decision'),changed=False));continue
        packets={v:p(t['question'],ev,cfg,prompt) for v,p in packs.items()}
        assert packets['control'][1]==t['observations']['model_attempts'][0]['messages']
        old,new=packets['control'],packets['candidate'];oldids=[v['chunk_id'] for v in old[0]];newids=[v['chunk_id'] for v in new[0]]
        assert newids[:len(oldids)]==oldids and len(newids)==len(set(newids))<=5 and new[2]<=6200
        assert new[1]==legacy(t['question'],ev,cfg,prompt)[1]
        rows.append(dict(question_id=qid,question=t['question'],bypassed=False,changed=old[1]!=new[1],
                         control_ids=oldids,candidate_ids=newids,control_bytes=old[2],candidate_bytes=new[2],
                         added_ids=[v for v in newids if v not in oldids],removed_ids=[],retained_order_changed=False,
                         messages={'control':old[1],'candidate':new[1]},source_trace_sha256=h))
    by={r['question_id']:r for r in rows};assert 'L14-01' in by['T034']['candidate_ids'] and by['T034']['candidate_bytes']==6069
    assert {'L12-06','L12-15'}<=set(by['T026']['candidate_ids'])
    # General packing contracts, no semantic labels in candidate code.
    row=dict(chunk_id='x',law_number=1,content_zh='正文',needs_rule_review=False,review_notes=[])
    data=[dict(row,chunk_id=f'x{i}') for i in range(11)];c=packs['candidate'];checks={}
    checks['five_slots']=len(c('问题',data,cfg,prompt)[0])==5
    big=[dict(v,content_zh='长'*3000) for v in data];big[7]=data[7]
    checks['skip_over_budget_then_fill']=[r['chunk_id'] for r in c('问题',big,cfg,prompt)[0]]==['x7']
    big[7]=dict(data[7],content_zh='长'*3000);big[10]=data[10]
    checks['top11_excluded']=not c('问题',big,cfg,prompt)[0]
    # Original graph rejects duplicate retrieval IDs; test duplicates only in refill window.
    duplicate=copy.deepcopy(big);duplicate[7]=data[7];duplicate[8]=data[7]
    ids=[v['chunk_id'] for v in c('问题',duplicate,cfg,prompt)[0]]
    checks['refill_duplicate_skipped']=ids==['x7']
    try:c('问'*3000,data,cfg,prompt)
    except ValueError:checks['oversize_question_rejected']=True
    checks['source_not_mutated']=data[0]==dict(row,chunk_id='x0')
    assert all(checks.values()) and len(checks)==6
    check_refs(before)
    value=dict(control_commit=BASE,sealed_formal_producer=FORMAL,runtime_86_and_598_identical=True,
               candidate_scope='Keep original context then fill spare capacity in Top10 order; no rerank/prompt/model/data change',
               rows=rows,changed_ids=[r['question_id'] for r in rows if r['changed']],
               byte_identical_to_E5_A_on_all_86_nonbypassed_prompts=True,packing_tests=checks,
               source_files=before,holdout_used=False)
    write(out/'audit.json',value)
    buf=__import__('io').StringIO();w=csv.writer(buf,lineterminator='\n');w.writerow(['question_id','bypassed','changed','control_ids','candidate_ids','control_bytes','candidate_bytes'])
    for r in rows:w.writerow([r['question_id'],r['bypassed'],r['changed'],','.join(r.get('control_ids',[])),','.join(r.get('candidate_ids',[])),r.get('control_bytes',0),r.get('candidate_bytes',0)])
    (out/'contexts90.csv').write_bytes(b'\xef\xbb\xbf'+buf.getvalue().encode())
    print(json.dumps(dict(changed=value['changed_ids'],packing_tests=checks,T034={k:by['T034'][k] for k in ('control_ids','candidate_ids','control_bytes','candidate_bytes')},legacy_equivalent=True)))
def pilot(out,audit_path):
    out.mkdir(parents=True,exist_ok=False);aud=read(audit_path);check_refs(aud['source_files'])
    cfg=config();prompt=(ROOT/cfg['prompt_file']).read_text('utf8');packs=packers();corpus={v['chunk_id']:v for v in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    from task13_audit import source_map
    gm={v:module(BASE,'scripts/rag_langgraph.py','e5_pilot_graph_'+v) for v in packs}
    for v in gm:gm[v].pack=packs[v]
    class Frozen(Operations):
        @property
        def completed_embeddings(self):return 0
        def retrieval(self,q,depth):self.obs['channels']=self.trace['observations']['channels'];return copy.deepcopy(self.obs['channels'])
        def fusion(self,*args):return copy.deepcopy(self.trace['observations']['fused'])
        def rerank(self,*args):return copy.deepcopy(self.trace['observations']['reranked'])
        def expand(self,ids):return [corpus[cid] for cid in ids]
        def generate(self,messages,schema):
            item=dict(messages=messages,schema=schema);self.obs['model_attempts'].append(item)
            try:r=super().generate(messages,schema);item['response']=r;return r
            except Exception as exc:
                item['error']=type(exc).__name__+': '+str(exc)
                if hasattr(exc,'response'):item['response']=exc.response
                raise
    chat=CountingChat(PinnedChat(cfg));ops=Frozen(None,chat,cfg,prompt,source_map());flows={v:gm[v].Flow(ops) for v in gm}
    # Pre-register four pairs for the known unstable primary cases and two for controls.
    schedule=[]
    for repeat in range(1,5):
        for pos,qid in enumerate(PRIMARY+(CONTROLS if repeat<=2 else [])):
            for v in (['control','candidate'] if (repeat+pos)%2 else ['candidate','control']):schedule.append(dict(question_id=qid,variant=v,repeat=repeat))
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    write(out/'metadata.json',dict(source_commit=commit,control_commit=BASE,sealed_control_producer=FORMAL,
         schedule=schedule,model=cfg['llm'],environment=runtime_identity(),audit_sha256=sha(audit_path),pilot_script=record(Path(__file__)),
         scope='Actual answer-model calls through graph; retrieval/rerank candidates replayed and identical in both arms; not fresh end-to-end retrieval timing',holdout_used=False))
    warm=generate(chat,[{'role':'system','content':'只输出一个JSON对象。'},{'role':'user','content':'返回ready为true。'}],{'type':'object','properties':{'ready':{'const':True}},'required':['ready'],'additionalProperties':False})
    write(out/'warmup.json',dict(response=warm,excluded=True))
    hashes={}
    for ix,item in enumerate(schedule,1):
        qid=item['question_id'];ops.trace=read(RUN/(qid+'.json'));ops.obs={'model_attempts':[]}
        r=flows[item['variant']].invoke(ops.trace['question']);ats=ops.obs['model_attempts']
        assert len(ats)==r['chat_calls']==len(r['attempts'])<=2
        expected=next(x for x in aud['rows'] if x['question_id']==qid)['messages'][item['variant']]
        assert ats[0]['messages']==expected
        if r['status']!='failed':assert safe_render(r['selected_ids'],corpus)==(r['answer'],r['citations'])
        for at,ar in zip(ats,r['selection_audits']):assert at['response']==ar['response']
        name=f"{qid}-{item['variant']}-r{item['repeat']}.json"
        write(out/name,dict(**item,question=ops.trace['question'],result=r,observations=ops.obs,
                           actual_new_embedding_calls=0,actual_new_reranker_calls=0))
        hashes[name]=sha(out/name)
        print(json.dumps(dict(done=ix,total=len(schedule),**item,status=r['status'],selected_ids=r['selected_ids'],calls=r['chat_calls']),ensure_ascii=False),flush=True)
    # Both variants must short-circuit D036 without calling the actual model.
    d036=read(RUN/'D036.json');ops.trace=d036;gates=[]
    for v in flows:
        before=ops.chat_calls;ops.obs={'model_attempts':[]};r=flows[v].invoke(d036['question'])
        assert r['status']=='refused' and r['chat_calls']==0 and ops.chat_calls==before and ops.obs=={'model_attempts':[]}
        gates.append(dict(variant=v,result=r))
    write(out/'D036_zero_call.json',gates)
    check_refs(aud['source_files']);write(out/'completed.json',dict(records=len(schedule),hashes=hashes,inputs_unchanged=True))
def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['audit','pilot']);p.add_argument('--out',type=Path,required=True);p.add_argument('--audit',type=Path);a=p.parse_args()
    audit(a.out) if a.mode=='audit' else pilot(a.out,a.audit)
if __name__=='__main__':main()
