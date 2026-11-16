"""Validate and recompute the FAISS experiment with the Python standard library."""
import json
import math
from statistics import median

from answer_eval_core import ROOT, canonical, read, record
from dense_retrieval_eval import percentile
from historical_evidence import frozen_bytes
from retrieval_metrics import compute_metrics

CONFIG = ROOT / 'config/faiss_hnsw_experiment.json'
REPORT = ROOT / 'reports/task15'
BASE = 'bcffd4e8c8566b5402e0009e0b3308e7b09ee043'
POLICY_RELEASE = '362bdc84f3f748bebfb38bb3cdb7dba649b981a9'
SOURCES_V1 = (
    'config/faiss_hnsw_experiment.json',
    'scripts/faiss_hnsw_eval.py',
    'scripts/run_faiss_hnsw.py',
    'scripts/dense_index.py',
    'scripts/retrieval_metrics.py',
    'scripts/dense_retrieval_eval.py',
    'scripts/run_retrieval_metrics.py',
)
SOURCES = (*SOURCES_V1, 'scripts/historical_evidence.py')
DENSE = ROOT / 'data/manifests/dense_index_manifest.json'
MAPPING = ROOT / 'data/manifests/dense_chunk_ids.json'
DATASET = ROOT / 'data/eval/dataset_manifest.json'


def config():
    cfg = read(CONFIG)
    expected = json.loads(frozen_bytes(CONFIG, POLICY_RELEASE))
    if canonical(cfg) != canonical(expected):
        raise ValueError('Experiment policy differs from task 15')
    return cfg


def source_records():
    return {p: record(ROOT / p) for p in SOURCES}


def questions(split):
    expected = {'dev': (40, 32), 'test': (50, 40)}.get(split)
    if expected is None:
        raise ValueError('Unknown evaluation split')
    path = ROOT / f'data/eval/retrieval_{split}.jsonl'
    manifest = json.loads(frozen_bytes(DATASET, BASE))
    raw = frozen_bytes(path, BASE)
    if split == 'test' and manifest['test_lock']['sha256'] != record(path)['sha256']:
        raise ValueError('Locked test hash differs')
    result = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if (len(result), sum(q['answerable'] is True for q in result)) != expected:
        raise ValueError('Question count or answerable denominator differs')
    return path, result


def mapping_rows():
    records = json.loads(frozen_bytes(MAPPING, BASE))
    ids = [v['chunk_id'] for v in records]
    if (len(ids) != 99 or len(set(ids)) != 99
            or any(type(v['position']) is not int or v['position'] != i for i, v in enumerate(records))):
        raise ValueError('Original corpus ID mapping is incomplete')
    return records


def known_ids():
    return {v['chunk_id'] for v in mapping_rows()}


def clocks(values, scale):
    return {
        'samples': len(values),
        'p50': percentile(values, 0.5) / scale,
        'p95': percentile(values, 0.95) / scale,
    }


def build_summary(cfg, builds):
    result = {}
    if set(builds) != set(cfg['graphs']):
        raise ValueError('Missing graph or unexpected build evidence')
    for graph, observations in builds.items():
        if len(observations) != cfg['build_repetitions']:
            raise ValueError('Incorrect number of independent graph builds')
        for number, obs in enumerate(observations, 1):
            fields = {'graph', 'repetition', 'build_ns', 'rss_before_bytes', 'rss_after_bytes',
                      'peak_working_set_bytes', 'index_bytes', 'index_sha256'}
            if (set(obs) != fields or type(obs['repetition']) is not int
                    or (obs['graph'], obs['repetition']) != (graph, number)):
                raise ValueError('Wrong graph build or repetition')
            amounts = ['build_ns', 'rss_before_bytes', 'rss_after_bytes', 'index_bytes']
            if any(type(obs[k]) is not int or obs[k] <= 0 for k in amounts):
                raise ValueError('Invalid clock, file size or process memory')
            peak = obs['peak_working_set_bytes']
            if peak is not None and (type(peak) is not int or peak < max(
                    obs['rss_before_bytes'], obs['rss_after_bytes'])):
                raise ValueError('Invalid peak working set')
            sha = obs['index_sha256']
            if len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
                raise ValueError('Invalid serialized graph fingerprint')
        artifacts = {(o['index_bytes'], o['index_sha256']) for o in observations}
        if len(artifacts) != 1:
            raise ValueError('Repeated builds did not create identical graph bytes')
        size, sha = artifacts.pop()
        result[graph] = {
            'build_ms': clocks([o['build_ns'] for o in observations], 1e6),
            'index_bytes': size,
            'index_sha256': sha,
            'rss_before_bytes_median': median([o['rss_before_bytes'] for o in observations]),
            'rss_after_bytes_median': median([o['rss_after_bytes'] for o in observations]),
            'rss_delta_bytes_median': median([
                o['rss_after_bytes'] - o['rss_before_bytes'] for o in observations]),
            'rss_delta_bytes_by_build': [o['rss_after_bytes'] - o['rss_before_bytes'] for o in observations],
            'peak_working_set_bytes_by_build': [o['peak_working_set_bytes'] for o in observations],
        }
    return result


