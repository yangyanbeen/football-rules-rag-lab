"""Additive Task13 integrity, retry, source and reproducibility repairs."""
import copy,subprocess,time,io,tarfile
from task13_core import *

CONFIG='config/task13_audit.json'
SOURCE_FILES=('scripts/task13_audit.py','scripts/query_task13_audit.py','scripts/task13_audit_client.py',
    'scripts/task13_audit_pipeline.py','scripts/run_integrated_rag_audit.py','scripts/prepare_task13_environment_checked.py',
    'scripts/export_task13_citation_sources.py','config/task13_audit.json','data/manifests/task13_citation_sources.json')
PUBLIC_FIELDS={'trace_id','question','profile','status','selected_ids','offered_ids','retrieved_ids','refusal_reason','error','answer_sha256','citations','configuration','indexes','timing','prompt_utf8_bytes','attempts','private_trace','new_formal_test_runs'}


def exact(v,keys,name):
    if not isinstance(v,dict) or set(v)!=set(keys):raise ValueError('Unexpected '+name+' fields')


def audit_config():
    base=app_config();v=read(ROOT/CONFIG)
    if type(base['ui']['share']) is not bool or type(base['ui']['port']) is not int:raise ValueError('Boolean/integer UI policy types differ')
    expected={'version':'task13-audit-1.1','base_config':'config/task13_app.json','corpus':base['corpus'],'citation_sources':'data/manifests/task13_citation_sources.json','environment':base['environment'],'private_root':'.runtime/task13-audit','ui':{'host':'127.0.0.1','port':7867,'share':False,'app_data':'.runtime/task13/audit/kotaemon'},'worker_timeout_seconds':420,'scope':v.get('scope')}
    if canonical(v)!=canonical(expected) or not isinstance(v['scope'],str) or not v['scope']:raise ValueError('Changed audit profile or types')
    return v


def ui_config():
    v=copy.deepcopy(app_config());a=audit_config();v['ui']=a['ui'];return v


def implementation():
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    sources={p:record(ROOT/p) for p in SOURCE_FILES}
    for p,r in sources.items():
        if digest(subprocess.check_output(['git','show',commit+':'+p],cwd=ROOT))!=r['sha256']:raise ValueError('Commit revised runtime before use: '+p)
    return {'version':audit_config()['version'],'source_commit':commit,'sources':sources,'base_package':record(ROOT/'reports/task13/delivery_manifest.json')}


def validate_implementation(v):
    exact(v,('version','source_commit','sources','base_package'),'implementation')
    if v['version']!=audit_config()['version'] or set(v['sources'])!=set(SOURCE_FILES) or v['base_package']!=record(ROOT/'reports/task13/delivery_manifest.json'):raise ValueError('Implementation profile differs')
    if not re.fullmatch('[a-f0-9]{40}',v['source_commit']) or subprocess.run(['git','merge-base','--is-ancestor',v['source_commit'],'HEAD'],cwd=ROOT,capture_output=True).returncode:raise ValueError('Invalid implementation producer')
    for p,r in v['sources'].items():
        if r!=record(ROOT/p) or digest(subprocess.check_output(['git','show',v['source_commit']+':'+p],cwd=ROOT))!=r['sha256']:raise ValueError('Implementation source differs')
    return True


def source_map():
    v=read(ROOT/audit_config()['citation_sources']);known=read(ROOT/'data/manifests/dense_chunk_ids.json')
    if v['version']!='task13-citation-sources-1.0' or v['records']!=99 or set(v['sources'])!={r['chunk_id'] for r in known} or v['corpus']!=read(ROOT/'reports/task13/delivery_manifest.json')['private_data']['corpus'] or v['generator']!=record(ROOT/'scripts/export_task13_citation_sources.py'):raise ValueError('Citation source table differs')
    for r in known:
        c=v['sources'][r['chunk_id']]
        if c['chunk_id']!=r['chunk_id'] or c['record_sha256']!=r['record_sha256'] or not c['content_zh_sha256']==c['quote_sha256']==r['content_zh_sha256']:raise ValueError('Source table hash differs')
    return v['sources']


