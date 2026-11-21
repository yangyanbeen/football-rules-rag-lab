"""E10 fixed-context A/B: only answer weights and pinned model identity differ."""
import argparse,copy,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
os.environ['LANGSMITH_TRACING']='false';os.environ['LANGCHAIN_TRACING_V2']='false'
from answer_eval_core import read,record,config,canonical
from answer_json_chat import generate,selection_schema
from rag_b0 import PinnedChat
from rag_langgraph import CountingChat,Operations
from citation_catalog_guard import safe_render
from e5_second_candidate import module,BASE
from e10_resources import Sampler,snapshot

D=ROOT/'optimization/experiments/E10_answer_model'
FROZEN=ROOT/'.runtime/phase2/e10-frozen/inputs.json'
DEPLOY=ROOT/'.runtime/phase2/e10-deployment'
CANDIDATE='e10-qwen2.5-7b-instruct-q4km:official'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    with p.open('xb') as f:f.write(canonical(v))
def check(refs):assert all(record(ROOT/n)==v for n,v in refs.items())
def assess(result,c):
    ids=result['selected_ids'];mask=[bool(set(ids)&set(v)) for v in c['support_per_point']]
    grade='runtime_error' if result['status']=='failed' else 'false_refusal' if result['status']=='refused' else 'correct' if all(mask) else 'partial' if any(mask) else 'incorrect'
    supported=[cid for cid in ids if any(cid in v for v in c['support_per_point'])]
    return dict(grade=grade,point_mask=mask,supported_ids=supported,citation_numerator=len(supported),citation_denominator=len(ids))

def prepare(out):
    out.mkdir(parents=True,exist_ok=False);f=read(FROZEN);check(f['source_files'])
    assert sha(D/'plan.json')==f['plan_sha256'] and sha(D/'context_review.json')==f['review_sha256']
    tags=read(DEPLOY/'tags.json')['models'];a=next(v for v in tags if v['name']=='qwen2.5:3b');b=next(v for v in tags if v['name']==CANDIDATE)
    ca=config();assert a['digest']==ca['llm']['digest'];cb=copy.deepcopy(ca);cb['llm'].update(name=CANDIDATE,digest=b['digest'])
    baseline_manifest=ROOT/'.runtime/phase2/e10-models/manifests/registry.ollama.ai/library/qwen2.5/3b'
    assert sha(baseline_manifest)==ca['llm']['digest']
    sa=read(DEPLOY/'baseline-show.json');sb=read(DEPLOY/'candidate-show.json')
    assert sa['template']==sb['template'] and sa.get('system')==sb.get('system') and sa.get('parameters')==sb.get('parameters')
    assert sb['details']['quantization_level']=='Q4_K_M'
    merged=read(ROOT/'.runtime/phase2/e10-download/qwen2.5-7b-instruct-q4_k_m.verified.json')
    stores=ROOT/'.runtime/phase2/e10-models'
    manifests=[stores/p/'library/e10-qwen2.5-7b-instruct-q4km/official' for p in ('manifests-v2/ollama.com','manifests/registry.ollama.ai')]
    manifest_path=next(p for p in manifests if p.is_file() and sha(p)==b['digest'])
    imported=read(manifest_path)
    layer=next(v for v in imported['layers'] if v['mediaType']=='application/vnd.ollama.image.model')
    assert layer['digest']=='sha256:'+merged['sha256']
    assert set(k for k in ca['llm'] if ca['llm'][k]!=cb['llm'][k])=={'name','digest'}
    refs=dict(f['source_files'])
    for p in [FROZEN,Path(__file__),ROOT/'optimization/e10_resources.py',D/'plan.json',D/'context_review.json',DEPLOY/'tags.json',DEPLOY/'baseline-show.json',DEPLOY/'candidate-show.json',baseline_manifest,manifest_path,ROOT/'.runtime/phase2/e10-download/qwen2.5-7b-instruct-q4_k_m.verified.json']:
        refs[p.relative_to(ROOT).as_posix()]=record(p)
    write(out/'prepared.json',dict(cases=f['cases'],schedule=f['schedule'],configs={'A':ca,'B':cb},
        source_files=refs,plan=read(D/'plan.json'),candidate_details=sb['details'],candidate_model_info=sb.get('model_info'),
        template_sha256=hashlib.sha256(sa['template'].encode()).hexdigest(),holdout_used=False))
    print(json.dumps(dict(candidate=b['name'],digest=b['digest'],details=sb['details'],primary_observations=36)))

