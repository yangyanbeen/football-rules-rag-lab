"""Actual revised backend demonstrations and browser-to-private-trace binding."""
import argparse,time
from task13_audit import *
from task13_audit_client import call_worker
from run_task13_demo import case_passes

FOLDER=ROOT/'reports/rechecks/task13-audit-20261114'


def backend():
    rows=[];started=now()
    for case in read(ROOT/'config/task13_demo.json')['cases']:
        result,trace,wall=call_worker(case['question']);passed=case_passes(case,result)
        rows.append({'id':case['id'],'passed':passed,'worker_wall_seconds':wall,'result':public_projection(result,ROOT/trace['path'])})
        print(json.dumps({'id':case['id'],'passed':passed,'status':result['status'],'selected':result['selected_ids']},ensure_ascii=False),flush=True)
    return {'version':'task13-audit-demo-1.0','status':'PASS' if all(r['passed'] for r in rows) else 'FAIL','passed':sum(r['passed'] for r in rows),'total':len(rows),'rows':rows,'started_at':started,'completed_at':now(),'new_formal_test_runs':0,'new_human_judgments':0,'scope':'Actual ad hoc integration examples with unchanged five questions/policies; not formal accuracy measurement.'}


def browser():
    journal=ROOT/'.runtime/task13-audit/ui-events.jsonl';events=[json.loads(s) for s in journal.read_text('utf-8').splitlines() if s.strip()];rows=[]
    for case in read(ROOT/'config/task13_demo.json')['cases']:
        matches=[e for e in events if e['question_sha256']==digest(case['question'].encode()) and e['source']=='kotaemon_integrated_audit_ui']
        if len(matches)!=1:raise ValueError('Expected one actual UI event per demonstration')
        event=matches[0];p=ROOT/event['private_trace']['path'];actual=read(p);validate_private(actual,case['question'],True)
        if record(p)!=event['private_trace'] or actual['implementation']!=event['implementation']:raise ValueError('UI event trace differs')
        snapshot=ROOT/'.runtime/task13-audit'/('ui-'+case['id']+'.txt');text=snapshot.read_text('utf-8');answers=re.findall(r'button "bot\x27s message: (.*)"',text)
        flatten=lambda s:re.sub(r'\s+',' ',s).strip()
        matched=bool(answers) and flatten(answers[-1])==flatten(actual['answer']);linked=all(c['source_url'] in text and c['license_url'] in text for c in actual['citations'])
        passed=case_passes(case,actual) and matched and linked and 'http://127.0.0.1:7867/' in text
        rows.append({'id':case['id'],'passed':passed,'browser_answer_matches_trace':matched,'source_and_license_links':linked,'snapshot':record(snapshot),'event_sha256':digest(canonical(event)),'worker_wall_seconds':event['worker_wall_seconds'],'result':public_projection(actual,p)})
    return {'version':'task13-audit-ui-1.0','captured_at':now(),'url':'http://127.0.0.1:7867/','status':'PASS' if all(r['passed'] for r in rows) else 'FAIL','passed':sum(r['passed'] for r in rows),'total':len(rows),'rows':rows,'ui_journal':record(journal),'new_formal_test_runs':0,'new_human_judgments':0,'scope':'Actual browser input/click and saved DOM linked to exact private model traces; no synthetic human judgments.'}


def replay(value,ui=False,private=False):
    cases=read(ROOT/'config/task13_demo.json')['cases']
    if value['status']!='PASS' or not value['passed']==value['total']==len(value['rows'])==5 or [r['id'] for r in value['rows']]!=[c['id'] for c in cases]:raise ValueError('Incomplete demo receipt')
    if value['new_formal_test_runs']!=0 or value['new_human_judgments']!=0:raise ValueError('Unexpected formal run/review')
    if len({r['result']['trace_id'] for r in value['rows']})!=5:raise ValueError('Duplicate demonstration trace')
    for case,row in zip(cases,value['rows']):
        v=row['result'];validate_public(v,True)
        if v['question']!=case['question'] or v['status']!=case['expected_status'] or (case['required_source'] and case['required_source'] not in v['selected_ids']):raise ValueError('Demonstration case differs')
        if type(row['worker_wall_seconds']) not in (int,float) or not math.isfinite(row['worker_wall_seconds']) or row['worker_wall_seconds']<v['timing']['total_seconds']:raise ValueError('Worker clock differs')
        if row['passed'] is not True:raise ValueError('Failed demo')
        if ui and (row['browser_answer_matches_trace'] is not True or row['source_and_license_links'] is not True):raise ValueError('Incomplete actual UI proof')
        if private:
            p=ROOT/v['private_trace']['path'];a=read(p)
            if record(p)!=v['private_trace'] or public_projection(a,p)!=v or not case_passes(case,a):raise ValueError('Private demonstration differs')
    if private and ui:
        current=browser();current.pop('captured_at');saved=copy.deepcopy(value);saved.pop('captured_at')
        if current!=saved:raise ValueError('Actual browser capture differs')
    return True


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('backend','browser'));p.add_argument('--report',required=True);a=p.parse_args();v=backend() if a.action=='backend' else browser();write_new(ROOT/a.report,v);print(json.dumps({k:v[k] for k in ('status','passed','total')}));raise SystemExit(v['status']!='PASS')