def summarize(cfg, labelled, predictions, builds):
    if [r['question_id'] for r in predictions] != [r['question_id'] for r in labelled]:
        raise ValueError('Predictions must cover the original split in order')
    known = known_ids()
    top_k = cfg['top_k']
    for row in predictions:
        if set(row) != {'question_id', 'methods'} or set(row['methods']) != set(cfg['methods']):
            raise ValueError('Prediction includes unexpected or missing fields')
        for method in row['methods'].values():
            if set(method) != {'ranked_ids', 'cosine_scores', 'search_ns'}:
                raise ValueError('Invalid method result fields')
            ids, scores, samples = method['ranked_ids'], method['cosine_scores'], method['search_ns']
            if len(ids) != top_k or len(set(ids)) != top_k or not set(ids) <= known:
                raise ValueError('Invalid or duplicate result IDs')
            if len(scores) != top_k or any(
                    type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1.00001 for v in scores):
                raise ValueError('Invalid cosine score')
            if scores != sorted(scores, reverse=True):
                raise ValueError('Cosine scores are not ordered')
            if len(samples) != cfg['query_repetitions'] or any(type(t) is not int or t <= 0 for t in samples):
                raise ValueError('Invalid query timing samples')

    results = {}
    comparison = []
    for name, settings in cfg['methods'].items():
        ranked = []
        durations = []
        overlaps = {5: [], 10: []}
        misses = []
        for row in predictions:
            method = row['methods'][name]
            ids = method['ranked_ids']
            exact = row['methods']['flat']['ranked_ids']
            ranked.append({'question_id': row['question_id'], 'results': [
                {'rank': n, 'chunk_id': chunk} for n, chunk in enumerate(ids, 1)]})
            durations.extend(method['search_ns'])
            for k in overlaps:
                overlaps[k].append(len(set(ids[:k]) & set(exact[:k])) / k)
            if set(ids) != set(exact):
                misses.append(row['question_id'])
                comparison.append({
                    'question_id': row['question_id'], 'method': name,
                    'flat_only_top10_ids': sorted(set(exact) - set(ids)),
                    'method_only_top10_ids': sorted(set(ids) - set(exact)),
                })
        results[name] = {
            'graph': settings['graph'], 'efSearch': settings['efSearch'],
            'quality': compute_metrics(labelled, ranked),
            'vector_search_ms': clocks(durations, 1e6),
            'mean_set_overlap_with_flat_at_5': sum(overlaps[5]) / len(labelled),
            'mean_set_overlap_with_flat_at_10': sum(overlaps[10]) / len(labelled),
            'different_top10_question_ids': misses,
        }
    for method in results.values():
        method['delta_vs_flat'] = {
            name: value - results['flat']['quality']['metrics'][name]
            for name, value in method['quality']['metrics'].items()
        }
    return {'graphs': build_summary(cfg, builds), 'methods': results, 'ann_top10_differences': comparison}


def select(cfg, summary):
    results = summary['methods']
    exact = results['flat']['quality']['metrics']
    eligible = [
        name for name, method in results.items()
        if method['mean_set_overlap_with_flat_at_10'] >= cfg['selection']['min_mean_flat_overlap_at_10']
        and all(method['quality']['metrics'][metric] >= exact[metric]
                for metric in cfg['selection']['required_quality'])
    ]
    winner = min(eligible, key=lambda name: (results[name]['vector_search_ms']['p50'], name != 'flat', name))
    return {'eligible_methods': sorted(eligible), 'selected_method': winner}
