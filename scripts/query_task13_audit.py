"""Revised process worker; private traces bind current committed repair sources."""
import argparse,importlib.metadata,sys
from task13_audit import *
from task13_query_rewrite import read_history, resolve_question

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');p.add_argument('--question');p.add_argument('--trace')
    p.add_argument('--history-stdin', action='store_true');a=p.parse_args();cfg=audit_config()
    if a.check and (a.question is not None or a.trace or a.history_stdin):raise ValueError('Readiness does not accept generation input')
    path=(ROOT/a.trace).resolve() if a.trace else None
    if not a.check and (path is None or not path.is_relative_to(ROOT/cfg['private_root']/'workers') or path.exists()):raise ValueError('Use a new private audit worker trace')
    question = normalize_question(a.question) if not a.check else None
    history = read_history(sys.stdin.buffer) if a.history_stdin else []
    upstream_clean();identity=implementation()
    packages={d.metadata['Name']:d.version for d in importlib.metadata.distributions()}
    if packages!=read(ROOT/'reports/task13/environment-final.json')['actual']['packages']:raise ValueError('Runtime packages differ from accepted262 versions')
    import task13_engine
    task13_engine.request_json=request_json
    with task13_engine.IntegratedEngine() as engine:
        if a.check:
            packet={'status':'READY','profile':cfg['version'],'records':99,'implementation':identity}
        else:
            resolution = None
            if history:
                question, resolution = resolve_question(question, history, engine.answer_cfg)
            result = engine.answer(question)
            if resolution is not None:
                result['query_resolution'] = resolution
            result['implementation'] = identity
            validate_private(result, question, True)
    if not a.check:
        write_new(path,result);packet={'status':result['status'],'trace_id':result['trace_id'],'private_trace':record(path)}
    print(json.dumps(packet,ensure_ascii=False))
