"""Versioned exact query caching with bounded memory and optional Redis storage."""
from collections import OrderedDict
from dataclasses import dataclass
import json
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
    'scripts/answer_eval_engine.py', 'scripts/citation_catalog_guard.py', 'scripts/query_cache.py',
)


def policy():
    return read(CONFIG)


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
    identity = {
        'corpus_version': dense['corpus_version'],
        'corpus_sha256': dense['corpus_sha256'],
        'configuration_and_implementation': {p: record(ROOT / p) for p in DEPENDENCIES},
        'current_index_manifests': {name: record(ROOT / app[name] / 'index_manifest.json')
                                    for name in ('dense_index', 'bm25_index')},
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
        except (ValueError, TypeError, KeyError):
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
        state, result = self.lookup(question)
        if state == 'hit':
            return result, state, None
        # Upstream errors propagate and never create a cache entry.
        result = loader(question)
        return result, state, self.store(question, result)
