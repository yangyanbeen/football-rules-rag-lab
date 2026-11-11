"""Record delegated owner acceptance without inventing per-question human review.

This is an administrative acceptance path requested by the project owner. The
original human-review validator remains unchanged and keeps its actual result.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from eval_dataset import EVAL, ROOT, active_reviews, digest, load_jsonl, write_json
from validate_eval_dataset import validate


def validate_owner_acceptance(directory=EVAL):
    manifest = json.loads((directory/'dataset_manifest.json').read_text('utf-8'))
    receipt_path = directory/'owner_approval_receipt.json'
    if not receipt_path.is_file():
        return {'status':'FAIL','errors':['Owner approval receipt missing']}
    receipt = json.loads(receipt_path.read_text('utf-8'))
    rows = load_jsonl(directory/'retrieval_dev.jsonl') + load_jsonl(directory/'retrieval_test.jsonl')
    expected = {r['question_id']:r['annotation_sha256'] for r in rows}
    approvals = receipt.get('records', [])
    actual = {r.get('question_id'):r.get('annotation_sha256') for r in approvals}
    structure = validate(directory, phase='structure')
    human_release_ok = False
    human_receipt_path = directory/'human_review_receipt.json'
    if manifest.get('release_status') == 'human_reviewed_and_test_locked' and human_receipt_path.exists():
        human_receipt = json.loads(human_receipt_path.read_text('utf-8'))
        human_records = human_receipt.get('records', [])
        human_release_ok = (manifest.get('human_review',{}).get('approved') == len(rows)
            and manifest['human_review'].get('receipt_sha256') == digest(human_receipt_path.read_bytes())
            and human_receipt.get('status') == 'APPROVED'
            and human_receipt.get('private_ledger_sha256') == manifest['human_review'].get('ledger_sha256')
            and len(human_records) == len(rows)
            and {r.get('question_id'):r.get('annotation_sha256') for r in human_records} == expected
            and all(r.get('reviewer_type') == 'human' and r.get('decision') == 'approved' for r in human_records))
    checks = {
        'structure': structure['status']=='PASS',
        'all_current_questions_approved': actual==expected and len(approvals)==len(rows)==90,
        'owner_delegation_explicit': receipt.get('approval_mode')=='owner_batch_authorized'
            and receipt.get('delegated_by')=='project_owner' and receipt.get('executed_by')=='Codex under explicit user instruction',
        'does_not_claim_individual_human_review': receipt.get('per_question_human_review_attested') is False,
        'authority_reference_present': isinstance(receipt.get('private_authorization_sha256'),str)
            and len(receipt['private_authorization_sha256'])==64,
        'receipt_matches_manifest': manifest.get('owner_approval',{}).get('receipt_sha256')==digest(receipt_path.read_bytes()),
        'candidate_files_unchanged_from_owner_approval': receipt.get('approved_file_sha256')=={k:v['sha256'] for k,v in manifest['files'].items()},
        'test_frozen_at_approved_bytes': manifest['test_lock'].get('state')=='locked'
            and manifest['test_lock'].get('approval_mode')=='owner_batch_authorized'
            and manifest['test_lock'].get('sha256')==digest((directory/'retrieval_test.jsonl').read_bytes()),
        'release_is_qualified': (manifest.get('release_status')=='owner_batch_approved_and_test_locked' or human_release_ok)
            and manifest.get('owner_approval',{}).get('approved')==len(rows),
        'test_not_used_for_parameter_selection': manifest['test_lock'].get('used_for_parameter_selection') is False,
    }
    return {'captured_at':datetime.now(timezone.utc).isoformat(),
            'status':'PASS_OWNER_AUTHORIZED' if all(checks.values()) else 'FAIL',
            'checks':checks,'approved':len(approvals),'total':len(rows),
            'per_question_human_review_attested':False,
            'original_human_review_criterion_automatically_satisfied':False,
            'scope':'Owner delegated batch acceptance and frozen snapshot; not individual human/expert annotation review',
            'errors':[k for k,v in checks.items() if not v]}


def approve(authorization_path):
    authorization_path=authorization_path.resolve(strict=True)
    if not authorization_path.is_relative_to(ROOT/'.runtime'):
        raise ValueError('Keep the actual user authorization under ignored .runtime/')
    authority=json.loads(authorization_path.read_text('utf-8'))
    if (authority.get('actor')!='project_owner' or authority.get('instruction')!='我授权你全部通过，赶紧操作'
            or authority.get('per_question_human_review_attested') is not False):
        raise ValueError('Explicit owner batch authorization and truthful review scope are required')
    manifest_path=EVAL/'dataset_manifest.json'
    manifest=json.loads(manifest_path.read_text('utf-8'))
    if manifest['test_lock']['state']=='locked':
        existing=validate_owner_acceptance()
        if existing['status']=='PASS_OWNER_AUTHORIZED':return existing
        raise ValueError('Existing frozen dataset cannot be overwritten')
    structure=validate(phase='structure')
    if structure['status']!='PASS':raise ValueError('Cannot accept structurally invalid data')
    rows=load_jsonl(EVAL/'retrieval_dev.jsonl')+load_jsonl(EVAL/'retrieval_test.jsonl')
    if authority.get('candidate_manifest_sha256')!=digest(manifest_path.read_bytes()):
        raise ValueError('Candidate changed since the owner authorization was recorded')
    now=datetime.now(timezone.utc).isoformat()
    receipt={'dataset_version':manifest['dataset_version'],'approval_mode':'owner_batch_authorized',
             'approved_at':now,'delegated_by':'project_owner','executed_by':'Codex under explicit user instruction',
             'private_authorization_sha256':digest(authorization_path.read_bytes()),
             'approval_summary':'Owner requested assistant to approve all current candidates; individual reading was not attested.',
             'per_question_human_review_attested':False,'approved_question_count':len(rows),
             'approved_file_sha256':{k:v['sha256'] for k,v in manifest['files'].items()},
             'records':[{'question_id':r['question_id'],'annotation_sha256':r['annotation_sha256'],
                         'decision':'approved','reviewer_type':'owner_delegated_batch'} for r in rows]}
    receipt_path=EVAL/'owner_approval_receipt.json'
    write_json(receipt_path,receipt)
    actual_human=sum(v['approved'] for v in active_reviews(rows).values())
    manifest['human_review']['approved']=actual_human
    manifest['release_status']='owner_batch_approved_and_test_locked'
    manifest['owner_approval']={'mode':'owner_batch_authorized','approved':len(rows),'total':len(rows),
                                'receipt_path':'data/eval/owner_approval_receipt.json','receipt_sha256':digest(receipt_path.read_bytes()),
                                'per_question_human_review_attested':False}
    manifest['test_lock']={'state':'locked','sha256':digest((EVAL/'retrieval_test.jsonl').read_bytes()),
                           'locked_at':now,'approval_mode':'owner_batch_authorized',
                           'used_for_parameter_selection':False,'formal_test_runs':0}
    write_json(manifest_path,manifest)
    return validate_owner_acceptance()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorization-file',type=Path)
    args=parser.parse_args()
    result=approve(args.authorization_file) if args.authorization_file else validate_owner_acceptance()
    write_json(ROOT/'reports/acceptance/task4_owner_acceptance.json',result)
    print(json.dumps({'status':result['status'],'approved':result.get('approved'),
                      'total':result.get('total'),'errors':result['errors']},ensure_ascii=False))
    return 0 if result['status']=='PASS_OWNER_AUTHORIZED' else 1


if __name__=='__main__':raise SystemExit(main())
