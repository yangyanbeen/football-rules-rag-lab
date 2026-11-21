"""Serial normal Worker/browser probes, correlated with stdlib Worker stage markers."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
from e12_browser_eval import ROOT,get,wait,save,lines,JOURNAL
from e12_browser_load_v3 import ObservedPage
from e14_resources import Sampler,snapshot,models
from e13_live import source_refs
from task13_audit_client import call_worker
from answer_eval_core import read,record

CASES=[('D036_first','某联赛队员累计三张黄牌一定停赛几场？没有给联赛和赛季。',False),
       ('players','球队最多上场多少人，其中哪个位置必须有一人？',False),
       ('D036_resident','某联赛队员累计三张黄牌一定停赛几场？没有给联赛和赛季。',False),
       ('fact_A','人工草坪的颜色有什么限制？',False),('fact_B','人工草坪的颜色有什么限制？',True)]

def main(a):
    out=a.out;refs=source_refs();save(out/'probe-metadata.json',dict(source_files=refs,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),hardware=snapshot(),cases=CASES,holdout_used=False,sample_interval_seconds=.25))
    sampler=Sampler(a.server_pid,out/'resources.jsonl',a.ui_pid);rows=[];browser=None;page=None;status='COMPLETED'
    try:
        for entry in ('worker','browser'):
            if entry=='browser':
                profile=out/'chrome';log=(out/'chrome.log').open('wb')
                browser=subprocess.Popen(['C:/Program Files/Google/Chrome/Application/chrome.exe','--headless=new','--remote-debugging-port=0','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-sync','--disable-extensions','--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows','--disable-features=CalculateNativeWinOcclusion','--window-size=1440,1000','--user-data-dir='+str(profile),'about:blank'],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);log.close()
                port=wait(lambda:(profile/'DevToolsActivePort').read_text('utf8').splitlines()[0],25,'Chrome port')
                page=ObservedPage(json.loads(get('http://127.0.0.1:'+port+'/json/new?about:blank','PUT')))
                page.request('Page.navigate',url='http://127.0.0.1:7867/');wait(page.ready,35,'chat input');time.sleep(2)
            for name,q,flag in CASES:
                if page:page.fresh();time.sleep(1.5)
                (out/'fact-flag.json').write_bytes(json.dumps(dict(enabled=flag)).encode());os.environ['FOOTBALL_SOURCE_FACTS']='1' if flag else '0'
                before=snapshot();before_models=models();offset=len(lines(JOURNAL));start=sampler.begin(entry+'-'+name);error=None;r=None;event=None;visible=False
                try:
                    if entry=='worker':r,reference,wall=call_worker(q)
                    else:
                        qh=hashlib.sha256(q.encode()).hexdigest();page.submit(q)
                        event=wait(lambda:next((e for e in lines(JOURNAL)[offset:] if e.get('question_sha256')==qh),None),120,name+' UI event')
                        reference=event['private_trace'];assert record(ROOT/reference['path'])==reference;r=read(ROOT/reference['path'])
                        def rendered():
                            answers=page.answers()
                            return answers and (('赛事' in answers[-1] and '赛季' in answers[-1]) if name.startswith('D036') else all(cid in answers[-1] for cid in r['selected_ids']) and ('绿色' in answers[-1] if name.startswith('fact') and r['status']=='answered' else '11' in answers[-1] if name=='players' else '证据' in answers[-1]))
                        wait(rendered,12,name+' visible response');visible=True
                except Exception as exc:error=type(exc).__name__+': '+str(exc)
                seconds=time.perf_counter()-start;resources=sampler.end(start);time.sleep(2);after=snapshot()
                events=[e for p in (out/'events').glob('*.jsonl') for e in lines(p) if start<=e['monotonic']<=start+seconds]
                row=dict(name=name,entry=entry,feature=flag,seconds=seconds,before=before,before_models=before_models,after_2s=after,resources=resources,events=events,result=r,event=event,visible=visible,error=error)
                save(out/(entry+'-'+name+'.json'),row);rows.append(row)
                print(json.dumps(dict(entry=entry,name=name,status=r['status'] if r else None,error=error,seconds=seconds,available_min_GiB=resources['available_min_GiB'],role_peaks=resources.get('role_peak_rss_GiB')),ensure_ascii=False),flush=True)
                if sampler.aborted or error:status='RESOURCE_STOP' if sampler.aborted else 'ENTRY_ERROR';break
            if status!='COMPLETED':break
        assert all(record(ROOT/n)==v for n,v in refs.items())
    except Exception:
        status='SCRIPT_ERROR';raise
    finally:
        if page:
            try:page.close()
            except Exception:pass
        if browser and browser.poll() is None:subprocess.run(['taskkill','/PID',str(browser.pid),'/T','/F'],capture_output=True);browser.wait(timeout=10)
        sampler.close();save(out/'probe-completed.json',dict(status=status,observations=len(rows),hashes={r['entry']+'-'+r['name']+'.json':hashlib.sha256((out/(r['entry']+'-'+r['name']+'.json')).read_bytes()).hexdigest() for r in rows},holdout_used=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--server-pid',type=int,required=True);p.add_argument('--ui-pid',type=int,required=True);main(p.parse_args())