def build(cfg,corpus,name):
    from task13_audit import source_map
    graph=module(BASE,'scripts/rag_langgraph.py','e10_graph_'+name)
    class Frozen(Operations):
        @property
        def completed_embeddings(self):return 0
        def retrieval(self,*args):return copy.deepcopy(self.trace['observations']['channels'])
        def fusion(self,*args):return copy.deepcopy(self.trace['observations']['fused'])
        def rerank(self,*args):return copy.deepcopy(self.trace['observations'].get('reranked',[{'chunk_id':c} for c in self.trace['result']['retrieved_ids']]))
        def expand(self,ids):return [corpus[c] for c in ids]
        def generate(self,messages,schema):
            item=dict(messages=messages,schema=schema);self.obs.append(item)
            try:r=super().generate(messages,schema);item['response']=r;return r
            except Exception as exc:
                item['error']=type(exc).__name__+': '+str(exc)
                if hasattr(exc,'response'):item['response']=exc.response
                raise
    ops=Frozen(None,CountingChat(PinnedChat(cfg)),cfg,(ROOT/cfg['prompt_file']).read_text('utf8'),source_map());ops.obs=[]
    def fixed_pack(q,evidence,policy,prompt):
        assert q==ops.case['question'] and [v['chunk_id'] for v in evidence]==ops.case['retrieved_ids']
        assert prompt==ops.case['messages'][0]['content']
        messages=copy.deepcopy(ops.case['messages']);assert len(canonical(messages))<=6200
        return [corpus[c] for c in ops.case['offered_ids']],messages,len(canonical(messages))
    graph.pack=fixed_pack
    return ops,graph.Flow(ops)

def normal_gates(ops,flow,cfg):
    q=read(ROOT/'.runtime/phase2/d036-gate-live90-final/D036.json')['question'];before=ops.chat_calls
    graph=flow.invoke(q);assert graph['status']=='refused' and graph['chat_calls']==0 and not graph['retrieved_ids']
    from task13_engine import IntegratedEngine
    from task13_core import app_config
    linear=IntegratedEngine.__new__(IntegratedEngine);linear.cfg=app_config();linear.answer_cfg=cfg;linear.chat=ops.chat;linear.retriever=None
    result=linear.answer(q)
    assert result['status']=='refused' and not result['attempts'] and result['retrieval'] is None and result['error'] is None
    assert ops.chat_calls==before
    return dict(graph=graph,linear=result,linear_constructor='Dependencies injected; unmodified normal answer method, no retriever or model consumed')

