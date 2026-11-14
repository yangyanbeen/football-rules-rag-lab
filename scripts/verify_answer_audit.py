"""Synthetic adversarial regressions and read-only replay; never submit human judgments."""
from __future__ import annotations
import argparse,copy,uuid
from pathlib import Path
from answer_audit_v2 import *
import answer_review_v2 as review


def verify(private=False):
    checks={};errors=[]
    def check(name,fn):
        try:
            checks[name]=fn() is True
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as e:checks[name]=False;errors.append({'check':name,'error':type(e).__name__+': '+str(e)})
    def rejected(fn):
        try:fn()
        except (ValueError,KeyError,TypeError,OSError,IndexError):return True
        return False
    for s in ('dev','test'):
        check(s+'_strict_original_run',lambda s=s:strict_run(s,private)['samples']==config()['formal_samples'][s])
    start=read(DIRECTORY/'test/run_started.json');completed=read(DIRECTORY/'test/completed.json')
    summary=replay('test');analysis=read(DIRECTORY/'test/error_analysis.json')
    for name,mutate in {
        'missing_all_artifacts':lambda d,a:d.update(artifacts={}),
        'missing_one_artifact':lambda d,a:d['artifacts'].pop('environment.json'),
        'unknown_artifact':lambda d,a:d['artifacts'].update(extra={}),
        'wrong_completed_split':lambda d,a:d.update(split='dev'),
        'wrong_completed_source':lambda d,a:d.update(source_commit='0'*40),
        'wrong_artifact_path':lambda d,a:d['artifacts']['summary.json'].update(path='other.json'),
        'empty_error_analysis':lambda d,a:a.update(cases=[]),
        'changed_error_vector':lambda d,a:a['cases'][0].update(false_refusal=False),
        'wrong_analysis_split':lambda d,a:a.update(split='dev'),
        'human_impersonation_in_analysis':lambda d,a:a.update(judgment_kind='human')}.items():
        def test(mutate=mutate):
            d,a=copy.deepcopy(completed),copy.deepcopy(analysis);mutate(d,a)
            return rejected(lambda:validate_completion('test',start,d,summary,a))
        check('reject_'+name,test)
    context=review.review_context();qid=context['ids'][0];q=context['labels'][qid];p=context['predictions'][qid]
    # These fixtures never enter the real ledger or an exported human receipt.
    fixture={'version':'answer-human-review-1.1','question_id':qid,'answer_sha256':p['answer_sha256'],
        'private_trace':p['trace'],'reviewer_type':'human','reviewer':'SYNTHETIC TEST ONLY',
        'reviewed_at':now(),'point_decisions':['no']*len(q['expected_answer_points']),
        'condition_decisions':['no']*len(q['required_conditions']),'citation_decisions':['no']*len(p['citations']),
        'refusal_appropriate':'no','reason':'SYNTHETIC ONLY; not a real judgment',
        'submission_channel':'explicit local browser form','context_sha256':context['identity']}
    check('synthetic_explicit_negative_decisions_valid',lambda:review.validate_review(fixture,context)==fixture)
    mutations={
        'missing_point':lambda r:r['point_decisions'].pop(),
        'extra_condition':lambda r:r['condition_decisions'].append('yes'),
        'boolean_as_verdict':lambda r:r['point_decisions'].__setitem__(0,True),
        'unknown_verdict':lambda r:r.update(refusal_appropriate='approved'),
        'missing_reviewer':lambda r:r.update(reviewer=' '),
        'missing_reason':lambda r:r.update(reason=''),
        'oversize_reason':lambda r:r.update(reason='x'*2001),
        'wrong_answer':lambda r:r.update(answer_sha256='0'*64),
        'wrong_trace':lambda r:r['private_trace'].update(sha256='0'*64),
        'changed_context':lambda r:r.update(context_sha256='0'*64),
        'unselected_id':lambda r:r.update(question_id='T999'),
        'AI_as_human':lambda r:r.update(reviewer_type='AI'),
        'bulk_approval_channel':lambda r:r.update(submission_channel='bulk owner approval'),
        'invalid_date':lambda r:r.update(reviewed_at='bad'),
        'naive_date':lambda r:r.update(reviewed_at='2026-11-14T08:25:00'),
        'future_date':lambda r:r.update(reviewed_at='2999-01-01T00:00:00+00:00'),
        'pre_answer_date':lambda r:r.update(reviewed_at='2020-01-01T00:00:00+00:00'),
        'unexpected_approval_field':lambda r:r.update(approved=True)}
    if p['status']=='refused':mutations['covered_claim_in_refusal']=lambda r:r['point_decisions'].__setitem__(0,'yes')
    for name,mutate in mutations.items():
        def test(mutate=mutate):
            r=copy.deepcopy(fixture);mutate(r)
            return rejected(lambda:review.validate_review(r,context))
        check('reject_review_'+name,test)
    def revise():
        r=copy.deepcopy(fixture);r['reason']='synthetic revision'
        result=review.aggregate(context,[fixture,r])
        return result['reviewed_samples']==1 and result['ledger_entries']==2 and result['status']=='PENDING'
    check('review_revisions_append_not_inflate_samples',revise)
    check('empty_ledger_stays_pending',lambda:review.aggregate(context,[])['status']=='PENDING')
    def all_negative():
        records=[]
        for id_ in context['ids']:
            q_=context['labels'][id_];p_=context['predictions'][id_];r=copy.deepcopy(fixture)
            r.update(question_id=id_,answer_sha256=p_['answer_sha256'],private_trace=p_['trace'],
                point_decisions=['no']*len(q_['expected_answer_points']),condition_decisions=['no']*len(q_['required_conditions']),
                citation_decisions=['no']*len(p_['citations']))
            records.append(r)
        result=review.aggregate(context,records)
        if result['status']!='REVIEW_COMPLETE' or any(m['numerator']!=0 for m in result['metrics'].values()):return False
        records[-1]['refusal_appropriate']='uncertain'
        return review.aggregate(context,records)['status']=='PENDING'
    check('synthetic_all_negative_is_completed_review_not_correct_answers',all_negative)
    def ledger_tests():
        def run():
            temp=ROOT/'.tmp'/('task12-synthetic-'+uuid.uuid4().hex)
            temp.mkdir(parents=True)
            path=temp/'synthetic.jsonl';review.save_review(fixture,context,path)
            before=path.read_bytes();review.save_review(fixture,context,path)
            if not path.read_bytes().startswith(before) or len(review.read_reviews(context,path))!=2:return False
            with review.ledger_lock(path):
                if not rejected(lambda:review.save_review(fixture,context,path)):return False
            path.write_bytes(b'{}\n')
            if not rejected(lambda:review.save_review(fixture,context,path)) or path.read_bytes()!=b'{}\n':return False
            path.write_bytes(canonical(fixture))
            return rejected(lambda:review.read_reviews(context,path))
        return run()
    check('synthetic_ledger_durable_append_lock_corruption_and_truncation',ledger_tests)
    if private:
        corpus=review.source_corpus();index=next(i for i,p in enumerate(rows(DIRECTORY/'test/predictions.jsonl')) if p['status']=='answered')
        q=questions('test')[index];p=rows(DIRECTORY/'test/predictions.jsonl')[index];g=rows(DIRECTORY/'test/judgments.jsonl')[index]
        actual=read(ROOT/p['trace']['path']);judge=read(ROOT/g['trace']['path'])
        mutations={
            'judge_prompt':lambda a,j,p:j['messages'][0].update(content='changed'),
            'judge_question':lambda a,j,p:j.update(question_id='T999'),
            'judge_attempt_schema':lambda a,j,p:j['attempts'][0].update(format={}),
            'judge_attempt_messages':lambda a,j,p:j['attempts'][0].update(messages=[]),
            'judge_counters':lambda a,j,p:j['attempts'][0].update(eval_count=0),
            'selection_prompt':lambda a,j,p:a['messages'][0].update(content='changed'),
            'selection_schema':lambda a,j,p:a['attempts'][0].update(format={}),
            'selection_counters':lambda a,j,p:a['attempts'][0].update(eval_count=0),
            'record_hash':lambda a,j,p:p['citations'][0].update(record_sha256='0'*64),
            'missing_clock':lambda a,j,p:p['timing'].pop('generation_seconds'),
            'impossible_clock':lambda a,j,p:p['timing'].update(total_seconds=0)}
        for name,mutate in mutations.items():
            def test(mutate=mutate):
                a,j,p_=copy.deepcopy(actual),copy.deepcopy(judge),copy.deepcopy(p);mutate(a,j,p_)
                return rejected(lambda:validate_trace(q,p_,g,a,j,corpus))
            check('reject_private_'+name,test)
    return {'version':'answer-audit-regression-1.1','captured_at':now(),
        'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),
        'checks':checks,'errors':errors,'new_model_requests':0,'private_trace_checks':private,
        'source_sha256':{n:record(ROOT/n)['sha256'] for n in ('scripts/answer_audit_v2.py','scripts/answer_review_v2.py','scripts/verify_answer_audit.py')},
        'scope':'Synthetic fixtures are temporary only; no human judgments created. Formal90 replay only.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--private',action='store_true');p.add_argument('--report',required=True);a=p.parse_args()
    result=verify(a.private);write_new(ROOT/a.report,result)
    print(json.dumps({k:result[k] for k in ('status','passed','total','errors')},ensure_ascii=False));raise SystemExit(result['status']!='PASS')
