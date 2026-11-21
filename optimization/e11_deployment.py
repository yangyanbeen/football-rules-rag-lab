"""E11: resident deployment, bounded preflights, then frozen E10 model-only A/B."""
import argparse,copy,json,socket,subprocess,sys,time
from pathlib import Path
from e10_model_comparison import ROOT,BASE,build,check,normal_gates,read,record,sha,write,assess
from e10_resources import Sampler,snapshot,psutil
from answer_eval_core import canonical
from answer_json_chat import generate,selection_schema
from citation_catalog_guard import safe_render

D=ROOT/'optimization/experiments/E11_deployment'
E10=ROOT/'.runtime/phase2/e10-prepared-final/prepared.json'

def memory_ok(resource):
    return bool(resource['samples'] and not resource['resource_abort']
        and .25<resource['process_rss_peak_GiB']<=6.5
        and resource['available_min_GiB'] is not None and resource['available_min_GiB']>=1)

def preflight_sequence(generic,representative):
    first=generic()
    if not (first['protocol_pass'] and memory_ok(first['resources'])):
        return dict(status='GENERIC_PREFLIGHT_FAILED',generic=first,representative=None)
    second=representative()
    if not (second['protocol_pass'] and second['technical_complete'] and memory_ok(second['resources']) and second['seconds']<=90):
        return dict(status='REPRESENTATIVE_PREFLIGHT_FAILED',generic=first,representative=second)
    return dict(status='PREFLIGHTS_PASSED',generic=first,representative=second)

def prepare(out):
    out.mkdir(parents=True,exist_ok=False);e=read(E10);check(e['source_files'])
    candidates=[];run=ROOT/'.runtime/phase2/d036-gate-live90-final'
    for path in sorted(run.glob('D*.json')):
        t=read(path);ats=t.get('observations',{}).get('model_attempts',[])
        if ats:
            m=ats[0]['messages'];candidates.append((len(canonical(m)),path,t,ats[0]))
    size,path,t,at=max(candidates,key=lambda v:(v[0],v[1].stem))
    assert 5580<=size<=6200
    case=dict(case_id=path.stem+'-deployment',question_id=path.stem,question=t['question'],
        messages=at['messages'],schema=at['schema'],offered_ids=t['result']['offered_ids'],
        retrieved_ids=t['result']['retrieved_ids'],source_trace=path.relative_to(ROOT).as_posix(),prompt_bytes=size)
    assert case['schema']==selection_schema(case['offered_ids'],3)
    refs=dict(e['source_files']);refs[E10.relative_to(ROOT).as_posix()]=record(E10)
    for p in [Path(__file__),ROOT/'optimization/e11_resident.py',ROOT/'optimization/run_e11_deployment.ps1',ROOT/'optimization/verify_e11_deployment.py',D/'plan.json',path]:
        refs[p.relative_to(ROOT).as_posix()]=record(p)
    write(out/'prepared.json',dict(e10=e,representative=case,source_files=refs,plan=read(D/'plan.json'),holdout_used=False))
    write(D/'representative_manifest.json',dict(question_id=path.stem,prompt_utf8_bytes=size,
        prompt_sha256=__import__('hashlib').sha256(canonical(case['messages'])).hexdigest(),
        offered_ids=case['offered_ids'],trace_sha256=sha(path),
        selection_rule='Maximum archived first-attempt Prompt byte size among existing D-series development questions, independent of answer grade.',
        excluded_from_primary_36=True))
    print(json.dumps(dict(representative=path.stem,prompt_utf8_bytes=size,primary_observations=len(e['schedule'])),ensure_ascii=False))

def timing(attempts):
    responses=[v.get('response',{}) for v in attempts]
    return dict(load_seconds=sum(v.get('load_duration',0) for v in responses)/1e9,
        server_resident_request_seconds=sum(max(0,v.get('total_duration',0)-v.get('load_duration',0)) for v in responses)/1e9,
        prompt_eval_seconds=sum(v.get('prompt_eval_duration',0) for v in responses)/1e9,
        generation_seconds=sum(v.get('eval_duration',0) for v in responses)/1e9,
        input_tokens=sum(v.get('prompt_eval_count',0) for v in responses),output_tokens=sum(v.get('eval_count',0) for v in responses))

