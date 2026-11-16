"""Check the task 16 deliverables, historical protections, and private trace binding."""
import argparse
import csv
import io
import json
import subprocess
import sys

from answer_eval_core import canonical, digest, now, read, record, write_new
from cache_experiment import BASE, REPORT, ROOT, WORKLOAD
from verify_query_cache import replay
from verify_task15_delivery import inventory_valid, pass_count, PRIVATE

REGISTRY = 'data/manifests/experiment_manifest.json'
ENTRY = 'TASK-016-EXACT-SEMANTIC-CACHE'
TAG = 'v0.16.0-query-cache-experiment'
APPEND = ('docs/EXPERIMENT_LOG.md', 'reports/all_experiments_summary.csv', 'reports/resume_evidence.md')
MUTABLE = {*APPEND, REGISTRY, 'data/manifests/project_file_manifest.json', 'README.md',
           'reports/README.md', 'docs/DELIVERY_STATUS.md'}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def artifact_names():
    return {
        'config/query_cache.json', 'data/eval/cache_query_workload_v1.json',
        'docs/TASK_16_SCOPE.md', 'docs/REDIS_CACHE_EXPERIMENT.md',
        'scripts/query_cache.py', 'scripts/cache_experiment.py', 'scripts/run_cache_experiment.py',
        'scripts/run_cached_query.py', 'scripts/verify_query_cache.py', 'scripts/verify_task16_delivery.py',
        *{f'reports/task16/{name}' for name in (
            'holdout-freeze.json', 'live-exact.json', 'redis-availability.json', 'replay-local.json',
            'replay-public.json')},
        *{f'reports/task16/{split}/{name}' for split in ('dev', 'holdout')
          for name in ('observations.json', 'summary.json', 'run_manifest.json')},
    }


def saved_replay(name):
    value = read(REPORT / name)
    ok = (pass_count(value, 34) and value['site_packages_disabled'] is True
          and value['producer'] == record(ROOT / 'scripts/verify_query_cache.py')
          and value['new_model_requests'] == value['new_formal_test_runs'] == value['new_human_judgments'] == 0)
    if name == 'replay-local.json':
        return ok
    checkout = value['public_checkout']
    members = ['scripts/verify_query_cache.py', 'reports/task16/holdout/summary.json',
               'reports/task16/live-exact.json', 'reports/task16/redis-availability.json']
    return (ok and checkout['clean_before_run'] is True and checkout['absent_paths'] == list(PRIVATE)
            and all(git('show', checkout['commit'] + ':' + p) == (ROOT / p).read_bytes() for p in members))


def local_evidence():
    import numpy as np

    for split in ('dev', 'holdout'):
        run = read(REPORT / split / 'run_manifest.json')
        path = ROOT / run['private_embeddings']['path']
        if record(path) != run['private_embeddings']:
            return False
        matrix = np.load(path, allow_pickle=False)
        if (matrix.shape != (24, 1024) or matrix.dtype != np.float32 or not np.isfinite(matrix).all()
                or digest(matrix.tobytes(order='C')) != run['vector_fingerprint']):
            return False

    live = read(REPORT / 'live-exact.json')
    for row in live['steps'][:3]:
        trace_path = ROOT / row['private_trace']['path']
        trace = read(trace_path)
        scored = trace['retrieval']['reranker']['results']
        if (record(trace_path) != row['private_trace']
                or digest(trace['question'].encode('utf-8')) != live['question_sha256']
                or digest(trace['answer'].encode('utf-8')) != row['answer_sha256']
                or len(trace['attempts']) != row['generation_attempts']
                or len(scored) != row['reranked_pairs']
                or [c['chunk_id'] for c in trace['citations']] != row['citation_ids']):
            return False
    return True


