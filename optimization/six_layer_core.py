"""Model-free six-layer diagnostics. Judgments and observations stay separate."""
from __future__ import annotations
import ast,hashlib,json,math,statistics,subprocess
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
POLICY=ROOT/'optimization/governance/policy.json'


def read(path):return json.loads(Path(path).read_text('utf-8-sig'))
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')
def digest(value):return hashlib.sha256(value).hexdigest()
def ref(path):
    path=Path(path).resolve();return dict(path=path.relative_to(ROOT).as_posix(),sha256=digest(path.read_bytes()),size_bytes=path.stat().st_size)
def local(path):
    result=(ROOT/path).resolve()
    if not result.is_relative_to(ROOT) or result==ROOT:raise ValueError('Expected a file inside project root')
    return result
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT).decode('utf8').strip()
def policy():return read(POLICY)
def write_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8',newline='\n') as stream:stream.write(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def ratio(n,d):return dict(numerator=n,denominator=d,value=n/d if d else None)
def ids(rows):return [r['chunk_id'] for r in rows]


def corpus_inventory(root=ROOT):
    cfg=read(root/'config/dense_index.json');path=root/'data/processed/rag_chunks_zh.jsonl'
    if not path.exists():return dict(available=False,integrity=None,reason='Private corpus is absent; not a passed data check')
    raw=path.read_bytes();rows=[json.loads(v) for v in raw.decode('utf8').splitlines()]
    if digest(raw)!=cfg['corpus_sha256']:raise ValueError('Corpus differs from frozen hash')
    if len(rows)!=cfg['expected_records'] or len({r['chunk_id'] for r in rows})!=len(rows):raise ValueError('Corpus count/IDs differ')
    bodies={};missing=[]
    for row in rows:
        if row['content_zh_sha256']!=digest(row['content_zh'].encode('utf8')):raise ValueError('Body hash differs: '+row['chunk_id'])
        if row['record_sha256']!=digest(canonical({k:v for k,v in row.items() if k!='record_sha256'})):raise ValueError('Record hash differs: '+row['chunk_id'])
        for key in ('source_url','source_lines','section_path','source_revision_id'):
            if not row.get(key):missing.append([row['chunk_id'],key])
        bodies.setdefault(row['content_zh_sha256'],[]).append(row['chunk_id'])
    lengths=[len(r['content_zh']) for r in rows]
    return dict(available=True,integrity=True,records=len(rows),missing_metadata=missing,
        body_characters=dict(minimum=min(lengths),median=statistics.median(lengths),mean=statistics.mean(lengths),maximum=max(lengths)),
        duplicate_body_groups=[v for v in bodies.values() if len(v)>1],
        expert_reviewed=sum(r.get('expert_reviewed') is True for r in rows),
        source_revision_verified=sum(r.get('source_revision_verified') is True for r in rows),
        authority='Frozen Wikipedia/AI translation; hash integrity is not expert or current-season verification')


def runtime_parameter_consistency(rerank,answer):
    """Check the active literal arguments, rather than reading an old config."""
    tree=ast.parse((ROOT/'scripts/reranker_live.py').read_text('utf8'))
    query=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='query')
    calls=[n for n in ast.walk(query) if isinstance(n,ast.Call)]
    literal=lambda n:ast.literal_eval(n)
    actual={}
    for call in calls:
        name=ast.unparse(call.func)
        if name in ('self.dense.query','self.bm25.query'):actual[name]=literal(call.args[1])
        elif name=='fuse':actual['rrf_k']=literal(call.args[1]);actual['fused_depth']=literal(call.args[2])
    expected={'self.dense.query':rerank['channel_top_k'],'self.bm25.query':rerank['channel_top_k'],
              'rrf_k':rerank['rrf_k'],'fused_depth':rerank['fused_top_k']}
    tree=ast.parse((ROOT/'scripts/task13_engine.py').read_text('utf8'))
    actual['method']=next(literal(n.args[1]) for n in ast.walk(tree) if isinstance(n,ast.Call) and ast.unparse(n.func)=='self.retriever.query')
    expected['method']=answer['retrieval_method']
    if canonical(actual)!=canonical(expected):raise ValueError('Active code and config disagree: '+str(actual))
    return dict(verified=True,active_arguments=actual)