def validate_public(v,revised=False):
    exact(v,PUBLIC_FIELDS|({'implementation'} if revised else set()),'public result')
    known=source_map()
    cfg=app_config();from task13_replay import file_ref
    if normalize_question(v['question'])!=v['question'] or v['profile']!=cfg['version'] or v['configuration']!=source_identity():raise ValueError('Public query/configuration differs')
    indexes={k:read(ROOT/'reports/task13/index-rebuild.json')[k] for k in ('dense_index','bm25_index')}
    if v['indexes']!=indexes or not re.fullmatch('[a-f0-9]{32}',v['trace_id']) or not re.fullmatch('[a-f0-9]{64}',v['answer_sha256']):raise ValueError('Public trace/index identity differs')
    file_ref(v['private_trace'],'.runtime/task13-audit/workers' if revised else '.runtime/task13/workers')
    for key,limit in (('retrieved_ids',10),('offered_ids',5),('selected_ids',3)):
        ids=v[key]
        if not isinstance(ids,list) or any(not isinstance(cid,str) or cid not in known for cid in ids) or len(set(ids))!=len(ids) or len(ids)>limit:raise ValueError('Invalid public '+key)
    if not set(v['selected_ids'])<=set(v['offered_ids'])<=set(v['retrieved_ids']) or [c['chunk_id'] for c in v['citations']]!=v['selected_ids']:raise ValueError('Public source selection differs')
    if v['status'] not in ('answered','refused') or (v['status']=='answered')!=bool(v['selected_ids']) or v['error'] is not None:raise ValueError('Public successful request status differs')
    if (v['refusal_reason'] is None)!=(v['status']=='answered') or (v['status']=='refused' and not isinstance(v['refusal_reason'],str)):raise ValueError('Public refusal reason differs')
    if type(v['prompt_utf8_bytes']) is not int or not 0<=v['prompt_utf8_bytes']<=6200 or not isinstance(v['attempts'],list) or len(v['attempts'])>2:raise ValueError('Public budget differs')
    if not v['retrieved_ids']:
        if v['refusal_reason']!='version_unverified' or any(v[k] for k in ('attempts','offered_ids','selected_ids','prompt_utf8_bytes')):raise ValueError('Invalid zero-inference version refusal')
    elif not v['attempts']:raise ValueError('Public result missing actual generation')
    for i,a in enumerate(v['attempts']):
        exact(a,('attempt','error','prompt_eval_count','eval_count','done_reason'),'attempt')
        if type(a['attempt']) is not int or a['attempt']!=i+1:raise ValueError('Public attempt sequence differs')
        if a['error'] is not None:
            if i==len(v['attempts'])-1 or not isinstance(a['error'],str) or not a['error']:raise ValueError('Uncompleted final attempt')
        elif i!=len(v['attempts'])-1 or a['done_reason']!='stop' or type(a['eval_count']) is not int or not 0<a['eval_count']<=1024 or type(a['prompt_eval_count']) is not int or not 0<a['prompt_eval_count']<=6656:raise ValueError('Public model attempt differs')
    t=v['timing'];exact(t,('retrieval_seconds','generation_seconds','total_seconds'),'timing')
    if any(type(x) not in (int,float) or not math.isfinite(x) or x<0 for x in t.values()) or t['total_seconds']+.01<t['retrieval_seconds']+t['generation_seconds']:raise ValueError('Public clock differs')
    for c in v['citations']:
        if canonical(c)!=canonical(known[c['chunk_id']]):raise ValueError('Citation metadata differs from frozen source')
    if type(v['new_formal_test_runs']) is not int or v['new_formal_test_runs']!=0:raise ValueError('Formal test counter differs')
    if revised:validate_implementation(v['implementation'])
    return True


def validate_private(v,question,revised=False):
    validate_result(v,question)
    if revised:validate_implementation(v['implementation'])
    if v['offered_ids']!=[r['chunk_id'] for r in v['context']]:raise ValueError('Offered source order differs from actual prompt')
    if not v['error']:
        if v['refusal_reason']=='version_unverified' and not v['retrieval']:
            if any(v[k] for k in ('context','messages','attempts','retrieved_ids','offered_ids','selected_ids','prompt_utf8_bytes')):raise ValueError('Version refusal contains inference')
        elif not v['attempts'] and v['refusal_reason']!='no_whole_evidence_within_budget':raise ValueError('Successful request missing actual generation')
    known=source_map()
    if any(canonical(c)!=canonical(known[c['chunk_id']]) for c in v['citations']):raise ValueError('Private source metadata differs')
    return True


def public_projection(v,path):
    validate_private(v,v['question'],True);p=public_result(v,path);p['implementation']=v['implementation'];validate_public(p,True);return p


