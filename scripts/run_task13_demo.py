"""Actual task13 integration regressions with complete private traces and public receipts."""
import argparse,sys,time
from task13_core import *
from task13_worker_client import call_worker


def case_passes(definition,result):
    validate_result(result,definition['question'])
    return (result['status']==definition['expected_status'] and result['error'] is None and
        (definition['required_source'] is None or definition['required_source'] in result['selected_ids']) and
        all(s in result['answer'] for s in definition['required_literals']) and
        (bool(result['citations']) if result['status']=='answered' else not result['citations']))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True);a=p.parse_args()
    target=(ROOT/a.report).resolve()
    if target.exists():raise ValueError('Use a new demo report')
    definitions=read(ROOT/'config/task13_demo.json');rows=[];started=now()
    for case in definitions['cases']:
        result,trace,wall=call_worker(case['question']);passed=case_passes(case,result)
        row={'id':case['id'],'expected_status':case['expected_status'],'passed':passed,'worker_wall_seconds':wall,
            'result':public_result(result,ROOT/trace['path'])}
        rows.append(row);print(json.dumps({'case':case['id'],'status':result['status'],'selected':result['selected_ids'],'passed':passed,'error':result['error']},ensure_ascii=False),flush=True)
    value={'version':'task13-demo-1.0','started_at':started,'completed_at':now(),'status':'PASS' if all(r['passed'] for r in rows) else 'FAIL',
        'passed':sum(r['passed'] for r in rows),'total':len(rows),'rows':rows,'configuration':source_identity(),
        'demo_definitions':record(ROOT/'config/task13_demo.json'),'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'new_formal_test_runs':0,'formal_eval_labels_used_for_generation':False,
        'answer_model_attempts':sum(len(r['result']['attempts']) for r in rows),
        'scope':'Five actual ad hoc integration examples; not formal answer accuracy, QPS or a new benchmark. Literal checks only validate displayed evidence presence.'}
    write_new(target,value);print(json.dumps({'status':value['status'],'passed':value['passed'],'total':value['total']}));return value['status']!='PASS'


if __name__=='__main__':raise SystemExit(main())
