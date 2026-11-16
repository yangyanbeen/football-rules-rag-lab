"""Exercise cache contracts and replay measured evidence without models or Redis."""
import argparse
from copy import deepcopy
from datetime import datetime
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

from answer_eval_core import canonical, digest, read, record, write_new
from cache_experiment import REPORT, ROOT, WORKLOAD, SemanticIndex, choose, nearest, source_records, summarize, workload
from historical_evidence import git_record
from query_cache import CONFIG, CacheUnavailable, ExactCache, MemoryBackend, RedisBackend, Scope, policy
from run_cache_experiment import FREEZE, dev_records
from run_cached_query import validator


def source_at(commit, path):
    if subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'], cwd=ROOT,
                      capture_output=True).returncode:
        raise ValueError('Evidence producer is not an ancestor')
    return subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT)


class Clock:
    value = 0

    def __call__(self):
        return self.value

    def advance_ms(self, value):
        self.value += value * 1_000_000


def controls(check):
    scope = Scope.create('u1', {'corpus': 'c1', 'model': 'm1', 'retrieval': 'r1'}, 100)
    clock = Clock()
    backend = MemoryBackend(2, clock)
    cache = ExactCache(backend, scope, lambda result: set(result) == {'id'})
    calls = []

    def load(question):
        calls.append(question)
        return {'id': question}

    check('miss_stores_loader_result', lambda: cache.fetch('goal', load) == ({'id': 'goal'}, 'miss', 'stored'))
    check('trim_is_exact_hit_without_loader', lambda: (
        cache.fetch(' goal ', load) == ({'id': 'goal'}, 'hit', None) and calls == ['goal']))
    check('changed_negation_remains_an_exact_miss', lambda: cache.lookup('not goal') == ('miss', None))
    check('key_hashes_question_without_plaintext', lambda: scope.key('goal').endswith(digest(b'goal'))
          and 'goal' not in scope.key('goal'))
    clock.advance_ms(99)
    check('valid_before_ttl_boundary', lambda: cache.lookup('goal')[0] == 'hit')
    clock.advance_ms(1)
    check('ttl_is_absolute_and_non_sliding', lambda: cache.lookup('goal') == ('miss', None))

    cache.store('goal', {'id': 'goal'})
    check('different_epoch_cannot_read_value', lambda: (
        ExactCache(backend, Scope('u2', scope.identity, 100), cache.validate).lookup('goal') == ('miss', None)))
    check('ttl_policy_is_keyed', lambda: (
        ExactCache(backend, Scope('u1', scope.identity, 200), cache.validate).lookup('goal') == ('miss', None)))
    for dimension in ('corpus', 'model', 'retrieval'):
        identity = {'corpus': 'c1', 'model': 'm1', 'retrieval': 'r1'}
        identity[dimension] += '-changed'
        check(dimension + '_version_isolation', lambda: (
            ExactCache(backend, Scope.create('u1', identity, 100), cache.validate).lookup('goal') == ('miss', None)))
    value = cache.lookup('goal')[1]
    value['id'] = 'changed'
    check('caller_mutation_cannot_modify_cached_value', lambda: cache.lookup('goal')[1] == {'id': 'goal'})
    cache.store('post', {'id': 'post'})
    cache.lookup('goal')
    cache.store('penalty', {'id': 'penalty'})
    check('bounded_lru_eviction', lambda: cache.lookup('post')[0] == 'miss' and len(backend.entries) == 2)
    backend.put(scope.key('penalty'), b'{"unexpected":true}', 100)
    check('corrupt_entry_is_recomputed', lambda: cache.fetch('penalty', load)[1:] == ('invalid_entry', 'stored'))
    packet = backend.get(scope.key('penalty'))
    backend.put(scope.key('goal'), packet, 100)
    check('wrong_key_payload_rejected', lambda: cache.lookup('goal') == ('invalid_entry', None))

    def error(_):
        raise RuntimeError('upstream failure')

    def upstream_failure():
        try:
            cache.fetch('failure', error)
        except RuntimeError:
            return cache.lookup('failure') == ('miss', None)
        return False

    check('upstream_error_never_cached', upstream_failure)
    check('uncacheable_value_is_not_written', lambda: cache.fetch('refuse', lambda _: {'refused': True})
          == ({'refused': True}, 'miss', 'not_cacheable'))

    class Down:
        def get(self, key):
            raise CacheUnavailable('test backend read')

        def put(self, key, value, ttl_ms):
            raise CacheUnavailable('test backend write')

    check('backend_failure_routes_to_upstream', lambda: ExactCache(Down(), scope, cache.validate).fetch('goal', load)
          == ({'id': 'goal'}, 'read_bypass', 'write_bypass'))
    check('oversized_answer_bypasses_store', lambda: (
        ExactCache(backend, scope, cache.validate, 100).store('oversized', {'id': 'x' * 256}) == 'not_cacheable'))
    source = {'chunk_id': 'ID-1', 'license_url': 'source'}
    eligible = validator({'ID-1': source}, lambda _: ('fixture', [source]))
    check('answer_requires_validated_content_and_citation', lambda: (
        eligible({'status': 'answered', 'answer': 'fixture', 'citations': [source], 'refusal_reason': None})
        and not eligible({'status': 'answered', 'answer': 'fixture', 'citations': [{'chunk_id': 'ID-1'}],
                          'refusal_reason': None})
        and not eligible({'status': 'refused', 'answer': 'fixture', 'citations': [], 'refusal_reason': 'reason'})))

    def redis_protocol():
        events = []

        class FakeError(Exception):
            pass

        def connect(**kwargs):
            events.append(('connect', kwargs))
            return SimpleNamespace(
                get=lambda key: (events.append(('get', key)), b'value')[1],
                set=lambda key, value, **kw: (events.append(('set', key, value, kw)), True)[1])
        module = SimpleNamespace(Redis=connect, exceptions=SimpleNamespace(RedisError=FakeError))
        with patch.dict(sys.modules, {'redis': module}):
            adapter = RedisBackend(port=6385)
            adapter.put('isolated', b'value', 100)
            result = adapter.get('isolated')
        return (events[0][1]['host'] == '127.0.0.1' and events[0][1]['port'] == 6385
                and events[1] == ('set', 'isolated', b'value', {'px': 100})
                and events[2] == ('get', 'isolated') and result == b'value')

    check('redis_adapter_uses_bound_loopback_and_atomic_px_contract', redis_protocol)

    semantic = SemanticIndex(2, clock)
    vector = [1] + [0] * 1023
    semantic.put(scope, 'b', vector)
    semantic.put(scope, 'a', vector)
    check('semantic_threshold_inclusion_and_deterministic_tie', lambda: nearest(semantic.rank(scope, vector), 1.0) == 'a')
    check('semantic_namespace_isolation', lambda: semantic.rank(Scope('private', scope.identity, 100), vector) == {})
    clock.advance_ms(100)
    check('semantic_ttl_expiry', lambda: semantic.rank(scope, vector) == {})


