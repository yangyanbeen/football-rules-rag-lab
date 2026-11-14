"""Independent five-metric arithmetic, without importing the production scorer."""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text('utf-8'))
def lines(p):return [json.loads(s) for s in (ROOT/p).read_text('utf-8').splitlines() if s.strip()]


def calculate(qs,ps,gs):
    def rate(a,b):return {'numerator':a,'denominator':b,'value':a/b if b else None}
    result={}
    for metric,key in [('answer_point_coverage','points'),('citation_correctness','citations'),('condition_exception_retention','conditions')]:
        vectors=[g['grade'][key] for g in gs]
        if any(type(v) is not bool for a in vectors for v in a):raise ValueError('Non-boolean grade')
        result[metric]=rate(sum(sum(a) for a in vectors),sum(len(a) for a in vectors))
    result['correct_refusal_rate']=rate(sum(not q['answerable'] and p['status']=='refused' and p['error'] is None for q,p in zip(qs,ps)),sum(not q['answerable'] for q in qs))
    result['false_refusal_rate']=rate(sum(q['answerable'] and p['status']=='refused' for q,p in zip(qs,ps)),sum(q['answerable'] for q in qs))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True);a=p.parse_args();checks={}
    qs=[{'answerable':True},{'answerable':True},{'answerable':False},{'answerable':False}]
    ps=[{'status':'answered','error':None},{'status':'refused','error':'failure'},{'status':'refused','error':None},{'status':'refused','error':'failure'}]
    gs=[{'grade':{'points':[True,False],'conditions':[True],'citations':[True,False]}},{'grade':{'points':[False],'conditions':[False],'citations':[]}},{'grade':{'points':[],'conditions':[],'citations':[]}},{'grade':{'points':[],'conditions':[],'citations':[]}}]
    actual=calculate(qs,ps,gs)
    expected={'answer_point_coverage':(1,3),'citation_correctness':(1,2),'condition_exception_retention':(1,2),'correct_refusal_rate':(1,2),'false_refusal_rate':(1,2)}
    for key,(n,d) in expected.items():checks['synthetic_'+key]=actual[key]=={'numerator':n,'denominator':d,'value':n/d}
    empty=calculate([],[],[]);checks['empty_denominators_are_null']=all(v=={'numerator':0,'denominator':0,'value':None} for v in empty.values())
    checks['runtime_failure_not_rewarded_as_correct_refusal']=actual['correct_refusal_rate']['numerator']==1
    bound={}
    for split in ('dev','test'):
        folder='reports/answer_evaluation/'+split+'/'
        qs=[q for q in lines('data/eval/answer_eval.jsonl') if q['split']==split]
        ps=lines(folder+'predictions.jsonl');gs=lines(folder+'judgments.jsonl');summary=read(folder+'summary.json')
        checks[split+'_sample_order_binding']=len(qs)==len(ps)==len(gs) and [q['question_id'] for q in qs]==[r['question_id'] for r in ps]==[r['question_id'] for r in gs]
        result=calculate(qs,ps,gs)
        for k,v in result.items():checks[split+'_'+k+'_independent_recompute']=v==summary['metrics'][k]
        bound[split]={name:hashlib.sha256((ROOT/folder/name).read_bytes()).hexdigest() for name in ('predictions.jsonl','judgments.jsonl','summary.json')}
    value={'version':'answer-independent-arithmetic-1.0','captured_at':datetime.now(timezone.utc).isoformat(),'status':'PASS' if all(checks.values()) else 'FAIL','passed':sum(checks.values()),'total':len(checks),'checks':checks,'bound_artifacts':bound,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'new_model_requests':0,'scope':'Independent arithmetic only, not semantic adjudication or human review'}
    output=(ROOT/a.report).resolve()
    if not output.is_relative_to(ROOT/'reports') or output.suffix!='.json':raise ValueError('Use a new reports JSON path')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:value[k] for k in ('status','passed','total')}));return value['status']!='PASS'


if __name__=='__main__':raise SystemExit(main())
