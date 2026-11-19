"""E5-A/A: fresh full-graph regression, candidate window only."""
import argparse,copy,json,os,subprocess,sys,time
from pathlib import Path
from types import ModuleType
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
os.environ['LANGSMITH_TRACING']='false';os.environ['LANGCHAIN_TRACING_V2']='false'
from answer_eval_core import canonical,config,digest,now,parse_selection,questions,read,record
from answer_json_chat import generate
from rag_langgraph import Flow,Operations
from run_langgraph_flow import committed_inputs,new_engine,operations,runtime_identity
from rag_b0 import PinnedChat
from task13_audit import source_map,upstream_clean

BASE='e8b0fd6bbdb70b1144d9a4e7f03d811da593b0f5'
def write(p,v):
    with p.open('xb') as f:f.write(canonical(v))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',choices=['live'],required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    cfg=config();assert (ROOT/cfg['prompt_file']).read_bytes()==(ROOT/'optimization/baseline/e8b0fd6/prompt_A.txt').read_bytes()
    cases=questions('dev')+questions('test');assert len(cases)==90
    cases=sorted(cases,key=lambda q:({'T034':0,'D021':1,'T032':2,'D002':3,'D019':4,'D001':5}.get(q['question_id'],6),q['question_id']))
    refs={x['question_id']:x for x in read(ROOT/'optimization/baseline/e8b0fd6/trace_manifest.local.json')}
    corpus={x['chunk_id']:x for x in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    baseline=ModuleType('e4_frozen_parser');baseline.__file__=str(ROOT/'scripts/answer_eval_core.py')
    exec(compile(subprocess.check_output(['git','show',BASE+':scripts/answer_eval_core.py'],cwd=ROOT),baseline.__file__,'exec'),baseline.__dict__)
    a.out.mkdir(parents=True,exist_ok=False);source,inputs=committed_inputs();environment=runtime_identity();upstream_clean()
    inputs['scripts/answer_eval_core.py']=record(ROOT/'scripts/answer_eval_core.py')
    inputs['scripts/answer_eval_engine.py']=record(ROOT/'scripts/answer_eval_engine.py')
    fixed={n:record(ROOT/n) for n in ['config/answer_evaluation_system.txt','config/answer_evaluation.json','config/langgraph_flow.json','data/eval/answer_eval.jsonl','data/processed/rag_chunks_zh.jsonl','data/manifests/task13_citation_sources.json','data/indexes/task13/dense-v1/index_manifest.json','data/indexes/bm25/task13-title-body-v1/index_manifest.json']}
    write(a.out/'metadata.json',dict(mode=a.mode,started=now(),source_commit=source,baseline_commit=BASE,source_files=inputs,environment=environment,policies=fixed,model=cfg['llm'],prompt_variant='A',scope='Fresh actual Flow.invoke, real retrieval/rerank/model' if a.mode=='live' else 'Captured baseline responses and retrieval: zero live inference; isolated parser control',holdout_used=False,question_count=90))
    class Recording(Operations):
        def retrieval(self,q,depth):
            v=super().retrieval(q,depth);self.obs['channels']=v;return v
        def fusion(self,*args):
            v=super().fusion(*args);self.obs['fused']=v;return v
        def expand(self,ids):
            v=super().expand(ids);self.obs['evidence']=v;return v
        def generate(self,messages,schema):
            item={'messages':messages,'schema':schema};self.obs['model_attempts'].append(item)
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
        def retrieval(self,*args):return self.trace['observations'].get('channels',{})
        def fusion(self,*args):return [{'chunk_id':cid} for cid in self.trace['result']['retrieved_ids']]
        def rerank(self,*args):return [{'chunk_id':cid} for cid in self.trace['result']['retrieved_ids']]
        def expand(self,ids):return [corpus[cid] for cid in ids]
        def generate(self,messages,schema):
            original=self.queue.pop(0);assert messages==original['messages'] and schema==original['schema']
            item=copy.deepcopy(original);self.obs['model_attempts'].append(item);self.chat.requests+=1;return item['response']
    engine=None
    if a.mode=='live':
        warm_start=time.perf_counter();warm=generate(PinnedChat(cfg),[{'role':'system','content':'只输出一个JSON对象。'},{'role':'user','content':'返回ready为true。'}],{'type':'object','properties':{'ready':{'const':True}},'required':['ready'],'additionalProperties':False})
        write(a.out/'warmup.json',dict(response=warm,seconds=time.perf_counter()-warm_start,excluded=True));engine=new_engine();base=operations(engine);ops=Recording(base.retriever,base.chat,base.answer_policy,base.prompt,base.sources)
    else:ops=Replay(None,Chat(),cfg,(ROOT/cfg['prompt_file']).read_text('utf8'),source_map())
    flow=Flow(ops);start=time.perf_counter();completed=[]
    try:
        for ix,q in enumerate(cases,1):
            qid=q['question_id'];ref=refs[qid];assert digest(Path(ref['private_path']).read_bytes())==ref['sha256'];prior=read(Path(ref['private_path']))
            ops.obs={'model_attempts':[]}
            if a.mode=='replay':ops.trace=prior;ops.queue=copy.deepcopy(prior['observations'].get('model_attempts',[]))
            result=flow.invoke(q['question']);assert len(result['selection_audits'])==len(result['attempts'])==len(ops.obs['model_attempts'])==result['chat_calls']<=2
            paired=[]
            for captured,audit in zip(ops.obs['model_attempts'],result['selection_audits']):
                assert audit['response']==captured.get('response')
                raw=captured.get('response',{}).get('message',{}).get('content')
                if raw is None:continue
                pair={'raw':raw}
                for name,parser in [('baseline',baseline.parse_selection),('E4',parse_selection)]:
                    try:pair[name]=parser(raw,result['offered_ids'],cfg)
                    except (ValueError,TypeError,KeyError) as exc:pair[name+'_error']=type(exc).__name__+': '+str(exc)
                assert audit['normalized_selection']==pair.get('E4')
                paired.append(pair)
            value=dict(question_id=qid,question=q['question'],result=result,observations=ops.obs,parser_comparison=paired,baseline_trace_sha256=ref['sha256'])
            write(a.out/f'{qid}.json',value);completed.append(qid)
            print(json.dumps(dict(mode=a.mode,done=ix,total=90,qid=qid,status=result['status'],ids=result['selected_ids'],calls=result['chat_calls'],seconds=round(result['wall_ns']/1e9,3)),ensure_ascii=False),flush=True)
    finally:
        if engine is not None:engine.close()
    assert all(record(ROOT/p)==v for p,v in {**inputs,**fixed}.items())
    write(a.out/'completed.json',dict(finished=now(),records=90,elapsed_seconds=time.perf_counter()-start,hashes={qid:digest((a.out/f'{qid}.json').read_bytes()) for qid in completed},inputs_unchanged=True))
    # Reproducible derived views for the existing independent semantic scorer.
    for split,name in [('dev','dev_40.json'),('test','regression_50.json')]:
        view=a.out/('score-'+split);view.mkdir();hashes={}
        meta=dict(split=split,variants=['E5_A'],dataset_sha256=digest((ROOT/'optimization/datasets'/name).read_bytes()),source_commit=source,derived_from_mode=a.mode,raw_parent=str(a.out),prompt_variant='A',holdout_used=False)
        write(view/'metadata.json',meta)
        for q in questions(split):
            qid=q['question_id'];raw=read(a.out/f'{qid}.json');r=raw['result'];attempts=raw['observations']['model_attempts'];responses=[x.get('response',{}) for x in attempts]
            item=dict(question_id=qid,variant='E5_A',question=q['question'],result=r,offered_ids=r['offered_ids'],retrieved_ids=r['retrieved_ids'],attempts=attempts,seconds=r['wall_ns']/1e9,chat_calls=r['chat_calls'],input_tokens=sum(x.get('prompt_eval_count',0) for x in responses),output_tokens=sum(x.get('eval_count',0) for x in responses),pre_generation_guard=not attempts,parent_trace_sha256=digest((a.out/f'{qid}.json').read_bytes()))
            file=qid+'-E.json';write(view/file,item);hashes[file]=digest((view/file).read_bytes())
        write(view/'completed.json',dict(records=len(hashes),hashes=hashes))
if __name__=='__main__':main()
