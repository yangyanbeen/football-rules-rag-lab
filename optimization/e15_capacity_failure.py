"""Preserve the stopped low-headroom run; no inference or inferred quality score."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,record,digest
def main():
    run=ROOT/'.runtime/phase2/e15-jit-special02';done=read(run/'completed.json');rows=[]
    for name,h in done['hashes'].items():
        p=run/name;assert digest(p.read_bytes())==h;r=read(p);low=r['resources']['low_point'];events=r['stage_events']
        prior=[e for e in events if e['monotonic']<=low['monotonic']]
        rows.append(dict(name=r['name'],before_available_GiB=r['before']['available_GiB'],before_models=[m['name'] for m in (r['before_models'] or [])],
            minimum_available_GiB=r['combined_available_min_GiB'],periodic_low_GiB=low['available']/2**30,
            low_latest_stage=max(prior,key=lambda e:e['monotonic'])['stage'] if prior else None,
            resource_protection_triggered=r['resources']['resource_abort'],controller_error=r['error'],valid_final_result=r['result'] is not None,
            worker_RSS_at_low_GiB=sum(p['rss'] for p in low['processes'] if p['role']=='worker')/2**30,
            ollama_RSS_at_low_GiB=sum(p['rss'] for p in low['processes'] if p['role']=='ollama')/2**30,
            raw=record(p)))
    v=dict(status=done['status'],completed_requests=done['observations'],rows=rows,new_model_calls=0,
        classification='Deployment headroom/resource interruption, not a semantic wrong-answer score. No completed A/B pair or acceptance from this run.',
        decision='No further heavy requests under this background load pending resource recovery or user choice to finish capacity diagnosis.',
        full90_executed=False,holdout40_used=False,raw_resources=record(run/'resources.jsonl'),source_commit=read(run/'metadata.json')['source_commit'])
    (ROOT/'optimization/reports/E15_low_headroom_failure.json').write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(v,ensure_ascii=False))
if __name__=='__main__':main()