def backend_boundaries():
    receipt = read(REPORT / 'redis-availability.json')
    return (
        receipt['status'] == 'PASS' and receipt['benchmark_backend'] == 'memory'
        and receipt['redis_server_available'] is False and receipt['live_redis_performance_measured'] is False
        and receipt['adapter_source'] == record(ROOT / 'scripts/query_cache.py')
        and receipt['redis_client_version'] == '5.2.1'
        and receipt['connection_probe'] in ('ConnectionRefusedError', 'TimeoutError')
        and receipt['read_state'] == 'read_bypass' and receipt['write_state'] == 'write_bypass'
        and receipt['upstream_control_invocations'] == 1 and receipt['probe_wall_ns'] > 0
    )


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
    paths = set(git('ls-tree', '-r', '--name-only', BASE).decode('utf-8').splitlines())
    changed = set(git('diff', '--name-only', BASE, '--').decode('utf-8').splitlines())
    check('907_prior_public_files_and_authority_documents_preserved', lambda: (
        len(paths) == 907 and paths <= tracked and (paths & changed) <= MUTABLE))
    for p in APPEND:
        check(p + '_append_only', lambda: (ROOT / p).read_bytes().startswith(git('show', BASE + ':' + p)))
    old = json.loads(git('show', BASE + ':' + REGISTRY))['experiments']
    entries = read(ROOT / REGISTRY)['experiments']
    added = entries[-1]
    check('27_prior_registry_objects_remain_identical', lambda: (
        len(old) == 27 and canonical(old) == canonical(entries[:-1])))
    check('new_entry_has_scope_models_hardware_sources_commands_and_metrics', lambda: (
        len(entries) == 28 and added['id'] == ENTRY and added['data_version']['workload'] == record(WORKLOAD)
        and all(added.get(key) for key in ('objective', 'control', 'main_variable', 'evaluation_version',
            'producer_commits', 'models', 'hardware', 'parameters', 'commands', 'decision', 'metrics'))))
    check('archive_file_records_match_public_artifacts', lambda: (
        len(added['artifacts']) == len(artifact_names())
        and {r['path'] for r in added['artifacts']} == artifact_names() <= tracked
        and all(record(ROOT / r['path']) == r for r in added['artifacts'])))
    check('csv_ids_match_registry', lambda: (
        [r['experiment_id'] for r in csv.DictReader(io.StringIO((ROOT / APPEND[1]).read_text('utf-8-sig')))]
        == [r['id'] for r in entries]))
    check('redis_unavailable_and_memory_used_explicitly', backend_boundaries)
    check('current_replay_has_all_34_checks', lambda: pass_count(replay(), 34))
    check('actual_local_replay_matches_current_scripts', lambda: saved_replay('replay-local.json'))
    check('isolated_public_replay_matches_current_scripts', lambda: saved_replay('replay-public.json'))
    check('report_and_reproduction_links_present', lambda: all(
        ref in (ROOT / path).read_text('utf-8') for ref, path in (
            ('reports/TASK_16_DELIVERY.md', 'README.md'), ('TASK_16_DELIVERY.md', 'docs/DELIVERY_STATUS.md'),
            ('REDIS_CACHE_EXPERIMENT.md', 'reports/TASK_16_DELIVERY.md'), (ENTRY, APPEND[0]),
            ('REDIS_CACHE_EXPERIMENT.md', APPEND[2]))))
    check('no_private_artifacts_in_public_index', lambda: not any(
        p.startswith(tuple(n + '/' for n in PRIVATE)) or p.endswith(('.npy', '.faiss', '.gguf'))
        for p in tracked))
    check('public_file_inventory_and_hashes_match', lambda: inventory_valid(tracked))
    if public_only:
        check('no_private_state_or_site_packages', lambda: (
            bool(sys.flags.no_site) and not any((ROOT / p).exists() for p in PRIVATE)))
    else:
        check('private_vectors_and_actual_worker_traces_match', local_evidence)
        check('preserved_earlier_private_snapshots_and_faiss_files', lambda: (
            (lambda private: len(private) == 323 and all(
                digest((ROOT / p).read_bytes()) == h for p, h in private.items()))
            (read(ROOT / '.runtime/task14/before.json')['private'])
            and __import__('verify_task15_delivery').native_files()))
        check('27_prior_tags_match', lambda: (
            (lambda tags: len(tags) == 27 and tags == read(ROOT / '.runtime/task16/remote_before.json')['tags'])
            ({ref: sha for sha, ref in (line.split() for line in git('show-ref', '--tags').decode('utf-8').splitlines())
              if ref != 'refs/tags/' + TAG})))
    return {
        'status': 'PASS' if not errors else 'FAIL', 'task16_fully_accepted': not errors,
        'passed': sum(checks.values()), 'total': len(checks), 'checks': checks, 'errors': errors,
        'captured_at': now(), 'public_only': public_only, 'source_sha256': record(__file__)['sha256'],
        'new_model_requests': 0, 'new_formal_test_runs': 0, 'new_human_judgments': 0,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-only', action='store_true')
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    receipt = verify(args.public_only)
    write_new(ROOT / args.report, receipt)
    print(json.dumps({k: receipt[k] for k in ('status', 'passed', 'total', 'errors')}))
    raise SystemExit(receipt['status'] != 'PASS')
