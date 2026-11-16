"""Compare the old and new archive show command in disposable Git worktrees."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from answer_eval_core import ROOT, canonical, digest, now, write_new

CLAIM = 'reranker_top40_r5'
BASE = 'a6aaca199ab420fca2af39e58e0fce32e03f1a23'


def exercise(checkout):
    path = (ROOT / checkout).resolve()
    scratch = (ROOT / '.tmp').resolve()
    if not path.is_relative_to(scratch) or path == scratch:
        raise ValueError('Use a disposable worktree under .tmp')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=path, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=path).strip():
        raise ValueError('Require a clean worktree')
    args = [sys.executable, '-X', 'utf8', '-S', '-B', 'scripts/task14_archive.py', 'show', '--claim', CLAIM]
    archive = path / 'reports/task14/archive.json'
    original = archive.read_bytes()
    positive = subprocess.run(args, cwd=path, capture_output=True)
    expected = json.loads(positive.stdout)['value'] if positive.returncode == 0 else None
    changed = json.loads(original)
    next(c for c in changed['claims'] if c['id'] == CLAIM)['value'] = 0
    try:
        archive.write_bytes(canonical(changed))
        negative = subprocess.run(args, cwd=path, capture_output=True)
    finally:
        archive.write_bytes(original)
    if archive.read_bytes() != original or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=path).strip():
        raise ValueError('Disposable archive was not restored')
    return {
        'checkout_commit': head, 'frozen_hash': digest(original), 'valid_lookup': expected,
        'tampered_exit_code': negative.returncode,
        'tampered_value_printed': json.loads(negative.stdout)['value'] if negative.returncode == 0 else None,
        'restored_clean': True,
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--legacy-checkout', type=Path, required=True)
    p.add_argument('--current-checkout', type=Path, required=True)
    p.add_argument('--report', required=True)
    a = p.parse_args()
    old, new = exercise(a.legacy_checkout), exercise(a.current_checkout)
    ok = (old['checkout_commit'] == BASE and old['frozen_hash'] == new['frozen_hash']
          and old['valid_lookup'] == new['valid_lookup'] == 1
          and old['tampered_exit_code'] == 0 and old['tampered_value_printed'] == 0
          and new['tampered_exit_code'] != 0 and new['tampered_value_printed'] is None)
    report = {'status': 'PASS' if ok else 'FAIL', 'claim': CLAIM, 'captured_at': now(),
              'legacy': old, 'current': new, 'new_model_requests': 0,
              'scope': 'Only disposable worktrees were temporarily mutated.'}
    write_new(ROOT / a.report, report)
    print(json.dumps(report))
    raise SystemExit(not ok)
