"""Reconcile immutable per-PID samples with exact Worker event windows, not role cache."""
import json,sys
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,record

def main():
    results=[];sources={}
    for name in ('e14-baseline01','e14-baseline02','e14-lazy01','e14-e13-special01','e14-live90-final'):
        run=ROOT/'.runtime/phase2'/name;windows=[]
        for path in (run/'events').glob('*.jsonl'):
            events=[json.loads(s) for s in path.read_text('utf8').splitlines()]
            for start in [e for e in events if e['stage']=='worker_enter']:
                segment=[e for e in events if e['monotonic']>=start['monotonic']]
                finish=next(e for e in segment if e['stage']=='worker_return')
                answer=next((e for e in segment if e['stage']=='answer_start' and e['monotonic']<=finish['monotonic']),None)
                answer_end=next((e for e in segment if e['stage']=='answer_end' and e['monotonic']<=finish['monotonic']),None)
                windows.append(dict(pid=start['pid'],begin=start['monotonic'],end=finish['monotonic'],
                    answer_begin_ns=answer['wall_ns'] if answer else None,answer_end_ns=answer_end['wall_ns'] if answer_end else None,
                    sampled_peak_bytes=0,native_peak_bytes=0,samples=0))
        folders=[run/'worker',run/'browser'] if name in ('e14-e13-special01','e14-live90-final') else [run]
        for folder in folders:
            resource=folder/'resources.jsonl'
            if not resource.exists():continue
            sources[resource.relative_to(ROOT).as_posix()]=record(resource)
            with resource.open(encoding='utf8') as f:
                for line in f:
                    row=json.loads(line)
                    for window in windows:
                        if window['begin']<=row['monotonic']<=window['end']:
                            p=next((p for p in row['processes'] if p['pid']==window['pid']),None)
                            if p:
                                window['sampled_peak_bytes']=max(window['sampled_peak_bytes'],p['rss'])
                                window['native_peak_bytes']=max(window['native_peak_bytes'],p['native_peak_rss']);window['samples']+=1
            for path in folder.glob('*.json'):
                data=read(path)
                if not isinstance(data,dict):continue
                r=data.get('result') or data.get('trace')
                if not isinstance(r,dict) or 'trace_id' not in r:continue
                stamp=round(datetime.fromisoformat(r['captured_at']).timestamp()*1e9)
                # datetime ISO timestamps can round just outside time_ns markers
                # on Windows; requests remain separated by several seconds.
                matches=[w for w in windows if w['answer_begin_ns'] is not None and w['answer_begin_ns']-100_000_000<=stamp<=w['answer_end_ns']+100_000_000]
                assert len(matches)==1,(path,len(matches));w=matches[0];assert w['samples']>0
                old=data['resources']['role_peak_rss_GiB']['worker']
                results.append(dict(trace_id=r['trace_id'],raw_record=record(path),worker_pid=w['pid'],
                    sampled_main_RSS_peak_GiB=w['sampled_peak_bytes']/2**30,native_main_RSS_peak_GiB=w['native_peak_bytes']/2**30,
                    prior_cached_role_tree_peak_GiB=old,samples=w['samples']))
    out=dict(method='Unique actual Worker answer event interval binds trace timestamp to PID, with100ms Windows datetime/time_ns tolerance. RSS/native peak from immutable original per-PID samples. Main process only, excludes venv launchers. Original cached role summaries retained; original global availability untouched.',
        raw_resources=sources,observations=len(results),cases=results,new_model_calls=0)
    (ROOT/'optimization/reports/E14_process_memory_reconciliation.json').write_bytes((json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(dict(observations=len(results),new_model_calls=0)))
if __name__=='__main__':main()