def live_matches():
    live = read(REPORT / 'live-exact.json')
    steps = live['steps']
    counters = ('worker_invocations', 'embedding_queries', 'reranked_pairs', 'generation_attempts')
    by_mode = {m: {k: sum(r[k] for r in steps if r['mode'] == m) for k in counters}
               for m in ('uncached', 'exact')}
    source = live['source']['path']
    return (
        live['status'] == 'PASS' and live['backend'] == 'memory' and len(steps) == 4
        and [r['mode'] for r in steps] == ['uncached', 'uncached', 'exact', 'exact']
        and [r['cache_state'] for r in steps] == ['disabled', 'disabled', 'miss', 'hit']
        and [r['store_state'] for r in steps] == [None, None, 'stored', None]
        and [r['worker_invocations'] for r in steps] == [1, 1, 1, 0]
        and [r['embedding_queries'] for r in steps] == [1, 1, 1, 0]
        and live['totals'] == by_mode and by_mode['uncached']['worker_invocations'] == 2
        and live['saved'] == {k: by_mode['uncached'][k] - by_mode['exact'][k] for k in counters}
        and all(r['citation_ids'] and r['wall_ns'] > 0 for r in steps)
        and steps[2]['answer_sha256'] == steps[3]['answer_sha256']
        and steps[2]['citation_ids'] == steps[3]['citation_ids']
        and steps[3]['private_trace'] is None
        and len({r['private_trace']['sha256'] for r in steps[:3]}) == 3
        and source == 'scripts/run_cached_query.py' and git_record(live['source_commit'], source) == live['source']
        and live['configuration'] == record(CONFIG)
        and live['new_formal_test_runs'] == live['new_human_judgments'] == 0
    )


