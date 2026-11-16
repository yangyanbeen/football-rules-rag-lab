"""Local Task17 query entry point and actual comparison with the audited chain."""
import argparse
import importlib.metadata
import json
import os
import platform
import subprocess
import time

from answer_eval_core import ROOT, canonical, digest, git, now, read, record, write_new
from rag_langgraph import CONFIG, CountingChat, Flow, NODES, Operations, policy
from task13_core import normalize_question

REPORT = ROOT / 'reports/task17'
LOCK = ROOT / 'config/task17-requirements.lock.txt'
FILES = (
    'config/langgraph_flow.json', 'config/task17-requirements.lock.txt',
    'scripts/rag_langgraph.py', 'scripts/run_langgraph_flow.py',
    'scripts/task13_engine.py', 'scripts/task13_audit.py', 'scripts/rrf.py',
    'config/task13_demo.json', 'config/task13_app.json', 'config/reranker_experiment.json',
    'config/dense_index.json', 'config/answer_evaluation.json',
)


def runtime_identity():
    expected = dict(line.split('==', 1) for line in LOCK.read_text('utf-8').splitlines() if line)
    actual = {d.metadata['Name'].lower().replace('_', '-'): d.version for d in importlib.metadata.distributions()}
    if expected != actual or actual['langgraph'] != policy()['langgraph_version']:
        raise ValueError('Use the isolated environment with the exact Task17 package lock')
    return {'python': platform.python_version(), 'system': platform.platform(),
            'processor': platform.processor(), 'packages': expected, 'package_lock': record(LOCK)}


def committed_inputs():
    sha = git('rev-parse', 'HEAD')
    records = {name: record(ROOT / name) for name in FILES}
    for name, ref in records.items():
        if digest(subprocess.check_output(['git', 'show', f'{sha}:{name}'], cwd=ROOT)) != ref['sha256']:
            raise ValueError('Commit Task17 experiment sources first: ' + name)
    return sha, records


def new_engine():
    import task13_engine
    from task13_audit import request_json

    # This is the same request adapter used by the audited linear worker.
    task13_engine.request_json = request_json
    return task13_engine.IntegratedEngine()


def operations(engine):
    from task13_audit import source_map

    engine.chat = CountingChat(engine.chat)
    return Operations(engine.retriever, engine.chat, engine.answer_cfg, engine.prompt, source_map())


def public_record(value, mode, case):
    request = value['request_id']
    path = ROOT / policy()['trace_root'] / (request + '.json')
    write_new(path, value)
    ref = {
        key: value[key] for key in (
            'request_id', 'question_sha256', 'status', 'reason', 'error_kind', 'selected_ids',
            'retrieved_ids', 'offered_ids', 'fault_applied', 'embedding_queries', 'reranked_pairs',
            'chat_calls', 'wall_ns', 'attempts',
        )
    }
    return {**ref, 'mode': mode, 'case': case, 'answer_sha256': digest(value['answer'].encode('utf-8')),
            'citation_hashes': [digest(canonical(c)) for c in value['citations']],
            'trace': record(path), 'obs': value['events'] if mode == 'graph' else value['stages']}


def linear(engine, ops, question):
    from task13_audit import validate_private

    start = time.perf_counter_ns()
    before = ops.chat_calls
    result = engine.answer(question)
    validate_private(result, question)
    actual = ops.chat_calls - before
    if result['error'] is not None or len(result['attempts']) != actual:
        raise ValueError('Linear comparison failed or its attempt count does not match recorded API requests')
    return {
        'request_id': result['trace_id'], 'question_sha256': digest(question.encode('utf-8')),
        'status': result['status'], 'reason': result['refusal_reason'], 'error_kind': None,
        'answer': result['answer'], 'citations': result['citations'], 'selected_ids': result['selected_ids'],
        'retrieved_ids': result['retrieved_ids'], 'offered_ids': result['offered_ids'],
        'fault_applied': False, 'embedding_queries': int(result['retrieval'] is not None),
        'reranked_pairs': len(result['retrieval']['reranker']['results']) if result['retrieval'] else 0,
        'chat_calls': actual, 'wall_ns': time.perf_counter_ns() - start, 'stages': result['timing'],
        'attempts': [{'attempt': a['attempt'], 'chat_calls': 1, 'outcome': 'accepted' if a['error'] is None else 'rejected'}
                     for a in result['attempts']],
    }


