"""Run the normal UI/worker with clock observations and isolated chat storage."""
import functools,hashlib,json,os,sys,threading,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
def instrument(client,path):
    underlying=client.LOCK;original=client.call_worker;local=threading.local();journal_lock=threading.Lock()
    def event(kind,**fields):
        value=dict(kind=kind,request_id=getattr(local,'request_id',None),wall_ns=time.time_ns(),monotonic_ns=time.perf_counter_ns(),
            pid=os.getpid(),thread_id=threading.get_ident(),**fields)
        with journal_lock:
            with path.open('a',encoding='utf8') as f:f.write(json.dumps(value,ensure_ascii=False)+'\n');f.flush()
    class ObservedLock:
        def __enter__(self):
            event('lock_wait');value=underlying.__enter__();event('lock_acquired');return value
        def __exit__(self,*args):
            try:return underlying.__exit__(*args)
            finally:event('lock_released')
    @functools.wraps(original)
    def measured(*args,**kwargs):
        previous=getattr(local,'request_id',None);local.request_id=uuid.uuid4().hex
        question=kwargs.get('question',args[0] if args else None)
        event('worker_enter',question_sha256=hashlib.sha256((question or '').encode()).hexdigest(),check=kwargs.get('check',False),
              history_supplied=bool(kwargs.get('history')))
        try:
            value=original(*args,**kwargs)
            fields={}
            if isinstance(value,tuple) and len(value)==3:
                fields=dict(status=value[0]['status'],trace_id=value[0]['trace_id'],private_trace=value[1])
            event('worker_return',**fields);return value
        except BaseException as exc:event('worker_error',error=type(exc).__name__);raise
        finally:local.request_id=previous
    client.LOCK=ObservedLock();client.call_worker=measured

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--profile',required=True);a=p.parse_args()
    assert a.profile.startswith('e12-delivery-') and a.profile.replace('-','').isalnum()
    import task13_audit_client as client
    instrument(client,a.out/'worker-events.jsonl')
    import run_integrated_rag_audit as launch
    load=launch.load_config
    def isolated():
        cfg=load();cfg['ui']['app_data']='.runtime/task13/'+a.profile;return cfg
    launch.load_config=isolated
    launch.main()
if __name__=='__main__':main()
