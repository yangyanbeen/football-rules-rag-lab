"""Verify Task17 delivery, historical artifacts and private trace linkage."""
import argparse
import csv
import io
import json
import subprocess
import sys

from answer_eval_core import canonical, digest, now, read, record, write_new
from verify_langgraph_replay import BASE, REPORT, ROOT, replay
from verify_task15_delivery import inventory_valid, native_files, pass_count, PRIVATE
from verify_task16_delivery import local_evidence

REGISTRY = 'data/manifests/experiment_manifest.json'
ENTRY = 'TASK-017-LANGGRAPH-ORCHESTRATION'
TAG = 'v0.17.0-langgraph-flow'
APPEND = ('docs/EXPERIMENT_LOG.md', 'reports/all_experiments_summary.csv', 'reports/resume_evidence.md')
MUTABLE = {*APPEND, REGISTRY, 'data/manifests/project_file_manifest.json',
           'README.md', 'reports/README.md', 'docs/DELIVERY_STATUS.md'}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def artifacts():
    return {
        'config/langgraph_flow.json', 'config/task17-requirements.lock.txt',
        'docs/TASK_17_SCOPE.md', 'docs/LANGGRAPH_FLOW.md',
        'scripts/rag_langgraph.py', 'scripts/run_langgraph_flow.py', 'scripts/verify_langgraph_controls.py',
        'scripts/verify_langgraph_replay.py', 'scripts/verify_task17_delivery.py',
        *{f'reports/task17/{name}' for name in (
            'live-comparison.json', 'controls.json', 'replay-local.json', 'replay-public.json')},
    }


def replay_receipt(name):
    r = read(REPORT / name)
    proof = (
        pass_count(r, 18) and r['site_packages_disabled'] is True
        and r['producer'] == record(ROOT / 'scripts/verify_langgraph_replay.py')
        and r['live_report'] == record(REPORT / 'live-comparison.json')
        and r['controlled_report'] == record(REPORT / 'controls.json')
        and r['new_model_requests'] == r['new_formal_test_runs'] == r['new_human_judgments'] == 0
    )
    if name == 'replay-local.json':
        return proof
    public = r['public_checkout']
    names = [r['producer']['path'], r['live_report']['path'], r['controlled_report']['path']]
    return (proof and public['clean_before_run'] is True and public['private_paths_absent'] == list(PRIVATE)
            and all(git('show', public['commit'] + ':' + n) == (ROOT / n).read_bytes() for n in names))


def private_traces():
    runs = read(REPORT / 'live-comparison.json')['rows']
    known = read(ROOT / 'data/manifests/task13_citation_sources.json')['sources']
    for row in runs:
        path = ROOT / row['trace']['path']
        trace = read(path)
        if record(path) != row['trace'] or digest(trace['answer'].encode('utf-8')) != row['answer_sha256']:
            return False
        if any(row[key] != trace[key] for key in (
            'request_id', 'question_sha256', 'status', 'reason', 'selected_ids', 'offered_ids', 'retrieved_ids',
            'embedding_queries', 'reranked_pairs', 'chat_calls', 'attempts', 'fault_applied', 'wall_ns',
        )):
            return False
        if row['citation_hashes'] != [digest(canonical(c)) for c in trace['citations']]:
            return False
        if any(canonical(c) != canonical(known[c['chunk_id']]) for c in trace['citations']):
            return False
        if trace['status'] != 'answered' and (trace['citations'] or trace['selected_ids']):
            return False
        if trace['status'] == 'failed' and 'corrupted' in trace['answer']:
            return False
        if row['obs'] != trace['events' if row['mode'] == 'graph' else 'stages']:
            return False
    return len(runs) == 7


