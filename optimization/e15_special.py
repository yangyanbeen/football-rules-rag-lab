"""Interleaved real frontend A/B; lifecycle and resource outcomes remain separate."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
from e12_browser_eval import ROOT,get,wait,save,lines,JOURNAL
from e12_browser_load_v3 import ObservedPage
from e14_resources import Sampler,snapshot,models
from e13_live import source_refs
from answer_eval_core import read,record

def main(a):
    out=a.out;refs=source_refs();labels={q['question_id']:q for q in read(ROOT/'optimization/datasets/dev_40.json')+read(ROOT/'optimization/datasets/regression_50.json')}
    pairs=[dict(qid=q,repeat=r) for r in (1,2) for q in ('D001','D003','D023','T013','T026')]+[dict(qid=q,repeat=1) for q in ('D002','T001','D004','D036')]
    schedule=[dict(**c,variant=v) for i,c in enumerate(pairs) for v in ('AB' if i%2==0 else 'BA')]
    save(out/'schedule.json',schedule);save(out/'metadata.json',dict(source_files=refs,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),hardware=snapshot(),schedule=schedule,first_normal_request_cold=True,source_facts=True,lazy_retrieval=True,target_wait_seconds=.2,holdout_used=False))
    sampler=Sampler(a.server_pid,out/'resources.jsonl',a.ui_pid,interval_seconds=.2);browser=None;page=None;rows=[];status='COMPLETED'
    try:
        profile=out/'chrome';log=(out/'chrome.log').open('wb')
        browser=subprocess.Popen(['C:/Program Files/Google/Chrome/Application/chrome.exe','--headless=new','--remote-debugging-port=0','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-sync','--disable-extensions','--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows','--disable-features=CalculateNativeWinOcclusion','--window-size=1440,1000','--user-data-dir='+str(profile),'about:blank'],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);log.close()
        port=wait(lambda:(profile/'DevToolsActivePort').read_text('utf8').splitlines()[0],25,'Chrome port')
        page=ObservedPage(json.loads(get('http://127.0.0.1:'+port+'/json/new?about:blank','PUT')))
        page.request('Page.navigate',url='http://127.0.0.1:7867/');wait(page.ready,35,'normal chat input');time.sleep(2)
        for index,item in enumerate(schedule,1):
            q=labels[item['qid']]['question'];name=item['qid']+'-r'+str(item['repeat'])+'-'+item['variant'];page.fresh();time.sleep(1.5)
            (out/'release-flag.json').write_bytes(json.dumps(dict(enabled=item['variant']=='B')).encode())
            before=snapshot();before_models=models();offset=len(lines(JOURNAL));qh=hashlib.sha256(q.encode()).hexdigest();start=sampler.begin(name);error=None;r=None;event=None
            try:
                page.submit(q);event=wait(lambda:next((e for e in lines(JOURNAL)[offset:] if e.get('question_sha256')==qh),None),120,name+' UI outcome')
                ref=event['private_trace'];assert record(ROOT/ref['path'])==ref;r=read(ROOT/ref['path'])
                def rendered():
                    answers=page.answers()
                    if not answers:return False
                    text=answers[-1]
                    if r['status']=='refused':return ('赛事' in text and '赛季' in text) if item['qid']=='D036' else '现有资料不足以可靠回答' in text
                    return all(cid in text for cid in r['selected_ids']) and '根据现有资料' in text
                wait(rendered,12,name+' visible final answer')
            except Exception as exc:error=type(exc).__name__+': '+str(exc)
            seconds=time.perf_counter()-start;resource=sampler.end(start)
            events=[e for p in (out/'events').glob('*.jsonl') for e in lines(p) if start<=e['monotonic']<=start+seconds]
            stage_mem=[e['memory']['available']/2**30 for e in events if 'available' in e.get('memory',{})]
            combined=min([resource['available_min_GiB']]+stage_mem)
            time.sleep(2);value=dict(name=name,question_id=item['qid'],question=q,repeat=item['repeat'],variant=item['variant'],seconds=seconds,result=r,event=event,error=error,
                before=before,before_models=before_models,after_2s=snapshot(),resources=resource,stage_events=events,combined_available_min_GiB=combined)
            save(out/(name+'.json'),value);rows.append(value)
            releases=[e for e in events if e['stage']=='reranker_release_end']
            print(json.dumps(dict(done=index,total=len(schedule),name=name,status=r['status'] if r else None,selected=r['selected_ids'] if r else None,seconds=seconds,min_available=combined,
                release_collected=releases[-1].get('object_collected') if releases else None,error=error),ensure_ascii=False),flush=True)
            if sampler.aborted or error:status='RESOURCE_STOP' if sampler.aborted else 'ENTRY_ERROR';break
        assert all(record(ROOT/n)==v for n,v in refs.items())
    except Exception:
        status='SCRIPT_ERROR';raise
    finally:
        if page:
            try:page.close()
            except Exception:pass
        if browser and browser.poll() is None:subprocess.run(['taskkill','/PID',str(browser.pid),'/T','/F'],capture_output=True);browser.wait(timeout=10)
        sampler.close();save(out/'completed.json',dict(status=status,observations=len(rows),hashes={r['name']+'.json':hashlib.sha256((out/(r['name']+'.json')).read_bytes()).hexdigest() for r in rows},holdout_used=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--server-pid',type=int,required=True);p.add_argument('--ui-pid',type=int,required=True);main(p.parse_args())