def inventory(profile='low_memory_facts'):
    p=policy();dense=read(ROOT/'config/dense_index.json');rerank=read(ROOT/'config/reranker_experiment.json')
    answer=read(ROOT/'config/answer_evaluation.json');app=read(ROOT/'config/task13_audit.json')
    if profile not in p['profiles']:raise ValueError('Unknown deployment profile')
    return dict(version=p['version'],source_commit=git('rev-parse','HEAD'),entry='frontend/start_integrated_rag_audit.ps1',
        port=app['ui']['port'],orchestration='linear Worker; LangGraph is an independent entry',profile=profile,
        intended_environment=p['profiles'][profile],runtime_services='not probed or started',
        layers=p['layers'],data=corpus_inventory(),parameter_consistency=runtime_parameter_consistency(rerank,answer),
        retrieval=dict(model=dense['model'],embedding=dense['embedding'],channel_depth=rerank['channel_top_k'],fused_depth=rerank['fused_top_k'],rrf_k=rerank['rrf_k']),
        rerank=dict(model=rerank['model_id'],precision=rerank['precision'],budget=int(answer['retrieval_method'].removeprefix('top')),
                    output_top_k=rerank['output_top_k'],max_pair_tokens=rerank['max_length'],batch_size=rerank['batch_size'],threshold=None),
        context=dict(consideration_window=answer['max_context_chunks'],maximum_chunks=answer['max_context_chunks'],
            whole_message_utf8_budget=answer['input_utf8_byte_budget'],whole_chunks_only=True,automatic_conflict_resolution=False),
        generation=dict(model=answer['llm'],max_selected=answer['max_selected_chunks'],max_calls=answer['max_generation_attempts'],rendering='original paragraphs'),
        independent_components=dict(langgraph='scripts/rag_langgraph.py (independent entry)',parent_child='experiment only',faiss='experiment only',exact_cache='independent entry',semantic_cache='not enabled by default'),
        not_present=['SQL/API task agents in default workflow','graded-relevance nDCG labels','unseen final acceptance set',
                     'structured rewrite-model call counts in legacy traces','incremental document ingestion in default entry'],
        datasets=p['datasets'],acceptance=p['acceptance'])


def snapshot(profile='low_memory_facts'):
    inv=inventory(profile);p=policy()
    names={n for n in git('ls-files','scripts','config','infra','optimization').splitlines() if not n.startswith(('optimization/reports/','optimization/baseline/'))}
    names.update(['optimization/governance/policy.json','optimization/six_layer_core.py','optimization/rag_diagnostics.py',
        'optimization/datasets/freeze_manifest.json'])
    frozen=read(ROOT/'optimization/datasets/freeze_manifest.json')
    names.update('optimization/'+r['path'] for r in frozen['files'])
    for key in ('dense_index','bm25_index'):
        names.add(read(ROOT/'config/task13_app.json')[key]+'/index_manifest.json')
    untracked={n:ref(local(n)) for n in git('ls-files','--others','--exclude-standard','scripts','config','infra','optimization').splitlines()
               if local(n).is_file() and Path(n).suffix in ('.py','.json','.txt','.tsv') and not n.startswith('optimization/reports/')}
    return dict(version='six-layer-snapshot-1',source_commit=inv['source_commit'],profile=profile,
        intended_environment=inv['intended_environment'],files={n:ref(local(n)) for n in sorted(names) if local(n).is_file()},
        untracked_source_observations=untracked,inventory=inv,dataset_usage=p['datasets'],services_started=False,new_model_calls=0)


def normalize(wrapper):
    r=wrapper.get('result',wrapper)
    if not isinstance(r,dict):return None
    if 'question' in r and 'timing' in r:return r
    obs=wrapper.get('observations')
    if not isinstance(obs,dict):raise ValueError('Unsupported/incomplete trace: Graph requires archived observations')
    evidence={e['chunk_id']:e for e in obs.get('evidence',[])}
    attempts=obs.get('model_attempts',[])
    return dict(r,question=wrapper['question'],error=r.get('error_kind'),refusal_reason=r.get('reason'),
        context=[evidence[c] for c in r['offered_ids']],messages=attempts[0]['messages'] if attempts else [],attempts=attempts,
        retrieval=dict(channels=obs.get('channels',{}),before=obs.get('fused',[]),method='top40',
            results=[dict(chunk_id=c,rank=i) for i,c in enumerate(r['retrieved_ids'],1)],reranker=None) if obs.get('channels') else None,
        timing={},_adapter='archived_graph_observations')


