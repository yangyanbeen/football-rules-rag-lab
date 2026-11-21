"""No inference: correlate E14 event windows, original PID samples and matched controls."""
import bisect,json,statistics,sys
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,record,digest

def save(p,v):p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
def main():
    run=ROOT/'.runtime/phase2/e14-live90-final';done=read(run/'worker/completed.json')
    samples=[json.loads(s) for s in (run/'worker/resources.jsonl').read_text('utf8').splitlines()]
    times=[s['monotonic'] for s in samples];groups={}
    for s in samples:groups.setdefault(s['label'],[]).append(s)
    pidmap={c['trace_id']:c['worker_pid'] for c in read(ROOT/'optimization/reports/E14_process_memory_reconciliation.json')['cases']}
    summaries=[];raw_by_id={};phases={}
    def observation(s,pid):
        worker=next((p for p in s['processes'] if p['pid']==pid),None)
        # Ollama model tree is rooted separately and never classified by Worker PID.
        ollama=[p for p in s['processes'] if p['role']=='ollama']
        return dict(monotonic=s['monotonic'],wall_ns=s['wall_ns'],available_GiB=s['available']/2**30,
            worker_RSS_GiB=worker['rss']/2**30 if worker else None,
            worker_private_GiB=worker['private']/2**30 if worker and worker['private'] is not None else None,
            ollama_RSS_GiB=sum(p['rss'] for p in ollama)/2**30,
            ollama_private_GiB=sum(p['private'] or 0 for p in ollama)/2**30,
            models=[m['name'] for m in (s.get('loaded_models') or [])])
    for order,(filename,h) in enumerate(done['hashes'].items(),1):
        path=run/'worker'/filename;assert digest(path.read_bytes())==h;t=read(path);r=t['result'];qid=t['name'];pid=pidmap[r['trace_id']]
        ss=groups[qid+'-B'];events=[json.loads(s) for s in (run/'events'/(str(pid)+'.jsonl')).read_text('utf8').splitlines()]
        stamp=datetime.fromisoformat(r['captured_at']).timestamp()*1e9
        answer=min([e for e in events if e['stage']=='answer_start'],key=lambda e:abs(e['wall_ns']-stamp))
        begin=max(e['monotonic'] for e in events if e['stage']=='worker_enter' and e['monotonic']<=answer['monotonic'])
        end=min(e['monotonic'] for e in events if e['stage']=='worker_return' and e['monotonic']>=answer['monotonic'])
        ev={e['stage']:e for e in events if begin<=e['monotonic']<=end};phases[qid]=ev
        low=min(ss,key=lambda s:s['available']);raw_by_id[qid]=(ss,low,pid)
        prior=[e for e in ev.values() if e['monotonic']<=low['monotonic']]
        nearest_stage=max(prior,key=lambda e:e['monotonic'])['stage'] if prior else 'before_worker_entry'
        anchors={}
        for name in ('reranker_construction_start','reranker_construction_end','retrieval_query_start','retrieval_query_end','answer_model_start','answer_model_end','result_validation_start','result_validation_end'):
            if name in ev:
                moment=ev[name]['monotonic'];point=min(ss,key=lambda s:abs(s['monotonic']-moment))
                anchors[name]=dict(seconds_from_query_sample_start=moment-ss[0]['monotonic'],sample_offset_seconds=point['monotonic']-moment,**observation(point,pid))
        row=dict(question_id=qid,order=order,worker_pid=pid,seconds=t['seconds'],retrieval=r['retrieval'] is not None,
            start=observation(ss[0],pid),end=observation(ss[-1],pid),low=observation(low,pid),low_latest_stage=nearest_stage,anchors=anchors,
            elapsed_to_low_seconds=low['monotonic']-ss[0]['monotonic'],max_resident_models=max(len(s.get('loaded_models') or []) for s in ss),
            worker_RSS_peak_GiB=max([p['rss']/2**30 for s in ss for p in s['processes'] if p['pid']==pid] or [0]),
            evidence_order=r['offered_ids'],prompt_utf8_bytes=r['prompt_utf8_bytes'],raw_record=record(path))
        summaries.append(row)
    lows=[r for r in summaries if r['low']['available_GiB']<1];assert len(lows)==10
    controls=[r for r in summaries if r['retrieval'] and r['low']['available_GiB']>=1]
    comparisons=[]
    for row in lows:
        names=row['start']['models'];pool=[v for v in controls if v['start']['models']==names]
        control=min(pool,key=lambda v:(abs(v['start']['available_GiB']-row['start']['available_GiB']),abs(v['order']-row['order']))) if pool else None
        ss,low,pid=raw_by_id[row['question_id']]
        nearby=samples[bisect.bisect_left(times,low['monotonic']-3):bisect.bisect_right(times,low['monotonic']+3)]
        comparisons.append(dict(low_case=row,matched_control=control,
            start_difference_GiB=abs(control['start']['available_GiB']-row['start']['available_GiB']) if control else None,
            matching_note='Same sampled model residency; closest starting availability. Not randomized causal evidence.' if control else 'No same-residency qualifying control in this run.',
            low_window_plus_minus3s=[observation(s,pid) for s in nearby]))
    gaps=[b-a for a,b in zip(times,times[1:])]
    value=dict(new_model_calls=0,source_resources=record(run/'worker/resources.jsonl'),raw_completed=record(run/'worker/completed.json'),
        method='Worker PID bound by archived answer timestamp/event window, no cached role labels. Starting availability is first sample for the request label, not an exact pre-launch measurement. Rerank completion approximated by retrieval_query_end; detailed retrieval timings retained in raw trace.',
        observations=90,low_cases=10,sampling=dict(median_seconds=statistics.median(gaps),max_gap_seconds=max(gaps)),
        low_stage_counts={s:sum(r['low_latest_stage']==s for r in lows) for s in sorted({r['low_latest_stage'] for r in lows})},
        comparisons=comparisons,request_order=summaries,
        caveats=['1-second ps snapshots do not exclude brief overlap','RSS is working set, private is committed private memory, not all physically resident','Archived code retains reranker on self.retriever through answer; observed Worker RSS cannot isolate ONNX from other imported dependencies','No current OS available-memory reading used for historical comparisons'])
    save(ROOT/'optimization/reports/E15_archive_memory_audit.json',value)
    print(json.dumps(dict(new_model_calls=0,low_stage_counts=value['low_stage_counts'],rows=[dict(q=r['question_id'],start=r['start']['available_GiB'],low=r['low']['available_GiB'],stage=r['low_latest_stage'],rss=r['low']['worker_RSS_GiB'],models=r['low']['models']) for r in lows]),ensure_ascii=False))
if __name__=='__main__':main()
