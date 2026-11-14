"""Task12 deterministic boundary regressions; no model calls or invented quality samples."""
import argparse,copy,json
from answer_eval_core import *
from answer_eval_engine import pack


def verify(path,saved=False):
    checks={};errors=[]
    def check(name,fn):
        try:
            checks[name]=bool(fn())
            if not checks[name]:errors.append({'check':name,'error':'False predicate'})
        except Exception as exc:checks[name]=False;errors.append({'check':name,'error':type(exc).__name__+': '+str(exc)})
    def rejects(fn):
        try:fn();return False
        except (ValueError,TypeError,KeyError):return True
    cfg=config();offered=['L01-01','L01-02'];good={'answerable':True,'chunk_ids':['L01-01'],'reason':None}
    check('fixed_model_cpu_context_and_budget',lambda:cfg['llm']['num_gpu']==0 and cfg['llm']['num_thread']==8 and cfg['llm']['temperature']==0 and cfg['llm']['num_ctx']>=6200+512+1024)
    check('valid_selection_preserved',lambda:parse_selection(json.dumps(good),offered,cfg)==good)
    bad=[[],{},dict(good,extra=1),dict(good,answerable='true'),dict(good,chunk_ids='L01-01'),dict(good,chunk_ids=[1]),dict(good,chunk_ids=['L01-01']*2),dict(good,chunk_ids=[]),dict(good,chunk_ids=['L99-99']),dict(good,chunk_ids=['L01-01','L01-02','L01-03','L01-04']),dict(good,reason='why'),{'answerable':False,'chunk_ids':['L01-01'],'reason':'insufficient_evidence'},{'answerable':False,'chunk_ids':[],'reason':'anything'}]
    for i,v in enumerate(bad,1):check('malformed_selection_'+str(i)+'_rejected',lambda v=v:rejects(lambda:parse_selection(json.dumps(v),offered,cfg)))
    for reason in ('insufficient_evidence','source_conflict','version_unverified'):
        v={'answerable':False,'chunk_ids':[],'reason':reason};check('controlled_refusal_'+reason,lambda v=v:parse_selection(json.dumps(v),offered,cfg)==v)
    q={'expected_answer_points':['宽7.32米'],'required_conditions':['成人比赛']};p={'status':'answered','citations':[{'chunk_id':'L01-01'}]}
    grade={'points':[True],'conditions':[False],'citations':[True],'reason':'Synthetic test only'}
    check('valid_grade_vectors_preserved',lambda:parse_grade(json.dumps(grade),q,p)==grade)
    badgrades=[dict(grade,points=[]),dict(grade,points=[1]),dict(grade,conditions='true'),dict(grade,citations=[True,False]),dict(grade,reason=''),dict(grade,extra=True)]
    for i,v in enumerate(badgrades,1):check('bad_judge_'+str(i)+'_rejected',lambda v=v:rejects(lambda:parse_grade(json.dumps(v),q,p)))
    check('refusal_cannot_claim_covered_points',lambda:rejects(lambda:parse_grade(json.dumps(dict(grade,citations=[])),q,{'status':'refused','citations':[]})))
    check('null_denominator_is_not_fabricated_zero_or_one',lambda:ratio(0,0)=={'numerator':0,'denominator':0,'value':None})
    check('denominator_exact',lambda:ratio(2,3)['value']==2/3)
    check('normalization_preserves_negation_units_numbers',lambda:normalized(' 不得 ７.３２ 米 ')==normalized('不得7.32米') and normalized('可')!=normalized('不可'))
    stub={'chunk_id':'L01-01','law_number':1,'content_zh':'x'*100,'source_revision_verified':False,'needs_rule_review':False,'review_notes':[]}
    check('whole_evidence_kept',lambda:pack('尺寸',[stub],cfg,'规则')[0]==[stub])
    huge={**stub,'content_zh':'中'*5000}
    check('oversize_evidence_skipped_without_truncation',lambda:pack('尺寸',[huge],cfg,'规则')[0]==[])
    check('long_question_rejected_without_truncation',lambda:rejects(lambda:pack('中'*4000,[],cfg,'规则')))
    check('full_messages_within_budget',lambda:pack('尺寸',[stub]*10,cfg,'规则')[2]<=6200 and len(pack('尺寸',[stub]*10,cfg,'规则')[0])==5)
    check('version_boundary_explicit',lambda:all(w in BOUNDARY for w in ('Wikipedia','非官方','未经过裁判专家审校','未独立核验')))
    check('all_declared_frozen_inputs_exist',lambda:all((ROOT/p).is_file() for p in INPUTS))
    if saved:
        for s in ('dev','test'):
            if (DIRECTORY/s/'summary.json').exists():check(s+'_saved_metrics_and_all_vectors_replay',lambda s=s:replay(s)['samples']==cfg['formal_samples'][s])
    result={'version':'answer-contract-1.0','captured_at':now(),'status':'PASS' if all(checks.values()) else 'FAIL',
      'passed':sum(checks.values()),'total':len(checks),'checks':checks,'errors':errors,'new_model_requests':0,
      'source_sha256':{p:record(ROOT/p)['sha256'] for p in NATIVE[:2]+('scripts/verify_answer_evaluation.py',)},
      'scope':'Synthetic boundary tests and optional saved replay; not answer accuracy samples'}
    write_new(path,result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True);p.add_argument('--saved',action='store_true');a=p.parse_args();r=verify(ROOT/a.report,a.saved);print(json.dumps(r,ensure_ascii=False));raise SystemExit(r['status']!='PASS')
