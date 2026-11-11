"""Deterministically expand AI-authored candidates; never invent human reviews."""
from __future__ import annotations

import json

from eval_dataset import CORPUS, EVAL, REVIEW_LEDGER, VERSION, active_reviews, canonical, digest, load_jsonl, question_digest, source_ref, write_json, write_jsonl


def build(directory=EVAL, ledger=REVIEW_LEDGER):
    manifest_path = directory / 'dataset_manifest.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text('utf-8')).get('test_lock', {}).get('state') == 'locked':
        raise ValueError('Test is frozen. Create a new version/directory; never overwrite a locked set.')
    annotations = json.loads((directory / 'annotations.json').read_text('utf-8'))
    corpus = {r['chunk_id']: r for r in load_jsonl(CORPUS)}
    outputs, negatives = {}, []
    for split in ('dev', 'test'):
        rows = []
        for item in annotations[split]:
            qid, question, intent, law, difficulty, ids, conditions, categories, negative, reason, *refusal = item
            row = {'question_id': qid, 'question': question, 'expected_chunk_ids': ids,
                   'answerable': bool(ids), 'topic': intent, 'intent_group': intent,
                   'law_numbers': sorted({corpus[x]['law_number'] for x in ids} | ({law} if law else set())),
                   'difficulty': difficulty, 'required_conditions': conditions, 'must_refuse': not bool(ids),
                   'refusal_reason': refusal[0] if refusal else None, 'categories': categories,
                   'split': split, 'dataset_version': VERSION, 'hard_negative_ids': ['HN-' + qid],
                   'source_references': [source_ref(corpus[x]) for x in ids],
                   'annotation_origin': 'AI-authored draft; not human-validated or official football guidance',
                   'answer_scope': 'Answer only from this fixed Wikipedia corpus; retain source/version/review qualifications'}
            negative_row = {'hard_negative_id': 'HN-' + qid, 'question_id': qid, 'chunk_id': negative,
                              'reason': reason, 'label': 'insufficient_for_target_answer',
                              'source_reference': source_ref(corpus[negative]),
                              'review_status': 'AI draft; human approval stored separately'}
            row['hard_negative_content_sha256'] = digest(canonical(negative_row))
            row['annotation_sha256'] = question_digest(row)
            negative_row['annotation_sha256'] = row['annotation_sha256']
            rows.append(row)
            negatives.append(negative_row)
        outputs['retrieval_' + split + '.jsonl'] = rows
    all_rows = outputs['retrieval_dev.jsonl'] + outputs['retrieval_test.jsonl']
    outputs['answer_eval.jsonl'] = [{**r, 'expected_answer_points': r['required_conditions'],
                                    'expected_refusal_reason': r['refusal_reason']} for r in all_rows]
    outputs['hard_negatives.jsonl'] = negatives
    for name, rows in outputs.items():
        write_jsonl(directory / name, rows)
    approved = sum(v['approved'] for v in active_reviews(all_rows, ledger).values())
    manifest = {'dataset_version': VERSION, 'release_status': 'candidate_awaiting_human_review',
                'corpus_version': 'corpus-b0-rag-adapter-1.0.0', 'corpus_sha256': digest(CORPUS.read_bytes()),
                'annotation_source_sha256': digest((directory / 'annotations.json').read_bytes()),
                'files': {name: {'sha256': digest((directory / name).read_bytes()), 'records': len(rows)} for name, rows in outputs.items()},
                'human_review': {'required': True, 'approved': approved, 'total': len(all_rows),
                                 'ledger_distribution': 'local-only; generated approvals forbidden'},
                'test_lock': {'state': 'awaiting_human_review', 'candidate_sha256': digest((directory / 'retrieval_test.jsonl').read_bytes()),
                              'used_for_parameter_selection': False, 'formal_test_runs': 0},
                'metric_scope': 'No real retrieval or answer performance measured by task 4',
                'license_scope': 'Original questions/annotations; source metadata retains Wikipedia attribution. No full source corpus distributed.'}
    write_json(manifest_path, manifest)
    return {'built': {k: len(v) for k, v in outputs.items()}, 'human_approved': approved, 'status': 'CANDIDATE'}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False))
