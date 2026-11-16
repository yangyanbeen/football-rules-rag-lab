"""Replay Task17 traces using only public evidence and the standard library."""
import argparse
from copy import deepcopy
from datetime import datetime
import json
import re
import subprocess
import sys

from answer_eval_core import ROOT, digest, read, record, write_new

REPORT = ROOT / 'reports/task17'
BASE = '415cba9407573942362ba00d5571d8f9904fae94'
CONFIG = ROOT / 'config/langgraph_flow.json'
LOCK = ROOT / 'config/task17-requirements.lock.txt'
NODES = ['route', 'version_check', 'retrieve', 'fuse', 'rerank', 'expand_context',
         'check_evidence', 'answer', 'check_citations', 'refusal', 'finish']
PAIRS = [('normal', 'linear'), ('normal', 'graph'), ('outside', 'graph'),
         ('outside', 'linear'), ('version', 'linear'), ('version', 'graph'), ('citation_fault', 'graph')]
ROW_FIELDS = {
    'request_id', 'question_sha256', 'status', 'reason', 'error_kind', 'selected_ids',
    'retrieved_ids', 'offered_ids', 'fault_applied', 'embedding_queries', 'reranked_pairs',
    'chat_calls', 'wall_ns', 'attempts', 'mode', 'case', 'answer_sha256', 'citation_hashes',
    'trace', 'obs', 'case_passed',
}
EVENT_FIELDS = {'request_id', 'seq', 'node', 'elapsed_ns', 'reason', 'retry', 'answer_attempts'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def hex_value(value, digits=64):
    return isinstance(value, str) and re.fullmatch(f'[a-f0-9]{{{digits}}}', value) is not None


def validate_event_trace(events, request, expected, wall_ns=None):
    require([e['node'] for e in events] == expected, 'Unexpected node sequence')
    for i, event in enumerate(events, 1):
        require(set(event) == EVENT_FIELDS and event['request_id'] == request
                and type(event['seq']) is int and event['seq'] == i, 'Unbound trace event')
        require(type(event['elapsed_ns']) is int and event['elapsed_ns'] > 0
                and type(event['retry']) is bool and type(event['answer_attempts']) is int
                and 0 <= event['answer_attempts'] <= 2, 'Invalid event timing or retry metadata')
    if wall_ns is not None:
        require(sum(e['elapsed_ns'] for e in events) <= wall_ns, 'Node durations exceed total time')
    answer = [e for e in events if e['node'] == 'answer']
    require([e['answer_attempts'] for e in answer] == list(range(1, len(answer) + 1)),
            'Answer attempt sequence differs')
    require([e['retry'] for e in answer] == ([True] * (len(answer) - 1) + [False] if answer else []),
            'Retry edge contradicts attempts')


def validate_row(row, known, cases):
    require(set(row) == ROW_FIELDS, 'Public row contains unknown or missing fields')
    require(hex_value(row['request_id'], 32) and hex_value(row['question_sha256'])
            and hex_value(row['answer_sha256']), 'Invalid public request identification')
    require(row['case_passed'] is True and type(row['fault_applied']) is bool, 'Case failed')
    expected = {'normal': ('answered', None), 'outside': ('refused', 'insufficient_evidence'),
                'version': ('refused', 'version_unverified'), 'citation_fault': ('failed', 'citation_invalid')}
    require((row['status'], row['reason']) == expected[row['case']] and row['error_kind'] is None,
            'Unexpected user result semantics')
    case = cases['normal' if row['case'] == 'citation_fault' else row['case']]
    require(digest(case['question'].strip().encode('utf-8')) == row['question_sha256'], 'Wrong query id')
    ids = row['selected_ids']
    for name, limit in [('selected_ids', 3), ('offered_ids', 5), ('retrieved_ids', 10)]:
        value = row[name]
        require(isinstance(value, list) and len(value) <= limit and len(set(value)) == len(value)
                and all(key in known for key in value), 'Unknown or duplicate evidence ID')
    require(set(ids) <= set(row['offered_ids']) <= set(row['retrieved_ids']), 'Evidence containment differs')
    require((row['status'] == 'answered') == bool(ids)
            and len(row['citation_hashes']) == len(ids) and all(hex_value(v) for v in row['citation_hashes']),
            'Unexpected citations for status')
    require(row['fault_applied'] == (row['case'] == 'citation_fault'), 'Incorrect fault disposition')
    ref = row['trace']
    require(set(ref) == {'path', 'size_bytes', 'sha256'} and hex_value(ref['sha256'])
            and ref['path'] == '.runtime/task17/traces/' + row['request_id'] + '.json'
            and type(ref['size_bytes']) is int and ref['size_bytes'] > 0, 'Wrong private trace link')
    require(all(type(row[k]) is int and row[k] >= 0 for k in ('wall_ns', 'embedding_queries', 'reranked_pairs', 'chat_calls'))
            and row['wall_ns'] > 0, 'Invalid resource clocks/counts')
    attempts = row['attempts']
    require(0 <= len(attempts) <= 2 and len(attempts) == row['chat_calls'], 'Retry or chat budget exceeded')
    for i, a in enumerate(attempts, 1):
        require(set(a) == {'attempt', 'chat_calls', 'outcome'} and type(a['attempt']) is int and a['attempt'] == i
                and type(a['chat_calls']) is int and a['chat_calls'] == 1
                and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,50}', a['outcome']), 'Invalid attempt metadata')
    if row['case'] == 'version':
        require(not attempts and not row['retrieved_ids'] and row['embedding_queries'] == row['reranked_pairs'] == 0,
                'Unsupported version consumed inference')
    else:
        require(row['embedding_queries'] == 1 and row['reranked_pairs'] == 40 and attempts
                and attempts[-1]['outcome'] == 'accepted', 'Incomplete successful downstream run')
    if row['mode'] == 'graph':
        if row['case'] == 'version':
            nodes = ['route', 'version_check', 'refusal', 'finish']
        else:
            nodes = [*NODES[:7], *(['answer'] * len(attempts))]
            if row['case'] in ('normal', 'citation_fault'):
                nodes.append('check_citations')
            if row['status'] != 'answered':
                nodes.append('refusal')
            nodes.append('finish')
        validate_event_trace(row['obs'], row['request_id'], nodes, row['wall_ns'])
        if row['fault_applied']:
            cite = next(e for e in row['obs'] if e['node'] == 'check_citations')
            require(cite['reason'] == 'citation_invalid', 'Missing citation rejection event')
    else:
        require(row['mode'] == 'linear', 'Unknown mode')
        stages = row['obs']
        require(set(stages) == {'retrieval_seconds', 'generation_seconds', 'total_seconds'}
                and all(type(v) in (int, float) and 0 <= v <= row['wall_ns'] / 1e9 for v in stages.values()),
                'Invalid original chain spans')
    return True


def graph_edges(topology):
    edges = {('__start__', 'route', False), ('finish', '__end__', False), ('refusal', 'finish', False),
             ('answer', 'answer', True), ('answer', 'check_citations', True), ('answer', 'refusal', True),
             ('check_citations', 'finish', True), ('check_citations', 'refusal', True)}
    for previous, following in zip(NODES[:7], NODES[1:8]):
        edges.add((previous, following, True))
        edges.add((previous, 'refusal', True))
    actual = {(e['source'], e['target'], e['conditional']) for e in topology['edges']}
    return topology['nodes'] == NODES and topology['recursion_limit'] == 24 and len(topology['edges']) == len(edges) and actual == edges


def replay():
    checks, errors = {}, []

    def check(name, pred):
        try:
            require(pred() is True, 'Verification predicate failed')
            checks[name] = True
        except Exception as exc:
            checks[name] = False
            errors.append({'check': name, 'error': str(exc)})

    live = read(REPORT / 'live-comparison.json')
    controls = read(REPORT / 'controls.json')
    rows = live['rows']
    known = {r['chunk_id'] for r in read(ROOT / 'data/manifests/dense_chunk_ids.json')}
    cases = {r['id']: r for r in read(ROOT / 'config/task13_demo.json')['cases']}
    check('real_seven_runs_match_frozen_order_and_case_results', lambda: (
        live['status'] == 'PASS' and live['passed'] == live['total'] == 7
        and [(r['case'], r['mode']) for r in rows] == PAIRS
        and len({r['request_id'] for r in rows}) == 7
        and datetime.fromisoformat(live['started_at']) <= datetime.fromisoformat(live['completed_at'])))
    check('actual_graph_topology_matches_reviewed_11_nodes_and_22_edges', lambda: graph_edges(live['topology']))
    check('all_public_traces_replay_and_bind_request_ids', lambda: all(validate_row(r, known, cases) for r in rows))
    check('normal_outputs_and_source_hashes_agree_across_paths', lambda: (
        rows[0]['answer_sha256'] == rows[1]['answer_sha256'] and rows[0]['selected_ids'] == rows[1]['selected_ids'] == ['L01-03']
        and rows[0]['citation_hashes'] == rows[1]['citation_hashes']))
    check('normal_and_outside_run_same_model_budgets', lambda: all(
        rows[a][k] == rows[b][k] for a, b in ((0, 1), (2, 3))
        for k in ('chat_calls', 'embedding_queries', 'reranked_pairs')))

    def producer():
        commit = live['producer_commit']
        if subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'],
                          cwd=ROOT, capture_output=True).returncode:
            return False
        return all(
            ref == record(ROOT / p) and ref['sha256'] == digest(
                subprocess.check_output(['git', 'show', commit + ':' + p], cwd=ROOT))
            for p, ref in live['sources'].items()) and len(live['sources']) == 12

    check('real_run_commit_and_runtime_sources_match', producer)
    check('exact_isolated_dependency_lock_and_positive_setup_and_compile_time', lambda: (
        live['environment']['package_lock'] == record(LOCK)
        and live['environment']['packages'] == dict(x.split('==') for x in LOCK.read_text('utf-8').splitlines())
        and live['environment']['packages']['langgraph'] == read(CONFIG)['langgraph_version']
        and len(live['environment']['packages']) == 112 and live['setup_ns'] > 0 and live['compile_ns'] > 0))
    check('synthetic_compiled_controls_and_sources_match', lambda: (
        controls['status'] == 'PASS' and controls['passed'] == controls['total'] == len(controls['checks']) == 15
        and all(v is True for v in controls['checks'].values()) and not controls['errors']
        and controls['producer'] == record(ROOT / 'scripts/verify_langgraph_controls.py')
        and controls['flow_source'] == record(ROOT / 'scripts/rag_langgraph.py')))
    check('retry_and_failure_controls_keep_two_attempt_ceiling', lambda: (
        controls['cases']['model_format_retry_then_success']['chat_calls'] == 2
        and controls['cases']['format_retries_stop_at_two']['chat_calls'] == 2
        and controls['cases']['format_retries_stop_at_two']['status'] == 'failed'
        and controls['cases']['post_identity_error_is_terminal']['chat_calls'] == 1
        and controls['cases']['retry_cannot_exceed_prompt_budget']['chat_calls'] == 1
        and controls['cases']['preflight_failure_makes_no_chat_request']['chat_calls'] == 0))
    check('new_experiments_do_not_change_formal_test_or_human_ledger', lambda: all(
        r['new_formal_test_runs'] == r['new_human_judgments'] == 0 for r in (live, controls))
        and controls['new_model_requests'] == 0)

    def bad(row_no, edit):
        bad_row = deepcopy(rows[row_no])
        edit(bad_row)
        try:
            validate_row(bad_row, known, cases)
        except ValueError:
            return True
        return False

    for name, index, edit in (
        ('unredacted_answer', 1, lambda r: r.update(answer='private')),
        ('unbound_trace_path', 1, lambda r: r['trace'].update(path='elsewhere.json')),
        ('unbound_node_id', 1, lambda r: r['obs'][0].update(request_id='0' * 32)),
        ('citation_check_skipped', 1, lambda r: r['obs'].pop(-2)),
        ('citation_leaked_on_failure', 6, lambda r: r.update(citation_hashes=['0' * 64])),
        ('inflated_retries', 1, lambda r: r.update(chat_calls=3)),
        ('version_hits_embedding', 5, lambda r: r.update(embedding_queries=1)),
        ('fabricated_wall_clock', 1, lambda r: r.update(wall_ns=1)),
    ):
        check('reject_' + name, lambda: bad(index, edit))
    return {
        'status': 'PASS' if not errors else 'FAIL', 'passed': sum(checks.values()),
        'total': len(checks), 'checks': checks, 'errors': errors, 'site_packages_disabled': bool(sys.flags.no_site),
        'producer': record(__file__), 'live_report': record(REPORT / 'live-comparison.json'),
        'controlled_report': record(REPORT / 'controls.json'),
        'new_model_requests': 0, 'new_formal_test_runs': 0, 'new_human_judgments': 0,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    receipt = replay()
    write_new(ROOT / args.report, receipt)
    print(json.dumps({k: receipt[k] for k in ('status', 'passed', 'total', 'errors')}))
    raise SystemExit(receipt['status'] != 'PASS')
