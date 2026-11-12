"""Synthetic Dense B0 contract checks; never reads real questions or calls models."""
from __future__ import annotations

import argparse
import copy
import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dense_retrieval_eval import (SOURCE_FIELDS, TIMINGS, load_config, normalize_query,
                                  percentile, summarize, validate_predictions)
from eval_dataset import ROOT, digest


def fixtures(cfg):
    """All IDs, questions, sources and observations below are invented fixtures."""
    run_id='a'*32
    sources=[dict(zip(SOURCE_FIELDS,(
        f'S{i:02d}',f'https://example.invalid/synthetic/{i}',[i*10,i*10+5],
        i,digest(f'record-{i}'.encode()),digest(f'content-{i}'.encode()))))
        for i in range(1,13)]
    questions=[
        {'question_id':'Q_A','question':'  \u3000合成Ａ\t问题  ',
         'answerable':True,'expected_chunk_ids':['S02','S11'],'categories':['synthetic-multi']},
        {'question_id':'Q_B','question':'合成B问题',
         'answerable':True,'expected_chunk_ids':['S06'],'categories':['synthetic-single']},
        {'question_id':'Q_C','question':'合成C问题',
         'answerable':True,'expected_chunk_ids':['S12'],'categories':['synthetic-single']},
        {'question_id':'Q_U','question':'合成无答案问题',
         'answerable':False,'expected_chunk_ids':[],'categories':['synthetic-outside']},
    ]
    predictions=[]
    for qi,q in enumerate(questions):
        results=[{**s,'rank':rank,'distance':rank/20,'score':1-rank/20}
                 for rank,s in enumerate(sources[:cfg['top_k']],1)]
        measurements=[]
        for rep in range(1,cfg['measured_repetitions']+1):
            sample=qi*cfg['measured_repetitions']+rep
            measurements.append({'repetition':rep,
                'ranked_ids':[r['chunk_id'] for r in results],
                'distances':[r['distance'] for r in results],
                'scores':[r['score'] for r in results],
                'normalization_seconds':sample/10000,
                'query_embedding_seconds':sample/1000,
                'vector_search_seconds':sample/5000,
                'total_seconds':sample/500,
                'embedding_observation':{'inputs':1,'prompt_eval_count':8,
                    'elapsed_seconds':sample/1000,'server_total_duration_ns':sample*1000,
                    'server_load_duration_ns':0}})
        predictions.append({'question_id':q['question_id'],
            'question_sha256':digest(q['question'].encode('utf-8')),
            'query':normalize_query(q['question']),'split':'dev','run_id':run_id,
            'results':results,'measurements':measurements})
    return questions,predictions,sources,run_id


