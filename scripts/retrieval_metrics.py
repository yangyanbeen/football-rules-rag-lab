"""Arithmetic only. Recall@K follows the original plan's any-support-hit rule."""
from __future__ import annotations


def compute_metrics(questions, predictions):
    by_question = {row['question_id']: row for row in questions}
    if len(by_question) != len(questions):
        raise ValueError('Duplicate question ID')
    by_prediction = {row['question_id']: row for row in predictions}
    if len(by_prediction) != len(predictions) or set(by_prediction) != set(by_question):
        raise ValueError('Predictions must cover every question exactly once')
    per_question = []
    for qid, row in by_question.items():
        ranked = by_prediction[qid]['results']
        ids = [entry['chunk_id'] for entry in ranked]
        if len(ids) != len(set(ids)) or [r['rank'] for r in ranked] != list(range(1, len(ranked) + 1)):
            raise ValueError('Predictions require unique chunk IDs and consecutive ranks starting at 1')
        if type(row['answerable']) is not bool:
            raise ValueError('answerable must be a boolean')
        expected = set(row['expected_chunk_ids'])
        if row['answerable'] != bool(expected):
            raise ValueError('Answerability and supporting evidence disagree')
        if not row['answerable']:
            per_question.append({'question_id': qid, 'retrieval_metric_included': False,
                                 'reason': 'No gold evidence; report refusal separately in task 12'})
            continue
        first = next((i for i, chunk in enumerate(ids[:10], 1) if chunk in expected), None)
        per_question.append({'question_id': qid, 'retrieval_metric_included': True,
                             'Recall@5': float(bool(expected.intersection(ids[:5]))),
                             'Recall@10': float(bool(expected.intersection(ids[:10]))),
                             'MRR@10': 1 / first if first else 0.0,
                             'all_gold_coverage@5': len(expected.intersection(ids[:5])) / len(expected),
                             'first_relevant_rank_within_10': first})
    included = [row for row in per_question if row['retrieval_metric_included']]
    if not included:
        raise ValueError('At least one answerable question is required for retrieval averages')
    return {'questions': len(questions), 'answerable_denominator': len(included),
            'unanswerable_excluded': len(questions) - len(included),
            'definitions': {'Recall@K': 'Fraction of answerable questions with at least one labelled supporting chunk in top K, per original technical design.',
                            'MRR@10': 'Mean reciprocal rank of first labelled support, zero beyond rank 10.',
                            'all_gold_coverage@5': 'Separate mean fraction of labelled support IDs retrieved, not the plan Recall@5.'},
            'metrics': {name: sum(r[name] for r in included) / len(included) for name in ('Recall@5','Recall@10','MRR@10','all_gold_coverage@5')},
            'nDCG@10': None, 'nDCG_reason': 'No graded relevance labels; not reported.', 'per_question': per_question}
