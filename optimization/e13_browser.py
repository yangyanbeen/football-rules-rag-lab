"""One real browser tab, fresh conversations, normal UI and default Worker."""
import argparse,base64,hashlib,json,subprocess,time
from pathlib import Path
from e12_browser_eval import ROOT,get,wait,save,lines,JOURNAL
from e12_browser_load_v3 import ObservedPage
from e13_live import content_score,source_refs
from e10_resources import Sampler,snapshot
from answer_eval_core import read,record

def run(out,pid):
    assert not out.exists();out.mkdir(parents=True)
    plan=read(ROOT/'optimization/experiments/E13_source_facts/plan.json')
    names=['grass_original','grass_paraphrase','pressure_original','pressure_paraphrase','goal_both_paraphrase','players','D036_gate']
    cases={c['name']:c for c in plan['pressure_questions']+plan['correct_controls']+plan['boundary_controls']}
    facts={f['fact_id']:f for f in read(ROOT/'config/source_bound_facts.json')['facts']}
    refs=source_refs();save(out/'metadata.json',dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_files=refs,hardware=snapshot(),scheduled_names=names,single_tab=True,fresh_conversation_per_request=True,
        submission='Visible normal chat textarea input and Send button; actual UI event and private default Worker trace verified',
        feature_enabled=True,holdout_used=False))
    sampler=Sampler(pid,out/'resources.jsonl');browser=None;page=None;rows=[];status='COMPLETED';error=None
    try:
        profile=out/'chrome';log=(out/'chrome.log').open('wb')
        browser=subprocess.Popen(['C:/Program Files/Google/Chrome/Application/chrome.exe','--headless=new','--remote-debugging-port=0',
            '--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-sync','--disable-extensions',
            '--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows',
            '--disable-features=CalculateNativeWinOcclusion','--window-size=1440,1000','--user-data-dir='+str(profile),'about:blank'],
            stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);log.close()
        port=wait(lambda:(profile/'DevToolsActivePort').read_text('utf8').splitlines()[0],25,'Chrome port')
        page=ObservedPage(json.loads(get('http://127.0.0.1:'+port+'/json/new?about:blank','PUT')))
        page.request('Page.navigate',url='http://127.0.0.1:7867/');wait(page.ready,35,'normal chat input');time.sleep(2)
        save(out/'chrome-version.json',page.request('Browser.getVersion'))
        for name in names:
            page.fresh();time.sleep(1.5)
            c=cases[name];offset=len(lines(JOURNAL));qh=hashlib.sha256(c['question'].encode()).hexdigest()
            start=sampler.begin(name);r=dict(name=name,question=c['question'],error=None)
            try:
                page.submit(c['question'])
                event=wait(lambda:next((e for e in lines(JOURNAL)[offset:] if e.get('question_sha256')==qh),None),120,name+' actual UI outcome')
                assert event['route']=='knowledge';path=ROOT/event['private_trace']['path'];assert record(path)==event['private_trace']
                trace=read(path);r.update(event=event,trace=trace,score=content_score(trace,c,facts),status=trace['status'],
                    selected_ids=trace['selected_ids'],technical_complete=trace['error'] is None)
                def rendered():
                    answers=page.answers()
                    if not answers:return False
                    text=answers[-1]
                    if not all(cid in text for cid in trace['selected_ids']):return False
                    if trace['status']=='refused':return '证据' in text or '赛事' in text or '赛季' in text
                    tokens=['绿色'] if name.startswith('grass') else ['59','108','千帕'] if name.startswith('pressure') else ['7.32','2.44'] if name.startswith('goal') else ['11','守门员']
                    return all(t in text for t in tokens)
                wait(rendered,12,name+' visible answer and source IDs');r['visible_answer_verified']=True
                if name=='D036_gate':
                    r['zero_call_gate']=trace['status']=='refused' and bool(trace['business_decision']) and trace['retrieval'] is None and not trace['attempts']
                if name=='grass_original':
                    screen=page.request('Page.captureScreenshot',format='png');(out/'grass-ui.png').write_bytes(base64.b64decode(screen['data']))
            except Exception as exc:r.update(error=type(exc).__name__+': '+str(exc),technical_complete=False)
            r.update(seconds=time.perf_counter()-start,resources=sampler.end(start));save(out/(name+'.json'),r);rows.append(r)
            print(json.dumps(dict(name=name,status=r.get('status'),selected=r.get('selected_ids'),score=r.get('score'),error=r['error'],
                seconds=r['seconds'],available_min_GiB=r['resources']['available_min_GiB']),ensure_ascii=False),flush=True)
            if (r.get('score') or {}).get('wrong_supplement'):status='STOP_WRONG_SUPPLEMENT';break
            if sampler.aborted:status='RESOURCE_STOP';break
            if r['error']:status='ENTRY_ERROR';break
        assert all(record(ROOT/n)==v for n,v in refs.items())
    except Exception as exc:
        status='SCRIPT_ERROR';error=type(exc).__name__+': '+str(exc);raise
    finally:
        if page:
            try:page.close()
            except Exception:pass
        if browser and browser.poll() is None:
            subprocess.run(['taskkill','/PID',str(browser.pid),'/T','/F'],capture_output=True);browser.wait(timeout=10)
        sampler.close()
        quality=len(rows)==len(names) and all(not r['error'] and r.get('technical_complete') and r.get('visible_answer_verified') and
            (r.get('zero_call_gate') if r['name']=='D036_gate' else r['score']['grade']=='correct') and not r['score'].get('wrong_supplement') for r in rows)
        resources=len(rows)==len(names) and all(r['seconds']<=60 and r['resources']['available_min_GiB'] is not None and r['resources']['available_min_GiB']>=1 for r in rows)
        hashes={r['name']+'.json':hashlib.sha256((out/(r['name']+'.json')).read_bytes()).hexdigest() for r in rows}
        save(out/'result.json',dict(status=status,error=error,observations=len(rows),quality_passed=quality,runtime_passed=resources,
            all_gates_passed=status=='COMPLETED' and quality and resources,hashes=hashes,holdout_used=False,
            per_observation=[{k:r.get(k) for k in ('name','status','selected_ids','score','error','seconds','resources','zero_call_gate','visible_answer_verified')} for r in rows]))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--server-pid',type=int,required=True);a=p.parse_args();run(a.out,a.server_pid)
