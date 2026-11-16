"""Verify Task 15 delivery, including the prior release and native artifacts."""
import argparse
import csv
import io
import json
import subprocess
import sys

from answer_eval_core import canonical, digest, now, read, record, write_new
from faiss_hnsw_eval import BASE, REPORT, ROOT, config
from verify_faiss_hnsw import replay

REGISTRY = 'data/manifests/experiment_manifest.json'
INVENTORY = 'data/manifests/project_file_manifest.json'
ENTRY = 'TASK-015-FAISS-HNSW-B0'
APPEND = ('docs/EXPERIMENT_LOG.md', 'reports/all_experiments_summary.csv', 'reports/resume_evidence.md')
MUTABLE = {*APPEND, REGISTRY, INVENTORY, 'README.md', 'docs/DELIVERY_STATUS.md', 'reports/README.md'}
PRIVATE = ('.runtime', '.models', '.venv', 'data/raw', 'data/processed', 'data/indexes', 'third_party')
TAG = 'v0.15.0-faiss-hnsw-benchmark'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def original(path):
    return git('show', f'{BASE}:{path}')


def pass_count(receipt, count):
    return (receipt['status'] == 'PASS' and receipt['passed'] == receipt['total'] == len(receipt['checks']) == count
            and all(v is True for v in receipt['checks'].values()) and not receipt['errors'])


def archive_artifacts():
    return {
        'config/faiss_hnsw_experiment.json', 'scripts/faiss_hnsw_eval.py', 'scripts/run_faiss_hnsw.py',
        'scripts/verify_faiss_hnsw.py', 'scripts/verify_task15_delivery.py',
        'docs/TASK_15_SCOPE.md', 'docs/FAISS_HNSW_EXPERIMENT.md',
        'reports/task15/test-freeze.json', 'reports/task15/replay-local.json', 'reports/task15/replay-public.json',
        *{f'reports/task15/{split}/{name}' for split in ('dev', 'test') for name in (
            'builds.json', 'predictions.jsonl', 'run_manifest.json', 'run_started.json', 'summary.json')},
    }


def inventory_valid(tracked):
    manifest = read(ROOT / INVENTORY)
    items = manifest['files']
    public = [r for r in items if r['distribution'] == 'public-git']
    frozen_local = [r for r in items if r['distribution'] == 'local-only']
    return (
        len(frozen_local) == 61 and set(r['path'] for r in public) == tracked - {INVENTORY}
        and len(items) == manifest['file_count'] == len(tracked) + 60
        and len({r['path'] for r in items}) == len(items)
        and all(record(ROOT / r['path']) == {k: r[k] for k in ('path', 'size_bytes', 'sha256')} for r in public)
    )


def recorded_replay(name):
    receipt = read(REPORT / name)
    valid = (pass_count(receipt, 17) and receipt['site_packages_disabled'] is True
             and receipt['source_sha256'] == record(ROOT / 'scripts/verify_faiss_hnsw.py')['sha256']
             and receipt['run_evidence'] == {split: record(REPORT / split / 'run_manifest.json')
                                             for split in ('dev', 'test')}
             and receipt['new_embedding_requests'] == receipt['new_test_runs'] == 0)
    if name == 'replay-public.json':
        checkout = receipt['public_checkout']
        return (valid and checkout['clean_before_run'] is True
                and checkout['private_paths_absent'] == list(PRIVATE)
                and all(git('show', checkout['commit'] + ':' + r['path']) == (ROOT / r['path']).read_bytes()
                        for r in receipt['run_evidence'].values()))
    return valid


def native_files():
    import numpy as np
    from run_faiss_hnsw import checked_vectors, native, open_indices

    cfg = config()
    faiss, _, _ = native(cfg)
    original_vectors, _ = checked_vectors(cfg, np)
    native_dir = ROOT / '.runtime/task15'
    builds = read(REPORT / 'dev/builds.json')
    for graph, observations in builds.items():
        for build in observations:
            actual = record(native_dir / 'dev' / f'{graph}-{build["repetition"]}.faiss')
            if (actual['sha256'], actual['size_bytes']) != (build['index_sha256'], build['index_bytes']):
                return False
    if set(open_indices(cfg, faiss, np, original_vectors, builds, native_dir / 'dev')) != set(cfg['graphs']):
        return False
    for split, count in [('dev', 40), ('test', 50)]:
        run = read(REPORT / split / 'run_manifest.json')
        path = native_dir / split / 'query_vectors.npy'
        if record(path) != run['query_vector_artifact']:
            return False
        queries = np.load(path, allow_pickle=False)
        if (queries.shape != (count, cfg['dimensions']) or queries.dtype != np.float32
                or not np.isfinite(queries).all()
                or not np.allclose(np.linalg.norm(queries, axis=1), 1, atol=1e-6, rtol=0)
                or digest(queries.tobytes(order='C')) != run['query_vector_fingerprint']):
            return False
    return True


