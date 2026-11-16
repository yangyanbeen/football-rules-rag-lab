"""Semantic match scoring and model-free cache workload aggregation."""
from dataclasses import dataclass
from math import fsum, isfinite, sqrt
import time

from answer_eval_core import ROOT, read, record
from dense_retrieval_eval import percentile
from query_cache import normalized, policy

BASE = '362bdc84f3f748bebfb38bb3cdb7dba649b981a9'
WORKLOAD = ROOT / 'data/eval/cache_query_workload_v1.json'
REPORT = ROOT / 'reports/task16'
SOURCES = ('scripts/query_cache.py', 'scripts/cache_experiment.py', 'scripts/run_cache_experiment.py',
           'scripts/run_cached_query.py', 'config/query_cache.json',
           'config/dense_index.json', 'data/eval/cache_query_workload_v1.json')


def source_records():
    return {name: record(ROOT / name) for name in SOURCES}


def unit_vector(values):
    vector = tuple(values)
    if len(vector) != 1024 or any(type(v) not in (int, float) or not isfinite(v) for v in vector):
        raise ValueError('Expected 1024 finite numeric vector dimensions')
    scale = sqrt(fsum(v * v for v in vector))
    if not isfinite(scale) or scale <= 0:
        raise ValueError('Expected a nonzero finite norm')
    return tuple(v / scale for v in vector)


@dataclass(frozen=True)
class Anchor:
    scope: str
    vector: tuple
    expires_ns: int


class SemanticIndex:
    """Bounded single-process vector cache used only by the experiment."""
    def __init__(self, capacity, clock=time.monotonic_ns):
        self.capacity = capacity
        self.clock = clock
        self.entries = {}

    def put(self, scope, anchor_id, vector):
        key = scope.prefix, anchor_id
        self.entries.pop(key, None)
        self.entries[key] = Anchor(scope.prefix, unit_vector(vector),
                                   self.clock() + scope.ttl_ms * 1_000_000)
        if len(self.entries) > self.capacity:
            self.entries.pop(next(iter(self.entries)))

    def rank(self, scope, values):
        vector = unit_vector(values)
        now = self.clock()
        scores = {}
        for key, entry in list(self.entries.items()):
            if now >= entry.expires_ns:
                del self.entries[key]
            elif entry.scope == scope.prefix:
                dot = fsum(a * b for a, b in zip(vector, entry.vector))
                scores[key[1]] = max(-1.0, min(1.0, dot))
        return scores


def workload(split):
    package = read(WORKLOAD)
    if package['version'] != 'football-cache-workload-v1':
        raise ValueError('Unknown workload version')
    data = package['splits'][split]
    anchors = {a['id']: normalized(a['question']) for a in data['anchors']}
    probes = data['probes']
    if len(data['anchors']) != len(anchors) or len(anchors) != 6:
        raise ValueError('Expected six unique anchor IDs')
    if len(set(anchors.values())) != 6 or len(probes) != 24 or len({p['id'] for p in probes}) != 24:
        raise ValueError('Duplicate anchor question or invalid probes')
    for row in probes:
        target, kind = row['accepted_anchor'], row['kind']
        is_exact = normalized(row['question']) in anchors.values()
        if kind == 'exact':
            valid = anchors.get(target) == normalized(row['question'])
        elif kind == 'paraphrase':
            valid = target in anchors and not is_exact
        else:
            valid = kind == 'near_negative' and target is None and not is_exact
        if not valid or not row['reason']:
            raise ValueError('Inconsistent authored reuse label')
    return data


def clocks(durations):
    if not durations:
        return {'samples': 0, 'p50_ms': None, 'p95_ms': None}
    return {'samples': len(durations), 'p50_ms': percentile(durations, .50) / 1e6,
            'p95_ms': percentile(durations, .95) / 1e6}


def nearest(scores, threshold):
    if not scores:
        return None
    winner = min(scores, key=lambda name: (-scores[name], name))
    return winner if scores[winner] >= threshold else None


