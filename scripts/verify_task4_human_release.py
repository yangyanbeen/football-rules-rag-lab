"""Check final human delivery and exercise owner-to-human promotion in .tmp only."""
from __future__ import annotations

import json
import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

from eval_dataset import CHECKLIST, EVAL, ROOT, active_reviews, digest, load_jsonl, write_json, write_jsonl
from freeze_eval_dataset import freeze
from owner_approve_eval import validate_owner_acceptance
from validate_eval_dataset import validate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,default=ROOT/'reports/acceptance/task4_human_release_verification.json')
    args=parser.parse_args()
    report=args.report.resolve()
    if not any(report.is_relative_to(ROOT/name) for name in ('reports','.tmp')) or report.suffix!='.json':
        raise ValueError('Use a JSON report under reports/ or .tmp/')
    before = {p.name: digest(p.read_bytes()) for p in EVAL.iterdir() if p.is_file()}
    folder = ROOT/'.tmp'/('task4-human-release-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
    folder.mkdir(parents=True)
    checks = []

    def record(name, passed):
        checks.append({'check': name, 'passed': bool(passed)})

    actual = validate(phase='delivery')
    record('real_full_human_delivery_passes', actual['status'] == 'PASS' and actual['human_review'] == {'approved': 90, 'total': 90})
    manifest = json.loads((EVAL/'dataset_manifest.json').read_text('utf-8'))
    receipt = json.loads((EVAL/'human_review_receipt.json').read_text('utf-8'))
    record('public_receipt_hash_and_ledger_match', digest((EVAL/'human_review_receipt.json').read_bytes()) == manifest['human_review']['receipt_sha256']
           and receipt['private_ledger_sha256'] == manifest['human_review']['ledger_sha256'])
    allowed_fields = {'question_id', 'annotation_sha256', 'reviewer_type', 'decision', 'reviewed_at'}
    record('public_records_omit_names_notes_and_checklists', len(receipt['records']) == 90 and all(set(r) == allowed_fields for r in receipt['records']))
    record('original_owner_receipt_still_valid', validate_owner_acceptance()['status'] == 'PASS_OWNER_AUTHORIZED')
    record('original_lock_preserved', receipt['existing_test_lock_preserved'] is True
           and manifest['test_lock']['approval_mode'] == 'owner_batch_authorized'
           and receipt['test_sha256'] == manifest['test_lock']['sha256'])

    def fixture(name):
        target = folder/name
        shutil.copytree(EVAL, target)
        copied = json.loads((target/'dataset_manifest.json').read_text('utf-8'))
        # Reset only the disposable copy to the earlier owner-approved state.
        copied['release_status'] = 'owner_batch_approved_and_test_locked'
        copied['human_review'] = {'required': True, 'approved': 2, 'total': 90}
        copied['test_lock'].pop('human_review_completed_at', None)
        write_json(target/'dataset_manifest.json', copied)
        return target

    def rejected(target, ledger):
        old = {p.name: digest(p.read_bytes()) for p in target.iterdir() if p.is_file()}
        try:
            freeze(target, ledger, allow_synthetic=True)
        except ValueError:
            return old == {p.name: digest(p.read_bytes()) for p in target.iterdir() if p.is_file()}
        return False

    target = fixture('missing-review')
    record('promotion_rejects_missing_reviews_without_writes', rejected(target, folder/'absent.jsonl'))
    rows = load_jsonl(EVAL/'retrieval_dev.jsonl')+load_jsonl(EVAL/'retrieval_test.jsonl')
    events = [{'question_id': r['question_id'], 'annotation_sha256': r['annotation_sha256'],
               'reviewer_type': 'human', 'reviewer_name': 'SYNTHETIC FIXTURE ONLY', 'decision': 'approved',
               'reviewed_at': datetime.now(timezone.utc).isoformat(), 'checklist': {k: True for k in CHECKLIST},
               'fixture_only': True} for r in rows]
    ledger = folder/'SYNTHETIC-review-fixture.jsonl'
    write_jsonl(ledger, events[:-1])
    record('promotion_rejects_89_of_90_without_writes', rejected(fixture('partial-review'), ledger))
    write_jsonl(ledger, events)
    record('synthetic_approvals_never_count_as_real', not any(v['approved'] for v in active_reviews(rows, ledger).values()))
    target = fixture('bad-owner-receipt')
    (target/'owner_approval_receipt.json').write_bytes(b'{}\n')
    record('promotion_rejects_invalid_owner_provenance', rejected(target, ledger))

    target = fixture('complete-promotion')
    old = json.loads((target/'dataset_manifest.json').read_text('utf-8'))
    data_hashes = {name: digest((target/name).read_bytes()) for name in old['files']}
    owner_hash = digest((target/'owner_approval_receipt.json').read_bytes())
    freeze(target, ledger, allow_synthetic=True)
    promoted = json.loads((target/'dataset_manifest.json').read_text('utf-8'))
    record('synthetic_only_promotion_passes_original_gate', validate(target, phase='delivery', ledger=ledger, allow_synthetic_reviews=True)['status'] == 'PASS')
    record('promotion_preserves_every_original_lock_field', all(promoted['test_lock'].get(k) == v for k, v in old['test_lock'].items()))
    record('promotion_preserves_data_and_owner_receipt', data_hashes == {name: digest((target/name).read_bytes()) for name in old['files']}
           and owner_hash == digest((target/'owner_approval_receipt.json').read_bytes()))
    hashes = {p.name: digest(p.read_bytes()) for p in target.iterdir() if p.is_file()}
    freeze(target, ledger, allow_synthetic=True)
    record('repeated_finalization_is_idempotent', hashes == {p.name: digest(p.read_bytes()) for p in target.iterdir() if p.is_file()})
    write_jsonl(ledger, events+[events[0]])
    record('later_ledger_edit_invalidates_sealed_release', validate(target, phase='delivery', ledger=ledger, allow_synthetic_reviews=True)['status'] == 'FAIL'
           and rejected(target, ledger))
    record('real_eval_files_unchanged_by_fixtures', before == {p.name: digest(p.read_bytes()) for p in EVAL.iterdir() if p.is_file()})
    result = {'captured_at': datetime.now(timezone.utc).isoformat(), 'status': 'PASS' if all(c['passed'] for c in checks) else 'FAIL',
              'passed': sum(c['passed'] for c in checks), 'total': len(checks), 'checks': checks,
              'actual_human_reviews_created': False, 'synthetic_records_only_under_ignored_tmp': True,
              'real_dataset_scores_computed': False,
              'implementation_sha256': {name: digest((ROOT/'scripts'/name).read_bytes()) for name in
                                        ('freeze_eval_dataset.py', 'owner_approve_eval.py', 'verify_task4_human_release.py')}}
    write_json(report, result)
    print(json.dumps({k: result[k] for k in ('status', 'passed', 'total', 'actual_human_reviews_created')}))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