def request_json(chat,messages,cfg,parser,schema):
    from answer_json_chat import generate
    attempts=[];last=None
    for i in range(cfg['max_generation_attempts']):
        current=messages if not i else messages+[{'role':'user','content':'上次输出格式无效。重新按规定只输出一个JSON对象，不加说明；不要改变原始证据。'}]
        if len(canonical(current))>cfg['input_utf8_byte_budget']:break
        a={'attempt':i+1,'messages':current,'format':schema,'response':None,'error':None,'prompt_eval_count':None,'eval_count':None,'done_reason':None};started=time.perf_counter();stop=False
        try:
            response=generate(chat,current,schema);a['response']=response
            for k in ('prompt_eval_count','eval_count','done_reason'):a[k]=response[k]
            parsed=parser(response['message']['content']);a['parsed']=parsed
            return parsed,attempts+[a],None
        except (ValueError,KeyError,TypeError,OSError,RuntimeError,TimeoutError) as exc:
            a['error']=type(exc).__name__+': '+str(exc);last=a['error']
            if hasattr(exc,'response'):a['response']=exc.response
            stop=getattr(exc,'retryable',True) is False or isinstance(exc,(OSError,RuntimeError,TimeoutError))
        finally:a['seconds']=time.perf_counter()-started
        attempts.append(a)
        if stop:break
    return None,attempts,last or 'No repair fits prompt budget'


def verify_package(v,private=False):
    from task13_package import FIXED,RECEIPTS
    exact(v,('version','created_at','source_commit','public_members','receipts','private_data','models','upstream_commit','policy'),'package')
    if v['version']!='task13-runtime-package-1.0' or not re.fullmatch('[a-f0-9]{40}',v['source_commit']) or subprocess.run(['git','merge-base','--is-ancestor',v['source_commit'],'HEAD'],cwd=ROOT,capture_output=True).returncode:raise ValueError('Unknown package producer/version')
    for r in v['public_members']+v['receipts']:
        from task13_replay import file_ref
        file_ref(r)
        if r['path'].startswith(('.runtime/','.models/','data/processed/','data/indexes/')):raise ValueError('Private data in public package')
    names=[r['path'] for r in v['public_members']+v['receipts']]
    if len(set(names))!=len(names):raise ValueError('Duplicate package member')
    with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive','--format=tar',v['source_commit']],cwd=ROOT))) as arc:
        producer={m.name:arc.extractfile(m).read() for m in arc.getmembers() if m.isfile()}
    expected=set(FIXED)|{n for n in producer if len(Path(n).parts)==2 and Path(n).parts[0] in ('scripts','config') and Path(n).suffix in ('.py','.ps1','.json','.txt')}
    if {r['path'] for r in v['public_members']}!=expected:raise ValueError('Incomplete runtime package members')
    if v['upstream_commit']!='9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9':raise ValueError('Package upstream differs')
    for r in v['public_members']+v['receipts']:
        if record(ROOT/r['path'])!=r:raise ValueError('Package member hash differs')
        if r in v['public_members'] and digest(producer[r['path']])!=r['sha256']:raise ValueError('Package member producer differs')
    if {r['path'] for r in v['receipts']}!={'reports/task13/'+n for n in RECEIPTS}:raise ValueError('Missing completed receipts')
    for n in RECEIPTS:
        if read(ROOT/'reports/task13'/n)['status']!='PASS':raise ValueError('Uncompleted receipt in package')
    cfg=app_config();inventory=read(ROOT/'data/manifests/local_data_files.json')
    corpus=next({k:r[k] for k in ('path','size_bytes','sha256')} for r in inventory['files'] if r['path']==cfg['corpus'])
    exact(v['private_data'],('corpus','inventory','indexes'),'private data references')
    if v['private_data']['corpus']!=corpus or v['private_data']['inventory']!=record(ROOT/'data/manifests/local_data_files.json') or v['private_data']['indexes']!={k:read(ROOT/'reports/task13/index-rebuild.json')[k] for k in ('dense_index','bm25_index')}:raise ValueError('Package data versions differ')
    models={'answer':answer_config()['llm'],'embedding':read(ROOT/'config/dense_index.json')['model'],'reranker':{k:read(ROOT/'config/reranker_experiment.json')[k] for k in ('model_id','revision','files','provider','threads')}}
    if canonical(v['models'])!=canonical(models):raise ValueError('Package model versions differ')
    if private:
        for r in (v['private_data']['inventory'],v['private_data']['corpus'],*v['private_data']['indexes'].values()):
            if record(ROOT/r['path'])!=r:raise ValueError('Private package reference differs')
    return True


def upstream_clean():
    p=ROOT/'third_party/kotaemon-v0.12.0'
    if subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'],text=True).strip()!='9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9' or subprocess.check_output(['git','-C',str(p),'status','--porcelain','--untracked-files=normal'],text=True).strip():raise ValueError('Fixed editable upstream contains uncommitted changes')
    return True


def panel(v):
    text=render_panel(v)
    for c in v['citations']:
        text+='<p><a target="_blank" rel="noopener noreferrer" href="'+html.escape(c['license_url'],quote=True)+'">'+html.escape(c['source_attribution']+' · '+c['license'])+'</a></p>'
    return text
