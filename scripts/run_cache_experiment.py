"""Measure cache reuse on a separately authored, frozen BGE-M3 workload."""
import argparse
import platform
import subprocess
import time

from answer_eval_core import canonical, digest, git, now, read, record, write_new
from cache_experiment import REPORT, ROOT, SOURCES, WORKLOAD, SemanticIndex, choose, source_records, summarize, workload
from query_cache import ExactCache, MemoryBackend, Scope, normalized, policy

FREEZE = REPORT / 'holdout-freeze.json'


def committed(paths):
    head = git('rev-parse', 'HEAD')
    for path in paths:
        before = subprocess.check_output(['git', 'show', head + ':' + path], cwd=ROOT)
        if before != (ROOT / path).read_bytes():
            raise ValueError('Commit experiment inputs before evaluation: ' + path)
    return head


def dev_records():
    folder = REPORT / 'dev'
    return {n: record(folder / n) for n in ('observations.json', 'summary.json', 'run_manifest.json')}


def freeze():
    paths = (*SOURCES, *(r['path'] for r in dev_records().values()))
    head = committed(paths)
    if (REPORT / 'holdout').exists():
        raise ValueError('Holdout has already run')
    d = REPORT / 'dev'
    output = summarize(workload('dev'), read(d / 'observations.json'))
    if canonical(output) != canonical(read(d / 'summary.json')):
        raise ValueError('Development summary differs from raw data')
    development = read(d / 'run_manifest.json')
    if development['source_files'] != source_records():
        raise ValueError('Development sources changed')
    write_new(FREEZE, {
        'version': 'task16-holdout-freeze-1.0', 'prepared_at': now(), 'development_commit': head,
        'selection': choose(output), 'workload': record(WORKLOAD), 'source_files': source_records(),
        'development': dev_records(), 'used_holdout_for_selection': False,
    })
    print(choose(output), flush=True)


def run(split):
    from dense_index import PinnedEmbedder
    import numpy as np

    output = REPORT / split
    if output.exists():
        raise ValueError('Already have an attempt in this report directory')
    head = committed(SOURCES)
    selection = None
    if split == 'holdout':
        head = committed((*SOURCES, FREEZE.relative_to(ROOT).as_posix()))
        grant = read(FREEZE)
        if (grant['source_files'] != source_records() or grant['development'] != dev_records()
                or grant['workload'] != record(WORKLOAD)
                or grant['selection'] != choose(read(REPORT / 'dev/summary.json'))
                or grant['used_holdout_for_selection'] is not False):
            raise ValueError('Holdout freeze or development evidence changed')
        selection = grant['selection']

    cfg = policy()
    data = workload(split)
    pin = PinnedEmbedder(read(ROOT / 'config/dense_index.json'))
    output.mkdir(parents=True)
    started = now()
    unique = list(dict.fromkeys(normalized(row['question']) for row in data['anchors'] + data['probes']))
    start = time.perf_counter_ns()
    vectors = pin.encode(unique)
    encoding_ns = time.perf_counter_ns() - start
    embedding_runtime = pin.runtime()
    private = ROOT / f'.runtime/task16/{split}-embeddings.npy'
    private.parent.mkdir(parents=True, exist_ok=True)
    with private.open('xb') as handle:
        np.save(handle, vectors, allow_pickle=False)
    vector_by_query = {q: v.tolist() for q, v in zip(unique, vectors)}
    scope = Scope.create('fixture-' + split, {'workload': record(WORKLOAD), 'model': pin.model_info,
                                             'sources': source_records()}, cfg['ttl_ms'])
    cache = ExactCache(MemoryBackend(cfg['capacity']), scope,
                       lambda r: isinstance(r, dict) and set(r) == {'anchor_id'} and isinstance(r['anchor_id'], str))
    semantic = SemanticIndex(cfg['capacity'])
    for anchor in data['anchors']:
        question = normalized(anchor['question'])
        if cache.store(question, {'anchor_id': anchor['id']}) != 'stored':
            raise ValueError('Could not seed the exact cache')
        semantic.put(scope, anchor['id'], vector_by_query[question])
    observations = []
    for probe in data['probes']:
        question = normalized(probe['question'])
        exact_ns, semantic_ns = [], []
        ids, score_sets = [], []
        for _ in range(cfg['warm_probe_repetitions']):
            begin = time.perf_counter_ns()
            outcome, value = cache.lookup(question)
            exact_ns.append(time.perf_counter_ns() - begin)
            if outcome == 'hit':
                ids.append(value['anchor_id'])
            elif outcome == 'miss':
                ids.append(None)
                begin = time.perf_counter_ns()
                score_sets.append(semantic.rank(scope, vector_by_query[question]))
                semantic_ns.append(time.perf_counter_ns() - begin)
            else:
                raise ValueError('Unexpected exact-cache failure in the fixture')
        if any(m != ids[0] for m in ids) or any(s != score_sets[0] for s in score_sets):
            raise ValueError('Warm probe repetitions changed match identity')
        observations.append({'id': probe['id'], 'exact_match': ids[0], 'exact_ns': exact_ns,
                             'semantic_rank_ns': semantic_ns, 'scores': score_sets[0] if score_sets else {}})
    summary = summarize(data, observations)
    write_new(output / 'observations.json', observations)
    write_new(output / 'summary.json', summary)
    write_new(output / 'run_manifest.json', {
        'version': 'task16-semantic-run-1.0', 'status': 'COMPLETE', 'split': split, 'backend': 'memory',
        'started_at': started, 'completed_at': now(), 'source_commit': head, 'source_files': source_records(),
        'workload': record(WORKLOAD), 'freeze': record(FREEZE) if selection else None, 'selection': selection,
        'observations': record(output / 'observations.json'), 'summary': record(output / 'summary.json'),
        'anchors': len(data['anchors']), 'probes': len(data['probes']),
        'embedding_model': pin.model_info, 'embedding_runtime': embedding_runtime, 'embedding_inputs': len(unique),
        'embedding_batches': pin.observations, 'batch_encoding_wall_ns': encoding_ns,
        'private_embeddings': record(private), 'vector_fingerprint': digest(vectors.tobytes(order='C')),
        'hardware': {'platform': platform.platform(), 'processor': platform.processor(),
                     'python': platform.python_version()},
        'new_answer_requests': 0, 'new_formal_test_runs': 0, 'new_human_judgments': 0,
        'command': 'python -B scripts/run_cache_experiment.py ' + split,
    })
    print(split + ': recorded scores and timings for 24 probes', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('dev', 'freeze', 'holdout'))
    args = parser.parse_args()
    if args.stage == 'freeze':
        freeze()
    else:
        run(args.stage)