def annotate_case(row, result, case):
    row['case_passed'] = (
        row['status'] == case['expected_status'] and row['error_kind'] is None
        and (case['required_source'] is None or case['required_source'] in row['selected_ids'])
        and all(literal in result['answer'] for literal in case['required_literals'])
        and bool(result['citations']) == (result['status'] == 'answered')
    )
    return row


def live_comparison(out):
    from task13_core import source_identity

    sha, inputs = committed_inputs()
    environment = runtime_identity()
    cases = {c['id']: c for c in read(ROOT / 'config/task13_demo.json')['cases']}
    rows = []
    started = now()
    begin = time.perf_counter_ns()
    with new_engine() as engine:
        ops = operations(engine)
        setup_ns = time.perf_counter_ns() - begin
        begin = time.perf_counter_ns()
        flow = Flow(ops)
        compile_ns = time.perf_counter_ns() - begin
        topology = flow.compiled.get_graph()
        edges = [{'source': e.source, 'target': e.target, 'conditional': e.conditional} for e in topology.edges]
        for pos, case_id in enumerate(policy()['comparison_cases']):
            case = cases[case_id]
            q = normalize_question(case['question'])
            order = ('linear', 'graph') if pos % 2 == 0 else ('graph', 'linear')
            for mode in order:
                result = linear(engine, ops, q) if mode == 'linear' else flow.invoke(q)
                row = annotate_case(public_record(result, mode, case_id), result, case)
                rows.append(row)
                print(json.dumps({'case': case_id, 'mode': mode, 'status': row['status'],
                                  'wall_ns': row['wall_ns'], 'passed': row['case_passed']}), flush=True)
        case = cases['normal']
        fault_flow = Flow(ops, citation_fault=True)
        result = fault_flow.invoke(case['question'])
        row = public_record(result, 'graph', 'citation_fault')
        row['case_passed'] = (row['status'] == 'failed' and row['reason'] == 'citation_invalid'
                              and row['fault_applied'] and not result['citations'] and not result['selected_ids']
                              and row['chat_calls'] >= 1)
        rows.append(row)
        print(json.dumps({'case': 'citation_fault', 'status': row['status'], 'passed': row['case_passed']}), flush=True)
    passed = sum(row['case_passed'] is True for row in rows)
    receipt = {
        'version': 'task17-live-comparison-1.0', 'status': 'PASS' if passed == len(rows) else 'FAIL',
        'passed': passed, 'total': len(rows), 'started_at': started, 'completed_at': now(),
        'producer_commit': sha, 'sources': inputs, 'configuration': source_identity(), 'environment': environment,
        'setup_ns': setup_ns, 'compile_ns': compile_ns,
        'topology': {'nodes': list(NODES), 'edges': edges, 'recursion_limit': policy()['recursion_limit']},
        'new_formal_test_runs': 0, 'new_human_judgments': 0, 'rows': rows,
        'scope': 'Sequential actual ad hoc examples; shared engine, fixed model configuration and alternating order.',
    }
    write_new(out, receipt)
    return receipt['status'] == 'PASS'


def main():
    os.environ['LANGSMITH_TRACING'] = 'false'
    os.environ['LANGCHAIN_TRACING_V2'] = 'false'
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--question')
    mode.add_argument('--live-report')
    args = parser.parse_args()
    if args.live_report:
        output = (ROOT / args.live_report).resolve()
        if not output.is_relative_to(REPORT) or output.exists():
            parser.error('Use a new report under reports/task17')
        return 0 if live_comparison(output) else 1
    question = normalize_question(args.question)
    runtime_identity()
    with new_engine() as engine:
        result = Flow(operations(engine)).invoke(question)
    row = public_record(result, 'graph', 'local_query')
    print(json.dumps({'request_id': row['request_id'], 'status': row['status'], 'reason': row['reason'],
                      'answer': result['answer'], 'citations': result['citations'], 'trace': row['trace']},
                     ensure_ascii=False))
    return 2 if row['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