def diagnose(wrapper,label=None,review=None,*,cfg=None,original_question=None,known_ids=None):
    cfg=cfg or read(ROOT/'config/answer_evaluation.json');limits=policy()['limits'];r=normalize(wrapper)
    findings=[]
    def finding(layer,code,severity='error',**detail):findings.append(dict(layer=layer,code=code,severity=severity,**detail))
    if r is None:
        finding('engineering','missing_result')
        r=dict(question=wrapper.get('question',(label or {}).get('question','')),error=wrapper.get('error') or 'Missing result',
               status='operational_error',retrieved_ids=[],offered_ids=[],selected_ids=[],attempts=[],timing={})
    retrieval=r.get('retrieval') or {};channels=retrieval.get('channels',{})
    stages={name:ids(channels.get(name,[])) for name in ('dense','bm25')}
    stages['union']=list(dict.fromkeys(stages['dense']+stages['bm25']))
    stages.update(fused=ids(retrieval.get('before',[])),rerank_input=ids(retrieval.get('before',[]))[:40],
        reranked=r.get('retrieved_ids',[]),prompt=r.get('offered_ids',[]),selected=r.get('selected_ids',[]))
    expected=(label or {}).get('expected_chunk_ids',[]);grade=(review or {}).get('grade')
    answerable=(label or {}).get('answerable');resolution=r.get('query_resolution')
    original=original_question or wrapper.get('question')
    if original is None and not resolution:original=r.get('question')
    if original is not None and resolution and digest(original.encode('utf8'))!=resolution['original_question_sha256']:
        finding('engineering','original_question_hash_mismatch')
    if resolution and resolution.get('outcome')=='fallback':finding('retrieval','history_rewrite_fallback','warning')
    operational=bool(r.get('error') or wrapper.get('error') or grade=='runtime_error')
    if operational:finding('engineering','operational_failure',detail=r.get('error') or wrapper.get('error'))
    if not set(stages['selected'])<=set(stages['prompt']):finding('generation','unoffered_selection')
    if len(r.get('attempts',[]))>limits['maximum_answer_calls']:finding('engineering','answer_call_budget_exceeded')
    attempts=r.get('attempts',[]);repaired=sum(bool(a.get('error')) for a in attempts)
    if repaired:finding('generation','schema_repair','warning',failed_attempts=repaired)
    if known_ids is not None and expected and not set(expected)<=set(known_ids) and grade!='correct':
        finding('data','annotated_source_absent_from_corpus',missing_ids=sorted(set(expected)-set(known_ids)))
    if not operational and label is not None and expected and grade not in ('correct','correct_refusal','runtime_error'):
        missing=[cid for cid in expected if cid not in stages['prompt']]
        if missing:
            if any(cid not in stages['union'] for cid in missing):layer,code='retrieval','annotated_candidate_missing'
            elif any(cid not in stages['rerank_input'] for cid in missing):layer,code='rerank','rerank_candidate_window'
            elif any(cid not in stages['reranked'] for cid in missing):layer,code='rerank','rerank_output_cutoff'
            else:
                layer='context';window=stages['reranked'][:cfg['max_context_chunks']]
                code='packing_window_loss' if any(cid not in window for cid in missing) else 'packing_budget_loss'
            # Annotated IDs are a diagnostic proxy, not exhaustive semantic relevance.
            finding(layer,code,'error' if review is not None else 'hypothesis',missing_annotated_ids=missing)
        elif review is not None and answerable is True:
            if r.get('status')=='refused':finding('generation','false_refusal_with_evidence')
            elif grade=='partial':finding('generation','evidence_coverage_incomplete')
            elif grade!='correct':finding('generation','wrong_evidence_selection')
    elif not operational and review is not None and answerable is False and r.get('status')=='answered':finding('generation','refusal_contract')
    unsupported=None
    if review is not None and not operational:
        supported=review.get('supported_citation_ids',[])
        if not set(supported)<=set(stages['selected']):raise ValueError('Review credits unselected citation')
        unsupported=[cid for cid in stages['selected'] if cid not in supported]
        if unsupported:finding('generation','unsupported_citations',chunk_ids=unsupported)
    resources=wrapper.get('resources') or {};wall=wrapper.get('seconds');available=resources.get('available_min_GiB')
    events=wrapper.get('stage_events',resources.get('stage_events',[]));event_map={e['stage']:e for e in events}
    memory_values=[v for v in (available,wrapper.get('combined_available_min_GiB')) if v is not None]
    memory_values += [e['memory']['available']/2**30 for e in events if 'available' in e.get('memory',{})]
    available=min(memory_values) if memory_values else None
    phases={}
    for name,a,b in [('worker','worker_enter','worker_return'),('imports','module_import_start','module_import_end'),
                     ('retrieval_dependencies','lazy_retrieval_construction_start','lazy_retrieval_construction_end'),
                     ('packing_and_preparation','retrieval_query_end','context_packed'),
                     ('answer_request','answer_model_start','answer_model_end'),
                     ('worker_validation','result_validation_start','result_validation_end'),
                     ('parent_validation','parent_validation_start','parent_validation_end')]:
        if a in event_map and b in event_map:phases[name]=event_map[b]['monotonic']-event_map[a]['monotonic']
    if wall is not None and wall>limits['wall_seconds']:finding('engineering','wall_time_exceeded',seconds=wall)
    if available is not None and available<limits['available_memory_GiB']:finding('engineering','memory_below_limit',available_GiB=available)
    if resources.get('resource_abort'):finding('engineering','resource_abort')
    rr=(retrieval.get('reranker') or {}).get('results',[])
    trunc=[dict(chunk_id=v['chunk_id'],original_tokens=v['original_tokens'],used_tokens=v['used_tokens'],truncated_tokens=v['truncated_tokens']) for v in rr if v.get('truncated_tokens',0)>0]
    if trunc:finding('rerank','pair_input_truncated','observation',pairs=trunc)
    errors=[f for f in findings if f['severity']=='error']
    primary=min(errors,key=lambda f:policy()['layers'][f['layer']]['order'])['layer'] if errors else None
    # Operational failures never become semantic refusals or failed retrieval metrics.
    if any(f['code'] in ('operational_failure','resource_abort','missing_result','original_question_hash_mismatch') for f in errors):primary='engineering'
    return dict(question_id=(label or {}).get('question_id',wrapper.get('question_id',wrapper.get('name'))),
        trace_id=r.get('trace_id',r.get('request_id')),adapter=r.get('_adapter','worker'),primary_layer=primary,findings=findings,
        semantic_review='unavailable_due_operational_failure' if operational else 'reviewed' if review is not None else 'pending',grade=grade,answerable=answerable,
        annotated_expected_ids=expected,stages=stages,unsupported_citation_ids=unsupported,
        query=dict(original_sha256=digest(original.encode('utf8')) if original is not None else (resolution or {}).get('original_question_sha256'),
            original_text_available=original is not None,effective_sha256=digest(r['question'].encode('utf8')),actual_retrieval_query=retrieval.get('query'),resolution=resolution),
        session=dict(conversation_sha256=(wrapper.get('event') or {}).get('conversation_sha256'),history_turns=(resolution or {}).get('history_turns',0),isolation_verified=None),
        prompt=dict(sha256=digest(canonical(r.get('messages',[]))),utf8_bytes=len(canonical(r.get('messages',[]))),offered_count=len(stages['prompt'])),
        packing_omissions=[dict(chunk_id=c,rerank_position=i,reason='outside_examined_window' if i>cfg['max_context_chunks'] else 'inferred_budget_skip')
                           for i,c in enumerate(stages['reranked'],1) if c not in stages['prompt']],
        performance=dict(engine_seconds=r.get('timing',{}).get('total_seconds'),wall_seconds=wall,minimum_available_GiB=available,
            answer_calls=len(attempts),total_model_calls=None if resolution else len(attempts),repair_attempts=repaired,resource_observed=available is not None,
            observed_phases_seconds=phases,phases_overlap=True,retrieval_timing=retrieval.get('timing')),
        model_output=[dict(raw_sha256=digest(canonical(a.get('response'))),parsed=a.get('parsed'),error=a.get('error')) for a in attempts])


