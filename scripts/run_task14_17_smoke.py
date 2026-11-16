"""Exercise the repaired normal cache and graph entry points with pinned local models."""
import argparse
import json
import os
import time

from answer_eval_core import ROOT, canonical, digest, git, now, read, record, write_new
from historical_evidence import git_record
from query_cache import MemoryBackend, policy
from rag_langgraph import Flow
from run_cached_query import session_fetch
from run_langgraph_flow import annotate_case, new_engine, operations, public_record, runtime_identity

FILES = (
    'scripts/query_cache.py', 'scripts/run_cached_query.py', 'scripts/rag_langgraph.py',
    'scripts/run_langgraph_flow.py', 'scripts/run_task14_17_smoke.py',
    'config/query_cache.json', 'config/langgraph_flow.json', 'config/task17-requirements.lock.txt',
)


def smoke():
    source = git('rev-parse', 'HEAD')
    sources = {n: record(ROOT / n) for n in FILES}
    if any(git_record(source, n) != ref for n, ref in sources.items()):
        raise ValueError('Commit the smoke producer and repaired components first')
    cases = {c['id']: c for c in read(ROOT / 'config/task13_demo.json')['cases']}
    runtime_identity()
    question = cases['normal']['question']
    backend = MemoryBackend(policy()['capacity'])
    cache = []
    for _ in range(2):
        start = time.perf_counter_ns()
        value, state, stored, obs = session_fetch(backend, 'task14-17-audit', question)
        cache.append({
            'state': state, 'stored': stored, 'status': value['status'], **obs,
            'answer_sha256': digest(value['answer'].encode()),
            'citation_hashes': [digest(canonical(c)) for c in value['citations']],
            'wall_ns': time.perf_counter_ns() - start,
        })
        print('cache', state, obs['worker_invocations'], flush=True)
    graph = []
    with new_engine() as engine:
        ops = operations(engine)
        flow = Flow(ops)
        for name in ('normal', 'version'):
            definition = cases[name]
            result = flow.invoke(definition['question'])
            graph.append(annotate_case(public_record(result, 'graph', name), result, definition))
            print('graph', name, result['status'], flush=True)
        result = Flow(ops, citation_fault=True).invoke(question)
        failure = public_record(result, 'graph', 'citation_fault')
        failure['case_passed'] = (failure['status']=='failed' and failure['reason']=='citation_invalid'
                                  and failure['fault_applied'] and not failure['citation_hashes'])
        graph.append(failure)
        print('graph', 'citation_fault', result['status'], flush=True)
    checks = {
        'cache_miss_stores_a_source_validated_answer': cache[0]['state']=='miss' and cache[0]['stored']=='stored'
        and cache[0]['status']=='answered' and cache[0]['worker_invocations']==1,
        'cache_hit_preserves_hashes_and_uses_zero_model_requests': cache[1]['state']=='hit'
        and cache[1]['answer_sha256']==cache[0]['answer_sha256']
        and cache[1]['citation_hashes']==cache[0]['citation_hashes']
        and all(cache[1][k]==0 for k in ('worker_invocations','embedding_queries','generation_attempts','reranked_pairs')),
        **{f'graph_{g["case"]}':g['case_passed'] for g in graph},
    }
    return {'status':'PASS' if all(checks.values()) else 'FAIL', 'passed':sum(checks.values()),
            'total':len(checks), 'checks':checks, 'captured_at':now(), 'source_commit':source,
            'source_files':sources, 'cache':cache, 'graph':graph,
            'new_formal_test_runs':0, 'new_human_judgments':0,
            'scope':'Real ad hoc repaired-entry smoke. Citation mutation is controlled and never returned as evidence.'}


if __name__ == '__main__':
    os.environ['LANGSMITH_TRACING'] = 'false'
    os.environ['LANGCHAIN_TRACING_V2'] = 'false'
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', required=True)
    a = p.parse_args()
    path = (ROOT / a.report).resolve()
    if path.exists() or not path.is_relative_to(ROOT / 'reports/rechecks/task14-17'):
        p.error('Use a new JSON report under reports/rechecks/task14-17')
    data = smoke()
    write_new(path, data)
    print(json.dumps({k:data[k] for k in ('status','passed','total')}))
    raise SystemExit(data['status']!='PASS')
