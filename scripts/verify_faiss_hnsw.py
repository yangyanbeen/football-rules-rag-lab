"""Replay the published FAISS benchmark and validate its frozen test provenance."""
import argparse
from copy import deepcopy
from datetime import datetime
import json
import math
import subprocess
import sys

from answer_eval_core import canonical, digest, read, record, rows, write_new
from faiss_hnsw_eval import (
    BASE, CONFIG, DATASET, DENSE, MAPPING, REPORT, ROOT,
    config, questions, select, source_records, summarize,
)
from run_retrieval_metrics import authorize_test


def graph_policy(cfg):
    reference = {**cfg['graphs']['hnsw_base'], 'efSearch': cfg['methods']['hnsw_base']['efSearch']}
    expected = {'hnsw_m8': 'M', 'hnsw_c40': 'efConstruction', 'hnsw_s64': 'efSearch'}
    if set(cfg['methods']) != {'flat', 'hnsw_base', *expected}:
        return False
    for name, key in expected.items():
        settings = cfg['methods'][name]
        method = {**cfg['graphs'][settings['graph']], 'efSearch': settings['efSearch']}
        if {p for p in reference if reference[p] != method[p]} != {key}:
            return False
    return cfg['methods']['hnsw_s64']['graph'] == cfg['methods']['hnsw_base']['graph']


def evidence(split):
    folder = REPORT / split
    question_file, labelled = questions(split)
    return (question_file, labelled, rows(folder / 'predictions.jsonl'),
            read(folder / 'builds.json'), read(folder / 'run_manifest.json'))


def run_matches(split, run, question_file, labelled):
    cfg = config()
    folder = REPORT / split
    source = run['source_commit']
    commit = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT)
    if subprocess.run(['git', 'merge-base', '--is-ancestor', source, 'HEAD'],
                      cwd=ROOT, capture_output=True).returncode:
        return False
    if any(commit('show', f'{source}:{p}') != (ROOT / p).read_bytes() for p in source_records()):
        return False
    artifact_paths = {'run_started.json', 'builds.json', 'summary.json', 'predictions.jsonl'}
    if run['public_artifacts'] != {name: record(folder / name) for name in artifact_paths}:
        return False
    pinned = read(ROOT / cfg['dense_config'])
    original = read(DENSE)
    inputs = {name: record(path) for name, path in (
        ('dataset_manifest', DATASET), ('questions', question_file), ('mapping', MAPPING),
        ('public_dense_manifest', DENSE), ('dense_config', ROOT / cfg['dense_config']))}
    vector_file = run['inputs']['document_vectors']
    doc_vector = original['artifact_files']['embeddings.npy']
    model = run['embedding_model']
    batches = run['embedding_batches']
    started = read(folder / 'run_started.json')
    return (
        run['status'] == 'COMPLETE' and run['split'] == started['split'] == split
        and run['purpose'] == ('development' if split == 'dev' else 'final_report')
        and run['used_for_parameter_selection'] is (split == 'dev')
        and started['source_commit'] == source and started['freeze'] == run['freeze']
        and datetime.fromisoformat(started['started_at']) <= datetime.fromisoformat(run['completed_at'])
        and run['source_files'] == source_records()
        and run['inputs'] == {**inputs, 'document_vectors': vector_file}
        and vector_file['path'] == cfg['corpus_vectors']
        and all(vector_file[k] == doc_vector[k] for k in ('size_bytes', 'sha256'))
        and original['vector_fingerprint'] == run['document_vector_fingerprint']
        and all(model[k] == pinned['model'][k]
                for k in ('name', 'digest', 'dimensions', 'quantization', 'ollama_version'))
        and run['embedding_runtime']['digest'] == model['digest']
        and run['embedding_runtime']['size_vram'] == 0
        and (run['query_embeddings'], run['new_document_embeddings'], run['new_answer_requests']) == (len(labelled), 0, 0)
        and len(batches) == math.ceil(len(labelled) / pinned['embedding']['batch_size'])
        and sum(b['inputs'] for b in batches) == len(labelled)
        and all(type(b['inputs']) is int and 0 < b['inputs'] <= pinned['embedding']['batch_size']
                and b['elapsed_seconds'] > 0 and b['server_total_duration_ns'] > 0 for b in batches)
        and run['environment']['packages'] == cfg['dependencies']
        and run['environment']['faiss_threads'] == cfg['threads']
        and run['query_vector_artifact']['path'] == f'.runtime/task15/{split}/query_vectors.npy'
    )


