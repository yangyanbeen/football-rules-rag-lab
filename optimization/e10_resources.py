"""Owned Ollama process-tree sampler; dependencies isolated from the app env."""
import json,sys,threading,time,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.runtime/phase2/e10-gguf-tools'))
import psutil

class Sampler:
    def __init__(self,pid,path):
        self.pid=pid;self.root=psutil.Process(pid);assert 'ollama' in self.root.name().lower()
        self.path=path;self.rows=[];self.label='idle';self.stop_event=threading.Event();self.aborted=False
        self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()
    def loop(self):
        critical=0
        with self.path.open('x',encoding='utf8') as f:
            while not self.stop_event.is_set():
                processes=[]
                try:processes=[self.root,*self.root.children(recursive=True)]
                except (psutil.NoSuchProcess,psutil.AccessDenied):pass
                details=[]
                for p in processes:
                    try:
                        m=p.memory_info();cpu=p.cpu_times()
                        details.append(dict(pid=p.pid,rss=m.rss,private=getattr(m,'private',None),cpu_seconds=cpu.user+cpu.system))
                    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
                memory=psutil.virtual_memory()
                row=dict(monotonic=time.perf_counter(),label=self.label,available=memory.available,total=memory.total,
                    process_rss=sum(v['rss'] for v in details),processes=details,client_rss=psutil.Process().memory_info().rss)
                self.rows.append(row);f.write(json.dumps(row)+'\n');f.flush()
                critical=critical+1 if memory.available<.35*2**30 else 0
                if critical>=3 and not self.aborted:
                    self.aborted=True
                    # This PID was supplied by the task-owned hidden server.
                    subprocess.run(['taskkill','/PID',str(self.pid),'/T','/F'],capture_output=True)
                    break
                self.stop_event.wait(.5)
    def begin(self,label):self.label=label;return time.perf_counter()
    def end(self,begin):
        end=time.perf_counter();values=[v for v in self.rows if begin<=v['monotonic']<=end]
        return dict(samples=len(values),process_rss_peak_GiB=max([v['process_rss']/2**30 for v in values] or [0]),
            available_min_GiB=min([v['available']/2**30 for v in values]) if values else None,
            client_rss_peak_GiB=max([v['client_rss']/2**30 for v in values] or [0]),resource_abort=self.aborted)
    def close(self):self.stop_event.set();self.thread.join(timeout=3)

def snapshot():
    m=psutil.virtual_memory()
    import platform
    return dict(total_GiB=m.total/2**30,available_GiB=m.available/2**30,logical_cpus=psutil.cpu_count(),processor=platform.processor(),
        psutil_version=psutil.__version__)
