"""Build FAISS indices and compare them on the original Dense B0 evaluation."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import time

from answer_eval_core import canonical, digest, git, now, read, record, rows, write_new
from dense_retrieval_eval import normalize_query
from faiss_hnsw_eval import (
    BASE, CONFIG, DATASET, DENSE, MAPPING, REPORT, ROOT, SOURCES, config, mapping_rows, questions,
    select, source_records, summarize,
)
from historical_evidence import frozen_bytes
from run_retrieval_metrics import authorize_test
from validate_eval_receipt import require_receipt

PRIVATE = ROOT / '.runtime/task15'
GRANT = REPORT / 'test-freeze.json'


def native(cfg):
    for package, expected in cfg['dependencies'].items():
        if importlib.metadata.version(package) != expected:
            raise ValueError(f'Expected {package}=={expected} in the isolated runtime')
    import faiss
    import numpy
    import psutil

    faiss.omp_set_num_threads(cfg['threads'])
    return faiss, numpy, psutil


def checked_vectors(cfg, np):
    path = ROOT / cfg['corpus_vectors']
    frozen = json.loads(frozen_bytes(DENSE, BASE))
    artifact = frozen['artifact_files']['embeddings.npy']
    actual = record(path)
    if any(artifact[k] != actual[k] for k in ('size_bytes', 'sha256')):
        raise ValueError('Document vector file differs from task 5')
    vectors = np.load(path, allow_pickle=False)
    if (vectors.dtype != np.float32 or vectors.shape != (cfg['vector_count'], cfg['dimensions'])
            or not vectors.flags.c_contiguous or not np.isfinite(vectors).all()
            or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-6, rtol=0)
            or digest(vectors.tobytes(order='C')) != frozen['vector_fingerprint']):
        raise ValueError('Frozen unit document vector matrix differs')
    mapping = mapping_rows()
    return vectors, [m['chunk_id'] for m in mapping]


def build_one(graph, repetition, target):
    cfg = config()
    faiss, np, psutil = native(cfg)
    vectors, _ = checked_vectors(cfg, np)
    settings = cfg['graphs'][graph]
    process = psutil.Process()
    before = process.memory_info().rss
    start = time.perf_counter_ns()
    if settings['type'] == 'IndexFlatIP':
        index = faiss.IndexFlatIP(cfg['dimensions'])
    else:
        index = faiss.IndexHNSWFlat(cfg['dimensions'], settings['M'], faiss.METRIC_INNER_PRODUCT)
        index.hnsw.efConstruction = settings['efConstruction']
    index.add(vectors)
    elapsed = time.perf_counter_ns() - start
    after = process.memory_info()
    if target.exists() or not target.resolve().is_relative_to(PRIVATE.resolve()):
        raise ValueError('Index output must be a new file in the private task directory')
    faiss.write_index(index, str(target))
    artifact = record(target)
    write_new(target.with_suffix('.json'), {
        'graph': graph, 'repetition': repetition, 'build_ns': elapsed,
        'rss_before_bytes': before, 'rss_after_bytes': after.rss,
        'peak_working_set_bytes': getattr(after, 'peak_wset', None),
        'index_bytes': artifact['size_bytes'], 'index_sha256': artifact['sha256'],
    })


def build_all(cfg, directory):
    evidence = {}
    for graph in cfg['graphs']:
        evidence[graph] = []
        for repetition in range(1, cfg['build_repetitions'] + 1):
            target = directory / f'{graph}-{repetition}.faiss'
            subprocess.run([sys.executable, '-B', __file__, 'build-child', graph,
                            str(repetition), str(target)], check=True, cwd=ROOT)
            evidence[graph].append(read(target.with_suffix('.json')))
    return evidence


def open_indices(cfg, faiss, np, vectors, builds, directory):
    indices = {}
    for graph, settings in cfg['graphs'].items():
        path = directory / f'{graph}-1.faiss'
        metadata = record(path)
        if (metadata['sha256'], metadata['size_bytes']) != (
                builds[graph][0]['index_sha256'], builds[graph][0]['index_bytes']):
            raise ValueError('Serialized graph differs from development evidence')
        index = faiss.read_index(str(path))
        if (type(index).__name__ != settings['type'] or index.ntotal != cfg['vector_count']
                or index.metric_type != faiss.METRIC_INNER_PRODUCT
                or index.d != cfg['dimensions'] or not np.array_equal(index.reconstruct_n(), vectors)):
            raise ValueError('Reloaded index type, metric, dimensions or vector order differs')
        if graph != 'flat' and (index.hnsw.efConstruction != settings['efConstruction']
                                or index.hnsw.nb_neighbors(0) != 2 * settings['M']):
            raise ValueError('Reloaded HNSW graph parameters differ')
        indices[graph] = index
    return indices


def search(cfg, faiss, indices, ids, query_vectors, query_ids):
    options = {}
    for name, method in cfg['methods'].items():
        index = indices[method['graph']]
        params = None
        if method['efSearch'] is not None:
            params = faiss.SearchParametersHNSW()
            params.efSearch = method['efSearch']
        options[name] = (index, params)

    top_k = cfg['top_k']
    generator = random.Random(cfg['order_seed'])
    for _ in range(cfg['warmup_rounds']):
        for index, params in options.values():
            index.search(query_vectors[:1], top_k, params=params)

    predictions = []
    order = list(options)
    for pos, qid in enumerate(query_ids):
        query = query_vectors[pos:pos + 1]
        results = {name: {'search_ns': []} for name in options}
        for repetition in range(cfg['query_repetitions']):
            generator.shuffle(order)
            for name in order:
                index, params = options[name]
                start = time.perf_counter_ns()
                distances, positions = index.search(query, top_k, params=params)
                elapsed = time.perf_counter_ns() - start
                found = []
                for score, index_position in zip(distances[0], positions[0]):
                    if not 0 <= index_position < len(ids):
                        raise ValueError('FAISS did not return a complete valid Top10')
                    found.append((float(score), ids[index_position]))
                found.sort(key=lambda pair: (-pair[0], pair[1]))
                row = results[name]
                ranked_ids = [chunk for _, chunk in found]
                scores = [score for score, _ in found]
                if repetition == 0:
                    row['ranked_ids'] = ranked_ids
                    row['cosine_scores'] = scores
                elif (ranked_ids, scores) != (row['ranked_ids'], row['cosine_scores']):
                    raise ValueError('Repeated searches differ under the fixed configuration')
                row['search_ns'].append(elapsed)
        predictions.append({'question_id': qid, 'methods': results})
    return predictions


def require_source(commit, names=SOURCES):
    if subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'],
                      cwd=ROOT, capture_output=True).returncode != 0:
        raise ValueError('Producer commit is missing from this checkout')
    for name in names:
        original = subprocess.check_output(['git', 'show', f'{commit}:{name}'], cwd=ROOT)
        if original != (ROOT / name).read_bytes():
            raise ValueError(f'Record immutable sources first: {name}')


def development_receipts():
    folder = REPORT / 'dev'
    return {name: record(folder / name) for name in (
        'run_manifest.json', 'builds.json', 'predictions.jsonl', 'summary.json')}


def freeze():
    if GRANT.exists() or (REPORT / 'test').exists():
        raise ValueError('This checkout already has a formal test freeze or attempt')
    cfg = config()
    folder = REPORT / 'dev'
    question_file, labelled = questions('dev')
    builds = read(folder / 'builds.json')
    summary = summarize(cfg, labelled, rows(folder / 'predictions.jsonl'), builds)
    if canonical(summary) != canonical(read(folder / 'summary.json')):
        raise ValueError('Development summary does not recompute')
    run = read(folder / 'run_manifest.json')
    from verify_faiss_hnsw import run_matches

    if not run_matches('dev', run, question_file, labelled):
        raise ValueError('Development receipt or producer does not match')
    current = git('rev-parse', 'HEAD')
    require_source(current, (*SOURCES, *(item['path'] for item in development_receipts().values())))
    if run['source_files'] != source_records():
        raise ValueError('Development code differs from the frozen configuration')
    manifest = read(DATASET)
    grant = {
        'version': 'faiss-hnsw-test-freeze-1.0', 'prepared_at': now(),
        'purpose': 'final_report', 'used_for_parameter_selection': False,
        'test_sha256': manifest['test_lock']['sha256'], 'dataset_version': manifest['dataset_version'],
        'dataset_manifest': record(DATASET), 'config_sha256': record(CONFIG)['sha256'],
        'pre_freeze_commit': current, 'source_files': source_records(),
        'development': development_receipts(), 'selection': select(cfg, summary),
    }
    authorize_test(manifest, 'final_report', grant, CONFIG.read_bytes())
    write_new(GRANT, grant)
    print(grant['selection'], flush=True)


def authorize(commit):
    require_source(commit, (*SOURCES, GRANT.relative_to(ROOT).as_posix()))
    grant = read(GRANT)
    if (grant['source_files'] != source_records() or grant['development'] != development_receipts()
            or grant['dataset_manifest'] != record(DATASET)):
        raise ValueError('Configuration, development evidence or dataset changed after freeze')
    cfg = config()
    if grant['selection'] != select(cfg, read(REPORT / 'dev/summary.json')):
        raise ValueError('Development selection has changed')
    authorize_test(read(DATASET), 'final_report', grant, CONFIG.read_bytes())
    return grant


def evaluate(split):
    from dense_index import PinnedEmbedder

    output = REPORT / split
    if output.exists():
        raise ValueError('Run directory exists. Preserve the original attempt.')
    cfg = config()
    faiss, np, psutil = native(cfg)
    vectors, ids = checked_vectors(cfg, np)
    commit = git('rev-parse', 'HEAD')
    require_source(commit)
    require_receipt()
    grant = authorize(commit) if split == 'test' else None
    pin = PinnedEmbedder(read(ROOT / cfg['dense_config']))
    output.mkdir(parents=True)
    write_new(output / 'run_started.json', {
        'split': split, 'started_at': now(), 'source_commit': commit,
        'freeze': record(GRANT) if grant else None,
    })
    work = PRIVATE / split
    work.mkdir(parents=True, exist_ok=False)
    if split == 'dev':
        builds = build_all(cfg, work)
    else:
        builds = read(REPORT / 'dev/builds.json')
    graph_directory = PRIVATE / 'dev'
    indices = open_indices(cfg, faiss, np, vectors, builds, graph_directory)
    question_file, labelled = questions(split)
    query_ids = [q['question_id'] for q in labelled]
    query_vectors = pin.encode([normalize_query(q['question']) for q in labelled])
    cpu_runtime = pin.runtime()
    np.save(work / 'query_vectors.npy', query_vectors, allow_pickle=False)
    predictions = search(cfg, faiss, indices, ids, query_vectors, query_ids)
    summary = summarize(cfg, labelled, predictions, builds)
    write_new(output / 'builds.json', builds)
    with (output / 'predictions.jsonl').open('x', encoding='utf-8', newline='\n') as handle:
        for prediction in predictions:
            handle.write(canonical(prediction).decode('utf-8') + '\n')
    write_new(output / 'summary.json', summary)
    write_new(output / 'run_manifest.json', {
        'version': cfg['version'], 'status': 'COMPLETE', 'completed_at': now(), 'split': split,
        'purpose': 'final_report' if grant else 'development', 'used_for_parameter_selection': not grant,
        'source_commit': commit, 'source_files': source_records(),
        'inputs': {name: record(path) for name, path in (
            ('dataset_manifest', DATASET), ('questions', question_file), ('mapping', MAPPING),
            ('public_dense_manifest', DENSE), ('document_vectors', ROOT / cfg['corpus_vectors']),
            ('dense_config', ROOT / cfg['dense_config']))},
        'document_vector_fingerprint': digest(vectors.tobytes(order='C')),
        'query_vector_fingerprint': digest(query_vectors.tobytes(order='C')),
        'query_vector_artifact': record(work / 'query_vectors.npy'),
        'embedding_model': pin.model_info, 'embedding_runtime': cpu_runtime,
        'embedding_batches': pin.observations, 'query_embeddings': len(query_vectors),
        'new_document_embeddings': 0, 'new_answer_requests': 0,
        'environment': {
            'python': platform.python_version(), 'platform': platform.platform(),
            'machine': platform.machine(), 'processor': platform.processor(),
            'logical_cpus': os.cpu_count(), 'physical_memory_bytes': psutil.virtual_memory().total,
            'faiss_options': faiss.get_compile_options(), 'faiss_threads': faiss.omp_get_max_threads(),
            'packages': cfg['dependencies'],
        },
        'build_origin': 'reports/task15/dev/builds.json',
        'freeze': record(GRANT) if grant else None, 'frozen_selection': grant['selection'] if grant else None,
        'command': f'python -B scripts/run_faiss_hnsw.py {split}',
        'public_artifacts': {name: record(output / name) for name in (
            'run_started.json', 'builds.json', 'summary.json', 'predictions.jsonl')},
    })
    print(f'{split}: saved {len(labelled)} questions for {len(cfg["methods"])} methods', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('dev', 'freeze', 'test', 'build-child'))
    parser.add_argument('build_args', nargs='*')
    args = parser.parse_args()
    if args.action == 'build-child':
        graph, repetition, target = args.build_args
        build_one(graph, int(repetition), Path(target))
    elif args.build_args:
        parser.error('Unexpected arguments')
    elif args.action == 'freeze':
        freeze()
    else:
        evaluate(args.action)


if __name__ == '__main__':
    main()
