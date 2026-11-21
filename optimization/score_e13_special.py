"""Independent per-question gates; repeat browser observations stay separate."""
import argparse,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text('utf8'))
def save(p,v):p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
def score(run,browser,out):
    done=read(run/'completed.json')
    for n,h in done['hashes'].items():assert hashlib.sha256((run/n).read_bytes()).hexdigest()==h
    rows=[read(run/n) for n in done['hashes']];plan=read(ROOT/'optimization/experiments/E13_source_facts/plan.json')
    by={(r['name'],r['variant']):r for r in rows};positive=[c for c in plan['pressure_questions'] if not c.get('replay_only')]
    def good(r):return not r['error'] and r['score']['grade']=='correct'
    boundaries=[by.get((c['name'],'B')) for c in plan['boundary_controls']]
    controls=[by.get((c['name'],v)) for c in plan['correct_controls'] for v in 'AB']
    candidates=[r for r in rows if r['variant']=='B'];supp=[r for r in candidates if r.get('result') and r['result'].get('fact_recovery',{}).get('applied')]
    quality=dict(registered_originals_and_paraphrases=all((c['name'],'B') in by and good(by[c['name'],'B']) for c in positive),
        no_incorrect_supplement=all(r and not r['error'] and not r['result'].get('fact_recovery',{}).get('applied') for r in boundaries) and not any(r.get('score',{}).get('wrong_supplement') for r in rows),
        original_correct_controls=all(r and good(r) for r in controls),
        every_added_citation_supported=all(r['score']['citation_numerator']==r['score']['citation_denominator'] for r in supp),
        technical_complete=len(rows)==26 and all(not r['error'] for r in rows),
        D036_zero_calls=all(by.get(('D036_gate',v)) and by[('D036_gate',v)].get('result') and not by[('D036_gate',v)]['result']['attempts'] and by[('D036_gate',v)]['result']['retrieval'] is None for v in 'AB'))
    runtime=dict(all_candidate_requests_at_most_60s=all(r['seconds']<=60 for r in candidates),
        all_candidate_available_at_least_1GiB=all(r['resources']['available_min_GiB'] is not None and r['resources']['available_min_GiB']>=1 for r in candidates))
    b=read(browser) if browser and browser.exists() else None
    result=dict(quality_gates=quality,runtime_gates=runtime,browser=b,
        all_gates_passed=bool(all(quality.values()) and all(runtime.values()) and b and b['all_gates_passed']),
        positive_unique_wordings=len(positive),registered_attributes=4,independent_objects=3,worker_observations=len(rows),
        recovered_wordings=[r['name'] for r in supp],per_observation=[dict(name=r['name'],variant=r['variant'],seconds=r['seconds'],
            available_min_GiB=r['resources']['available_min_GiB'],status=r['result']['status'] if r.get('result') else None,
            selected_ids=r['result']['selected_ids'] if r.get('result') else [],score=r.get('score'),recovery=r['result'].get('fact_recovery') if r.get('result') else None,error=r['error']) for r in rows],
        holdout_used=False,full90_executed=False)
    save(out,result);print(json.dumps({k:result[k] for k in ('quality_gates','runtime_gates','all_gates_passed','recovered_wordings')},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--browser',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args();score(a.run,a.browser,a.out)
