"""Score saved predictions, with a gate against candidate-test parameter tuning."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval_dataset import CORPUS, EVAL, ROOT, digest, load_jsonl, write_json
from retrieval_metrics import compute_metrics
from validate_eval_dataset import validate


def authorize_test(manifest, purpose, run_manifest, config_data):
    if purpose != 'final_report':
        raise ValueError('Test labels may not be used to select parameters; use development only')
    lock = manifest.get('test_lock', {})
    if lock.get('state') != 'locked':
        raise ValueError('Test candidate is not human-reviewed and locked')
    if (not run_manifest or run_manifest.get('purpose') != 'final_report'
            or run_manifest.get('used_for_parameter_selection') is not False
            or run_manifest.get('dataset_version') != manifest['dataset_version']
            or run_manifest.get('test_sha256') != lock['sha256']
            or run_manifest.get('config_sha256') != digest(config_data)):
        raise ValueError('Final test needs a matching dataset/configuration snapshot and explicit reporting purpose')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=('dev','test'), default='dev')
    parser.add_argument('--predictions', required=True)
    parser.add_argument('--purpose', choices=('development','final_report'), default='development')
    parser.add_argument('--run-manifest')
    parser.add_argument('--config')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    manifest = json.loads((EVAL/'dataset_manifest.json').read_text('utf-8'))
    if args.split == 'test':
        run = json.loads(Path(args.run_manifest).read_text('utf-8')) if args.run_manifest else None
        authorize_test(manifest, args.purpose, run, Path(args.config).read_bytes() if args.config else b'')
        reviewed = validate(phase='delivery')
        if reviewed['status'] != 'PASS':raise ValueError('Full task 4 acceptance must pass before a formal test run')
    elif validate(phase='structure')['status'] != 'PASS':
        raise ValueError('Candidate structure validation failed')
    output = (ROOT/args.output).resolve()
    if not any(output.is_relative_to(ROOT/p) for p in ('.runtime','reports')) or output.suffix != '.json':
        raise ValueError('Use a separate JSON report under .runtime/ or reports/')
    predictions = load_jsonl(args.predictions)
    known = {r['chunk_id'] for r in load_jsonl(CORPUS)}
    if any(x['chunk_id'] not in known for r in predictions for x in r['results']):raise ValueError('Prediction references an unknown corpus chunk')
    results = compute_metrics(load_jsonl(EVAL/f'retrieval_{args.split}.jsonl'), predictions)
    write_json(output, {'dataset_version': manifest['dataset_version'], 'split': args.split,
                        'label_status': manifest['release_status'], 'purpose': args.purpose,
                        'predictions_sha256': digest(Path(args.predictions).read_bytes()),
                        'question_file_sha256': manifest['files'][f'retrieval_{args.split}.jsonl']['sha256'],
                        'scope': 'Provisional AI labels until actually human-reviewed; not official rules accuracy', **results})
    print(json.dumps({'split': args.split, 'label_status': manifest['release_status'], 'metrics': results['metrics']}))


if __name__ == '__main__':main()
