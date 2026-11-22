"""Candidate-only normal Worker and UI pilot; historical inputs, no sealed set."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
from e12_browser_eval import ROOT,get,wait,save,lines,JOURNAL
from e12_browser_load_v3 import ObservedPage
from e14_resources import Sampler,snapshot,models
from e13_live import source_refs
from task13_audit_client import call_worker
from answer_eval_core import read,record


def main(a):
    assert os.environ.get('FOOTBALL_LOW_MEMORY')=='1'
    out=a.out;refs=source_refs()
    labels={q['question_id']:q for q in read(ROOT/'optimization/datasets/dev_40.json')+read(ROOT/'optimization/datasets/regression_50.json')}
    cases=['D036','D001','D004','T026','D001']
    save(out/'metadata.json',dict(source_files=refs,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        hardware=snapshot(),cases=cases,scope='Candidate-only serial residency pilot; historical input comparisons are not concurrent A/B.',
        startup_floor_GiB=5.0,request_floor_GiB=3.25,acceptance_minimum_GiB=1,acceptance_maximum_seconds=60,holdout_used=False))
    sampler=Sampler(a.server_pid,out/'resources.jsonl',a.ui_pid,interval_seconds=.2)
    rows=[];browser=None;page=None;status='COMPLETED'
    try:
        for entry in ('worker','browser'):
            if entry=='browser':
                profile=out/'chrome';log=(out/'chrome.log').open('wb')
                browser=subprocess.Popen(['C:/Program Files/Google/Chrome/Application/chrome.exe','--headless=new','--remote-debugging-port=0',
                    '--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-sync','--disable-extensions',
                    '--window-size=1440,1000','--user-data-dir='+str(profile),'about:blank'],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);log.close()
                port=wait(lambda:(profile/'DevToolsActivePort').read_text('utf8').splitlines()[0],25,'Chrome port')
                page=ObservedPage(json.loads(get('http://127.0.0.1:'+port+'/json/new?about:blank','PUT')))
                page.request('Page.navigate',url='http://127.0.0.1:7867/');wait(page.ready,35,'chat input');time.sleep(2)
            for pos,qid in enumerate(cases,1):
                q=labels[qid]['question'];name=f'{entry}-{pos}-{qid}'
                if page:page.fresh();time.sleep(1)
                before=snapshot();before_models=models()
                if before['available_GiB']<3.25:
                    status='HEADROOM_STOP';save(out/'headroom-stop.json',dict(name=name,before=before,required_GiB=3.25));break
                offset=len(lines(JOURNAL));start=sampler.begin(name);r=None;error=None;reference=None
                try:
                    if entry=='worker':r,reference,_=call_worker(q)
                    else:
                        qh=hashlib.sha256(q.encode()).hexdigest();page.submit(q)
                        def outcome():
                            event=next((e for e in lines(JOURNAL)[offset:] if e.get('question_sha256')==qh),None)
                            if event:return event
                            answers=page.answers()
                            if answers and '本次请求未能完成' in answers[-1]:raise RuntimeError('Visible Worker failure')
                        event=wait(outcome,100,name+' UI outcome');reference=event['private_trace']
                        assert record(ROOT/reference['path'])==reference;r=read(ROOT/reference['path'])
                        def rendered():
                            answers=page.answers()
                            return answers and (('赛事' in answers[-1] and '赛季' in answers[-1]) if qid=='D036' else
                                ('根据现有资料' in answers[-1] and all(cid in answers[-1] for cid in r['selected_ids'])) if r['status']=='answered' else
                                '现有资料不足以可靠回答' in answers[-1])
                        wait(rendered,12,name+' visible response')
                except Exception as exc:error=type(exc).__name__+': '+str(exc)
                seconds=time.perf_counter()-start;resources=sampler.end(start)
                events=[e for p in (out/'events').glob('*.jsonl') for e in lines(p) if start<=e['monotonic']<=start+seconds]
                stage_values=[e['memory']['available']/2**30 for e in events if 'available' in e.get('memory',{})]
                minimum=min([resources['available_min_GiB']]+stage_values)
                time.sleep(1);after=snapshot();after_models=models()
                row=dict(name=name,entry=entry,question_id=qid,question=q,before=before,before_models=before_models,seconds=seconds,
                    result=r,private_trace=reference,error=error,resources=resources,stage_events=events,combined_available_min_GiB=minimum,
                    after_1s=after,after_models=after_models)
                save(out/(name+'.json'),row);rows.append(row)
                print(json.dumps(dict(name=name,status=r['status'] if r else None,selected=r['selected_ids'] if r else None,
                    seconds=seconds,min_available_GiB=minimum,role_peak_rss=resources.get('role_peak_rss_GiB'),idle_models=after_models,error=error),ensure_ascii=False),flush=True)
                if sampler.aborted or error:status='RESOURCE_STOP' if sampler.aborted else 'ENTRY_ERROR';break
                if minimum<1:status='RESOURCE_GATE_FAILED';break
            if status!='COMPLETED':break
        assert all(record(ROOT/n)==v for n,v in refs.items())
    except Exception:
        status='SCRIPT_ERROR';raise
    finally:
        if page:
            try:page.close()
            except Exception:pass
        if browser and browser.poll() is None:
            subprocess.run(['taskkill','/PID',str(browser.pid),'/T','/F'],capture_output=True);browser.wait(timeout=10)
        sampler.close();save(out/'completed.json',dict(status=status,observations=len(rows),
            hashes={r['name']+'.json':hashlib.sha256((out/(r['name']+'.json')).read_bytes()).hexdigest() for r in rows},holdout_used=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--server-pid',type=int,required=True);p.add_argument('--ui-pid',type=int,required=True);main(p.parse_args())
