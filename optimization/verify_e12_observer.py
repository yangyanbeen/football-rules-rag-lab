"""Verify observation preserves the original worker lock and return/errors."""
import concurrent.futures,json,threading,time
from pathlib import Path
from types import SimpleNamespace
from e12_observed_ui import instrument
ROOT=Path(__file__).resolve().parents[1]
def main():
    out=ROOT/'.runtime/phase2/e12-observer-check';out.mkdir(exist_ok=False)
    client=SimpleNamespace(LOCK=threading.RLock());state=dict(active=0,peak=0)
    started=threading.Event();sentinel=object()
    def original(question):
        with client.LOCK:
            state['active']+=1;state['peak']=max(state['peak'],state['active'])
            started.set()
            try:
                time.sleep(.08)
                if question=='error':raise LookupError('fixture')
                return sentinel
            finally:state['active']-=1
    client.call_worker=original;instrument(client,out/'events.jsonl')
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        a=pool.submit(client.call_worker,'first');assert started.wait(1)
        b=pool.submit(client.call_worker,'second');assert a.result() is sentinel and b.result() is sentinel
    assert state['peak']==1
    try:client.call_worker('error')
    except LookupError as exc:assert str(exc)=='fixture'
    else:raise AssertionError('Exception was changed')
    rows=[json.loads(v) for v in (out/'events.jsonl').read_text().splitlines()]
    by={}
    for r in rows:by.setdefault(r['request_id'],{})[r['kind']]=r
    assert len(by)==3
    waits=[(r['lock_acquired']['wall_ns']-r['lock_wait']['wall_ns'])/1e9 for r in by.values()]
    assert max(waits)>.03 and all(r['lock_released']['wall_ns']>=r['lock_acquired']['wall_ns'] for r in by.values())
    print(json.dumps(dict(passed=4,return_identity_preserved=True,exception_preserved=True,
        original_lock_serialization_preserved=True,independent_request_clocks=True,max_observed_wait_seconds=max(waits),model_calls=0)))
if __name__=='__main__':main()