def run(out,prepared,pid):
    out.mkdir(parents=True,exist_ok=False);data=read(prepared);check(data['source_files'])
    assert not subprocess.check_output(['git','diff',BASE,'--','scripts','config'],cwd=ROOT)
    corpus={v['chunk_id']:v for v in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    engines={v:build(data['configs'][v],corpus,v) for v in 'AB'};by={c['case_id']:c for c in data['cases']}
    sampler=Sampler(pid,out/'resources.jsonl');hashes={};records=[];calls_before={v:engines[v][0].chat_calls for v in 'AB'}
    # Audit the locked base interpreter in a clean process; monitoring tools
    # live outside that environment and are disclosed separately.
    environment=json.loads(subprocess.check_output([sys.executable,'-B','-c',
        "import sys,json;sys.path.insert(0,'scripts');from run_langgraph_flow import runtime_identity;print(json.dumps(runtime_identity()))"],cwd=ROOT,text=True,encoding='utf8'))
    environment['experiment_monitoring_tools']=read(DEPLOY/'psutil-tool.json')
    environment['audit_scope']='Exact locked base environment checked in clean interpreter; extra psutil loaded only for owned-process monitoring, not installed into base venv.'
    write(out/'metadata.json',dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        prepared_sha256=sha(prepared),models={v:data['configs'][v]['llm'] for v in 'AB'},environment=environment,
        primary_schedule=data['schedule'],maximum_extra_observations=24,actual_new_retrieval_calls=0,
        latency_scope=data['plan']['latency_scope'],source_files=data['source_files'],server_pid=pid,hardware_at_run=snapshot(),holdout_used=False))
    try:
        gates={v:normal_gates(*engines[v],data['configs'][v]) for v in 'AB'};write(out/'D036_zero_call.json',gates)
        begin=sampler.begin('deployment-probe-B')
        try:
            response=generate(engines['B'][0].chat,[{'role':'system','content':'只输出一个JSON对象。'},{'role':'user','content':'返回ready为true。'}],
                {'type':'object','properties':{'ready':{'const':True}},'required':['ready'],'additionalProperties':False})
            probe=dict(response=response,error=None,resources=sampler.end(begin),excluded_from_quality=True)
        except Exception as exc:
            probe=dict(error=type(exc).__name__+': '+str(exc),resources=sampler.end(begin),excluded_from_quality=True)
            if hasattr(exc,'read'):
                try:probe['server_error_body']=json.loads(exc.read().decode('utf8'))
                except (ValueError,TypeError,UnicodeError):pass
        write(out/'deployment_probe.json',probe)
        resource=probe['resources']
        feasible=(probe['error'] is None and resource['samples']>0 and not sampler.aborted and .25<resource['process_rss_peak_GiB']<=6.5
                  and resource['available_min_GiB'] is not None and resource['available_min_GiB']>=1)
        if not feasible:
            write(out/'completed.json',dict(status='DEPLOYMENT_PREFLIGHT_FAILED',primary_observations=0,hashes={},probe_calls=engines['B'][0].chat_calls-calls_before['B'],holdout_used=False))
            print(json.dumps(dict(status='DEPLOYMENT_PREFLIGHT_FAILED',resources=resource,error=probe['error'])),flush=True);return
        def invoke(item):
            ops,flow=engines[item['variant']];c=by[item['case_id']];ops.case=c;ops.trace=read(ROOT/c['source_trace']);ops.obs=[]
            before=sampler.begin(f"{item['phase']}-{item['case_id']}-{item['variant']}-r{item['repeat']}")
            result=flow.invoke(c['question']);resources=sampler.end(before)
            assert result['chat_calls']==len(ops.obs)==len(result['selection_audits'])<=2
            assert result['offered_ids']==c['offered_ids']
            for at in ops.obs:
                assert at['messages'][:len(c['messages'])]==c['messages'] and at['schema']==c['schema']
            if result['status']!='failed':assert safe_render(result['selected_ids'],corpus)==(result['answer'],result['citations'])
            name=f"{item['phase']}-{item['case_id']}-{item['variant']}-r{item['repeat']}.json"
            value=dict(**item,question_id=c['question_id'],question=c['question'],result=result,
                observations={'model_attempts':ops.obs},resources=resources,score=assess(result,c),new_embedding_calls=0,new_reranker_calls=0)
            write(out/name,value);hashes[name]=sha(out/name);records.append(value)
            print(json.dumps(dict(done=len(records),**item,status=result['status'],selected=result['selected_ids'],grade=value['score']['grade'],seconds=result['wall_ns']/1e9,resources=resources),ensure_ascii=False),flush=True)
            if sampler.aborted:raise RuntimeError('Task-owned model process stopped by critical memory budget')
        for item in data['schedule']:invoke(item)
        triggers=[]
        for key in [q+'-native' for q in ('D001','D002','D003','D012','D004','D009')]:
            a,b=(next(v for v in records if v['phase']=='primary' and v['case_id']==key and v['variant']==variant) for variant in 'AB')
            recovery=a['score']['grade']=='false_refusal' and b['score']['grade']=='correct'
            original=key in ('D004-native','D009-native')
            def cite(v):
                d=v['score']['citation_denominator'];return v['score']['citation_numerator']/d if d else 0
            regression=original and a['score']['grade']=='correct' and (b['score']['grade']!='correct' or cite(b)<cite(a))
            if recovery or regression:triggers.append(dict(case_id=key,recovery=recovery,control_regression=regression))
        write(out/'retest_triggers.json',triggers)
        for trigger in triggers:
            for repeat,order in [(4,'AB'),(5,'BA')]:
                for variant in order:invoke(dict(case_id=trigger['case_id'],variant=variant,repeat=repeat,phase='confirmation'))
        check(data['source_files'])
        write(out/'completed.json',dict(status='COMPLETED',primary_observations=36,total_observations=len(records),
            quality_model_calls=sum(v['result']['chat_calls'] for v in records),probe_calls=1,hashes=hashes,holdout_used=False,inputs_unchanged=True))
    finally:sampler.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','run']);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--prepared',type=Path);p.add_argument('--server-pid',type=int);a=p.parse_args()
    prepare(a.out) if a.mode=='prepare' else run(a.out,a.prepared,a.server_pid)
if __name__=='__main__':main()