def frozen_test(development, test, summary):
    grant_path = REPORT / 'test-freeze.json'
    grant = read(grant_path)
    authorize_test(read(DATASET), 'final_report', grant, CONFIG.read_bytes())
    selection = select(config(), summary)
    receipts = {n: record(REPORT / 'dev' / n) for n in (
        'run_manifest.json', 'builds.json', 'predictions.jsonl', 'summary.json')}
    previous = grant['pre_freeze_commit']
    for receipt in receipts.values():
        source = subprocess.check_output(['git', 'show', previous + ':' + receipt['path']], cwd=ROOT)
        if digest(source) != receipt['sha256']:
            return False
    frozen = subprocess.check_output(['git', 'show', test['source_commit'] + ':reports/task15/test-freeze.json'], cwd=ROOT)
    start = read(REPORT / 'test/run_started.json')
    times = [development['completed_at'], grant['prepared_at'], start['started_at'], test['completed_at']]
    return (
        grant['development'] == receipts and grant['source_files'] == source_records()
        and grant['dataset_manifest'] == record(DATASET)
        and (grant['selection'] == test['frozen_selection'] == selection)
        and development['freeze'] is None and development['frozen_selection'] is None
        and test['freeze'] == record(grant_path) and digest(frozen) == test['freeze']['sha256']
        and [datetime.fromisoformat(t) for t in times] == sorted(datetime.fromisoformat(t) for t in times)
    )


def replay():
    cfg = config()
    checks, errors = {}, []

    def check(name, fn):
        try:
            if fn() is not True:
                raise ValueError('Verification predicate failed')
            checks[name] = True
        except Exception as exc:
            checks[name] = False
            errors.append({'check': name, 'error': str(exc)})

    check('one_parameter_changed_per_hnsw_arm', lambda: graph_policy(cfg))
    check('original_task_14_acceptance', lambda: (
        read(ROOT / 'reports/task14/delivery-final.json')['task14_fully_accepted'] is True))
    data = {split: evidence(split) for split in ('dev', 'test')}
    for split, (path, labelled, predictions, builds, run) in data.items():
        check(split + '_original_producer_and_inputs', lambda: run_matches(split, run, path, labelled))
        check(split + '_recall_overlap_clocks_and_resource_summary', lambda: (
            canonical(summarize(cfg, labelled, predictions, builds)) ==
            canonical(read(REPORT / split / 'summary.json'))))
    _, labelled, predictions, builds, development = data['dev']
    _, _, _, test_builds, test = data['test']
    check('same_document_vectors_machine_settings_and_graphs', lambda: (
        builds == test_builds and development['environment'] == test['environment']
        and development['document_vector_fingerprint'] == test['document_vector_fingerprint']
        and development['embedding_model'] == test['embedding_model']))
    check('development_selection_frozen_in_git_before_test', lambda: (
        frozen_test(development, test, read(REPORT / 'dev/summary.json'))))

    def rejects(change):
        attempt_rows = deepcopy(predictions)
        attempt_builds = deepcopy(builds)
        change(attempt_rows, attempt_builds)
        try:
            summarize(cfg, labelled, attempt_rows, attempt_builds)
        except ValueError:
            return True
        return False

    changes = {
        'missing_question': lambda pred, build: pred.pop(),
        'extra_vector_field': lambda pred, build: pred[0].update(vector=[1, 2]),
        'duplicate_chunk': lambda pred, build: pred[0]['methods']['flat']['ranked_ids'].__setitem__(
            0, pred[0]['methods']['flat']['ranked_ids'][1]),
        'cosine_over_one': lambda pred, build: pred[0]['methods']['flat']['cosine_scores'].__setitem__(0, 2.0),
        'wrong_repeat_count': lambda pred, build: pred[0]['methods']['flat']['search_ns'].pop(),
        'negative_elapsed': lambda pred, build: pred[0]['methods']['flat']['search_ns'].__setitem__(0, -3),
        'boolean_elapsed': lambda pred, build: pred[0]['methods']['flat']['search_ns'].__setitem__(0, True),
        'invalid_build_rss': lambda pred, build: build['flat'][0].update(rss_after_bytes=0),
        'different_serialized_graph': lambda pred, build: build['flat'][0].update(index_sha256='0' * 64),
    }
    for name, change in changes.items():
        check('reject_' + name, lambda: rejects(change))
    return {
        'status': 'PASS' if all(checks.values()) else 'FAIL',
        'passed': sum(checks.values()), 'total': len(checks), 'checks': checks, 'errors': errors,
        'site_packages_disabled': bool(sys.flags.no_site),
        'source_sha256': record(__file__)['sha256'],
        'run_evidence': {split: record(REPORT / split / 'run_manifest.json') for split in data},
        'new_embedding_requests': 0, 'new_test_runs': 0,
        'scope': 'Replay saved ranks and measurements without models or private vectors.',
        'baseline': BASE,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    arguments = parser.parse_args()
    receipt = replay()
    write_new(ROOT / arguments.report, receipt)
    print(json.dumps({k: receipt[k] for k in ('status', 'passed', 'total', 'errors')}))
    raise SystemExit(receipt['status'] != 'PASS')