def verify():
    cfg=load_config()
    qs,ps,sources,run=fixtures(cfg)
    checks={}
    errors={}

    def check(name,operation):
        try:
            checks[name]=bool(operation())
            if not checks[name]:errors[name]='Assertion was false'
        except Exception as exc:
            checks[name]=False
            errors[name]=type(exc).__name__+': '+str(exc)

    def reject(name,mutation):
        def operation():
            q,p,s=copy.deepcopy((qs,ps,sources))
            mutation(q,p,s)
            try:validate_predictions(q,p,cfg,s,'dev',run)
            except (ValueError,KeyError,TypeError):return True
            return False
        check(name,operation)

    check('valid_synthetic_predictions',lambda:validate_predictions(qs,ps,cfg,sources,'dev',run))
    summary=summarize(qs,ps,cfg,sources,'dev',run)
    quality=summary['quality']
    check('answerable_and_unanswerable_denominators',lambda:
          quality['questions']==4 and quality['answerable_denominator']==3
          and quality['unanswerable_excluded']==1)
    expected={'Recall@5':1/3,'Recall@10':2/3,'MRR@10':2/9,'all_gold_coverage@5':1/6}
    for metric,value in expected.items():
        check('hand_calculated_'+metric,lambda metric=metric,value=value:
              math.isclose(quality['metrics'][metric],value,rel_tol=0,abs_tol=1e-12))
    check('no_graded_label_ndcg_claim',lambda:quality['nDCG@10'] is None)
    check('latency_includes_all_questions_and_repetitions',lambda:
          summary['latency']['questions']==4 and summary['latency']['samples']==12)
    check('hand_calculated_latency_p50_ms',lambda:
          math.isclose(summary['latency']['stages']['total_seconds']['p50'],13,abs_tol=1e-12))
    check('hand_calculated_latency_p95_ms',lambda:
          math.isclose(summary['latency']['stages']['total_seconds']['p95'],22.9,abs_tol=1e-12))
    check('linear_percentile_arithmetic',lambda:percentile([0,10,20,30],.5)==15
          and math.isclose(percentile([0,10,20,30],.95),28.5,abs_tol=1e-12))
    check('nfkc_and_whitespace_normalization',lambda:
          normalize_query(' \u3000足球１２３\t规则 \n')=='足球123 规则')
    for name,value in (('blank',' \t\n'),('nontext',True),('oversized','球'*401)):
        def bad_normalization(value=value):
            try:normalize_query(value)
            except ValueError:return True
            return False
        check('reject_'+name+'_query',bad_normalization)
    for name,values,q in (('empty',[],.5),('negative_q',[1,2],-.1),
                          ('large_q',[1,2],1.1),('nan_sample',[1,float('nan')],.5),
                          ('inf_sample',[1,float('inf')],.5),('bool_q',[1,2],True)):
        def bad_percentile(values=values,q=q):
            try:percentile(values,q)
            except (ValueError,TypeError,OverflowError):return True
            return False
        check('reject_percentile_'+name,bad_percentile)

    reject('reject_cross_split_prediction',lambda q,p,s:p[0].update(split='test'))
    reject('reject_unknown_question_id',lambda q,p,s:p[0].update(question_id='Q_OTHER'))
    reject('reject_duplicate_predictions',lambda q,p,s:p.__setitem__(1,copy.deepcopy(p[0])))
    reject('reject_missing_prediction',lambda q,p,s:p.pop())
    reject('reject_duplicate_questions',lambda q,p,s:q.__setitem__(1,copy.deepcopy(q[0])))
    reject('reject_wrong_normalized_query',lambda q,p,s:p[0].update(query='unbound'))
    reject('reject_wrong_question_hash',lambda q,p,s:p[0].update(question_sha256='0'*64))
    reject('reject_wrong_run_identity',lambda q,p,s:p[0].update(run_id='b'*32))
    reject('reject_shallow_quality_results',lambda q,p,s:p[0]['results'].pop())
    reject('reject_boolean_rank',lambda q,p,s:p[0]['results'][0].update(rank=True))
    reject('reject_nonconsecutive_rank',lambda q,p,s:p[0]['results'][0].update(rank=2))
    reject('reject_boolean_chunk_id',lambda q,p,s:p[0]['results'][0].update(chunk_id=True))
    reject('reject_duplicate_chunk_id',lambda q,p,s:p[0]['results'].__setitem__(1,copy.deepcopy(p[0]['results'][0])))
    reject('reject_unknown_chunk_id',lambda q,p,s:p[0]['results'][0].update(chunk_id='S999'))
    reject('reject_string_gold_container',lambda q,p,s:q[0].update(expected_chunk_ids='S02'))
    reject('reject_set_gold_container',lambda q,p,s:q[0].update(expected_chunk_ids={'S02'}))
    reject('reject_duplicate_gold_ids',lambda q,p,s:q[0].update(expected_chunk_ids=['S02','S02']))
    reject('reject_unknown_gold_id',lambda q,p,s:q[0].update(expected_chunk_ids=['S999']))
    reject('reject_boolean_answerability',lambda q,p,s:q[0].update(answerable=1))
    reject('reject_answerability_gold_disagreement',lambda q,p,s:q[0].update(answerable=False))
    reject('reject_unanswerable_with_gold',lambda q,p,s:q[-1].update(expected_chunk_ids=['S01']))
    reject('reject_duplicate_source_ids',lambda q,p,s:s.__setitem__(1,copy.deepcopy(s[0])))
    reject('reject_shallow_source_map',lambda q,p,s:s.__delitem__(slice(9,None)))
    reject('reject_forged_source_url',lambda q,p,s:p[0]['results'][0].update(source_url='https://example.invalid/forged'))
    reject('reject_forged_source_hash',lambda q,p,s:p[0]['results'][0].update(record_sha256='0'*64))
    reject('reject_extra_result_body',lambda q,p,s:p[0]['results'][0].update(content_zh='synthetic body'))
    reject('reject_extra_prediction_body',lambda q,p,s:p[0].update(question='synthetic body'))
    reject('reject_extra_source_body',lambda q,p,s:s[0].update(content_zh='synthetic body'))
    for field in ('distance','score'):
        for label,value in (('nan',float('nan')),('inf',float('inf')),('bool',True)):
            reject('reject_'+label+'_'+field,
                   lambda q,p,s,field=field,value=value:p[0]['results'][0].update({field:value}))
    reject('reject_score_distance_disagreement',lambda q,p,s:p[0]['results'][0].update(score=.123))
    reject('reject_out_of_range_distance',lambda q,p,s:p[0]['results'][0].update(distance=-.1,score=1.1))
    reject('reject_unsorted_quality_ranking',lambda q,p,s:p[0]['results'][0].update(distance=.6,score=.4))
    reject('reject_missing_measurement',lambda q,p,s:p[0]['measurements'].pop())
    reject('reject_duplicate_repetition',lambda q,p,s:p[0]['measurements'][1].update(repetition=1))
    reject('reject_boolean_repetition',lambda q,p,s:p[0]['measurements'][0].update(repetition=True))
    reject('reject_shallow_repeated_ranking',lambda q,p,s:p[0]['measurements'][1]['ranked_ids'].pop())
    reject('reject_unknown_repeated_id',lambda q,p,s:p[0]['measurements'][1]['ranked_ids'].__setitem__(0,'S999'))
    reject('reject_duplicate_repeated_id',lambda q,p,s:p[0]['measurements'][1]['ranked_ids'].__setitem__(1,'S01'))
    reject('reject_nonfinite_repeated_score',lambda q,p,s:p[0]['measurements'][1]['scores'].__setitem__(0,float('nan')))
    reject('reject_repeated_score_distance_disagreement',lambda q,p,s:p[0]['measurements'][1]['scores'].__setitem__(0,.123))
    reject('reject_first_measurement_quality_mismatch',lambda q,p,s:p[0]['measurements'][0]['ranked_ids'].__setitem__(0,'S12'))
    for field in TIMINGS:
        for label,value in (('nan',float('nan')),('inf',float('inf')),('negative',-.1),('bool',True)):
            reject('reject_'+label+'_'+field,
                   lambda q,p,s,field=field,value=value:p[0]['measurements'][0].update({field:value}))
    reject('reject_missing_timing_stage',lambda q,p,s:p[0]['measurements'][0].pop('vector_search_seconds'))
    reject('reject_total_omits_stages',lambda q,p,s:p[0]['measurements'][0].update(total_seconds=.0001))
    reject('reject_missing_embedding_observation',lambda q,p,s:p[0]['measurements'][0].pop('embedding_observation'))
    reject('reject_missing_prompt_count',lambda q,p,s:p[0]['measurements'][0]['embedding_observation'].pop('prompt_eval_count'))
    for label,value in (('boolean',True),('zero',0),('negative',-1),('float',1.0)):
        reject('reject_'+label+'_prompt_count',lambda q,p,s,value=value:
               p[0]['measurements'][0]['embedding_observation'].update(prompt_eval_count=value))
    reject('reject_multiple_embedding_inputs',lambda q,p,s:p[0]['measurements'][0]['embedding_observation'].update(inputs=2))
    reject('reject_boolean_embedding_inputs',lambda q,p,s:p[0]['measurements'][0]['embedding_observation'].update(inputs=True))
    reject('reject_embedding_observation_full_text',lambda q,p,s:p[0]['measurements'][0]['embedding_observation'].update(content_zh='synthetic body'))
    reject('reject_negative_embedding_elapsed',lambda q,p,s:p[0]['measurements'][0]['embedding_observation'].update(elapsed_seconds=-1))
    reject('reject_nonfinite_embedding_elapsed',lambda q,p,s:p[0]['measurements'][0]['embedding_observation'].update(elapsed_seconds=float('nan')))
    for field in ('server_total_duration_ns','server_load_duration_ns'):
        reject('reject_boolean_'+field,lambda q,p,s,field=field:
               p[0]['measurements'][0]['embedding_observation'].update({field:True}))
        reject('reject_negative_'+field,lambda q,p,s,field=field:
               p[0]['measurements'][0]['embedding_observation'].update({field:-1}))

    def varying_repetitions_are_disclosed():
        q,p,s=copy.deepcopy((qs,ps,sources))
        m=p[0]['measurements'][1]
        m['ranked_ids']=['S12']+m['ranked_ids'][1:]
        result=summarize(q,p,cfg,s,'dev',run)
        return result['repeated_rankings_identical'] is False and result['quality']['metrics']==quality['metrics']
    check('later_ranking_variation_does_not_change_first_repetition_quality',varying_repetitions_are_disclosed)
    def test_report_scope():
        p=copy.deepcopy(ps)
        for row in p:row['split']='test'
        result=summarize(qs,p,cfg,sources,'test',run)
        return (result['purpose']=='final_report' and 'development_cases' not in result['error_analysis']
                and result['quality']['metrics']==quality['metrics'])
    check('synthetic_test_scope_is_final_report_without_development_cases',test_report_scope)
    for name,split,identity in (('unknown_split','training',run),('short_run','dev','a'),
                                ('nonhex_run','dev','z'*32)):
        def invalid_identity(split=split,identity=identity):
            try:validate_predictions(qs,ps,cfg,sources,split,identity)
            except ValueError:return True
            return False
        check('reject_'+name,invalid_identity)
    with tempfile.TemporaryDirectory(prefix='task7-contract-config-',dir=ROOT/'.tmp') as folder:
        path=Path(folder)/'config.json'
        for name,field,value in (('depth','top_k',5),('bool_depth','top_k',True),
                                 ('repetitions','measured_repetitions',1),('cache','cache',True),
                                 ('selection','used_for_parameter_selection',True)):
            bad=copy.deepcopy(cfg);bad[field]=value
            path.write_text(json.dumps(bad),encoding='utf-8')
            def bad_config():
                try:load_config(path)
                except ValueError:return True
                return False
            check('reject_changed_config_'+name,bad_config)
    return {'status':'PASS' if all(checks.values()) else 'FAIL',
        'check_count':len(checks),'passed_checks':sum(checks.values()),'checks':checks,
        'failed_checks':[name for name,value in checks.items() if not value],'errors':errors,
        'source_sha256':{name:digest((ROOT/'scripts'/name).read_bytes()) for name in
                         ('dense_retrieval_eval.py','verify_dense_retrieval_contract.py')},
        'checked_at':datetime.now(timezone.utc).isoformat(),
        'fixture_scope':'Invented Q_A/Q_B/Q_C/Q_U and S01-S12 only; no actual benchmark result',
        'real_evaluation_question_files_read':False,'model_requests':0,
        'production_index_opened':False,'dataset_or_index_modified':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',required=True)
    args=parser.parse_args()
    report=(ROOT/args.report).resolve()
    if (report.suffix!='.json' or not any(report.is_relative_to(ROOT/base) and report!=ROOT/base
        for base in ('reports','.tmp'))):raise ValueError('Use a new JSON report under reports/ or .tmp/')
    if report.exists():raise ValueError('Refusing to overwrite an existing contract report')
    (ROOT/'.tmp').mkdir(exist_ok=True)
    result=verify()
    report.parent.mkdir(parents=True,exist_ok=True)
    with report.open('x',encoding='utf-8',newline='\n') as output:
        json.dump(result,output,ensure_ascii=False,indent=2);output.write('\n')
    print(json.dumps({'status':result['status'],'check_count':result['check_count'],
        'passed_checks':result['passed_checks'],'failed_checks':result['failed_checks'],
        'report':report.relative_to(ROOT).as_posix()}))
    raise SystemExit(0 if result['status']=='PASS' else 1)


if __name__=='__main__':main()
