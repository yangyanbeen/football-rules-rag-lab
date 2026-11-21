"""Optional standard-library stage markers; no user content or runtime dependency."""
import json,os,time
from pathlib import Path

def mark(stage,**details):
    target=os.environ.get('FOOTBALL_RUNTIME_EVENTS')
    if not target:return
    path=Path(target).resolve();root=Path(__file__).resolve().parents[1]/'.runtime/phase2'
    if not path.is_relative_to(root) or not path.parent.name.startswith('e14-') or path.name!='events':
        raise ValueError('Use an experiment-owned E14 events directory')
    value=dict(stage=stage,pid=os.getpid(),parent_pid=os.getppid(),monotonic=time.perf_counter(),wall_ns=time.time_ns(),**details)
    with (path/(str(os.getpid())+'.jsonl')).open('a',encoding='utf8') as f:f.write(json.dumps(value)+'\n')
