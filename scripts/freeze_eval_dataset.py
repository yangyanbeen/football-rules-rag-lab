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
    if manifest['test_lock']['state'] == 'locked':
        result = validate(directory,phase='delivery',ledger=ledger,allow_synthetic_reviews=allow_synthetic)
        if result['status'] != 'PASS':raise ValueError('Existing lock or human review is invalid')
        return 'Already locked; no files changed'
    structure = validate(directory,phase='structure',ledger=ledger)
    if structure['status'] != 'PASS':raise ValueError('Structure must pass before freezing')
    rows = load_jsonl(directory/'retrieval_dev.jsonl') + load_jsonl(directory/'retrieval_test.jsonl')
    approvals = active_reviews(rows,ledger,allow_synthetic=allow_synthetic)
    pending = [qid for qid,v in approvals.items() if not v['approved']]
    if pending:
        raise ValueError(f'Cannot freeze: {len(pending)}/{len(rows)} questions lack matching real human approval. Use http://127.0.0.1:7862/; no generated sign-off.')
    manifest['release_status'] = 'human_reviewed_and_test_locked'
    manifest['human_review'].update(approved=len(rows), total=len(rows), ledger_sha256=digest(ledger.read_bytes()))
    manifest['test_lock'] = {'state':'locked','sha256':digest((directory/'retrieval_test.jsonl').read_bytes()),
                             'locked_at':datetime.now(timezone.utc).isoformat(),
                             'used_for_parameter_selection':False,'formal_test_runs':0}
    # Public review receipts intentionally omit the actual reviewer's name/notes.
    write_json(directory/'human_review_receipt.json', {'dataset_version':manifest['dataset_version'],
        'status':'APPROVED','reviewed_questions':len(rows),'private_ledger_sha256':manifest['human_review']['ledger_sha256'],
        'records':[{'question_id':r['question_id'],'annotation_sha256':r['annotation_sha256'],
                    'reviewer_type':'human','decision':'approved','reviewed_at':approvals[r['question_id']]['event']['reviewed_at']} for r in rows]})
    write_json(path,manifest)
    return 'All questions human-approved; test frozen. Run delivery validation before committing.'


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(freeze())
