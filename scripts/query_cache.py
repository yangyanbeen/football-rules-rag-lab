"""Versioned exact query caching with bounded memory and optional Redis storage."""
from collections import OrderedDict
from dataclasses import dataclass
import json
import math
import re
import threading
import time

from answer_eval_core import ROOT, canonical, digest, read, record

CONFIG = ROOT / 'config/query_cache.json'
DEPENDENCIES = (
    'config/task13_audit.json', 'config/task13_app.json', 'config/dense_index.json',
    'config/answer_evaluation.json', 'config/answer_evaluation_system.txt',
    'config/reranker_experiment.json', 'config/citation_catalog_notes.json',
    'data/manifests/task13_citation_sources.json', 'reports/task13/index-rebuild.json',
    'reports/task13/delivery_manifest.json',
    'scripts/task13_engine.py', 'scripts/task13_audit.py', 'scripts/query_task13_audit.py',
    'scripts/task13_core.py', 'scripts/task13_audit_client.py', 'scripts/run_cached_query.py',
    'scripts/answer_eval_core.py', 'scripts/answer_eval_engine.py', 'scripts/answer_json_chat.py',
    'scripts/answer_review_v2.py', 'scripts/citation_catalog_guard.py', 'scripts/query_cache.py',
    'scripts/bm25_index.py', 'scripts/dense_index.py', 'scripts/dense_retrieval_eval.py',
    'scripts/rag_b0.py', 'scripts/reranker_live.py', 'scripts/reranker_eval.py',
    'scripts/bge_reranker.py', 'scripts/rrf.py', 'config/bm25_b0.json', 'config/bm25_dependency.json',
    'config/bm25_userdict.txt', 'config/bm25_stopwords.txt',
)
FLIGHTS = tuple(threading.RLock() for _ in range(64))


def policy():
    cfg = read(CONFIG)
    fields = {'version', 'ttl_ms', 'capacity', 'max_payload_bytes', 'semantic_thresholds',
              'warm_probe_repetitions'}
    if not isinstance(cfg, dict) or set(cfg) != fields or cfg['version'] != 'football-query-cache-v1':
        raise ValueError('Invalid cache policy')
    limits = {'ttl_ms': 86_400_000, 'capacity': 4096, 'max_payload_bytes': 1_048_576,
              'warm_probe_repetitions': 4096}
    if any(type(cfg[k]) is not int or not 0 < cfg[k] <= limit for k, limit in limits.items()):
        raise ValueError('Cache policy limits must be positive integers in range')
    values = cfg['semantic_thresholds']
    if (not isinstance(values, list) or not values or len(values) > 100
            or any(type(x) not in (int, float) or not 0 < x <= 1 or not math.isfinite(x) for x in values)
            or values != sorted(set(values))):
        raise ValueError('Semantic thresholds must be unique, ascending values in (0, 1]')
    return cfg


def normalized(question):
    # Same normalization as the underlying audited answer worker.
    if not isinstance(question, str) or not question.strip() or len(question.encode('utf-8')) > 1200:
        raise ValueError('Question must be nonblank text within 1200 UTF-8 bytes')
    return question.strip()


@dataclass(frozen=True)
class Scope:
    epoch: str
    identity: str
    ttl_ms: int

    @classmethod
    def create(cls, epoch, identity, ttl_ms):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,40}', epoch):
            raise ValueError('Use a short cache epoch with letters, digits, hyphens or underscores')
        if type(ttl_ms) is not int or not 0 < ttl_ms <= 86_400_000:
            raise ValueError('Invalid cache lifetime')
        return cls(epoch, digest(canonical(identity)), ttl_ms)

    @property
    def prefix(self):
        return f'football-qcache:v1:{self.epoch}:{self.identity}:px{self.ttl_ms}:'

    def key(self, question):
        return self.prefix + digest(normalized(question).encode('utf-8'))


