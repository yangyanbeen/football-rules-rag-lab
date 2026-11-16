"""Reproduce and verify repairs across the four final stages, without model requests."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Lock, RLock
from unittest.mock import patch

from answer_eval_core import ROOT, canonical, digest, now, read, record, write_new
import faiss_hnsw_eval as faiss_eval
import query_cache
import run_cached_query
from rag_langgraph import Flow
from verify_langgraph_controls import Fixture, NORMAL, QUESTION, SOURCE, EVIDENCE

REPORT = ROOT / 'reports/rechecks/task14-17'
BASE = 'a6aaca199ab420fca2af39e58e0fce32e03f1a23'


def rejects(call, classes=(ValueError,)):
    try:
        call()
    except classes:
        return True
    return False


def strict_pointer():
    from task14_archive import pointer

    values = {'rows': [10, 20], 'a/b': {'~name': 99}, '~9': 24}
    return (
        pointer(values, '/rows/0') == 10 and pointer(values, '/a~1b/~0name') == 99
        and all(rejects(lambda key=key: pointer(values, '/rows/' + key)) for key in ('-1', '+1', '01', ' 1'))
    )


def pointer_escape():
    from task14_archive import pointer

    return rejects(lambda: pointer({'~9': 1}, '/~9'))


def faiss_policy():
    candidate = deepcopy(read(faiss_eval.CONFIG))
    candidate['threads'] = True
    candidate['methods']['hnsw_s64']['graph'] = 'hnsw_m8'
    with patch.object(faiss_eval, 'read', return_value=candidate):
        return rejects(faiss_eval.config)


def faiss_mapping():
    altered = read(faiss_eval.MAPPING)
    altered[0]['chunk_id'], altered[1]['chunk_id'] = altered[1]['chunk_id'], altered[0]['chunk_id']
    with TemporaryDirectory(dir=ROOT / '.tmp') as path:
        clone = Path(path) / 'dense_chunk_ids.json'
        clone.write_bytes(canonical(altered))
        with patch.object(faiss_eval, 'MAPPING', clone):
            return rejects(faiss_eval.known_ids)


def faiss_development():
    original = ROOT / 'data/eval/retrieval_dev.jsonl'
    lines = original.read_text('utf-8').splitlines()
    row = json.loads(lines[0])
    row['question'] = 'Mutation for the development hash control'
    lines[0] = canonical(row).decode()
    with TemporaryDirectory(dir=ROOT / '.tmp') as path:
        clone = Path(path)
        dev = clone / 'data/eval/retrieval_dev.jsonl'
        dev.parent.mkdir(parents=True)
        dev.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        with patch.object(faiss_eval, 'ROOT', clone):
            return rejects(lambda: faiss_eval.questions('dev'))


def faiss_build_boolean():
    builds = read(ROOT / 'reports/task15/dev/builds.json')
    builds['flat'][0]['repetition'] = True
    return rejects(lambda: faiss_eval.build_summary(faiss_eval.config(), builds))


def cache_for(backend):
    scope = query_cache.Scope.create('test', {'version': 1}, 5000)
    return query_cache.ExactCache(backend, scope, lambda r: isinstance(r, dict) and set(r) == {'answer'})


def corrupt_packet():
    backend = query_cache.MemoryBackend(4)
    cache = cache_for(backend)
    # Within payload byte limit but deeper than Python's JSON parser supports.
    backend.put(cache.scope.key('q'), b'[' * 2000 + b'0' + b']' * 2000, 5000)
    try:
        value, state, stored = cache.fetch('q', lambda _: {'answer': 'fresh'})
    except RecursionError:
        return False
    return (value, state, stored) == ({'answer': 'fresh'}, 'invalid_entry', 'stored')


def scope_changes(rel):
    old = query_cache.application_scope('probe')

    def modified(path):
        value = record(path)
        if value['path'] == rel:
            value['sha256'] = '0' * 64
        return value

    with patch.object(query_cache, 'record', side_effect=modified):
        try:
            return query_cache.application_scope('probe') != old
        except ValueError:
            return True


def cache_policy():
    candidate = deepcopy(read(query_cache.CONFIG))
    candidate['max_payload_bytes'] = True
    candidate['semantic_thresholds'] = [0.85, 2.0]
    with patch.object(query_cache, 'read', return_value=candidate):
        return rejects(query_cache.policy)


def same_key_concurrency():
    backend = query_cache.MemoryBackend(4)
    first_entered, second_entered, release = Event(), Event(), Event()
    lock = Lock()
    invocations = []

    def loader(q):
        with lock:
            invocations.append(q)
            (first_entered if len(invocations) == 1 else second_entered).set()
        if not release.wait(2):
            raise RuntimeError('Control did not release loader')
        return {'answer': 'fresh'}

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(cache_for(backend).fetch, 'q', loader)
        if not first_entered.wait(2):
            release.set()
            return False
        b = pool.submit(cache_for(backend).fetch, 'q', loader)
        second_entered.wait(0.25)
        release.set()
        values = [a.result(timeout=3), b.result(timeout=3)]
    return invocations == ['q'] and [v[1] for v in values] == ['miss', 'hit']


def poisoned_cache_answer():
    data = {'status': 'answered', 'answer': 'altered text', 'citations': [SOURCE], 'refusal_reason': None}
    source = {SOURCE['chunk_id']: SOURCE}
    try:
        validate = run_cached_query.validator(source, lambda _: ('expected text', [SOURCE]))
    except TypeError:
        # Original validator validated citation fields but did not reconstruct the answer.
        return not run_cached_query.validator(source)(data)
    return not validate(data) and validate({**data, 'answer': 'expected text'})


def cache_scope_race():
    data = {'status': 'answered', 'answer': 'checked text', 'citations': [SOURCE], 'refusal_reason': None}
    values = [query_cache.Scope.create('test', {'version': n}, 5000) for n in (1, 2)]
    scope = values[0]
    backend = query_cache.MemoryBackend(4)

    def loader(q):
        nonlocal scope
        scope = values[1]
        return data, {}

    with patch.object(run_cached_query, 'application_scope', side_effect=lambda _: scope):
        with patch.object(run_cached_query, 'source_map', return_value={SOURCE['chunk_id']: SOURCE}):
            with patch.object(run_cached_query, 'validator', return_value=lambda v: v == data):
                result = rejects(lambda: run_cached_query.session_fetch(backend, 'test', 'q', loader), (RuntimeError,))
    return result and backend.get(values[0].key('q')) is None


class VerifiedFixture(Fixture):
    def __init__(self, responses=(NORMAL,), corrupt=False):
        super().__init__(responses)
        self.request_lock = RLock()
        self.completed_embeddings = 0
        self.evidence = {**EVIDENCE, 'content_zh_sha256': digest(EVIDENCE['content_zh'].encode())}
        self.evidence['record_sha256'] = digest(canonical(self.evidence))
        self.sources = {SOURCE['chunk_id']: {**SOURCE,
                                           'content_zh_sha256': self.evidence['content_zh_sha256'],
                                           'record_sha256': self.evidence['record_sha256']}}
        if corrupt:
            self.evidence['content_zh'] = 'Changed context in a controlled test'

    def retrieval(self, question, depth):
        self.completed_embeddings += 1
        return super().retrieval(question, depth)

    def expand(self, ids):
        return [self.evidence for _ in ids]

    def render(self, ids, context):
        return 'controlled test answer', [self.sources[ids[0]]]


def corrupt_graph_context():
    fixture = VerifiedFixture(corrupt=True)
    result = Flow(fixture).invoke(QUESTION)
    return result['status'] == 'failed' and result['chat_calls'] == 0 and result['citations'] == []


def graph_fault_accounting():
    fixture = VerifiedFixture()
    fixture.retrieval_failure = True
    result = Flow(fixture).invoke(QUESTION)
    return result['status'] == 'failed' and result['embedding_queries'] == fixture.completed_embeddings == 1


def graph_concurrency():
    entered, overlapping = Event(), Event()
    lock = Lock()

    class ConcurrentFixture(VerifiedFixture):
        active = 0
        peak = 0

        def generate(self, messages, schema):
            with lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
                self.chat_calls += 1
                (entered if self.chat_calls == 1 else overlapping).set()
            overlapping.wait(0.25)
            with lock:
                self.active -= 1
            return {'message': {'content': json.dumps(NORMAL)}}

    fixture = ConcurrentFixture()
    first, second = Flow(fixture), Flow(fixture)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(first.invoke, QUESTION)
        if not entered.wait(2):
            return False
        b = pool.submit(second.invoke, QUESTION)
        values = [a.result(timeout=5), b.result(timeout=5)]
    return fixture.peak == 1 and all(v['chat_calls'] == 1 and v['embedding_queries'] == 1 for v in values)


def invalid_request_id():
    fixture = VerifiedFixture()
    flow = Flow(fixture)
    refused = [rejects(lambda v=v: flow.invoke(QUESTION, request_id=v)) for v in ('', 1, 0, True)]
    return all(refused) and fixture.chat_calls == 0


def run():
    checks = {
        '14_pointer_indices_follow_json_pointer_grammar': strict_pointer,
        '14_reject_unknown_pointer_escape': pointer_escape,
        '15_reject_drift_in_preregistered_policy': faiss_policy,
        '15_reject_permuted_vector_id_mapping': faiss_mapping,
        '15_reject_changed_development_questions_before_tuning': faiss_development,
        '15_reject_boolean_repeat_number': faiss_build_boolean,
        '16_corrupt_cache_packet_recovers_through_loader': corrupt_packet,
        '16_scope_tracks_embedding_implementation': lambda: scope_changes('scripts/dense_index.py'),
        '16_scope_tracks_corpus_bytes': lambda: scope_changes('data/processed/rag_chunks_zh.jsonl'),
        '16_scope_tracks_index_payload_bytes': lambda: scope_changes(
            'data/indexes/task13/dense-v1/embeddings.npy'),
        '16_reject_invalid_policy_types_and_thresholds': cache_policy,
        '16_same_key_concurrent_miss_loads_once': same_key_concurrency,
        '16_cached_answer_matches_verified_source_render': poisoned_cache_answer,
        '16_version_change_during_load_does_not_cache': cache_scope_race,
        '17_context_integrity_before_model_request': corrupt_graph_context,
        '17_partial_retrieval_preserves_completed_embedding_count': graph_fault_accounting,
        '17_graphs_sharing_engine_have_request_local_counters': graph_concurrency,
        '17_reject_invalid_explicit_request_identifiers': invalid_request_id,
    }
    results = {}
    exceptions = {}
    for name, check in checks.items():
        try:
            results[name] = check() is True
        except Exception as exc:
            results[name] = False
            exceptions[name] = type(exc).__name__ + ': ' + str(exc)
    return results, exceptions


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    parser.add_argument('--baseline', action='store_true')
    options = parser.parse_args()
    results, exceptions = run()
    delivered = all(v is not options.baseline for v in results.values())
    receipt = {'status': 'PASS' if delivered else 'FAIL', 'checked_at': now(),
               'phase': 'legacy_reproduction' if options.baseline else 'current_regressions',
               'checks': results, 'exceptions': exceptions, 'passed': sum(results.values()), 'total': len(results),
               'producer': record(__file__), 'base': BASE,
               'new_model_requests': 0, 'new_formal_test_runs': 0, 'new_human_judgments': 0}
    write_new(ROOT / options.report, receipt)
    print(json.dumps({k: receipt[k] for k in ('status', 'phase', 'passed', 'total', 'checks', 'exceptions')}))
    raise SystemExit(not delivered)
