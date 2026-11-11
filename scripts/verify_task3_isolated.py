"""Rerun the original task 3 suite in a disposable fixture, preserving evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', default='reports/acceptance/task3_recheck.json')
    args = parser.parse_args()
    output = (ROOT / args.report).resolve()
    if output.suffix != '.json' or not any(output.is_relative_to(ROOT / p) for p in ('reports', '.tmp')):
        raise ValueError('Use a JSON receipt under reports/ or .tmp/')
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S-%f')
    fixture = ROOT / '.tmp' / f'task3-isolated-{stamp}'
    fixture.mkdir(parents=True, exist_ok=False)
    inventory = json.loads((ROOT / 'data/manifests/local_data_files.json').read_text('utf-8'))
    lock = json.loads((ROOT / 'data/manifests/task1_task2_baseline_lock.json').read_text('utf-8'))
    paths = {x['path'] for x in inventory['files']}
    paths.update(x['path'] for x in lock['files'] + lock['append_only_files'])
    paths.update(['scripts/build_rag_dataset.py', 'scripts/validate_rag_dataset.py',
                  'scripts/verify_task3_delivery.py', 'docs/RAG_DATA_SCHEMA.md',
                  'data/manifests/rag_dataset_manifest.json', 'data/manifests/sources.csv',
                  'data/manifests/task1_task2_baseline_lock.json'])
    before = {}
    for name in sorted(paths):
        source = (ROOT / name).resolve()
        if not source.is_relative_to(ROOT):
            raise ValueError('Input escapes this checkout')
        before[name] = sha(source)
        dest = fixture / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    command = [sys.executable, str(fixture / 'scripts/verify_task3_delivery.py')]
    process = subprocess.run(command, cwd=fixture, env=env, text=True, encoding='utf-8',
                             capture_output=True, timeout=180)
    unchanged = all(sha(ROOT / name) == checksum for name, checksum in before.items())
    suite_path = fixture / 'reports/task3_delivery_verification.json'
    suite = json.loads(suite_path.read_text('utf-8')) if suite_path.exists() else None
    validation_path = fixture / 'reports/task3_dataset_validation.json'
    validation = json.loads(validation_path.read_text('utf-8')) if validation_path.exists() else None
    result = {
        'generated_at': datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
        'criteria': 'Original task 3, unchanged',
        'execution': {'python_version': sys.version.split()[0],
                      'python_scope': 'Explicit interpreter; may reuse the original local environment',
                      'fixture': fixture.relative_to(ROOT).as_posix(), 'exit_code': process.returncode,
                      'stdout': process.stdout, 'stderr': process.stderr},
        'input_files_unchanged': unchanged,
        'canonical_validation': validation,
        'original_delivery_suite': suite,
        'status': 'PASS' if process.returncode == 0 and unchanged and suite and suite['status'] == 'PASS' else 'FAIL',
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(f"Task 3 isolated review: {result['status']}; inputs unchanged={unchanged}")
    if suite:
        print(f"Original suite: {suite['positive_checks_passed']}/{suite['positive_checks_total']}; corrupt cases rejected: {suite['negative_cases_rejected']}/{suite['negative_cases_total']}")
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
