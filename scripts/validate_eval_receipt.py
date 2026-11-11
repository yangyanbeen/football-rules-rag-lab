"""Validate the published review receipt without needing corpus text or a private ledger.

This checks published metadata consistency, not a new proof of human reading.
Original full acceptance still requires the actual private matching reviews.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from eval_dataset import EVAL, ROOT, digest, load_jsonl, question_digest, write_json


def instant(value):
    if not isinstance(value,str):
        raise ValueError('Receipt timestamps must be strings')
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Receipt timestamps need a timezone')
    return parsed


def validate_receipt(directory=EVAL):
    directory=Path(directory)
    checks=[]
    def check(name, passed):checks.append({'check':name,'passed':bool(passed)})
    try:
        manifest=json.loads((directory/'dataset_manifest.json').read_text('utf-8'))
        receipt_path=directory/'human_review_receipt.json'
        receipt=json.loads(receipt_path.read_text('utf-8'))
        dev,test=load_jsonl(directory/'retrieval_dev.jsonl'),load_jsonl(directory/'retrieval_test.jsonl')
        rows=dev+test
        names=('retrieval_dev.jsonl','retrieval_test.jsonl','answer_eval.jsonl','hard_negatives.jsonl')
        check('published_eval_files_match_manifest',set(manifest['files'])==set(names) and all(
            digest((directory/name).read_bytes())==manifest['files'][name]['sha256']
            and len(load_jsonl(directory/name))==manifest['files'][name]['records'] for name in names))
        expected={row['question_id']:row['annotation_sha256'] for row in rows}
        check('unique_90_reviewed_questions',len(dev)==40 and len(test)==50 and len(expected)==len(rows)==90)
        check('annotation_hashes_match_published_labels',all(row['annotation_sha256']==question_digest(row) for row in rows))
        review=manifest['human_review']
        check('human_release_counts_and_status',manifest['release_status']=='human_reviewed_and_test_locked'
              and review['approved']==review['total']==len(rows))
        check('receipt_path_and_hash',review['receipt_path']=='data/eval/human_review_receipt.json'
              and review['receipt_sha256']==digest(receipt_path.read_bytes()))
        check('receipt_version_status_count',receipt['dataset_version']==manifest['dataset_version']
              and receipt['status']=='APPROVED' and receipt['reviewed_questions']==len(rows))
        records=receipt['records']
        check('each_receipt_record_binds_current_question',len(records)==len(rows)
              and {r['question_id']:r['annotation_sha256'] for r in records}==expected
              and len({r['question_id'] for r in records})==len(records))
        check('all_receipt_decisions_are_human_approved',all(r['reviewer_type']=='human' and r['decision']=='approved' for r in records))
        allowed={'question_id','annotation_sha256','reviewer_type','decision','reviewed_at'}
        check('public_records_do_not_expose_private_review_fields',all(set(r)==allowed for r in records))
        completed=instant(receipt['completed_at'])
        check('review_times_precede_completed_release',completed<=datetime.now(timezone.utc)
              and all(instant(r['reviewed_at'])<=completed for r in records))
        ledger_sha=review['ledger_sha256']
        check('private_ledger_hash_bound_without_disclosure',isinstance(ledger_sha,str)
              and re.fullmatch('[0-9a-f]{64}',ledger_sha) is not None and receipt['private_ledger_sha256']==ledger_sha)
        lock=manifest['test_lock']
        test_sha=digest((directory/'retrieval_test.jsonl').read_bytes())
        check('test_lock_and_receipt_bind_same_test_bytes',lock['state']=='locked' and lock['used_for_parameter_selection'] is False
              and lock['sha256']==receipt['test_sha256']==test_sha)
        check('receipt_completion_matches_locked_release',receipt['completed_at']==lock.get('human_review_completed_at',lock['locked_at'])
              and instant(lock['locked_at'])<=completed)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        return {'status':'FAIL','checks':checks,'errors':[type(exc).__name__+': '+str(exc).replace(str(directory),'<eval>')],
                'private_human_reading_independently_proven':False}
    errors=[c['check'] for c in checks if not c['passed']]
    return {'status':'PASS_PUBLIC_RECEIPT' if not errors else 'FAIL','passed':sum(c['passed'] for c in checks),
            'total':len(checks),'checks':checks,'errors':errors,'reviewed_questions':len(rows),
            'scope':'Published receipt consistency only; full delivery still requires the private matching human reviews',
            'private_human_reading_independently_proven':False}


def require_receipt(directory=EVAL):
    result=validate_receipt(directory)
    if result['status']!='PASS_PUBLIC_RECEIPT':
        raise ValueError('Published human review receipt is invalid: '+', '.join(result['errors']))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=EVAL)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    result=validate_receipt(args.data_dir)
    if args.report:
        path=args.report.resolve()
        if not any(path.is_relative_to(ROOT/name) for name in ('reports','.tmp')) or path.suffix!='.json':
            raise ValueError('Use a JSON report under reports/ or .tmp/')
        write_json(path,result)
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['status']=='PASS_PUBLIC_RECEIPT' else 1


if __name__=='__main__':raise SystemExit(main())
