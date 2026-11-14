"""Isolated optimized query worker; full traces are private, stdout is a small readiness packet."""
import argparse,sys
from task13_core import *


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--question');p.add_argument('--check',action='store_true');p.add_argument('--trace');a=p.parse_args()
    if a.check and (a.question is not None or a.trace):raise ValueError('Check mode does not accept an answer input')
    path=(ROOT/a.trace).resolve() if a.trace else None
    if not a.check and (path is None or not path.is_relative_to(ROOT/'.runtime/task13') or path.exists()):raise ValueError('Use a new private task13 trace path')
    if not a.check:normalize_question(a.question)
    from task13_engine import IntegratedEngine
    with IntegratedEngine() as engine:
        if a.check:
            print(json.dumps({'status':'READY','profile':engine.cfg['version'],'records':99,'config_sha256':record(ROOT/CONFIG)['sha256']}));return
        result=engine.answer(a.question);validate_result(result,a.question)
    # The worker declares completion only after cleanup and read-only checks.
    write_new(path,result)
    print(json.dumps({'status':result['status'],'trace_id':result['trace_id'],'private_trace':record(path)}))


if __name__=='__main__':main()
