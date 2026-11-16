"""Local exact-cache entry point for the audited football question-answer worker."""
import argparse
import json
import sys
import time

from answer_eval_core import ROOT, canonical, digest, git, now, read, record, write_new
from citation_catalog_guard import safe_render
from query_cache import CONFIG, ExactCache, MemoryBackend, RedisBackend, application_scope, policy
from task13_audit import source_map
from task13_audit_client import call_worker
from task13_core import local_corpus


def answer_value(result):
    return {name: result[name] for name in ('status', 'answer', 'citations', 'refusal_reason')}


def validator(sources, render=None):
    if render is None:
        def render(ids):
            return safe_render(ids, local_corpus())

    def cacheable(value):
        if (not isinstance(value, dict) or set(value) != {'status', 'answer', 'citations', 'refusal_reason'}
                or value['status'] != 'answered' or not isinstance(value['answer'], str)
                or not value['answer'] or value['refusal_reason'] is not None):
            return False
        citations = value['citations']
        if not isinstance(citations, list) or not 1 <= len(citations) <= 3:
            return False
        ids = [c.get('chunk_id') for c in citations if isinstance(c, dict)]
        if (len(ids) != len(citations) or any(not isinstance(cid, str) for cid in ids)
                or len(set(ids)) != len(ids)
                or any(canonical(cite) != canonical(sources.get(cid)) for cid, cite in zip(ids, citations))):
            return False
        answer, expected = render(ids)
        return value['answer'] == answer and canonical(citations) == canonical(expected)
    return cacheable


def loader(question):
    result, detail, _ = call_worker(question)
    scored = result['retrieval']['reranker']['results'] if result['retrieval'] else []
    return answer_value(result), {
        'worker_invocations': 1, 'embedding_queries': int(result['retrieval'] is not None),
        'reranked_pairs': len(scored), 'generation_attempts': len(result['attempts']),
        'private_trace': detail,
    }


def session_fetch(backend, epoch, question, load=loader):
    cfg = policy()
    scope = application_scope(epoch)
    cache = ExactCache(backend, scope, validator(source_map()), cfg['max_payload_bytes'])
    observation = {'worker_invocations': 0, 'embedding_queries': 0, 'reranked_pairs': 0,
                   'generation_attempts': 0, 'private_trace': None}

    def upstream(q):
        value, trace = load(q)
        if application_scope(epoch) != scope:
            raise RuntimeError('问答配置在处理中发生变化，请重新提交问题。')
        observation.update(trace)
        return value

    value, state, store = cache.fetch(question, upstream)
    if state == 'hit' and application_scope(epoch) != scope:
        raise RuntimeError('缓存配置在读取期间发生变化，请重新提交问题。')
    return value, state, store, observation


def live(report):
    cases = read(ROOT / 'config/task13_demo.json')['cases']
    question = next(case['question'] for case in cases if case['id'] == 'normal')
    backend = MemoryBackend(policy()['capacity'])
    steps = []
    for mode in ('uncached', 'uncached', 'exact', 'exact'):
        start = time.perf_counter_ns()
        if mode == 'uncached':
            value, timing = loader(question)
            state, store = 'disabled', None
        else:
            value, state, store, timing = session_fetch(backend, 'task16-live', question)
        elapsed = time.perf_counter_ns() - start
        if value['status'] != 'answered':
            raise ValueError('Exact live comparison requires successful answers')
        steps.append({
            'mode': mode, 'cache_state': state, 'store_state': store, 'wall_ns': elapsed,
            'answer_sha256': digest(value['answer'].encode('utf-8')),
            'citation_ids': [c['chunk_id'] for c in value['citations']], **timing,
        })
        print(json.dumps({'mode': mode, 'cache_state': state, 'worker_invocations': timing['worker_invocations']}),
              flush=True)
    if [s['cache_state'] for s in steps] != ['disabled', 'disabled', 'miss', 'hit'] or steps[2]['answer_sha256'] != steps[3]['answer_sha256']:
        raise ValueError('Live cache path did not reuse the original answer')
    counters = ('worker_invocations', 'embedding_queries', 'reranked_pairs', 'generation_attempts')
    totals = {mode: {k: sum(r[k] for r in steps if r['mode'] == mode) for k in counters}
              for mode in ('uncached', 'exact')}
    write_new(report, {
        'status': 'PASS', 'version': 'task16-live-exact-1.0', 'captured_at': now(),
        'source_commit': git('rev-parse', 'HEAD'),
        'configuration': record(CONFIG), 'source': record(__file__),
        'backend': 'memory', 'question_sha256': digest(question.encode('utf-8')),
        'steps': steps, 'totals': totals, 'saved': {k: totals['uncached'][k] - totals['exact'][k] for k in counters},
        'new_formal_test_runs': 0, 'new_human_judgments': 0,
        'scope': 'Ad hoc repeated audited query from Task13 demo. Measures actual worker invocations and API attempts.',
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('memory', 'redis'), default='memory')
    parser.add_argument('--redis-port', type=int, default=6379)
    parser.add_argument('--epoch', default='local')
    parser.add_argument('--live-report', type=str)
    options = parser.parse_args()
    if options.live_report:
        destination = (ROOT / options.live_report).resolve()
        if destination.exists() or not destination.is_relative_to(ROOT / 'reports/task16'):
            parser.error('Use a new report under reports/task16')
        live(destination)
        return
    backend = RedisBackend(options.redis_port) if options.backend == 'redis' else MemoryBackend(policy()['capacity'])
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            value, state, store, _ = session_fetch(backend, options.epoch, line)
            result = {'result': value, 'cache_state': state, 'store_state': store, 'backend': options.backend}
        except (ValueError, RuntimeError, OSError) as exc:
            result = {'error': str(exc), 'backend': options.backend}
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