def retrieval_metrics(cases,stage,k):
    rows=[r for r in cases if r.get('answerable') is True and r.get('annotated_expected_ids')]
    ranks=[];hit=gold=returned=all_hit=any_hit=0
    for row in rows:
        expected=set(row['annotated_expected_ids']);actual=row['stages'][stage][:k];matched=expected&set(actual)
        hit+=len(matched);gold+=len(expected);returned+=len(actual);any_hit+=bool(matched);all_hit+=expected<=set(actual)
        first=next((i for i,c in enumerate(actual,1) if c in expected),None);ranks.append(1/first if first else 0)
    return dict(stage=stage,k=k,questions=len(rows),annotated_any_hit=ratio(any_hit,len(rows)),annotated_all_hit=ratio(all_hit,len(rows)),
        annotated_recall_micro=ratio(hit,gold),annotated_precision_proxy=ratio(hit,returned),MRR=sum(ranks)/len(rows) if rows else None,
        graded_nDCG=None,reason='No graded relevance labels; unannotated equivalent support is not necessarily irrelevant')


def check_plan(plan,baseline,current=None):
    p=policy();problems=[];change=plan.get('variable',{})
    if plan.get('baseline_snapshot_sha256')!=digest(canonical(baseline)):problems.append('baseline_snapshot_identity')
    layer=plan.get('layer')
    if layer not in p['layers']:problems.append('unknown_layer')
    if not isinstance(change,dict):problems.append('unregistered_single_variable');change={}
    if set(change)!={'name','before','after'} or change.get('name') not in p['layers'].get(layer,{}).get('experiment_variables',[]):problems.append('unregistered_single_variable')
    if change.get('before')==change.get('after'):problems.append('no_variable_change')
    if 'changes' in plan or 'variables' in plan:problems.append('multiple_or_ambiguous_variable_declaration')
    for key in ('hypothesis','development_dataset','metrics','thresholds','stop_conditions'):
        if not plan.get(key):problems.append('missing_'+key)
    if not isinstance(plan.get('metrics'),list) or not isinstance(plan.get('thresholds'),dict) or not isinstance(plan.get('stop_conditions'),list):problems.append('invalid_preregistration_types')
    thresholds=plan.get('thresholds') if isinstance(plan.get('thresholds'),dict) else {}
    special=thresholds.get('special') or {}
    if not isinstance(special,dict) or any(type(special.get(k)) is not int or special[k]<1 for k in ('independent_questions','paired_repeats')) or not special.get('pass_conditions'):problems.append('special_counts_and_pass_conditions_required')
    resources=thresholds.get('resources',{})
    if not isinstance(resources,dict) or resources.get('max_wall_seconds',float('inf'))>p['limits']['wall_seconds'] or resources.get('min_available_GiB',0)<p['limits']['available_memory_GiB']:problems.append('resource_gate_missing_or_weakened')
    registry={d['id']:d for d in p['datasets']}
    dataset=registry.get(plan.get('development_dataset'))
    if dataset is None or dataset['role']!='development':problems.append('development_data_not_registered_as_development')
    for dataset_id in plan.get('unseen_datasets',[]):
        item=registry.get(dataset_id)
        if item is None or not item.get('unseen'):problems.append('unseen_data_not_available:'+str(dataset_id))
        elif local(item['path']).exists():
            exposed={r['sha256'] for r in read(ROOT/'optimization/datasets/freeze_manifest.json')['files']}
            if digest(local(item['path']).read_bytes()) in exposed:problems.append('exposed_data_renamed_as_unseen:'+dataset_id)
    if plan.get('merge') is not False:problems.append('merge_must_be_explicitly_false')
    allowed=plan.get('allowed_files',[])
    if not isinstance(allowed,list):problems.append('invalid_allowed_files');allowed=[]
    if not allowed:problems.append('missing_allowed_files')
    for name in allowed:
        if not isinstance(name,str):problems.append('invalid_allowed_file');continue
        try:local(name)
        except (ValueError,OSError):problems.append('invalid_allowed_file')
        if name.startswith(('data/','optimization/datasets/')):problems.append('cannot_tune_frozen_data')
    if current is not None:
        changed={n for n,r in baseline['files'].items() if current['files'].get(n)!=r}
        added=set(current['files'])-set(baseline['files']);unplanned=(changed|added)-set(allowed)
        if unplanned:problems.append('undeclared_file_changes:'+','.join(sorted(unplanned)))
        if current['intended_environment']!=baseline['intended_environment']:problems.append('profile_changed_outside_single_variable')
        old=baseline.get('untracked_source_observations',{});new=current.get('untracked_source_observations',{})
        if any(n not in allowed and old.get(n)!=new.get(n) for n in set(old)|set(new)):problems.append('undeclared_untracked_source_changes')
    return dict(valid=not problems,violations=problems,services_started=False,new_model_calls=0,
        final_acceptance='blocked until a genuinely unseen final set is registered',
        scope='Protocol preflight only; it does not run or approve the quality of an experiment')
