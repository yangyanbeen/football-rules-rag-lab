"""Delivery gate for the Task14–17 audit and the immutable original evidence."""
import argparse
import csv
import io
import json
import subprocess
import sys

from answer_eval_core import ROOT, canonical, digest, now, read, record, write_new
from historical_evidence import git_record
from verify_faiss_hnsw import replay as replay_faiss
from verify_langgraph_replay import replay as replay_graph, validate_row
from verify_query_cache import replay as replay_cache
from verify_task15_delivery import PRIVATE, inventory_valid, pass_count
from task14_archive import verify_archive

BASE = 'a6aaca199ab420fca2af39e58e0fce32e03f1a23'
REPORT = ROOT / 'reports/rechecks/task14-17'
ENTRY = 'TASK-014-017-DELIVERY-AUDIT'
TAG = 'v0.17.1-task14-17-audit'
REGISTRY = 'data/manifests/experiment_manifest.json'
APPEND = ('docs/EXPERIMENT_LOG.md', 'reports/all_experiments_summary.csv', 'reports/resume_evidence.md')
REPAIRED = {
    'scripts/task14_archive.py',
    'scripts/faiss_hnsw_eval.py', 'scripts/run_faiss_hnsw.py', 'scripts/verify_faiss_hnsw.py',
    'scripts/query_cache.py', 'scripts/run_cached_query.py', 'scripts/verify_query_cache.py',
    'scripts/rag_langgraph.py', 'scripts/verify_langgraph_controls.py', 'scripts/verify_langgraph_replay.py',
}
MUTABLE = {*APPEND, *REPAIRED, REGISTRY, 'data/manifests/project_file_manifest.json',
           'README.md', 'reports/README.md', 'docs/DELIVERY_STATUS.md'}
REPLAYS = {'archive-replay.json': 43, 'faiss-replay.json': 17, 'cache-replay.json': 34,
           'graph-replay.json': 18, 'graph-controls.json': 15}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def artifacts():
    return {
        *REPAIRED, 'scripts/historical_evidence.py',
        'scripts/verify_task14_17_regressions.py', 'scripts/verify_task14_17_delivery.py',
        'scripts/verify_task14_show_cli.py', 'scripts/run_task14_17_smoke.py',
        'docs/TASK_14_17_AUDIT.md',
        *{f'reports/rechecks/task14-17/{n}' for n in (
            'before.json', 'regressions-first.json', *REPLAYS, 'archive-cli.json',
            'live-smoke.json', 'native-prior.json', 'redis-fallback.json')},
    }


def before_after():
    old, new = [read(REPORT / name) for name in ('before.json', 'regressions-first.json')]
    source = record(ROOT / 'scripts/verify_task14_17_regressions.py')
    return (old['phase'] == 'legacy_reproduction' and new['phase'] == 'current_regressions'
            and old['status'] == new['status'] == 'PASS' and old['passed'] == 0 and new['passed'] == 18
            and set(old['checks']) == set(new['checks']) and old['total'] == new['total'] == len(new['checks']) == 18
            and all(v is False for v in old['checks'].values()) and all(v is True for v in new['checks'].values())
            and old['producer'] == new['producer'] == source and old['base'] == new['base'] == BASE
            and not new['exceptions'] and all(r['new_model_requests'] == r['new_formal_test_runs']
                                            == r['new_human_judgments'] == 0 for r in (old, new)))


def cli_evidence():
    receipt = read(REPORT / 'archive-cli.json')
    old, new = receipt['legacy'], receipt['current']
    return (receipt['status'] == 'PASS' and old['checkout_commit'] == BASE
            and old['frozen_hash'] == new['frozen_hash'] == record(ROOT / 'reports/task14/archive.json')['sha256']
            and old['valid_lookup'] == new['valid_lookup'] == 1
            and old['tampered_exit_code'] == 0 and old['tampered_value_printed'] == 0
            and new['tampered_exit_code'] != 0 and new['tampered_value_printed'] is None
            and old['restored_clean'] is True and new['restored_clean'] is True)


