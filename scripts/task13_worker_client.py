"""Serialize process-isolated task13 requests and reject unbound worker results."""
import os,subprocess,threading,time
from task13_core import *

LOCK=threading.RLock()


def call_worker(question=None,check=False):
    cfg=app_config();start=time.perf_counter();trace=ROOT/'.runtime/task13/workers'/(uuid.uuid4().hex+'.json')
    if not check:question=normalize_question(question)
    command=[str(ROOT/cfg['environment']),'-B','-X','faulthandler',str(ROOT/'scripts/query_task13.py')]
    command+=['--check'] if check else ['--question',question,'--trace',str(trace)]
    with LOCK:
        proc=subprocess.run(command,cwd=ROOT,env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,encoding='utf-8',timeout=cfg['worker_timeout_seconds'],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if proc.returncode:
        trace.parent.mkdir(parents=True,exist_ok=True);trace.with_suffix('.stderr.log').write_text(proc.stderr,'utf-8')
        raise RuntimeError('Integrated worker failed; see private task13 log')
    packet=json.loads(proc.stdout)
    if check:
        if packet!={'status':'READY','profile':cfg['version'],'records':99,'config_sha256':record(ROOT/CONFIG)['sha256']}:raise ValueError('Invalid worker readiness')
        return packet
    if packet.get('private_trace')!=record(trace):raise ValueError('Worker output trace binding differs')
    result=read(trace);validate_result(result,question)
    if packet.get('trace_id')!=result['trace_id'] or packet.get('status')!=result['status']:raise ValueError('Worker output status differs')
    return result,record(trace),time.perf_counter()-start
