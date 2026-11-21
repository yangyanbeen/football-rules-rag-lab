"""External 250ms process-tree samples; accepted Worker environment is untouched."""
import json,os,subprocess,time,urllib.request
from e10_resources import Sampler as Base,psutil,snapshot

HTTP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def models():
    try:
        with HTTP.open('http://127.0.0.1:11434/api/ps',timeout=.2) as r:return json.load(r).get('models',[])
    except Exception:return None

class Sampler(Base):
    def __init__(self,pid,path,ui_pid):
        self.ui_pid=ui_pid;self.process_labels={};super().__init__(pid,path)
    def loop(self):
        critical=0;loaded=None;last=0
        with self.path.open('x',encoding='utf8') as f:
            while not self.stop_event.is_set():
                processes={}
                for root,role in ((self.pid,'ollama'),(self.ui_pid,'ui'),(os.getpid(),'observer')):
                    try:
                        parent=psutil.Process(root)
                        for p in [parent,*parent.children(recursive=True)]:
                            processes[p.pid]=(p,role)
                    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
                details=[]
                for pid,(p,role) in processes.items():
                    try:
                        if pid not in self.process_labels:
                            cmd=' '.join(p.cmdline());self.process_labels[pid]='worker' if 'query_task13_audit.py' in cmd else 'chrome' if 'chrome.exe' in cmd.lower() else role
                        m=p.memory_info();cpu=p.cpu_times()
                        details.append(dict(pid=pid,parent_pid=p.ppid(),role=self.process_labels[pid],rss=m.rss,private=getattr(m,'private',None),native_peak_rss=getattr(m,'peak_wset',m.rss),cpu_seconds=cpu.user+cpu.system))
                    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
                now=time.perf_counter()
                if now-last>=1:loaded=models();last=now
                memory=psutil.virtual_memory();row=dict(monotonic=now,wall_ns=time.time_ns(),label=self.label,available=memory.available,total=memory.total,
                    processes=details,process_rss=sum(v['rss'] for v in details),client_rss=psutil.Process().memory_info().rss,loaded_models=loaded)
                self.rows.append(row);f.write(json.dumps(row)+'\n');f.flush()
                critical=critical+1 if memory.available<.35*2**30 else 0
                if critical>=3:
                    self.aborted=True;subprocess.run(['taskkill','/PID',str(self.pid),'/T','/F'],capture_output=True);break
                self.stop_event.wait(.25)
    def end(self,begin):
        value=super().end(begin);rows=[r for r in self.rows if r['monotonic']>=begin]
        if rows:
            low=min(rows,key=lambda r:r['available']);value['low_point']=low
            value['role_peak_rss_GiB']={role:max(sum(p['rss'] for p in r['processes'] if p['role']==role) for r in rows)/2**30 for role in ('worker','ui','ollama','chrome','observer')}
        return value
