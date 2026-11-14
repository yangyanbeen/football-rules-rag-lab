"""Independent human-sample arithmetic and error analysis, without editing frozen answers."""
from __future__ import annotations
import argparse
from answer_eval_core import *
import answer_review_v2 as review
from citation_catalog_guard import load_policy

HUMAN='reports/answer_evaluation_acceptance/human-review-completed.json'
ANALYSIS='reports/answer_evaluation_acceptance/human-quality-analysis.json'


def strict_human(value):
    context=review.review_context();review.validate_public_summary(value,context)
    if value['status']!='REVIEW_COMPLETE' or value['reviewed_samples']!=12 or value['missing_ids'] or value['unresolved_ids']:
        raise ValueError('Real twelve-question human review incomplete')
    receipt=value.get('private_ledger')
    if not isinstance(receipt,dict) or set(receipt)!={'path','size_bytes','sha256'}:
        raise ValueError('Missing or non-redacted private ledger receipt')
    for key in ('required_samples','reviewed_samples','ledger_entries'):
        if type(value[key]) is not int:raise ValueError('Human count must be an integer')
    for metric,key in (('answer_point_coverage','point_decisions'),('citation_correctness','citation_decisions'),('condition_exception_retention','condition_decisions')):
        decisions=[d for r in value['per_question'] for d in r[key]]
        m=value['metrics'][metric]
        if any(type(m[k]) is not int for k in ('numerator','denominator','uncertain')) or m!={**ratio(decisions.count('yes'),len(decisions)),'uncertain':decisions.count('uncertain')}:
            raise ValueError('Human metric does not independently recompute')
    return context


def analyze(value):
    context=strict_human(value);policy=load_policy();grades={g['question_id']:g for g in rows(DIRECTORY/'test/judgments.jsonl')}
    cases=[];diffs=[];counts={k:[0,0] for k in ('points','conditions','citations')}
    for r in value['per_question']:
        q=context['labels'][r['question_id']];p=context['predictions'][r['question_id']]
        missing_points=[s for s,v in zip(q['expected_answer_points'],r['point_decisions']) if v=='no']
        missing_conditions=[s for s,v in zip(q['required_conditions'],r['condition_decisions']) if v=='no']
        bad=[{'chunk_id':c['chunk_id'],'classification':'catalog_number_not_official' if c['chunk_id'] in policy else 'human_rejected_support_or_relevance'}
            for c,v in zip(p['citations'],r['citation_decisions']) if v=='no']
        if missing_points or missing_conditions or bad or r['refusal_appropriate']=='no':
            cases.append({'question_id':r['question_id'],'status':p['status'],'missing_points':missing_points,
                'missing_conditions':missing_conditions,'rejected_citations':bad,
                'false_refusal_by_frozen_label':q['answerable'] and p['status']=='refused',
                'human_answerability_choice_appropriate':r['refusal_appropriate']=='yes'})
        disagreement={}
        for key,decision in (('points','point_decisions'),('conditions','condition_decisions'),('citations','citation_decisions')):
            human=[v=='yes' for v in r[decision]];ai=grades[r['question_id']]['grade'][key]
            if len(human)!=len(ai):raise ValueError('AI/human comparison vector differs')
            slots=[i for i,(h,a) in enumerate(zip(human,ai)) if h!=a]
            counts[key][0]+=len(slots);counts[key][1]+=len(human)
            if slots:disagreement[key]=slots
        if disagreement:diffs.append({'question_id':r['question_id'],'different_zero_based_slots':disagreement})
    rs=value['per_question'];answerable=sum(r['answerable'] for r in rs);must_refuse=len(rs)-answerable
    return {'version':'answer-human-quality-1.0','human_reviewed_questions':12,'ledger_entries':value['ledger_entries'],
        'human_semantic_metrics':value['metrics'],
        'label_based_refusal_metrics':{
            'correct_refusal_rate':ratio(sum(not r['answerable'] and r['status']=='refused' for r in rs),must_refuse),
            'false_refusal_rate':ratio(sum(r['answerable'] and r['status']=='refused' for r in rs),answerable)},
        'human_answerability_choice_appropriate':ratio(sum(r['refusal_appropriate']=='yes' for r in rs),len(rs)),
        'AI_human_disagreement':{k:ratio(*v) for k,v in counts.items()},'AI_human_different_questions':diffs,
        'error_cases':cases,'model_configuration':record(ROOT/CONFIG),'human_receipt':record(ROOT/HUMAN),
        'review_assistance':'AI supplied suggested choices before the user explicitly submitted each local browser form; not independent blind review or referee expertise.',
        'interpretation':'Twelve error-prioritized reviewed test answers only. Zero unanswerable samples means correct refusal is null, not100%. No overall50 accuracy, improvement or causal gain claim; frozen AI results unchanged.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',default=ANALYSIS);a=p.parse_args()
    result=analyze(read(ROOT/HUMAN));write_new(ROOT/a.report,result)
    print(json.dumps({k:result[k] for k in ('human_reviewed_questions','human_semantic_metrics','label_based_refusal_metrics','human_answerability_choice_appropriate')},ensure_ascii=False))
