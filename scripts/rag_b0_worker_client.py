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
    started=time.perf_counter()
    try:
        # Import helpers only; never create DenseIndex in the UI process.
        from rag_b0 import load_config, normalize_query, validate_worker_result
        import hashlib
        cfg=load_config()
        if not check:normalize_query(question,cfg)
        folder=ROOT/'.runtime/rag-b0/workers';folder.mkdir(parents=True,exist_ok=True)
        trace=folder/(uuid.uuid4().hex+'.json')
        command=[sys.executable,'-X','faulthandler',str(ROOT/'scripts/query_rag_b0.py')]
        command+=['--check'] if check else ['--query',question,'--trace',str(trace)]
        with WORKER_LOCK:
            proc=subprocess.run(command,cwd=ROOT,env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1'},
                capture_output=True,text=True,encoding='utf-8',timeout=420,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if proc.returncode:
            trace.with_suffix('.stderr.log').write_text(proc.stderr,encoding='utf-8')
            raise RuntimeError('Isolated worker exited with code '+str(proc.returncode))
        if check:
            ready=json.loads(proc.stdout)
            config_sha=hashlib.sha256((ROOT/'config/rag_b0.json').read_bytes()).hexdigest()
            if (not isinstance(ready,dict) or set(ready)!={'status','records','config_sha256'} or ready['status']!='READY'
                    or type(ready['records']) is not int or ready['records']!=99 or ready['config_sha256']!=config_sha):
                raise ValueError('Invalid worker readiness packet')
            return ready
        result=json.loads(trace.read_text('utf-8'))
        validate_worker_result(result,question)
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,subprocess.TimeoutExpired) as exc:
        if check:raise
        result={'trace_id':uuid.uuid4().hex,'captured_at':datetime.now(timezone.utc).isoformat(),
            'question':question if isinstance(question,str) else None,'status':'refused','answer':'现有资料不足以可靠回答这个问题，无法据此给出确定结论。',
            'citations':[],'context':[],'retrieval':None,'generation':None,'generation_attempted':False,
            'refusal_reason':'isolated_worker_failed','error':type(exc).__name__+': '+str(exc),'timing':{}}
    result['timing']['worker_wall_seconds']=time.perf_counter()-started
    return result
