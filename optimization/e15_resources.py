"""Periodic plus exact diagnostic stage minima for E15 acceptance runs."""
import json,time
from e14_resources import Sampler as Base

class Sampler(Base):
    def __init__(self,pid,path,ui_pid,event_root):
        self.event_root=event_root;super().__init__(pid,path,ui_pid,interval_seconds=.2)
    def end(self,begin):
        value=super().end(begin);end=time.perf_counter();events=[]
        for path in self.event_root.glob('*.jsonl'):
            for line in path.read_text('utf8').splitlines():
                try:event=json.loads(line)
                except ValueError:continue
                if begin<=event['monotonic']<=end:events.append(event)
        stage=[e for e in events if 'available' in e.get('memory',{})]
        value['periodic_available_min_GiB']=value['available_min_GiB']
        value['stage_available_min_GiB']=min([e['memory']['available']/2**30 for e in stage]) if stage else None
        if stage:
            low=min(stage,key=lambda e:e['memory']['available'])
            if value['available_min_GiB'] is None or low['memory']['available']/2**30<value['available_min_GiB']:
                value['available_min_GiB']=low['memory']['available']/2**30;value['low_stage_snapshot']=low
        value['stage_events']=events
        return value
