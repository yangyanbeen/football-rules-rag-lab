"""Bind actual browser DOM snapshots to the isolated UI worker journal."""
import argparse,re
from task13_core import *
from run_task13_demo import case_passes


def capture():
    journal=ROOT/'.runtime/task13/ui-events.jsonl'
    events=[json.loads(line) for line in journal.read_text('utf-8').splitlines() if line.strip()]
    definitions=read(ROOT/'config/task13_demo.json')['cases'];rows=[]
    flatten=lambda s:re.sub(r'\s+',' ',s).strip()
    for case in definitions:
        candidates=[e for e in events if e['question_sha256']==digest(case['question'].encode()) and e['source']=='kotaemon_integrated_ui']
        if len(candidates)!=1:raise ValueError('Expected one actual UI event for '+case['id'])
        event=candidates[0];path=ROOT/event['private_trace']['path']
        if record(path)!=event['private_trace']:raise ValueError('UI trace identity differs')
        actual=read(path);validate_result(actual,case['question'])
        snapshot=ROOT/'.runtime/task13'/('ui-'+case['id']+'.txt');text=snapshot.read_text('utf-8')
        answers=re.findall(r'button "bot\x27s message: (.*)"',text)
        rendered=bool(answers) and flatten(answers[-1])==flatten(actual['answer'])
        linked=all(c['source_url'] in text and c['license_url'] in text for c in actual['citations'])
        passed=case_passes(case,actual) and rendered and linked and 'http://127.0.0.1:7866/' in text and '请输入足球规则问题' in text
        rows.append({'id':case['id'],'passed':passed,'browser_answer_matches_actual_trace':rendered,'source_and_license_links_visible':linked,
            'browser_snapshot':record(snapshot),'ui_event_sha256':digest(canonical(event)),
            'worker_wall_seconds':event['worker_wall_seconds'],'result':public_result(actual,path)})
    return {'version':'task13-ui-demo-1.0','captured_at':now(),'url':'http://127.0.0.1:7866/','status':'PASS' if all(r['passed'] for r in rows) else 'FAIL',
        'passed':sum(r['passed'] for r in rows),'total':len(rows),'rows':rows,'ui_journal':record(journal),
        'actual_browser_submissions':len(rows),'new_formal_test_runs':0,'raw_browser_snapshots_public':False,
        'source_sha256':{n:record(ROOT/n)['sha256'] for n in ('scripts/run_integrated_rag.py','scripts/task13_pipeline.py','scripts/task13_worker_client.py','scripts/capture_task13_ui.py')},
        'scope':'Actual browser input/click actions, displayed answers and source links bound to saved worker traces; not human semantic judgments or quality measurements.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True);a=p.parse_args()
    v=capture();write_new(ROOT/a.report,v);print(json.dumps({'status':v['status'],'passed':v['passed'],'total':v['total'],'rows':[{k:r[k] for k in ('id','passed','browser_answer_matches_actual_trace','source_and_license_links_visible')} for r in v['rows']]}));raise SystemExit(v['status']!='PASS')