def measurement(split):
    folder = REPORT / split
    observations = read(folder / 'observations.json')
    summary = read(folder / 'summary.json')
    run = read(folder / 'run_manifest.json')
    pin = read(ROOT / 'config/dense_index.json')['model']
    return (
        canonical(summarize(workload(split), observations)) == canonical(summary)
        and set(run['source_files']) == set(source_records())
        and all(git_record(run['source_commit'], p) == r for p, r in run['source_files'].items())
        and run['observations'] == record(folder / 'observations.json')
        and run['summary'] == record(folder / 'summary.json')
        and run['split'] == split and run['status'] == 'COMPLETE' and run['backend'] == 'memory'
        and run['anchors'] == 6 and run['probes'] == run['embedding_inputs'] == 24
        and len(run['embedding_batches']) == 6 and sum(b['inputs'] for b in run['embedding_batches']) == 24
        and run['embedding_model']['digest'] == run['embedding_runtime']['digest'] == pin['digest']
        and run['embedding_model']['ollama_version'] == pin['ollama_version']
        and run['embedding_runtime']['size_vram'] == 0 and run['batch_encoding_wall_ns'] > 0
        and run['workload'] == record(WORKLOAD)
        and run['new_answer_requests'] == run['new_formal_test_runs'] == run['new_human_judgments'] == 0
    )


def freeze_matches():
    grant = read(FREEZE)
    dev = read(REPORT / 'dev/run_manifest.json')
    holdout = read(REPORT / 'holdout/run_manifest.json')
    times = (dev['completed_at'], grant['prepared_at'], holdout['started_at'], holdout['completed_at'])
    return (
        grant['used_holdout_for_selection'] is False
        and grant['source_files'] == dev['source_files'] == holdout['source_files']
        and grant['development'] == dev_records()
        and all(digest(source_at(grant['development_commit'], r['path'])) == r['sha256']
                for r in grant['development'].values())
        and grant['workload'] == record(WORKLOAD) and dev['freeze'] is None and dev['selection'] is None
        and grant['selection'] == choose(read(REPORT / 'dev/summary.json')) == holdout['selection']
        and holdout['freeze'] == record(FREEZE)
        and digest(source_at(holdout['source_commit'], holdout['freeze']['path'])) == holdout['freeze']['sha256']
        and list(map(datetime.fromisoformat, times)) == sorted(map(datetime.fromisoformat, times))
    )


def replay():
    checks, errors = {}, []

    def check(name, predicate):
        try:
            if predicate() is not True:
                raise ValueError('Verification predicate failed')
            checks[name] = True
        except Exception as exc:
            checks[name] = False
            errors.append({'check': name, 'error': str(exc)})

    controls(check)
    check('real_exact_hit_reuses_answer_with_unchanged_citations_and_zero_worker', live_matches)
    for split in ('dev', 'holdout'):
        check(split + '_model_free_metrics_and_measurement_provenance', lambda: measurement(split))
    check('development_threshold_frozen_before_holdout', freeze_matches)

    def mutation(change):
        data = deepcopy(read(REPORT / 'holdout/observations.json'))
        change(data)
        try:
            summarize(workload('holdout'), data)
        except ValueError:
            return True
        return False

    for name, change in {
        'missing_probe': lambda data: data.pop(),
        'fabricated_exact_hit': lambda data: data[2].update(exact_match='H1'),
        'vector_leak': lambda data: data[0].update(embedding=[0] * 1024),
        'invalid_similarity': lambda data: data[1]['scores'].update(H1=1.1),
        'invalid_clock_type': lambda data: data[0]['exact_ns'].__setitem__(0, True),
        'incomplete_samples': lambda data: data[1]['semantic_rank_ns'].pop(),
    }.items():
        check('reject_' + name, lambda: mutation(change))
    return {
        'status': 'PASS' if not errors else 'FAIL', 'passed': sum(checks.values()), 'total': len(checks),
        'checks': checks, 'errors': errors, 'site_packages_disabled': bool(sys.flags.no_site),
        'producer': record(__file__), 'new_model_requests': 0, 'new_formal_test_runs': 0, 'new_human_judgments': 0,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    result = replay()
    write_new(ROOT / args.report, result)
    print(json.dumps({k: result[k] for k in ('status', 'passed', 'total', 'errors')}))
    raise SystemExit(result['status'] != 'PASS')
