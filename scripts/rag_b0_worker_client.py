"""Process boundary for Windows UI/native-index compatibility; no web API."""
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WORKER_LOCK=threading.RLock()


def call_worker(question=None, check=False):
    folder=ROOT/'.runtime/rag-b0/workers'
    folder.mkdir(parents=True,exist_ok=True)
    trace=folder/(uuid.uuid4().hex+'.json')
    command=[sys.executable,'-X','faulthandler',str(ROOT/'scripts/query_rag_b0.py')]
    command+=['--check'] if check else ['--query',question,'--trace',str(trace)]
    started=time.perf_counter()
    try:
        with WORKER_LOCK:
            proc=subprocess.run(command,cwd=ROOT,env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1'},
                capture_output=True,text=True,encoding='utf-8',timeout=420,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if proc.returncode:
            trace.with_suffix('.stderr.log').write_text(proc.stderr,encoding='utf-8')
            raise RuntimeError('Isolated worker exited with code '+str(proc.returncode))
        if check:return json.loads(proc.stdout)
        result=json.loads(trace.read_text('utf-8'))
        if result['question']!=question:raise ValueError('Worker question mismatch')
    except (OSError,ValueError,KeyError,RuntimeError,subprocess.TimeoutExpired) as exc:
        if check:raise
        result={'trace_id':uuid.uuid4().hex,'captured_at':datetime.now(timezone.utc).isoformat(),
            'question':question,'status':'refused','answer':'现有资料不足以可靠回答这个问题，无法据此给出确定结论。',
            'citations':[],'context':[],'retrieval':None,'generation':None,'generation_attempted':False,
            'refusal_reason':'isolated_worker_failed','error':type(exc).__name__+': '+str(exc),'timing':{}}
    result['timing']['worker_wall_seconds']=time.perf_counter()-started
    return result