def residents(roots):
    values={}
    for pid in roots:
        p=psutil.Process(pid)
        for proc in [p,*p.children(recursive=True)]:
            try:values[proc.pid]=dict(pid=proc.pid,name=proc.name(),rss_GiB=proc.memory_info().rss/2**30)
            except psutil.NoSuchProcess:pass
    return list(values.values())

def listen(port):
    s=socket.socket();s.settimeout(.5)
    try:return s.connect_ex(('127.0.0.1',port))==0
    finally:s.close()

def run(out,prepared,pid,ui_pid,worker_ready,wait_seconds):
    out.mkdir(parents=True,exist_ok=False);p=read(prepared);check(p['source_files']);data=p['e10']
    assert not subprocess.check_output(['git','diff',BASE,'--','scripts','config'],cwd=ROOT)
    worker=read(worker_ready);assert worker['status']=='READY' and listen(7867)
    roots=[ui_pid,worker['pid']]
    environment=json.loads(subprocess.check_output([sys.executable,'-B','-c',
        "import sys,json;sys.path.insert(0,'scripts');from run_langgraph_flow import runtime_identity;print(json.dumps(runtime_identity()))"],cwd=ROOT,text=True,encoding='utf8'))
    write(out/'metadata.json',dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        prepared_sha256=sha(prepared),source_files=p['source_files'],models={v:data['configs'][v]['llm'] for v in 'AB'},
        environment=environment,monitoring_tools=read(ROOT/'.runtime/phase2/e10-deployment/psutil-tool.json'),
        hardware_at_start=snapshot(),resident_processes=residents(roots),resident_worker=worker,ui_port=7867,
        primary_schedule=data['schedule'],maximum_extra_observations=24,actual_new_retrieval_calls=0,
        latency_scope=data['plan']['latency_scope'],holdout_used=False))
    sampler=Sampler(pid,out/'resources.jsonl');hashes={};records=[];events=[]
    corpus={v['chunk_id']:v for v in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    engines={v:build(data['configs'][v],corpus,'e11_'+v) for v in 'AB'}
    counts={v:engines[v][0].chat_calls for v in 'AB'}
    def finish(status,**extra):
        check(p['source_files'])
        write(out/'completed.json',dict(status=status,primary_observations=sum(r['phase']=='primary' for r in records),
            total_observations=len(records),actual_model_calls=sum(engines[v][0].chat_calls-counts[v] for v in 'AB'),
            hashes=hashes,inputs_unchanged=True,full90_executed=False,holdout_used=False,**extra))
        print(json.dumps(dict(status=status,observations=len(records),**extra),ensure_ascii=False),flush=True)
    def invoke(item,c):
        assert listen(7867) and all(psutil.pid_exists(v) for v in roots)
        ops,flow=engines[item['variant']];ops.case=c;ops.trace=read(ROOT/c['source_trace']);ops.obs=[]
        before=sampler.begin(f"{item['phase']}-{item['case_id']}-{item['variant']}-r{item['repeat']}")
        result=flow.invoke(c['question']);resource=sampler.end(before)
        assert result['chat_calls']==len(ops.obs)==len(result['selection_audits'])<=2
        assert result['offered_ids']==c['offered_ids']
        for at in ops.obs:assert at['messages'][:len(c['messages'])]==c['messages'] and at['schema']==c['schema']
        if result['status']!='failed':assert safe_render(result['selected_ids'],corpus)==(result['answer'],result['citations'])
        return dict(**item,question_id=c['question_id'],question=c['question'],result=result,
            observations=dict(model_attempts=ops.obs),resources=resource,model_timing=timing(ops.obs),
            resident_processes=residents(roots),new_embedding_calls=0,new_reranker_calls=0)
    try:
        deadline=time.perf_counter()+wait_seconds
        while True:
            available=snapshot()['available_GiB'];events.append(dict(monotonic=time.perf_counter(),available_GiB=available))
            if available>=6.5:break
            if sampler.aborted or time.perf_counter()>=deadline:
                write(out/'startup_memory.json',dict(samples=events,threshold_GiB=6.5,passed=False))
                finish('STARTUP_MEMORY_NOT_READY',last_available_GiB=available);return
            if len(events)==1 or len(events)%6==0:print(json.dumps(dict(status='WAITING_FOR_STARTUP_MEMORY',available_GiB=available,threshold_GiB=6.5)),flush=True)
            time.sleep(min(5,max(0,deadline-time.perf_counter())))
        write(out/'startup_memory.json',dict(samples=events,threshold_GiB=6.5,passed=True))
        gates={v:normal_gates(*engines[v],data['configs'][v]) for v in 'AB'};write(out/'D036_zero_call.json',gates)
        def generic():
            before=sampler.begin('generic-B');start=time.perf_counter();error=None;response=None;ok=False
            try:
                response=generate(engines['B'][0].chat,[{'role':'system','content':'只输出一个JSON对象。'},{'role':'user','content':'返回ready为true。'}],
                    {'type':'object','properties':{'ready':{'const':True}},'required':['ready'],'additionalProperties':False})
                ok=json.loads(response['message']['content'])=={'ready':True}
            except Exception as exc:
                error=type(exc).__name__+': '+str(exc)
                if hasattr(exc,'response'):response=exc.response
            value=dict(response=response,error=error,protocol_pass=ok,seconds=time.perf_counter()-start,
                resources=sampler.end(before),excluded_from_quality=True,resident_processes=residents(roots))
            write(out/'generic_probe.json',value);return value
        def representative():
            c=p['representative'];row=invoke(dict(case_id=c['case_id'],variant='B',repeat=0,phase='representative'),c)
            row.update(protocol_pass=bool(row['result']['selection_audits']) and row['result']['selection_audits'][-1]['normalized_selection'] is not None,
                technical_complete=row['result']['status']!='failed',seconds=row['result']['wall_ns']/1e9,excluded_from_primary_36=True)
            write(out/'representative_probe.json',row);return row
        preflights=preflight_sequence(generic,representative);write(out/'preflight_summary.json',preflights)
        if preflights['status']!='PREFLIGHTS_PASSED':finish(preflights['status']);return
        print(json.dumps(dict(status='PREFLIGHTS_PASSED',starting_frozen_36=True)),flush=True)
        by={c['case_id']:c for c in data['cases']}
        def save_observation(item):
            row=invoke(item,by[item['case_id']]);row['score']=assess(row['result'],by[item['case_id']])
            name=f"{item['phase']}-{item['case_id']}-{item['variant']}-r{item['repeat']}.json"
            write(out/name,row);hashes[name]=sha(out/name);records.append(row)
            print(json.dumps(dict(done=len(records),**item,grade=row['score']['grade'],selected=row['result']['selected_ids'],
                seconds=row['result']['wall_ns']/1e9,resources=row['resources'],model_timing=row['model_timing']),ensure_ascii=False),flush=True)
            return memory_ok(row['resources']) and not sampler.aborted
        for item in data['schedule']:
            if not save_observation(item):finish('PILOT_RESOURCE_FAILED');return
        triggers=[]
        for key in [q+'-native' for q in ('D001','D002','D003','D012','D004','D009')]:
            a,b=(next(v for v in records if v['phase']=='primary' and v['case_id']==key and v['variant']==variant) for variant in 'AB')
            recovery=a['score']['grade']=='false_refusal' and b['score']['grade']=='correct'
            def cite(v):
                d=v['score']['citation_denominator'];return v['score']['citation_numerator']/d if d else 0
            regression=key in ('D004-native','D009-native') and a['score']['grade']=='correct' and (b['score']['grade']!='correct' or cite(b)<cite(a))
            if recovery or regression:triggers.append(dict(case_id=key,recovery=recovery,control_regression=regression))
        write(out/'retest_triggers.json',triggers)
        for trigger in triggers:
            for repeat,order in [(4,'AB'),(5,'BA')]:
                for variant in order:
                    if not save_observation(dict(case_id=trigger['case_id'],variant=variant,repeat=repeat,phase='confirmation')):
                        finish('PILOT_RESOURCE_FAILED');return
        finish('COMPLETED',quality_model_calls=sum(r['result']['chat_calls'] for r in records),probe_calls=1,
            representative_model_calls=preflights['representative']['result']['chat_calls'])
    finally:sampler.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','run']);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--prepared',type=Path);parser.add_argument('--server-pid',type=int);parser.add_argument('--ui-pid',type=int)
    parser.add_argument('--worker-ready',type=Path);parser.add_argument('--memory-wait-seconds',type=int,default=600);args=parser.parse_args()
    prepare(args.out) if args.mode=='prepare' else run(args.out,args.prepared,args.server_pid,args.ui_pid,args.worker_ready,args.memory_wait_seconds)
