"""Read existing sequential traces; do not attribute outside-engine time to one stage."""
import argparse,hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main(run,out):
    done=json.loads((run/'completed.json').read_text('utf8'));rows=[]
    for name,sha in done['hashes'].items():
        path=run/name;assert hashlib.sha256(path.read_bytes()).hexdigest()==sha
        r=json.loads(path.read_text('utf8'));t=r['result']['timing']
        rows.append(dict(name=r['name'],variant=r['variant'],wall_seconds=r['seconds'],**t,
            outside_engine_seconds=r['seconds']-t['total_seconds'],answer_model_calls=len(r['result']['attempts'])))
    value=dict(new_model_calls=0,source_run=run.as_posix(),observations=len(rows),rows=rows,
        outside_engine_median_seconds=statistics.median(r['outside_engine_seconds'] for r in rows),
        outside_engine_range_seconds=[min(r['outside_engine_seconds'] for r in rows),max(r['outside_engine_seconds'] for r in rows)],
        gate_only_rows=[r for r in rows if not r['answer_model_calls']],
        interpretation='Wall minus IntegratedEngine.answer total includes subprocess/import/engine initialization, environment/source validation, cleanup and parent validation. Not isolated initialization or queue timing.',
        queue_wait_measured=False,worker_rss_measured=False,
        memory_interpretation='Existing sampler records total system available memory and Ollama RSS, not an isolated Worker peak. Persistent-worker memory savings remain untested.',
        production_changed=False,full90_executed=False,holdout_used=False)
    out.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps({k:value[k] for k in ('observations','outside_engine_median_seconds','outside_engine_range_seconds','new_model_calls')},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();main(a.run,a.out)
