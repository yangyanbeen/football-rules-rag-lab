"""Pilot input parity, existing source reviews, and measured whole-request resources."""
import argparse,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,record,digest
from task13_audit import validate_private


def main(run):
    done=read(run/'completed.json');meta=read(run/'metadata.json')
    old={c['question_id']:c for c in read(ROOT/'optimization/reports/E14_live90_metrics.json')['cases'] if c['variant']=='candidate'}
    rows=[];gains={'embedding':[],'answer_after_generation':[]};queue=[]
    for name,sha in done['hashes'].items():
        p=run/name;assert digest(p.read_bytes())==sha;t=read(p);r=t['result'];qid=t['question_id']
        stages=t['stage_events'];by={e['stage']:e for e in stages}
        parity=False;review=None;zero=False;order=False
        if r:
            validate_private(r,t['question'],True)
            archived=read(ROOT/old[qid]['raw_record']['path'])['result']
            parity=all(r[k]==archived[k] for k in ('question','messages','context','retrieved_ids')) and (r['retrieval'] or {}).get('results')==(archived['retrieval'] or {}).get('results')
            if r['status']==old[qid]['status'] and r['selected_ids']==old[qid]['selected_ids']:
                review={k:old[qid][k] for k in ('grade','point_mask','supported_citation_ids','note')}
            else:queue.append(dict(name=name,question=t['question'],selected_ids=r['selected_ids'],context=r['context']))
            if qid=='D036':
                zero=r['status']=='refused' and r['retrieval'] is None and not r['attempts'] and not any(
                    s in by for s in ('lazy_retrieval_construction_start','answer_before_retrieval_unload_start','answer_model_start'))
                order=zero
            else:
                wanted=('answer_before_retrieval_unload_end','embedding_unload_end','jit_reranker_construction_start',
                        'reranker_release_end','answer_model_start','answer_after_generation_unload_end')
                order=all(s in by for s in wanted)
                if order:
                    order=all(by[a]['monotonic']<by[b]['monotonic'] for a,b in zip(wanted,wanted[1:])) and by['reranker_release_end']['object_collected']
        for model in gains:
            a=by.get(model+'_unload_start');b=by.get(model+'_unload_end')
            if a and b and b['was_loaded']:gains[model].append((b['memory']['available']-a['memory']['available'])/2**30)
        rows.append(dict(name=t['name'],entry=t['entry'],question_id=qid,error=t['error'],seconds=t['seconds'],
            minimum_available_GiB=t['combined_available_min_GiB'],before_available_GiB=t['before']['available_GiB'],
            process_tree_rss_peak_GiB=t['resources']['process_rss_peak_GiB'],role_peak_rss=t['resources']['role_peak_rss_GiB'],
            idle_models=t['after_models'],inputs_equal_to_E14=parity,review=review,D036_zero=zero,residency_order=order,
            selected_ids=r['selected_ids'] if r else None,raw_record=record(p)))
    normal=[r for r in rows if r['question_id']!='D036']
    cited=sum(len(r['selected_ids'] or []) for r in rows)
    supported=sum(len(r['review']['supported_citation_ids']) for r in rows if r['review'])
    gaps=[]
    samples=[json.loads(s) for s in (run/'resources.jsonl').read_text('utf8').splitlines()]
    gaps=[b['monotonic']-a['monotonic'] for a,b in zip(samples,samples[1:])]
    gates=dict(complete10=done['status']=='COMPLETED' and len(rows)==10,
        technical=all(not r['error'] and r['review'] for r in rows),historical_inputs_identical=all(r['inputs_equal_to_E14'] for r in rows),
        source_review_no_change=not queue and len(rows)==10,latency=all(r['seconds']<=60 for r in rows),
        available_at_least1=all(r['minimum_available_GiB']>=1 for r in rows),
        residency_order=all(r['residency_order'] for r in rows),idle_no_models=all(r['idle_models']==[] for r in rows),
        D036_zero=sum(r['D036_zero'] for r in rows)==2)
    value=dict(scope=meta['scope'],source_commit=meta['source_commit'],startup_available_GiB=read(run/'preflight.json')['snapshot']['available_GiB'],
        gates=gates,pilot_passed=all(gates.values()),requests=len(rows),normal_requests=len(normal),
        minimum_available_GiB=min(r['minimum_available_GiB'] for r in rows),max_seconds=max(r['seconds'] for r in rows),
        normal_median_seconds=statistics.median(r['seconds'] for r in normal),
        citation_support=dict(numerator=supported,denominator=cited),
        unload_available_gain_GiB={k:dict(observations=len(v),median=statistics.median(v),minimum=min(v),maximum=max(v)) for k,v in gains.items() if v},
        sampling=dict(target_seconds=.2,actual_median_seconds=statistics.median(gaps),maximum_gap_seconds=max(gaps)),
        cases=rows,pending_reviews=queue,full90_executed=False,holdout40_used=False,
        limitations=['Historical E14 input and source-review comparison; not simultaneous A/B.',
            '5.0GiB launch floor is an experimental precheck; this run does not establish a minimum hardware specification.',
            'Working-set sum may double-count shared pages; role peaks occur at different times and must not be summed.',
            'Periodic and stage snapshots cannot rule out unobserved gaps; no concurrency or long-run acceptance.'])
    p=ROOT/'optimization/reports/E15_low_memory_pilot.json';p.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
    print(json.dumps({k:v for k,v in value.items() if k not in ('cases','limitations')},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);main(p.parse_args().run)