def smoke_evidence():
    v = read(REPORT / 'live-smoke.json')
    if not pass_count({**v, 'errors': []}, 5) or v['new_formal_test_runs'] or v['new_human_judgments']:
        return False
    if not all(ref == git_record(v['source_commit'], p) == record(ROOT / p) for p, ref in v['source_files'].items()):
        return False
    if len(v['cache']) != 2 or len(v['graph']) != 3:
        return False
    miss, hit = v['cache']
    if ((miss['state'], hit['state'], miss['status'], hit['status']) != ('miss', 'hit', 'answered', 'answered')
            or miss['stored'] != 'stored' or hit['stored'] is not None or hit['private_trace'] is not None
            or miss['answer_sha256'] != hit['answer_sha256'] or miss['citation_hashes'] != hit['citation_hashes']
            or miss['embedding_queries'] != 1 or miss['reranked_pairs'] != 40
            or not 1 <= miss['generation_attempts'] <= 2
            or any(hit[k] for k in ('worker_invocations', 'embedding_queries', 'reranked_pairs', 'generation_attempts'))):
        return False
    known = {r['chunk_id'] for r in read(ROOT / 'data/manifests/dense_chunk_ids.json')}
    cases = {r['id']: r for r in read(ROOT / 'config/task13_demo.json')['cases']}
    return ([r['case'] for r in v['graph']] == ['normal', 'version', 'citation_fault']
            and all(validate_row(v, known, cases) for v in v['graph']))


def private_smoke():
    live = read(REPORT / 'live-smoke.json')
    miss = live['cache'][0]
    old = read(ROOT / miss['private_trace']['path'])
    if (record(ROOT / miss['private_trace']['path']) != miss['private_trace']
            or digest(old['answer'].encode()) != miss['answer_sha256']
            or [digest(canonical(c)) for c in old['citations']] != miss['citation_hashes']):
        return False
    for row in live['graph']:
        path = ROOT / row['trace']['path']
        trace = read(path)
        if (record(path) != row['trace'] or digest(trace['answer'].encode()) != row['answer_sha256']
                or [digest(canonical(c)) for c in trace['citations']] != row['citation_hashes']
                or trace['events'] != row['obs'] or trace['status'] != row['status']
                or trace['request_id'] != row['request_id']):
            return False
    return True


