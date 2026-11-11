"""Freeze only after real matching human approvals; no approval-generating path."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from eval_dataset import EVAL, REVIEW_LEDGER, active_reviews, canonical, digest, load_jsonl, write_json
from validate_eval_dataset import validate


def freeze(directory=EVAL, ledger=REVIEW_LEDGER, allow_synthetic=False):
    path = directory/'dataset_manifest.json'
    manifest = json.loads(path.read_text('utf-8'))
    already_locked = manifest['test_lock']['state'] == 'locked'
    if already_locked and manifest.get('release_status') == 'human_reviewed_and_test_locked':
        result = validate(directory,phase='delivery',ledger=ledger,allow_synthetic_reviews=allow_synthetic)
        if result['status'] != 'PASS':raise ValueError('Existing lock or human review is invalid')
        return 'Already locked; no files changed'
    if already_locked:
        from owner_approve_eval import validate_owner_acceptance
        if (manifest.get('release_status') != 'owner_batch_approved_and_test_locked'
                or validate_owner_acceptance(directory)['status'] != 'PASS_OWNER_AUTHORIZED'):
            raise ValueError('Only a valid owner-approved snapshot can be finalized after human review')
    structure = validate(directory,phase='structure',ledger=ledger)
    if structure['status'] != 'PASS':raise ValueError('Structure must pass before freezing')
    ledger_before = digest(ledger.read_bytes()) if ledger.exists() else None
    rows = load_jsonl(directory/'retrieval_dev.jsonl') + load_jsonl(directory/'retrieval_test.jsonl')
    approvals = active_reviews(rows,ledger,allow_synthetic=allow_synthetic)
    pending = [qid for qid,v in approvals.items() if not v['approved']]
    if pending:
        raise ValueError(f'Cannot freeze: {len(pending)}/{len(rows)} questions lack matching real human approval. Use http://127.0.0.1:7862/; no generated sign-off.')
    if digest(ledger.read_bytes()) != ledger_before:
        raise ValueError('Human review ledger changed while finalizing; pause review submissions and retry')
    previous_release = manifest['release_status']
    completed_at = datetime.now(timezone.utc).isoformat()
    manifest['release_status'] = 'human_reviewed_and_test_locked'
    manifest['human_review'].update(approved=len(rows), total=len(rows), ledger_sha256=ledger_before)
    if already_locked:
        # Evidence is completed for exactly the same bytes. Never unlock the
        # test, reset its usage history, or replace the original lock time.
        manifest['test_lock']['human_review_completed_at'] = completed_at
    else:
        manifest['test_lock'] = {'state':'locked','sha256':digest((directory/'retrieval_test.jsonl').read_bytes()),
                                 'locked_at':completed_at,
                                 'used_for_parameter_selection':False,'formal_test_runs':0}
    # Public review receipts intentionally omit the actual reviewer's name/notes.
    write_json(directory/'human_review_receipt.json', {'dataset_version':manifest['dataset_version'],
        'status':'APPROVED','reviewed_questions':len(rows),'private_ledger_sha256':manifest['human_review']['ledger_sha256'],
        'completed_at':completed_at,'previous_release_status':previous_release,
        'existing_test_lock_preserved':already_locked,'test_sha256':manifest['test_lock']['sha256'],
        'records':[{'question_id':r['question_id'],'annotation_sha256':r['annotation_sha256'],
                    'reviewer_type':'human','decision':'approved','reviewed_at':approvals[r['question_id']]['event']['reviewed_at']} for r in rows]})
    manifest['human_review'].update(receipt_path='data/eval/human_review_receipt.json',
                                   receipt_sha256=digest((directory/'human_review_receipt.json').read_bytes()))
    write_json(path,manifest)
    return 'All questions human-approved; test frozen. Run delivery validation before committing.'


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(freeze())