def application_scope(epoch):
    cfg = policy()
    dense = read(ROOT / 'config/dense_index.json')
    app = read(ROOT / 'config/task13_app.json')
    corpus = record(ROOT / app['corpus'])
    if corpus['sha256'] != dense['corpus_sha256']:
        raise ValueError('The current corpus does not match the frozen version')
    index_assets = {}
    for name in ('dense_index', 'bm25_index'):
        index = (ROOT / app[name]).resolve()
        if not index.is_relative_to(ROOT / 'data/indexes') or not (index / 'index_manifest.json').is_file():
            raise ValueError('The current index is missing or outside the index directory')
        index_assets[name] = [record(p) for p in sorted(index.rglob('*')) if p.is_file()]
    identity = {
        'corpus_version': dense['corpus_version'],
        'corpus_sha256': dense['corpus_sha256'],
        'corpus_file': corpus,
        'configuration_and_implementation': {p: record(ROOT / p) for p in DEPENDENCIES},
        'current_index_assets': index_assets,
        'cache_policy': cfg,
    }
    return Scope.create(epoch, identity, cfg['ttl_ms'])


class MemoryBackend:
    """Thread-safe bounded LRU with a fixed monotonic expiry."""
    def __init__(self, capacity, clock=time.monotonic_ns):
        if type(capacity) is not int or capacity < 1:
            raise ValueError('Invalid memory cache capacity')
        self.capacity = capacity
        self.clock = clock
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            entry = self.entries.get(key)
            if entry is None:
                return None
            expires, value = entry
            if self.clock() >= expires:
                del self.entries[key]
                return None
            self.entries.move_to_end(key)
            return value

    def put(self, key, value, ttl_ms):
        with self.lock:
            self.entries[key] = (self.clock() + ttl_ms * 1_000_000, value)
            self.entries.move_to_end(key)
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)


class CacheUnavailable(RuntimeError):
    """Cache backend is temporarily unavailable."""


class RedisBackend:
    """A single trusted loopback Redis instance with connection and read timeouts."""
    def __init__(self, port=6379, database=0):
        import redis

        self.client = redis.Redis(host='127.0.0.1', port=port, db=database, decode_responses=False,
                                  socket_timeout=0.25, socket_connect_timeout=0.25)
        self.backend_error = redis.exceptions.RedisError

    def get(self, key):
        try:
            return self.client.get(key)
        except self.backend_error as exc:
            raise CacheUnavailable('Redis GET failed') from exc

    def put(self, key, value, ttl_ms):
        try:
            if self.client.set(key, value, px=ttl_ms) is not True:
                raise CacheUnavailable('Redis SET did not acknowledge the write')
        except self.backend_error as exc:
            raise CacheUnavailable('Redis SET failed') from exc


class ExactCache:
    def __init__(self, backend, scope, validate, payload_limit=65536):
        self.backend = backend
        self.scope = scope
        self.validate = validate
        self.payload_limit = payload_limit

    def lookup(self, question):
        key = self.scope.key(question)
        try:
            raw = self.backend.get(key)
        except CacheUnavailable:
            return 'read_bypass', None
        if raw is None:
            return 'miss', None
        try:
            if type(raw) is not bytes or len(raw) > self.payload_limit:
                raise ValueError('Invalid cache packet size')
            packet = json.loads(raw)
            result = packet['result']
            if (set(packet) != {'key', 'result', 'sha256'} or packet['key'] != key
                    or digest(canonical(result)) != packet['sha256'] or self.validate(result) is not True):
                raise ValueError('Unexpected cache packet identity')
        except (ValueError, TypeError, KeyError, RecursionError):
            return 'invalid_entry', None
        return 'hit', result

    def store(self, question, result):
        if self.validate(result) is not True:
            return 'not_cacheable'
        key = self.scope.key(question)
        packet = canonical({'key': key, 'result': result, 'sha256': digest(canonical(result))})
        if len(packet) > self.payload_limit:
            return 'not_cacheable'
        try:
            self.backend.put(key, packet, self.scope.ttl_ms)
        except CacheUnavailable:
            return 'write_bypass'
        return 'stored'

    def fetch(self, question, loader):
        question = normalized(question)
        bucket = int(self.scope.key(question)[-8:], 16) % len(FLIGHTS)
        with FLIGHTS[bucket]:
            state, result = self.lookup(question)
            if state == 'hit':
                return result, state, None
            result = loader(question)
            return result, state, self.store(question, result)