def verify(public_only):
    checks, errors = {}, []

    def check(name, pred):
        try:
            if pred() is not True:
                raise ValueError('Verification predicate failed')
            checks[name] = True
        except Exception as exc:
            checks[name] = False
            errors.append({'check': name, 'error': str(exc)})

    tracked = set(git('ls-files').decode().splitlines())
    original = set(git('ls-tree', '-r', '--name-only', BASE).decode().splitlines())
    changed = set(git('diff', '--name-only', BASE, '--').decode().splitlines())
    check('original_release_paths_authorities_reports_configs_and_formal_data_preserved', lambda: (
        len(original) == 947 and original <= tracked and original & changed <= MUTABLE and REPAIRED <= changed))
    for n in APPEND:
        check(n + '_retains_history', lambda p=n: (ROOT / p).read_bytes().startswith(git('show', BASE + ':' + p)))
    earlier = json.loads(git('show', BASE + ':' + REGISTRY))['experiments']
    records = read(ROOT / REGISTRY)['experiments']
    entry = records[-1]
    check('29_original_registry_entries_remain_exact', lambda: (
        len(earlier) == 29 and canonical(records[:-1]) == canonical(earlier)))
    check('repair_registration_complete_and_artifacts_checkable', lambda: (
        len(records) == 30 and entry['id'] == ENTRY
        and entry['source_commit'] == read(REPORT / 'live-smoke.json')['source_commit']
        and all(entry.get(k) for k in ('objective', 'control', 'main_variable', 'data_version', 'evaluation_version',
           'models', 'parameters', 'hardware', 'commands', 'artifacts', 'metrics', 'decision'))
        and len(entry['artifacts']) == len(artifacts())
        and {r['path'] for r in entry['artifacts']} == artifacts() <= tracked
        and all(record(ROOT / r['path']) == r for r in entry['artifacts'])))
    check('csv_order_matches_registry', lambda: (
        [r['experiment_id'] for r in csv.DictReader(io.StringIO((ROOT / APPEND[1]).read_text('utf-8-sig')))]
        == [r['id'] for r in records]))
    check('eighteen_before_after_mechanism_controls', before_after)
    check('cli_rejects_mutated_value_and_valid_value_still_returns', cli_evidence)
    check('all_recorded_historical_replays_and_actual_controlled_graph_pass', lambda: (
        all(pass_count(read(REPORT / n), size) for n, size in REPLAYS.items())))
    check('current_task14_report_recomputes_exactly_from_original_producer', lambda: verify_archive(
        read(ROOT / 'reports/task14/archive.json')))
    check('current_task15_replays_all_seventeen_historical_checks', lambda: pass_count(replay_faiss(), 17))
    check('current_task16_replays_all_thirty_four_historical_checks', lambda: pass_count(replay_cache(), 34))
    check('current_task17_replays_all_eighteen_historical_checks', lambda: pass_count(replay_graph(), 18))
    check('five_real_smoke_checks_bind_to_repaired_producer', smoke_evidence)
    check('actual_redis_client_fallback_and_unmeasured_server_distinguished', lambda: (
        (lambda r: r['status'] == 'PASS' and r['adapter'] == record(ROOT / 'scripts/query_cache.py')
         and r['redis_client_version'] == '5.2.1' and r['read'] == 'read_bypass' and r['write'] == 'write_bypass'
         and r['source_calls'] == 1 and r['connection'] in ('ConnectionRefusedError', 'TimeoutError')
         and r['redis_server_benchmarked'] is False)(read(REPORT / 'redis-fallback.json'))))
    check('original_faiss_and_cache_private_proofs_recorded', lambda: (
        (lambda r: r['status'] == 'PASS' and len(r['checks']) == 2 and all(v is True for v in r['checks'].values()))
        (read(REPORT / 'native-prior.json'))))
    check('inventory_integrity_matches_current_git_index', lambda: inventory_valid(tracked))
    check('no_private_payload_is_published', lambda: not any(
        path.startswith(tuple(p + '/' for p in PRIVATE)) or path.endswith(('.npy', '.gguf', '.faiss'))
        for path in tracked))
    check('repair_report_and_commands_are_linked', lambda: all(
        word in (ROOT / path).read_text('utf-8') for path, word in (
            ('README.md', 'TASK_14_17_SUPPLEMENT.md'), ('docs/DELIVERY_STATUS.md', 'TASK_14_17_SUPPLEMENT.md'),
            ('reports/TASK_14_17_SUPPLEMENT.md', 'TASK_14_17_AUDIT.md'), (APPEND[0], ENTRY),
            (APPEND[2], 'TASK_14_17_AUDIT.md'))))
    if public_only:
        check('independent_public_only_checkout', lambda: (
            bool(sys.flags.no_site) and not any((ROOT / p).exists() for p in PRIVATE)))
    else:
        check('all_smoke_rows_link_to_actual_private_traces', private_smoke)
        check('original_private_323_snapshots_unchanged', lambda: (
            (lambda v: len(v) == 323 and all(digest((ROOT / p).read_bytes()) == sha for p, sha in v.items()))
            (read(ROOT / '.runtime/task14/before.json')['private'])))
        check('29_prior_tags_unchanged', lambda: (
            (lambda tags: len(tags) == 29 and tags == read(ROOT / '.runtime/task14-17/remote-before.json')['tags'])
            ({ref: sha for sha, ref in (line.split() for line in git('show-ref', '--tags').decode().splitlines())
              if ref != 'refs/tags/' + TAG})))
    return {
        'status': 'PASS' if not errors else 'FAIL', 'task14_17_repairs_accepted': not errors,
        'passed': sum(checks.values()), 'total': len(checks), 'checks': checks, 'errors': errors,
        'captured_at': now(), 'public_only': public_only, 'source_sha256': record(__file__)['sha256'],
        'new_model_requests': 0, 'new_formal_test_runs': 0, 'new_human_judgments': 0,
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--public-only', action='store_true')
    p.add_argument('--report', required=True)
    a = p.parse_args()
    receipt = verify(a.public_only)
    write_new(ROOT / a.report, receipt)
    print(json.dumps({k: receipt[k] for k in ('status', 'passed', 'total', 'errors')}))
    raise SystemExit(receipt['status'] != 'PASS')