def verify(public_only):
    checks, errors = {}, []

    def check(name, predicate):
        try:
            if predicate() is not True:
                raise ValueError('Verification predicate failed')
            checks[name] = True
        except Exception as exc:
            checks[name] = False
            errors.append({'check': name, 'error': str(exc)})

    tracked = set(git('ls-files').decode('utf-8').splitlines())
    prior = set(git('ls-tree', '-r', '--name-only', BASE).decode('utf-8').splitlines())
    changed = set(git('diff', '--name-only', BASE, '--').decode('utf-8').splitlines())
    check('931_prior_public_files_and_two_authority_documents_preserved', lambda: (
        len(prior) == 931 and prior <= tracked and prior & changed <= MUTABLE))
    for n in APPEND:
        check(n + '_append_only', lambda p=n: (ROOT / p).read_bytes().startswith(git('show', BASE + ':' + p)))
    old = json.loads(git('show', BASE + ':' + REGISTRY))['experiments']
    registry = read(ROOT / REGISTRY)['experiments']
    added = registry[-1]
    check('28_prior_experiment_records_preserved', lambda: (
        len(old) == 28 and canonical(old) == canonical(registry[:-1])))
    check('new_experiment_entry_fields_metrics_and_actual_producer_complete', lambda: (
        len(registry) == 29 and added['id'] == ENTRY
        and added['source_commit'] == read(REPORT / 'live-comparison.json')['producer_commit']
        and all(added.get(k) for k in ('objective', 'control', 'main_variable', 'data_version',
            'evaluation_version', 'models', 'parameters', 'hardware', 'commands', 'metrics', 'decision'))))
    check('every_registered_delivery_artifact_matches_index_and_hashes', lambda: (
        len(added['artifacts']) == len(artifacts())
        and {r['path'] for r in added['artifacts']} == artifacts() <= tracked
        and all(record(ROOT / r['path']) == r for r in added['artifacts'])))
    check('csv_order_matches_29_experiments', lambda: (
        [r['experiment_id'] for r in csv.DictReader(io.StringIO((ROOT / APPEND[1]).read_text('utf-8-sig')))]
        == [row['id'] for row in registry]))
    check('result_links_task17_and_compatibility_with_task16', lambda: (
        read(ROOT / 'reports/task16/delivery-final.json')['task16_fully_accepted'] is True
        and all(ref in (ROOT / p).read_text('utf-8') for p, ref in (
            ('README.md', 'reports/TASK_17_DELIVERY.md'), ('docs/DELIVERY_STATUS.md', 'TASK_17_DELIVERY.md'),
            ('reports/TASK_17_DELIVERY.md', 'LANGGRAPH_FLOW.md'), (APPEND[0], ENTRY), (APPEND[2], 'LANGGRAPH_FLOW.md')))))
    check('recompute_actual_and_controlled_trace_evidence', lambda: pass_count(replay(), 18))
    check('local_replay_receipt_bound_to_current_files', lambda: replay_receipt('replay-local.json'))
    check('public_replay_receipt_bound_to_current_files', lambda: replay_receipt('replay-public.json'))
    check('public_inventory_and_hashes_match', lambda: inventory_valid(tracked))
    check('no_private_bodies_vectors_or_runtime_traces_tracked', lambda: not any(
        path.startswith(tuple(p + '/' for p in PRIVATE)) or path.endswith(('.gguf', '.npy', '.faiss'))
        for path in tracked))
    check('actual_resource_totals_and_quality_boundaries_match', lambda: (
        (lambda rows, metrics: all(
            metrics['actual_requests'][k] == sum(r[k] for r in rows)
            for k in ('embedding_queries', 'reranked_pairs', 'chat_calls')))
        (read(REPORT / 'live-comparison.json')['rows'], added['metrics'])
        and added['metrics']['new_formal_test_runs'] == added['metrics']['new_human_judgments'] == 0))
    if public_only:
        check('stdlib_only_clean_public_checkout', lambda: (
            bool(sys.flags.no_site) and not any((ROOT / p).exists() for p in PRIVATE)))
    else:
        check('all_seven_private_traces_bound_to_verified_sources', private_traces)
        check('frozen_323_private_snapshots_and_task15_16_proofs_match', lambda: (
            (lambda before: len(before) == 323 and all(digest((ROOT / p).read_bytes()) == h for p, h in before.items()))
            (read(ROOT / '.runtime/task14/before.json')['private']) and native_files() and local_evidence()))
        check('28_previous_tags_preserved', lambda: (
            (lambda tags: len(tags) == 28 and tags == read(ROOT / '.runtime/task17/remote_before.json')['tags'])
            ({ref: sha for sha, ref in (line.split() for line in git('show-ref', '--tags').decode('utf-8').splitlines())
              if ref != 'refs/tags/' + TAG})))
    return {
        'status': 'PASS' if not errors else 'FAIL', 'task17_fully_accepted': not errors,
        'passed': sum(checks.values()), 'total': len(checks), 'checks': checks, 'errors': errors,
        'captured_at': now(), 'public_only': public_only, 'source_sha256': record(__file__)['sha256'],
        'new_model_requests': 0, 'new_formal_test_runs': 0, 'new_human_judgments': 0,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-only', action='store_true')
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    r = verify(args.public_only)
    write_new(ROOT / args.report, r)
    print(json.dumps({k: r[k] for k in ('status', 'passed', 'total', 'errors')}))
    raise SystemExit(r['status'] != 'PASS')