def validate_observations(data, observations):
    anchors = {a['id']: normalized(a['question']) for a in data['anchors']}
    reps = policy()['warm_probe_repetitions']
    if [r['id'] for r in observations] != [r['id'] for r in data['probes']]:
        raise ValueError('Missing, reordered or duplicated workload probes')
    for probe, row in zip(data['probes'], observations):
        if set(row) != {'id', 'exact_match', 'exact_ns', 'semantic_rank_ns', 'scores'}:
            raise ValueError('Unknown public measurement fields')
        matches = [aid for aid, query in anchors.items() if normalized(probe['question']) == query]
        exact_match = matches[0] if matches else None
        if row['exact_match'] != exact_match:
            raise ValueError('Exact match conflicts with normalized query keys')
        scores = row['scores']
        if set(scores) != (set() if exact_match else set(anchors)):
            raise ValueError('Semantic scores do not cover eligible candidates')
        if any(type(s) not in (float, int) or not isfinite(s) or not -1 <= s <= 1 for s in scores.values()):
            raise ValueError('Invalid similarity score')
        if (len(row['exact_ns']) != reps or len(row['semantic_rank_ns']) != (0 if exact_match else reps)
                or any(type(n) is not int or n <= 0 for n in row['exact_ns'] + row['semantic_rank_ns'])):
            raise ValueError('Invalid lookup clock')


def summarize(data, observations):
    validate_observations(data, observations)
    methods = ['exact', *policy()['semantic_thresholds']]
    output = {}
    total = len(observations)
    for threshold in methods:
        exact_only = threshold == 'exact'
        hit_ns, miss_ns, errors, outcomes = [], [], [], []
        hit_count = 0
        right = 0
        added = 0
        safe_positives = 0
        for case, row in zip(data['probes'], observations):
            target = case['accepted_anchor']
            safe_positives += target is not None
            match = row['exact_match']
            elapsed = row['exact_ns']
            if not match and not exact_only:
                match = nearest(row['scores'], threshold)
                elapsed = [a + b for a, b in zip(elapsed, row['semantic_rank_ns'])]
            if not match:
                miss_ns.extend(elapsed)
                outcome = 'miss'
            else:
                hit_count += 1
                hit_ns.extend(elapsed)
                if match == target:
                    right += 1
                    added += row['exact_match'] is None
                    outcome = 'correct_hit'
                else:
                    outcome = 'wrong_hit'
                    errors.append({'probe': row['id'], 'matched_anchor': match, 'expected_anchor': target,
                                   'kind': case['kind'], 'similarity': row['scores'][match]})
            outcomes.append({'id': row['id'], 'outcome': outcome, 'matched_anchor': match})
        exact_hits = sum(r['exact_match'] is not None for r in observations)
        output[str(threshold)] = {
            'threshold': None if exact_only else threshold,
            'probes': total, 'eligible_reuse_probes': safe_positives,
            'hits': hit_count, 'correct_hits': right, 'new_correct_semantic_hits': added,
            'wrong_hits': len(errors), 'misses': total - hit_count,
            'hit_rate': hit_count / total,
            'wrong_hit_rate_among_hits': len(errors) / hit_count if hit_count else None,
            'wrong_hit_rate_among_requests': len(errors) / total,
            'eligible_reuse_recall': right / safe_positives,
            'cache_only_hit_latency': clocks(hit_ns), 'cache_only_miss_latency': clocks(miss_ns),
            'budget': {'baseline_downstream_requests': total, 'modeled_downstream_requests': total - hit_count,
                       'modeled_embedding_queries_with_reuse': total - exact_hits,
                       'safe_downstream_requests_avoided': right,
                       'unsafe_downstream_requests_avoided': len(errors)},
            'errors': errors, 'outcomes': outcomes,
        }
    return output


def choose(summary):
    options = [r for r in summary.values() if r['threshold'] is not None and r['wrong_hits'] == 0]
    if not options:
        return {'threshold': None, 'reason': 'No zero-error development threshold'}
    row = max(options, key=lambda r: (r['new_correct_semantic_hits'], r['threshold']))
    return {'threshold': row['threshold'], 'reason': 'Zero development wrong hits, then highest additional correct reuse, then strictest threshold'}
