"""Whole fixed90 input parity, residency, latency and memory trend audit."""
import argparse,collections,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,record,digest


def main(run):
    worker=run/'worker';done=read(worker/'completed.json');metadata=read(worker/'metadata.json')
    quality=read(ROOT/'optimization/reports/E15_low_memory_live90_metrics.json')
    old={v['question_id']:v for v in read(ROOT/'optimization/reports/E14_live90_metrics.json')['cases'] if v['variant']=='candidate'}
    samples=[json.loads(line) for line in (worker/'resources.jsonl').read_text('utf8').splitlines()]
    grouped={}
    for sample in samples:grouped.setdefault(sample['label'],[]).append(sample)
    rows=[];trend=[]
    for name,sha in done['hashes'].items():
        path=worker/name;assert digest(path.read_bytes())==sha;t=read(path);r=t['result'];qid=t['name'];events=t['resources']['stage_events']
        historical=read(ROOT/old[qid]['raw_record']['path'])['result'];by={e['stage']:e for e in events}
        inputs=bool(r and all(r[k]==historical[k] for k in ('question','messages','context','retrieved_ids'))
                    and (r['retrieval'] or {}).get('results')==(historical['retrieval'] or {}).get('results'))
        normal=bool(r and r['attempts']);ordered=False
        if normal:
            wanted=['answer_before_retrieval_unload_end','embedding_unload_end','jit_reranker_construction_start',
                    'reranker_release_end','answer_model_start','answer_after_generation_unload_end']
            ordered=all(s in by for s in wanted) and all(by[a]['monotonic']<by[b]['monotonic'] for a,b in zip(wanted,wanted[1:]))
            ordered=ordered and by['reranker_release_end'].get('object_collected') is True
        elif r:
            ordered=not any(s in by for s in ('lazy_retrieval_construction_start','answer_model_start'))
        periodic=t['resources'].get('low_point');stage=t['resources'].get('low_stage_snapshot')
        low=stage if stage else periodic
        if stage:low_stage=stage['stage']
        else:
            prior=[e for e in events if low and e['monotonic']<=low['monotonic']]
            low_stage=max(prior,key=lambda e:e['monotonic'])['stage'] if prior else 'before_worker_entry'
        ss=grouped.get(qid+'-B',[])
        if ss:trend.append(dict(question_id=qid,first_available_GiB=ss[0]['available']/2**30,last_available_GiB=ss[-1]['available']/2**30))
        rows.append(dict(question_id=qid,inputs_equal_E14=inputs,residency_order=ordered,normal=normal,seconds=t['seconds'],
            minimum_available_GiB=t['resources']['available_min_GiB'],low_stage=low_stage,
            peak_process_tree_rss_GiB=t['resources']['process_rss_peak_GiB'],roles=t['resources'].get('role_peak_rss_GiB'),
            calls=len(r['attempts']) if r else 0,extra_retry_calls=max(0,len(r['attempts'])-1) if r else 0,
            input_tokens=sum(a.get('prompt_eval_count') or 0 for a in r['attempts']) if r else 0,
            output_tokens=sum(a.get('eval_count') or 0 for a in r['attempts']) if r else 0,
            status=r['status'] if r else None,error=t['error'],raw_record=record(path)))
    gaps=[b['monotonic']-a['monotonic'] for a,b in zip(samples,samples[1:])]
    times=sorted(r['seconds'] for r in rows);first=[t['first_available_GiB'] for t in trend[:10]];last=[t['first_available_GiB'] for t in trend[-10:]]
    all_events=[json.loads(line) for p in (run/'events').glob('*.jsonl') for line in p.read_text('utf8').splitlines() if line.strip()]
    all_stage_available=[e['memory']['available']/2**30 for e in all_events if 'available' in e.get('memory',{})]
    gates=dict(complete90=done['status']=='COMPLETED' and len(rows)==90,all_inputs_identical=len(rows)==90 and all(r['inputs_equal_E14'] for r in rows),
        all_residency_order=len(rows)==90 and all(r['residency_order'] for r in rows),quality_and_resource=quality['overall_pass'],
        startup_and_request_stage_minimum=bool(all_stage_available) and min(all_stage_available)>=1)
    result=dict(source_commit=metadata['source_commit'],quality_report=record(ROOT/'optimization/reports/E15_low_memory_live90_metrics.json'),
        gates=gates,overall_pass=all(gates.values()),actual_records=len(rows),
        memory=dict(minimum_available_GiB=min(r['minimum_available_GiB'] for r in rows),all_stage_minimum_including_UI_readiness_GiB=min(all_stage_available),below1=sum(r['minimum_available_GiB']<1 for r in rows),
            low_stages=dict(collections.Counter(r['low_stage'] for r in rows)),peak_task_tree_rss_GiB=max(r['peak_process_tree_rss_GiB'] for r in rows)),
        latency=dict(median_seconds=statistics.median(times),p95_nearest_rank_seconds=times[max(0,(95*len(times)+99)//100-1)],maximum_seconds=max(times),above60=sum(t>60 for t in times)),
        calls=dict(answer=sum(r['calls'] for r in rows),retry=sum(r['extra_retry_calls'] for r in rows),input_tokens=sum(r['input_tokens'] for r in rows),output_tokens=sum(r['output_tokens'] for r in rows)),
        sampling=dict(target_seconds=.2,actual_median_seconds=statistics.median(gaps),maximum_gap_seconds=max(gaps)),
        trend=dict(first10_start_available_median_GiB=statistics.median(first),last10_start_available_median_GiB=statistics.median(last),
            per_question=trend,interpretation='System background and page cache are uncontrolled; do not infer a leak or leak absence from these medians alone.'),
        cases=rows,holdout_used=False,comparison='Actual candidate90 versus historical E14 source review and inputs; no concurrent independent control inference.')
    path=ROOT/'optimization/reports/E15_low_memory90_resource_audit.json';path.write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','trend')},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);main(p.parse_args().run)
