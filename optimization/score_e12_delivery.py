"""Separate historical quality, functional checks and real browser load outcomes."""
import argparse,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def lines(p):return [json.loads(v) for v in p.read_text('utf8').splitlines() if v.strip()]
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
def main(run,out,functional_run=None,load4_run=None):
    done=read(run/'browser-completed.json')
    for name,h in done['hashes'].items():assert sha(run/name)==h
    meta=read(run/'browser-metadata.json')
    for n,r in meta['source_files'].items():
        p=ROOT/n;assert sha(p)==r['sha256'] and p.stat().st_size==r['size_bytes'],n
    rows=[read(run/name) for name in done['hashes']]
    additional_events=[]
    additional_resources=[]
    if load4_run:
        extra_done=read(load4_run/'browser-completed.json')
        extra_meta=read(load4_run/'browser-metadata.json')
        for name,h in extra_done['hashes'].items():assert sha(load4_run/name)==h
        for n,r in extra_meta['source_files'].items():
            p=ROOT/n;assert sha(p)==r['sha256'] and p.stat().st_size==r['size_bytes'],n
        rows=[r for r in rows if not r['name'].startswith('load-c4-')]
        rows.extend(read(load4_run/name) for name in extra_done['hashes'])
        additional_events=lines(load4_run/'worker-events.jsonl')
        additional_resources=lines(load4_run/'resources.jsonl')
    functional_run=functional_run or run
    initial_done=read(functional_run/'browser-completed.json')
    initial_meta=read(functional_run/'browser-metadata.json')
    for name,h in initial_done['hashes'].items():assert sha(functional_run/name)==h
    for n,r in initial_meta['source_files'].items():
        p=ROOT/n;assert sha(p)==r['sha256'] and p.stat().st_size==r['size_bytes'],n
    initial_rows=[read(functional_run/name) for name in initial_done['hashes']]
    if functional_run!=run:rows.extend(r for r in initial_rows if r['phase']=='functional')
    by={r['name']:r for r in rows}
    d036=[read(functional_run/n) for n in ('d036-browser.json','d036-browser-r2.json') if (functional_run/n).exists()]
    ordinary=by.get('ordinary',{});sources=by.get('sources',{});topic=by.get('topic_switch',{})
    empty=by.get('isolation_empty',{});first=by.get('parameters_explicit',{});follow=by.get('parameters_followup',{})
    def traced(r):return r.get('trace',{})
    functional=dict(
        D036_normal_browser_and_worker=bool(d036) and all(v['passed'] and v['retrieval_query_calls']==v['answer_model_calls']==0 for v in d036),
        ordinary_answer=ordinary.get('status')=='answered' and 'L03-01' in ordinary.get('selected_ids',[]),
        visible_source_links=any('wikipedia.org' in s for s in ordinary.get('visible_source_links',[])),
        source_presentation=sources.get('event',{}).get('route')=='previous_answer' and sources.get('selected_ids')==ordinary.get('selected_ids') and sources.get('answer_attempts')==0,
        topic_switch=topic.get('status')=='answered' and 'L02-01' in topic.get('selected_ids',[]) and topic.get('query_resolution',{}).get('outcome')=='unchanged' and topic.get('effective_query')==topic.get('question') and topic.get('conversation_sha256')==ordinary.get('conversation_sha256'),
        empty_new_conversation=empty.get('status')=='no_previous_evidence' and not empty.get('selected_ids') and empty.get('conversation_sha256')!=ordinary.get('conversation_sha256'),
        explicit_parameters_enter_retrieval=traced(first).get('retrieval') is not None and traced(first).get('business_decision') is None,
        history_parameters_carried=traced(follow).get('retrieval') is not None and traced(follow).get('business_decision') is None and '中超' in follow.get('effective_query','') and '2025' in follow.get('effective_query','') and follow.get('query_resolution',{}).get('history_turns')==1,
        all_load_conversations_history_free=all(r.get('trace') is None or 'query_resolution' not in r['trace'] for r in rows if r['phase']=='load'))
    all_events=lines(run/'worker-events.jsonl')+additional_events
    entries={e['request_id']:e for e in all_events if e['kind']=='worker_enter'}
    functional['all_load_conversations_history_free']=all(
        r.get('worker_request_id') in entries and not entries[r['worker_request_id']]['history_supplied']
        for r in rows if r['phase']=='load')
    plan=read(ROOT/'optimization/experiments/E12_delivery/plan.json')
    support_cases={c['id']:c for c in plan['load_requests']}
    def render_unverified(r):return 'answer rendered' in r.get('runtime_error','')
    def deadline_timeout(r):return bool(r.get('client_timeout') and not render_unverified(r))
    def semantic(r):
        if r.get('semantic_score'):return r['semantic_score']
        if not r.get('trace'):return None
        case=support_cases[r['name'].rsplit('-',1)[-1]]
        ids=r['trace']['selected_ids'];mask=[bool(set(ids)&set(v)) for v in case['support_per_point']]
        sup={cid for v in case['support_per_point'] for cid in v}
        return dict(grade='false_refusal' if r['trace']['status']=='refused' else 'correct' if all(mask) else 'partial' if any(mask) else 'incorrect',
            point_mask=mask,citation_numerator=sum(cid in sup for cid in ids),citation_denominator=len(ids),
            derived_from_validated_backend_trace=True)
    def derived_queue(r):
        if r.get('queue_timing'):return r['queue_timing']
        qh=hashlib.sha256(r['question'].encode()).hexdigest()
        starts=[e for e in all_events if e['kind']=='worker_enter' and e.get('question_sha256')==qh and e['wall_ns']>=r['submitted_ns']]
        if not starts:return None
        start=min(starts,key=lambda v:v['wall_ns']);events={e['kind']:e for e in all_events if e['request_id']==start['request_id']}
        if 'lock_acquired' in events:
            result=dict(worker_lock_wait_seconds=(events['lock_acquired']['wall_ns']-events['lock_wait']['wall_ns'])/1e9,
                worker_service_completed='worker_return' in events,derived_from_post_run_observer=True)
            result['frontend_dispatch_seconds']=(start['wall_ns']-r['submitted_ns'])/1e9
            if 'lock_released' in events:
                result['worker_locked_service_seconds']=(events['lock_released']['wall_ns']-events['lock_acquired']['wall_ns'])/1e9
            if 'worker_return' in events:result['backend_returned_ns']=events['worker_return']['wall_ns']
            return result
        if 'lock_wait' in events:return dict(worker_lock_wait_lower_bound_seconds=(r['completed_ns']-events['lock_wait']['wall_ns'])/1e9,worker_service_completed=False)
    loads={}
    for level in (1,2,4):
        rr=[r for r in rows if r['phase']=='load' and r['name'].startswith('load-c'+str(level)+'-')]
        records=[]
        for r in rr:
            records.append(dict(name=r['name'],question=r['question'],seconds=r['seconds'],status=r.get('status'),
                technical_complete=r['technical_complete'],client_timeout=deadline_timeout(r),error=r.get('runtime_error'),
                raw_timeout_flag=r['client_timeout'],render_verification_timeout=render_unverified(r),
                backend_completed=bool(r.get('trace') and r['trace']['error'] is None),
                visible_reply_seconds=r['seconds'] if r['technical_complete'] else None,
                observation_end_seconds=r['seconds'],queue_timing=derived_queue(r),selected_ids=r.get('selected_ids'),semantic_score=semantic(r),
                available_min_GiB=r['resources']['available_min_GiB'],rss_peak_GiB=r['resources']['process_rss_peak_GiB']))
            if r.get('worker_request_id'):
                returned=next((e for e in all_events if e['request_id']==r['worker_request_id'] and e['kind']=='worker_return'),None)
                if returned:records[-1]['backend_return_seconds']=(returned['wall_ns']-r['submitted_ns'])/1e9
            if r.get('trace') and r.get('queue_timing'):
                timing=r['trace']['timing'];records[-1]['stage_timing']=dict(timing,
                    outside_answer_locked_seconds=max(0,r['queue_timing']['worker_locked_service_seconds']-timing['total_seconds']),
                    model_loading_seconds=sum(at.get('response',{}).get('load_duration',0) for at in r['trace']['attempts'])/1e9)
        counts=dict(completed_observations=len(rr),technical_complete=sum(r['technical_complete'] for r in rr),
            backend_completed=sum(bool(r.get('trace') and r['trace']['error'] is None) for r in rr),
            client_timeouts=sum(deadline_timeout(r) for r in rr),render_verification_timeouts=sum(render_unverified(r) for r in rr),
            operational_or_automation_errors=sum(not r['technical_complete'] and not deadline_timeout(r) and not render_unverified(r) for r in rr))
        gates=dict(four_observations=len(rr)==4,all_technical=len(rr)==4 and all(r['technical_complete'] and not r['client_timeout'] for r in rr),
            every_latency_at_most_60=len(rr)==4 and all(r['seconds']<=60 for r in rr),
            available_at_least_1GiB=len(rr)==4 and all(r['resources']['available_min_GiB'] is not None and r['resources']['available_min_GiB']>=1 for r in rr))
        num=sum((semantic(r) or {}).get('citation_numerator',0) for r in rr)
        den=sum((semantic(r) or {}).get('citation_denominator',0) for r in rr)
        loads[str(level)]=dict(counts=counts,gates=gates,passed=all(gates.values()),
            per_request=records,max_seconds=max([r['seconds'] for r in rr] or [0]),
            min_available_GiB=min([r['resources']['available_min_GiB'] for r in rr if r['resources']['available_min_GiB'] is not None] or [0]),
            full_correct=sum((semantic(r) or {}).get('grade')=='correct' for r in rr),
            citation_support=dict(numerator=num,denominator=den),observations_are_small_sample=True)
    single=[by[n] for n in ('single_fact_r1','single_fact_r2') if n in by]
    single_audit=dict(observations=len(single),false_refusals=sum(r.get('semantic_score',{}).get('grade')=='false_refusal' for r in single),
        correct_support_in_prompt=sum('L01-01' in traced(r).get('offered_ids',[]) for r in single),
        per_observation=[dict(name=r['name'],status=r.get('status'),score=r.get('semantic_score'),selected_ids=r.get('selected_ids'),
            offered_ids=traced(r).get('offered_ids'),seconds=r['seconds']) for r in single])
    tested_pass=[int(n) for n,g in loads.items() if g['passed']]
    latency_pass=[int(n) for n,g in loads.items() if g['gates']['all_technical'] and g['gates']['every_latency_at_most_60']]
    resource_samples=lines(run/'resources.jsonl')+additional_resources
    initial_resource_samples=lines(functional_run/'resources.jsonl')
    transport=[r for r in rows if r['phase']=='transport']
    result=dict(run_status='CONFIRMED_LOAD_COHORTS_COMPLETED' if load4_run and extra_done['status']=='COMPLETED' else done['status'],
        cohort_status=dict(initial=initial_done['status'],load12=done['status'],load4=extra_done['status'] if load4_run else None),
        historical_quality_source='optimization/reports/E12_historical_quality_scope.json',
        functional_checks=functional,functional_passed=sum(functional.values()),functional_total=len(functional),
        D036_observations=len(d036),D036_worker_walls=[v['event']['worker_wall_seconds'] for v in d036],
        concurrent_zero_model_transport=dict(observations=len(transport),passed=sum(bool(r.get('zero_call_gate') and r.get('submission_confirmed')) for r in transport)),
        functional_observations=[dict(name=r['name'],seconds=r['seconds'],status=r.get('status'),selected_ids=r.get('selected_ids'),
            queue_timing=r.get('queue_timing'),query_resolution=r.get('query_resolution'),effective_query=r.get('effective_query'),
            minimum_available_GiB=r['resources']['available_min_GiB'],trace_record=r.get('trace_record')) for r in rows if r['phase']=='functional'],
        single_fact_observation=single_audit,load=loads,
        highest_tested_submission_concurrency_passing_all_gates=max(tested_pass) if tested_pass else None,
        highest_tested_submission_concurrency_passing_latency_and_technical=max(latency_pass) if latency_pass else None,
        original_worker_model_execution_serialized=True,capacity_is_not_sustained_SLA=True,
        global_available_min_GiB=min(v['available'] for v in resource_samples)/2**30,
        initial_functional_cohort_available_min_GiB=min(v['available'] for v in initial_resource_samples)/2**30,
        global_model_process_rss_peak_GiB=max(v['process_rss'] for v in resource_samples)/2**30,
        full90_rerun=False,holdout40_used=False,inference_source_commit=meta['source_commit'],
        functional_source_commit=initial_meta['source_commit'],
        load4_source_commit=extra_meta['source_commit'] if load4_run else None,
        initial_measurement_cohort=dict(valid_serial_samples=[dict(name=r['name'],seconds=r['seconds']) for r in initial_rows if r['phase']=='load' and r['name'].startswith('load-c1-')],
            unconfirmed_concurrent_submission=[r['name'] for r in initial_rows if r['phase']=='load' and r.get('client_timeout')],
            disposition='Retained; initial level-2 timeout without Worker entry is a measurement/admission uncertainty, excluded from confirmed backend timeout claims. Controlled recheck is a separate cohort.'),
        interpretation='Normal UI and real retrieval/worker boundary. Timeout means 120-second client observation deadline, distinct from unchanged 420-second worker timeout. No first result replaced with a retry; semantic and runtime failures separated.',
        limitations=['First single-fact observation overlapped the second zero-model D036 rendering recheck; actual lock wait retained. Formal load waves start after functional phase.',
            'D036 second observation was required to capture visible refusal after browser file-export path restrictions; both raw records are retained.',
            'The intermediate four-tab D008 Worker entry at +69.741s was later than its five-second observation. That row is not a five-second model timeout; final four-request confirmation uses actual question POST and the full120s deadline.',
            'Final C4 D008 has a valid answered backend trace but its twelve-second DOM-render verification expired. Preserve the raw timeout flag while deriving a render-verification category, distinct from the 120-second client deadline and420-second Worker timeout.',
            'Quoted source identity/integrity is distinct from frozen-point citation relevance.',
            'History isolation test does not establish account authorization security.'])
    save(out,result)
    print(json.dumps(dict(functional_checks=functional,single_fact=single_audit,capacity=result['highest_tested_submission_concurrency_passing_all_gates'],
        latency_capacity=result['highest_tested_submission_concurrency_passing_latency_and_technical'],
        load={k:dict(counts=v['counts'],gates=v['gates'],max_seconds=v['max_seconds'],min_available_GiB=v['min_available_GiB']) for k,v in loads.items()}),ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--functional-run',type=Path);p.add_argument('--load4-run',type=Path);a=p.parse_args();main(a.run,a.out,a.functional_run,a.load4_run)
