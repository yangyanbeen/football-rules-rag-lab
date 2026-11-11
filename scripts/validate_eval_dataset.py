"""Validate task 4 structure or the original full human-reviewed delivery gate."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from eval_dataset import CORPUS, EVAL, ROOT, VERSION, active_reviews, canonical, digest, load_jsonl, question_digest, source_ref, write_json


def normalize(value):
    return re.sub(r'\W+', '', value).casefold()


def validate(directory=EVAL, corpus_path=CORPUS, phase='structure', ledger=None, allow_synthetic_reviews=False):
    directory, corpus_path = Path(directory), Path(corpus_path)
    errors, checks = [], []
    def check(name, passed, detail=None):
        checks.append({'check': name, 'passed': bool(passed), 'detail': detail})
        if not passed: errors.append(name)
    corpus_list = load_jsonl(corpus_path)
    corpus = {r['chunk_id']: r for r in corpus_list}
    check('corpus_has_99_unique_units', len(corpus) == len(corpus_list) == 99)
    manifest = json.loads((directory / 'dataset_manifest.json').read_text('utf-8'))
    check('corpus_matches_manifest', digest(corpus_path.read_bytes()) == manifest['corpus_sha256'])
    check('annotation_input_matches_manifest', digest((directory / 'annotations.json').read_bytes()) == manifest['annotation_source_sha256'])
    datasets = {}
    for name in ('retrieval_dev.jsonl', 'retrieval_test.jsonl', 'answer_eval.jsonl', 'hard_negatives.jsonl'):
        rows = load_jsonl(directory / name)
        datasets[name] = rows
        expected = manifest['files'][name]
        check('file_integrity_' + name, expected['records'] == len(rows) and expected['sha256'] == digest((directory / name).read_bytes()))
    dev, test, answers, negatives = (datasets[n] for n in ('retrieval_dev.jsonl', 'retrieval_test.jsonl', 'answer_eval.jsonl', 'hard_negatives.jsonl'))
    rows = dev + test
    check('pilot_development_30_to_50', 30 <= len(dev) <= 50, {'count': len(dev), 'suggested_not_original_mandatory_threshold': True})
    check('first_test_candidate_at_least_50', len(test) >= 50, {'count': len(test), 'suggested_not_original_mandatory_threshold': True})
    qids = [r.get('question_id') for r in rows]
    check('unique_question_ids', len(set(qids)) == len(qids) and all(isinstance(x, str) and re.fullmatch(r'[DT]\d{3}', x) for x in qids))
    check('questions_nonempty_and_no_exact_duplicates', all(isinstance(r.get('question'), str) and len(r['question'].strip()) >= 8 for r in rows) and len({normalize(r['question']) for r in rows}) == len(rows))
    check('dev_test_distinct_intent_groups', not ({r['intent_group'] for r in dev} & {r['intent_group'] for r in test}))
    failures = []
    required = {'question_id','question','expected_chunk_ids','answerable','topic','difficulty','required_conditions','must_refuse','refusal_reason','source_references','law_numbers','categories','annotation_sha256','hard_negative_ids','hard_negative_content_sha256','split','dataset_version','annotation_origin','answer_scope','intent_group'}
    for row in rows:
        reasons = []
        if not required <= row.keys(): reasons.append('required fields missing')
        if type(row.get('answerable')) is not bool or type(row.get('must_refuse')) is not bool or row['must_refuse'] == row['answerable']: reasons.append('answer/refusal flags invalid')
        ids = row.get('expected_chunk_ids')
        if not isinstance(ids, list) or len(set(ids)) != len(ids) or not all(x in corpus for x in ids): reasons.append('invalid or duplicate supporting ID')
        elif bool(ids) != row['answerable']: reasons.append('answerability/support mismatch')
        elif canonical(row.get('source_references')) != canonical([source_ref(corpus[x]) for x in ids]): reasons.append('citation/source/review boundary differs from original')
        if row['answerable'] and (not row['required_conditions'] or row['refusal_reason'] is not None): reasons.append('answerable must have conditions and no refusal reason')
        if not row['answerable'] and (not isinstance(row['refusal_reason'], str) or len(row['refusal_reason'].strip()) < 8 or row['required_conditions']): reasons.append('unanswerable missing reason or asserts answer conditions')
        if row['difficulty'] not in ('easy','medium','hard') or not isinstance(row['topic'], str) or not row['topic']: reasons.append('topic/difficulty invalid')
        if not isinstance(row['law_numbers'], list) or not all(type(x) is int and 1 <= x <= 17 for x in row['law_numbers']): reasons.append('invalid law numbers')
        if not isinstance(row['categories'], list) or not row['categories'] or not set(row['categories']) <= {'term','number','condition','exception','cross_chunk','version','out_of_scope','unanswerable'}: reasons.append('invalid categories')
        if row['annotation_sha256'] != question_digest(row): reasons.append('question content hash mismatch')
        if row['dataset_version'] != VERSION or row['split'] not in ('dev','test') or not isinstance(row['annotation_origin'], str): reasons.append('version/split/origin invalid')
        if 'cross_chunk' in row['categories'] and len(ids) < 2: reasons.append('cross-chunk question lacks multiple supporting units')
        if reasons: failures.append({'question_id': row['question_id'], 'errors': reasons})
    check('all_question_labels_and_provenance_valid', not failures, failures)
    check('split_membership', all(r['split'] == 'dev' for r in dev) and all(r['split'] == 'test' for r in test))
    check('answer_eval_one_to_one_aligned', len(answers) == len(rows) and all(
        answer == {**row, 'expected_answer_points': row['required_conditions'], 'expected_refusal_reason': row['refusal_reason']}
        for answer, row in zip(answers, rows)))
    by_id = {r['question_id']: r for r in rows}
    negative_ids, negative_errors = set(), []
    for negative in negatives:
        qid, chunk = negative.get('question_id'), negative.get('chunk_id')
        row = by_id.get(qid)
        bad = (not row or chunk not in corpus or negative.get('hard_negative_id') in negative_ids
               or chunk in row['expected_chunk_ids'] or not isinstance(negative.get('reason'), str) or len(negative['reason'].strip()) < 12
               or negative.get('annotation_sha256') != row['annotation_sha256']
               or digest(canonical({k:v for k,v in negative.items() if k != 'annotation_sha256'})) != row['hard_negative_content_sha256']
               or canonical(negative.get('source_reference')) != canonical(source_ref(corpus[chunk]))
               or negative.get('label') != 'insufficient_for_target_answer')
        if bad: negative_errors.append(qid)
        negative_ids.add(negative.get('hard_negative_id'))
    check('hard_negative_ids_reasons_and_sources', not negative_errors, negative_errors)
    check('each_question_has_a_traceable_hard_negative', len(negatives) == len(rows) and all(
        set(r['hard_negative_ids']) == {n['hard_negative_id'] for n in negatives if n['question_id'] == r['question_id']} and r['hard_negative_ids'] for r in rows))
    coverage = {}
    for split, group in (('dev',dev),('test',test)):
        laws = sorted({law for r in group for law in r['law_numbers']})
        categories = Counter(c for r in group for c in r['categories'])
        coverage[split] = {'questions': len(group), 'answerable': sum(r['answerable'] for r in group),
                           'unanswerable': sum(r['must_refuse'] for r in group), 'laws': laws,
                           'categories': dict(categories), 'difficulty': dict(Counter(r['difficulty'] for r in group))}
        check(split + '_covers_rules_1_to_17', laws == list(range(1,18)), laws)
        check(split + '_covers_required_question_types', all(categories[x] > 0 for x in ('term','number','condition','exception','cross_chunk','version','out_of_scope')))
    legacy = load_jsonl(ROOT / 'data/quality_regression/development_cases.jsonl')
    check('test_does_not_reuse_16_tuned_questions', not ({normalize(r['question']) for r in legacy} & {normalize(r['question']) for r in test}))
    reviews = active_reviews(rows, allow_synthetic=allow_synthetic_reviews, **({'ledger': ledger} if ledger is not None else {}))
    approved = sum(r['approved'] for r in reviews.values())
    if phase == 'delivery':
        check('all_questions_actually_human_reviewed', approved == len(rows), {'approved': approved, 'total': len(rows), 'not_approved': [k for k,v in reviews.items() if not v['approved']]})
        lock = manifest['test_lock']
        check('test_frozen_after_review', lock.get('state') == 'locked' and lock.get('sha256') == digest((directory / 'retrieval_test.jsonl').read_bytes()) and lock.get('used_for_parameter_selection') is False)
        check('release_status_matches_human_review', manifest.get('release_status') == 'human_reviewed_and_test_locked' and manifest['human_review']['approved'] == approved)
        if lock.get('state') == 'locked':
            ledger_path = Path(ledger) if ledger is not None else ROOT/'.runtime/eval_review/reviews.jsonl'
            check('frozen_review_ledger_integrity', ledger_path.exists() and manifest['human_review'].get('ledger_sha256') == digest(ledger_path.read_bytes()))
    return {'captured_at': datetime.now(timezone.utc).isoformat(), 'phase': phase,
            'status': 'PASS' if not errors else 'FAIL', 'passed': sum(x['passed'] for x in checks), 'total': len(checks),
            'errors': errors, 'checks': checks, 'coverage': coverage,
            'human_review': {'approved': approved, 'total': len(rows)},
            'does_not_prove': ['AI labels are factually correct', 'human review happened without matching real records', 'expert or official rule validation', 'retrieval or answer accuracy']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('structure','delivery'), default='structure')
    parser.add_argument('--report', default='reports/acceptance/task4_structure.json')
    args = parser.parse_args()
    output = (ROOT / args.report).resolve()
    if not output.is_relative_to(ROOT / 'reports') or output.suffix != '.json': raise ValueError('Use a JSON receipt under reports/')
    try:
        result = validate(phase=args.phase)
    except (KeyError,TypeError,ValueError,OSError) as exc:
        result = {'phase':args.phase, 'status':'FAIL', 'errors':[f'{type(exc).__name__}: {exc}']}
    write_json(output, result)
    print(json.dumps({k:v for k,v in result.items() if k in ('status','phase','passed','total','errors','human_review','coverage')}, ensure_ascii=False))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