def verify(public_only):
    checks, errors = {}, []

    def check(name, fn):
        try:
            if fn() is not True:
                raise ValueError('Verification predicate failed')
            checks[name] = True
        except Exception as exc:
            checks[name] = False
            errors.append({'check': name, 'error': str(exc)})

    tracked = set(git('ls-files').decode('utf-8').splitlines())
    names = set(git('ls-tree', '-r', '--name-only', BASE).decode('utf-8').splitlines())
    diff = set(git('diff', '--name-only', BASE, '--').decode('utf-8').splitlines())
    check('884_prior_public_paths_and_authority_documents_preserved', lambda: (
        len(names) == 884 and names <= tracked and names & diff <= MUTABLE))
    for path in APPEND:
        check(path + '_append_only', lambda p=path: (ROOT / p).read_bytes().startswith(original(p)))
    old = json.loads(original(REGISTRY))['experiments']
    current = read(ROOT / REGISTRY)['experiments']
    entry = current[-1]
    check('26_original_registry_entries_equal', lambda: (
        len(old) == 26 and canonical(current[:-1]) == canonical(old)))
    check('one_complete_new_registration', lambda: (
        len(current) == 27 and entry['id'] == ENTRY
        and all(entry.get(k) for k in ('objective', 'control', 'main_variable', 'data_version',
            'evaluation_version', 'producer_commits', 'models', 'parameters', 'hardware', 'commands', 'artifacts',
            'metrics', 'decision'))
        and entry['producer_commits'] == {split: read(REPORT / split / 'run_manifest.json')['source_commit']
                                          for split in ('dev', 'test')}))
    check('new_artifact_hashes_and_paths_match', lambda: (
        len(entry['artifacts']) == len(archive_artifacts())
        and {r['path'] for r in entry['artifacts']} == archive_artifacts() <= tracked
        and all(record(ROOT / r['path']) == r for r in entry['artifacts'])))
    check('csv_order_matches_registry', lambda: (
        [r['experiment_id'] for r in csv.DictReader(io.StringIO((ROOT / APPEND[1]).read_text('utf-8-sig')))]
        == [r['id'] for r in current]))
    check('four_baseline_metrics_and_documentation_delivered', lambda: (
        all(p in (ROOT / f).read_text('utf-8') for p, f in (
            ('reports/TASK_15_DELIVERY.md', 'README.md'), ('TASK_15_DELIVERY.md', 'docs/DELIVERY_STATUS.md'),
            ('FAISS_HNSW_EXPERIMENT.md', 'reports/TASK_15_DELIVERY.md'), (ENTRY, APPEND[0]),
            ('FAISS_HNSW_EXPERIMENT.md', APPEND[2])))
        and all(k in entry['metrics'] for k in ('recall_at_5', 'query_p50_ms', 'query_p95_ms', 'graphs'))))
    check('no_vector_model_or_private_payload_tracked', lambda: not any(
        n.startswith(tuple(p + '/' for p in PRIVATE)) or n.endswith(('.faiss', '.npy', '.npz', '.gguf'))
        for n in tracked))
    check('current_file_inventory_exact', lambda: inventory_valid(tracked))
    check('all_17_replay_checks_pass_with_current_code', lambda: pass_count(replay(), 17))
    check('local_saved_replay_passed', lambda: recorded_replay('replay-local.json'))
    check('clean_public_replay_passed', lambda: recorded_replay('replay-public.json'))
    check('task14_archive_is_still_reproducible', lambda: subprocess.run(
        [sys.executable, '-S', '-B', 'scripts/task14_archive.py', 'verify'], cwd=ROOT, capture_output=True).returncode == 0)
    if public_only:
        check('no_site_packages_or_private_artifacts_public_checkout', lambda: (
            bool(sys.flags.no_site) and not any((ROOT / p).exists() for p in PRIVATE)))
    else:
        check('native_graph_and_query_snapshots_match_saved_evidence', native_files)
        check('323_prior_private_snapshots_remain_identical', lambda: (
            (lambda prior: len(prior) == 323 and all(digest((ROOT / p).read_bytes()) == h for p, h in prior.items()))
            (read(ROOT / '.runtime/task14/before.json')['private'])))
        check('26_prior_tags_remain_identical', lambda: (
            (lambda tags: len(tags) == 26 and tags == read(ROOT / '.runtime/task15/remote_before.json')['tags'])
            ({ref: sha for sha, ref in (line.split() for line in git('show-ref', '--tags').decode('utf-8').splitlines())
              if ref != 'refs/tags/' + TAG})))
    return {
        'status': 'PASS' if not errors else 'FAIL', 'task15_fully_accepted': not errors,
        'passed': sum(checks.values()), 'total': len(checks), 'checks': checks, 'errors': errors,
        'captured_at': now(), 'public_only': public_only, 'source_sha256': record(__file__)['sha256'],
        'new_embedding_requests': 0, 'new_test_runs': 0,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-only', action='store_true')
    parser.add_argument('--report', required=True)
    arguments = parser.parse_args()
    result = verify(arguments.public_only)
    write_new(ROOT / arguments.report, result)
    print(json.dumps({k: result[k] for k in ('status', 'passed', 'total', 'errors')}))
    raise SystemExit(result['status'] != 'PASS')
