"""Exercise task 4 validators/metric arithmetic using disposable synthetic cases.

Synthetic review records exist only in temporary fixtures and never count as
real manual review. No live test predictions, model calls or label approvals.
"""
from __future__ import annotations

import json
import math
import shutil
from datetime import datetime, timezone

from eval_dataset import CHECKLIST, CORPUS, EVAL, ROOT, active_reviews, canonical, digest, load_jsonl, question_digest, write_json, write_jsonl
from retrieval_metrics import compute_metrics
from run_retrieval_metrics import authorize_test
from validate_eval_dataset import validate
from build_eval_dataset import build
from freeze_eval_dataset import freeze


def main():
    before = {p.name:digest(p.read_bytes()) for p in EVAL.iterdir() if p.is_file()}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    fixture_root = ROOT/'.tmp'/('task4-workflow-'+stamp)
    fixture_root.mkdir(parents=True)
    outcomes = []
    def record(name, passed, detail=None):
        outcomes.append({'check':name,'passed':bool(passed),'detail':detail})

    structure = validate(phase='structure')
    record('real_candidate_structure', structure['status']=='PASS', {'checks':[structure['passed'],structure['total']]})
    questions=[{'question_id':'fixture-A','answerable':True,'expected_chunk_ids':['a','b']},
               {'question_id':'fixture-B','answerable':True,'expected_chunk_ids':['d']},
               {'question_id':'fixture-U','answerable':False,'expected_chunk_ids':[]}]
    def prediction(qid, ids):
        return {'question_id':qid,'results':[{'chunk_id':x,'rank':i,'score':1/i} for i,x in enumerate(ids,1)]}
    predictions=[prediction('fixture-A',['x','b']),prediction('fixture-B',['u','v','w','x','y','d']),prediction('fixture-U',[])]
    score=compute_metrics(questions,predictions)
    hand={'Recall@5':.5,'Recall@10':1.0,'MRR@10':(1/2+1/6)/2,'all_gold_coverage@5':.25}
    for name,value in hand.items():record('hand_calculated_'+name, math.isclose(score['metrics'][name],value,abs_tol=1e-12), {'expected':value,'actual':score['metrics'][name]})
    record('unanswerable_excluded_from_retrieval_denominator',score['answerable_denominator']==2 and score['unanswerable_excluded']==1)
    record('no_unjustified_nDCG',score['nDCG@10'] is None)
    for name,bad in [('missing_prediction',predictions[:2]),('duplicate_question_prediction',predictions+[predictions[0]]),
                     ('duplicate_ranked_chunk',[prediction('fixture-A',['a','a']),*predictions[1:]]),
                     ('nonconsecutive_ranks',[{**predictions[0],'results':[{'chunk_id':'b','rank':3}]},*predictions[1:]])]:
        try:compute_metrics(questions,bad); rejected=False
        except ValueError:rejected=True
        record('metrics_reject_'+name,rejected)

    cases = [
        ('duplicate_question_id',lambda d,t,a,n:d[1].update(question_id=d[0]['question_id'])),
        ('unknown_support',lambda d,t,a,n:d[0].update(expected_chunk_ids=['L99-99'])),
        ('string_answerable',lambda d,t,a,n:d[0].update(answerable='true')),
        ('empty_refusal_reason',lambda d,t,a,n:d[-1].update(refusal_reason='')),
        ('forged_support_url',lambda d,t,a,n:d[0]['source_references'][0].update(source_url='https://invalid.example/')),
        ('overstated_revision_verified',lambda d,t,a,n:d[0]['source_references'][0].update(source_revision_verified=True)),
        ('overstated_expert_review',lambda d,t,a,n:d[0]['source_references'][0].update(expert_reviewed=True)),
        ('missing_required_field',lambda d,t,a,n:d[0].pop('difficulty')),
        ('negative_is_support',lambda d,t,a,n:n[0].update(chunk_id=d[0]['expected_chunk_ids'][0])),
        ('empty_negative_reason',lambda d,t,a,n:n[0].update(reason='')),
        ('forged_negative_source',lambda d,t,a,n:n[0]['source_reference'].update(source_id='invented')),
        ('test_duplicates_dev_question',lambda d,t,a,n:t[0].update(question=d[0]['question'])),
        ('test_duplicates_dev_intent',lambda d,t,a,n:t[0].update(intent_group=d[0]['intent_group'])),
        ('duplicate_support_id',lambda d,t,a,n:d[0].update(expected_chunk_ids=d[0]['expected_chunk_ids']*2)),
        ('cross_chunk_without_second_unit',lambda d,t,a,n:d[0]['categories'].append('cross_chunk')),
        ('invalid_law_zero',lambda d,t,a,n:d[0].update(law_numbers=[0])),
    ]
    corpus={r['chunk_id']:r for r in load_jsonl(CORPUS)}
    rejections=[]
    for name, mutate in cases:
        folder=fixture_root/name
        shutil.copytree(EVAL,folder)
        d,t,a,n=(load_jsonl(folder/file) for file in ('retrieval_dev.jsonl','retrieval_test.jsonl','answer_eval.jsonl','hard_negatives.jsonl'))
        mutate(d,t,a,n)
        by_id={r['question_id']:r for r in d+t}
        for neg in n:
            row=by_id.get(neg['question_id'])
            if row:row['hard_negative_content_sha256']=digest(canonical({k:v for k,v in neg.items() if k!='annotation_sha256'}))
        for row in d+t:row['annotation_sha256']=question_digest(row)
        for neg in n:
            if neg['question_id'] in by_id:neg['annotation_sha256']=by_id[neg['question_id']]['annotation_sha256']
        a=[{**r,'expected_answer_points':r['required_conditions'],'expected_refusal_reason':r['refusal_reason']} for r in d+t]
        manifest=json.loads((folder/'dataset_manifest.json').read_text('utf-8'))
        for file,values in zip(('retrieval_dev.jsonl','retrieval_test.jsonl','answer_eval.jsonl','hard_negatives.jsonl'),(d,t,a,n)):
            write_jsonl(folder/file,values)
            manifest['files'][file]={'sha256':digest((folder/file).read_bytes()),'records':len(values)}
        write_json(folder/'dataset_manifest.json',manifest)
        try:
            result=validate(folder,phase='structure',ledger=fixture_root/'nonexistent-ledger.jsonl')
            rejected=result['status']=='FAIL'
            failures=result['errors']
        except (ValueError,TypeError,KeyError) as exc:
            rejected=True;failures=[type(exc).__name__]
        rejections.append({'case':name,'rejected':rejected,'validator_errors':failures,'outer_and_annotation_hashes_recalculated':True})
    record('all_16_rehashed_corrupt_cases_rejected',all(r['rejected'] for r in rejections),rejections)

    # Test the full state transition only in an explicitly synthetic fixture.
    transition = fixture_root/'SYNTHETIC-freeze-roundtrip'
    shutil.copytree(EVAL,transition)
    no_ledger = fixture_root/'no-real-person-review.jsonl'
    # An actually frozen release must never be rebuilt; a fixture may reset its
    # own manifest in order to exercise the candidate -> frozen transition.
    copied_manifest=json.loads((transition/'dataset_manifest.json').read_text('utf-8'))
    copied_manifest['test_lock']['state']='awaiting_human_review'
    write_json(transition/'dataset_manifest.json',copied_manifest)
    build(transition,no_ledger)
    first={p.name:digest(p.read_bytes()) for p in transition.iterdir() if p.is_file()}
    build(transition,no_ledger)
    record('isolated_candidate_build_is_deterministic',first=={p.name:digest(p.read_bytes()) for p in transition.iterdir() if p.is_file()})
    try:freeze(transition,no_ledger);rejected=False
    except ValueError:rejected=True
    record('freeze_refuses_missing_human_review',rejected)
    synthetic_ledger=fixture_root/'SYNTHETIC-90-review-records-ONLY.jsonl'
    synthetic_rows=load_jsonl(transition/'retrieval_dev.jsonl')+load_jsonl(transition/'retrieval_test.jsonl')
    write_jsonl(synthetic_ledger,[{'question_id':r['question_id'],'annotation_sha256':r['annotation_sha256'],
        'reviewer_type':'human','reviewer_name':'SYNTHETIC TEST FIXTURE; NOT A PERSON',
        'decision':'approved','reviewed_at':datetime.now(timezone.utc).isoformat(),
        'checklist':{k:True for k in CHECKLIST},'fixture_only':True} for r in synthetic_rows])
    record('synthetic_records_never_count_as_real_reviews',not any(v['approved'] for v in active_reviews(synthetic_rows,synthetic_ledger).values()))
    freeze(transition,synthetic_ledger,allow_synthetic=True)
    record('synthetic_only_complete_lock_roundtrip',validate(transition,phase='delivery',ledger=synthetic_ledger,allow_synthetic_reviews=True)['status']=='PASS')
    try:build(transition,no_ledger);rejected=False
    except ValueError:rejected=True
    record('builder_refuses_overwriting_frozen_test',rejected)
    frozen_manifest=json.loads((transition/'dataset_manifest.json').read_text('utf-8'))
    authorize_test(frozen_manifest,'final_report',{'purpose':'final_report','used_for_parameter_selection':False,
                   'dataset_version':frozen_manifest['dataset_version'],'test_sha256':frozen_manifest['test_lock']['sha256'],
                   'config_sha256':digest(b'synthetic immutable config')},b'synthetic immutable config')
    record('synthetic_final_report_requires_matching_config',True)
    try:
        authorize_test(frozen_manifest,'final_report',{'purpose':'final_report','used_for_parameter_selection':False,
            'dataset_version':frozen_manifest['dataset_version'],'test_sha256':frozen_manifest['test_lock']['sha256'],
            'config_sha256':digest(b'old configuration')},b'new configuration')
        rejected=False
    except ValueError:rejected=True
    record('test_gate_rejects_changed_configuration',rejected)
    modified=json.loads(json.dumps(synthetic_rows[0]))
    modified['required_conditions'].append('SYNTHETIC altered condition')
    modified['annotation_sha256']=question_digest(modified)
    record('annotation_edit_invalidates_previous_review',not active_reviews([modified],synthetic_ledger)[modified['question_id']]['approved'])

    real_rows=load_jsonl(EVAL/'retrieval_dev.jsonl')+load_jsonl(EVAL/'retrieval_test.jsonl')
    row=real_rows[0]
    fixture_event={'question_id':row['question_id'],'annotation_sha256':row['annotation_sha256'],
                   'reviewer_type':'ai','reviewer_name':'SYNTHETIC FIXTURE ONLY','decision':'approved',
                   'reviewed_at':datetime.now(timezone.utc).isoformat(),'checklist':{k:True for k in CHECKLIST}}
    fake_path=fixture_root/'synthetic-review-fixture.jsonl'
    write_jsonl(fake_path,[fixture_event])
    record('ai_signoff_rejected',not active_reviews([row],fake_path)[row['question_id']]['approved'])
    fixture_event.update(reviewer_type='human',annotation_sha256='0'*64)
    write_jsonl(fake_path,[fixture_event])
    record('stale_human_hash_rejected',not active_reviews([row],fake_path)[row['question_id']]['approved'])
    fixture_event.update(annotation_sha256=row['annotation_sha256'],reviewed_at='2099-01-01T00:00:00+00:00')
    write_jsonl(fake_path,[fixture_event])
    record('future_review_timestamp_rejected',not active_reviews([row],fake_path)[row['question_id']]['approved'])
    fixture_event.update(reviewed_at=datetime.now(timezone.utc).isoformat(),checklist={})
    write_jsonl(fake_path,[fixture_event])
    record('incomplete_review_checklist_rejected',not active_reviews([row],fake_path)[row['question_id']]['approved'])
    manifest=json.loads((EVAL/'dataset_manifest.json').read_text('utf-8'))
    for name,purpose in [('parameter_tuning','development'),('unreviewed_test','final_report')]:
        candidate={**manifest,'test_lock':{'state':'awaiting_human_review'}}
        try:authorize_test(candidate,purpose,None,b'');rejected=False
        except ValueError:rejected=True
        record('test_gate_rejects_'+name,rejected)
    record('original_eval_inputs_unchanged',before=={p.name:digest(p.read_bytes()) for p in EVAL.iterdir() if p.is_file()})
    result={'captured_at':datetime.now(timezone.utc).isoformat(),
            'status':'PASS' if all(x['passed'] for x in outcomes) else 'FAIL',
            'scope':'Automated structure/arithmetic/adversarial checks ONLY; does not complete required real human annotation review.',
            'passed':sum(x['passed'] for x in outcomes),'total':len(outcomes),'checks':outcomes,
            'synthetic_hand_calculation':{'questions':questions,'predictions':predictions,'expected_metrics':hand,'actual':score},
            'real_dataset_scores_computed':False,'actual_human_reviews_created':False,
            'implementation_sha256':{name:digest((ROOT/'scripts'/name).read_bytes()) for name in (
                'eval_dataset.py','build_eval_dataset.py','validate_eval_dataset.py','retrieval_metrics.py',
                'run_retrieval_metrics.py','freeze_eval_dataset.py','serve_eval_review.py','verify_task4_workflow.py','recheck_task4.ps1')},
            'synthetic_review_notice':'Only disposable .tmp fixtures contain synthetic review records to test program logic. They never count toward the real dataset.'}
    write_json(ROOT/'reports/acceptance/task4_workflow_verification.json',result)
    print(json.dumps({'status':result['status'],'passed':result['passed'],'total':result['total'],
                      'corrupt_cases_rejected':sum(r['rejected'] for r in rejections),'actual_human_reviews_created':False}))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
