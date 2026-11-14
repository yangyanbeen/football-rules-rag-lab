"""Synthetic acceptance regressions plus optional private display checks; no new reviews."""
import argparse,copy
from answer_acceptance import *
from citation_catalog_guard import safe_render,make_preview


def verify(private=False):
    checks={};errors=[]
    def check(name,fn):
        try:
            checks[name]=fn() is True
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as e:checks[name]=False;errors.append({'check':name,'error':type(e).__name__+': '+str(e)})
    def reject(fn):
        try:fn()
        except (ValueError,KeyError,TypeError,OSError):return True
        return False
    value=read(ROOT/HUMAN);analysis=analyze(value)
    check('actual_twelve_reviews_and_thirteen_append_entries',lambda:value['reviewed_samples']==12 and value['ledger_entries']==13 and not value['missing_ids'] and not value['unresolved_ids'])
    check('human_analysis_recomputes',lambda:canonical(analysis)==canonical(read(ROOT/ANALYSIS)))
    check('independent_human_point_and_condition21_of27',lambda:analysis['human_semantic_metrics']['answer_point_coverage']=={'numerator':21,'denominator':27,'value':21/27,'uncertain':0} and analysis['human_semantic_metrics']['condition_exception_retention']=={'numerator':21,'denominator':27,'value':21/27,'uncertain':0})
    check('independent_human_citations9_of20',lambda:analysis['human_semantic_metrics']['citation_correctness']=={'numerator':9,'denominator':20,'value':.45,'uncertain':0})
    check('zero_unanswerable_refusal_rate_is_null',lambda:analysis['label_based_refusal_metrics']['correct_refusal_rate']=={'numerator':0,'denominator':0,'value':None})
    check('false_refusal_sample_rate2_of12',lambda:analysis['label_based_refusal_metrics']['false_refusal_rate']=={'numerator':2,'denominator':12,'value':2/12})
    check('answerability_choice_is_not_answer_correctness',lambda:analysis['human_answerability_choice_appropriate']==ratio(10,12) and any(r['question_id']=='T014' and r['human_answerability_choice_appropriate'] and r['missing_points'] for r in analysis['error_cases']))
    check('AI_guidance_and_biased_sample_disclosed',lambda:'AI supplied' in analysis['review_assistance'] and 'error-prioritized' in analysis['interpretation'])
    cases={
        'human_pending':lambda v:v.update(status='PENDING'),
        'missing_review':lambda v:v['per_question'].pop(),
        'duplicate_review':lambda v:v['per_question'].append(copy.deepcopy(v['per_question'][0])),
        'unknown_review':lambda v:v['per_question'][0].update(question_id='T999'),
        'uncertain_judgment':lambda v:v['per_question'][0]['point_decisions'].__setitem__(0,'uncertain'),
        'wrong_answer_hash':lambda v:v['per_question'][0].update(answer_sha256='0'*64),
        'inflated_points':lambda v:v['metrics']['answer_point_coverage'].update(numerator=27,value=1),
        'boolean_uncertain':lambda v:v['metrics']['answer_point_coverage'].update(uncertain=False),
        'private_name_in_receipt':lambda v:v['private_ledger'].update(reviewer='PRIVATE TEST NAME'),
        'private_note_in_row':lambda v:v['per_question'][0].update(reason='PRIVATE TEST NOTE'),
        'lost_ledger_receipt':lambda v:v.update(private_ledger=None),
        'invented_ledger_count':lambda v:v.update(ledger_entries=1)}
    for name,mutate in cases.items():
        def run(mutate=mutate):
            changed=copy.deepcopy(value);mutate(changed)
            return reject(lambda:strict_human(changed))
        check('reject_'+name,run)
    check('catalog_notes_have_no_invented_official_numbers',lambda:len(load_policy())==2 and all(r['official_law_number'] is None for r in load_policy().values()))
    if private:
        corpus=review.source_corpus()
        for cid in ('L03-02','L03-04'):
            def run(cid=cid):
                original=canonical(corpus[cid]);answer,cs=safe_render([cid],corpus)
                return '本地编目第3组' in answer and '· 第3条 ·' not in answer and corpus[cid]['content_zh'] in answer and cs[0]['official_law_number'] is None and 'law_number' not in cs[0] and cs[0]['source_catalog_metadata']=={'law_number':3} and cs[0]['record_sha256']==corpus[cid]['record_sha256'] and canonical(corpus[cid])==original and '署名与许可' in answer and answer.endswith(BOUNDARY)
            check(cid+'_actual_whole_body_preserved_and_ambiguous_label_suppressed',run)
        check('unknown_source_rejected',lambda:reject(lambda:safe_render(['L99-99'],corpus)))
        check('duplicate_selection_rejected',lambda:reject(lambda:safe_render(['L03-04','L03-04'],corpus)))
        def changed_version():
            c=copy.deepcopy(corpus);c['L03-04']['record_sha256']='0'*64
            return reject(lambda:safe_render(['L03-04'],c))
        check('stale_catalog_note_rejected_for_other_corpus_version',changed_version)
        check('empty_selection_stays_refused',lambda:safe_render([],corpus)==(REFUSAL+'\n'+BOUNDARY,[]))
        def preview():
            v=make_preview('T006')
            original=review.review_context()['predictions']['T006']
            return v['source_answer_sha256']==original['answer_sha256'] and v['answer_sha256']!=original['answer_sha256'] and v['new_model_requests']==0
        check('derived_preview_bound_to_original_without_regrading',preview)
    return {'version':'answer-acceptance-cases-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL',
        'passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'private':private,'new_model_requests':0,'new_human_judgments':0,
        'source_sha256':{n:record(ROOT/n)['sha256'] for n in ('scripts/answer_acceptance.py','scripts/citation_catalog_guard.py','scripts/verify_answer_acceptance_cases.py')},
        'scope':'Actual stored human judgments plus isolated in-memory corruptions. No form submitted or formal model request repeated.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--private',action='store_true');p.add_argument('--report',required=True);a=p.parse_args()
    v=verify(a.private);write_new(ROOT/a.report,v);print(json.dumps({k:v[k] for k in ('status','passed','total','errors')},ensure_ascii=False));raise SystemExit(v['status']!='PASS')
