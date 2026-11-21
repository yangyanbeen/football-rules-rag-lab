"""Controlled load recheck: verify real submissions before timing the Worker."""
import argparse,concurrent.futures,hashlib,json,subprocess,sys,threading,time
from pathlib import Path
from e12_browser_eval import ROOT,Page,get,wait,save,lines,JOURNAL
from e10_resources import Sampler,snapshot
from answer_eval_core import read,record

class ObservedPage(Page):
    def submit(self,question):
        value=json.dumps(question,ensure_ascii=False)
        assert self.js("(()=>{const e=document.querySelector('#chat-input textarea');if(!e||e.disabled)return false;Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(e,"+value+");e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true})()")
        assert self.js("(()=>{const bs=Array.from(document.querySelectorAll('#chat-input button')).filter(e=>e.getClientRects().length&&!e.disabled);if(!bs.length)return false;bs[bs.length-1].click();return true})()")

    def __init__(self,item):
        self.network=[];super().__init__(item)
        self.request('Network.enable')
        self.request('Emulation.setDeviceMetricsOverride',width=1440,height=1000,deviceScaleFactor=1,mobile=False)
        self.request('Emulation.setFocusEmulationEnabled',enabled=True)
    def request(self,method,**params):
        self.number+=1;self.ws.send(json.dumps(dict(id=self.number,method=method,params=params)))
        while True:
            msg=json.loads(self.ws.recv())
            if msg.get('method')=='Network.requestWillBeSent':
                request=msg['params']['request']
                if '/queue/' in request['url'] or '/api/' in request['url']:
                    self.network.append(dict(timestamp=msg['params']['timestamp'],url=request['url'],method=request['method'],post_data=request.get('postData')))
            if msg.get('id')==self.number:
                if 'error' in msg:raise RuntimeError(msg['error'])
                return msg.get('result',{})

def main(a):
    out=a.out;plan=read(ROOT/'optimization/experiments/E12_delivery/plan.json')
    refs={n:record(ROOT/n) for n in subprocess.check_output(['git','ls-files','scripts','config'],cwd=ROOT,text=True).splitlines()}
    for name in ('e12_browser_load_v3.py','e12_browser_eval.py','e12_observed_ui.py','run_e12_load4_confirmation.ps1'):
        refs['optimization/'+name]=record(ROOT/'optimization'/name)
    for name in ('plan.json','load_recheck.json','load4_confirmation.json'):
        path='optimization/experiments/E12_delivery/'+name;refs[path]=record(ROOT/path)
    save(out/'browser-metadata.json',dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_files=refs,hardware=snapshot(),normal_worker=True,profile=a.profile,
        browser_controls='background timers/rendering not throttled; per-page focus emulation and 1440x1000 viewport; actual Worker entry verified',holdout_used=False))
    sampler=Sampler(a.server_pid,out/'resources.jsonl');browser=None;pages=[];rows=[];waves=[];status='COMPLETED';error=None
    def ask(page,name,question,offset,barrier,case=None):
        barrier.wait(timeout=20);start_ns=time.time_ns();start=time.perf_counter();qh=hashlib.sha256(question.encode()).hexdigest()
        r=dict(name=name,phase='load' if case else 'transport',question=question,submitted_ns=start_ns)
        try:
            page.submit(question)
            def entered():
                return next((e for e in lines(out/'worker-events.jsonl') if e['kind']=='worker_enter' and e.get('question_sha256')==qh and e['wall_ns']>=start_ns),None)
            def submitted_packet():
                page.js("Boolean(document.querySelector('#chat-input'))")
                for packet in page.network:
                    try:body=json.loads(packet.get('post_data') or '{}')
                    except ValueError:continue
                    if body.get('fn_index')==1 and question in str(body.get('data')):return True
                return False
            wait(submitted_packet,5,name+' actual frontend question packet')
            r['submission_confirmed']=True
            entry=wait(entered,max(1,120-(time.perf_counter()-start)),name+' actual Worker dispatch')
            r.update(worker_request_id=entry['request_id'],dispatch_seconds=(entry['wall_ns']-start_ns)/1e9)
            event=wait(lambda:next((e for e in lines(JOURNAL)[offset:] if e.get('question_sha256')==qh),None),max(1,120-(time.perf_counter()-start)),name+' UI outcome')
            trace_path=ROOT/event['private_trace']['path'];assert record(trace_path)==event['private_trace'];trace=read(trace_path)
            r.update(event=event,trace=trace,trace_record=event['private_trace'],status=trace['status'],selected_ids=trace['selected_ids'],
                technical_complete=trace['error'] is None,client_timeout=False)
            wait(lambda:any(trace['answer'][:35] in text for text in page.answers()),12,name+' answer rendered')
            observations={e['kind']:e for e in lines(out/'worker-events.jsonl') if e['request_id']==entry['request_id']}
            r['queue_timing']=dict(frontend_dispatch_seconds=r['dispatch_seconds'],
                worker_lock_wait_seconds=(observations['lock_acquired']['wall_ns']-observations['lock_wait']['wall_ns'])/1e9,
                worker_locked_service_seconds=(observations['lock_released']['wall_ns']-observations['lock_acquired']['wall_ns'])/1e9,
                worker_function_seconds=(observations['worker_return']['wall_ns']-observations['worker_enter']['wall_ns'])/1e9)
            if case:
                ids=trace['selected_ids'];mask=[bool(set(ids)&set(v)) for v in case['support_per_point']];support={c for v in case['support_per_point'] for c in v}
                r['semantic_score']=dict(grade='false_refusal' if trace['status']=='refused' else 'correct' if all(mask) else 'partial' if any(mask) else 'incorrect',
                    point_mask=mask,citation_numerator=sum(c in support for c in ids),citation_denominator=len(ids))
            else:r['zero_call_gate']=trace['status']=='refused' and trace['business_decision'] is not None and trace['retrieval'] is None and not trace['attempts']
        except TimeoutError as exc:r.update(runtime_error=str(exc),technical_complete=False,client_timeout=bool(r.get('submission_confirmed')),submission_confirmed=r.get('submission_confirmed',False))
        except Exception as exc:r.update(runtime_error=type(exc).__name__+': '+str(exc),technical_complete=False,client_timeout=False,automation_error=True)
        r.update(seconds=time.perf_counter()-start,completed_ns=time.time_ns(),resources=sampler.end(start))
        save(out/(name+'.json'),r);save(out/(name+'-network.json'),page.network)
        print(json.dumps({k:r.get(k) for k in ('name','submission_confirmed','status','technical_complete','client_timeout','seconds','queue_timing','semantic_score','runtime_error')},ensure_ascii=False),flush=True)
        return r
    try:
        profile=out/'chrome';log=(out/'chrome.log').open('wb')
        browser=subprocess.Popen(['C:/Program Files/Google/Chrome/Application/chrome.exe','--headless=new','--remote-debugging-port=0',
            '--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-sync','--disable-extensions',
            '--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows',
            '--disable-features=CalculateNativeWinOcclusion','--window-size=1440,1000','--user-data-dir='+str(profile),'about:blank'],
            stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);log.close()
        port=wait(lambda:(profile/'DevToolsActivePort').read_text('utf8').splitlines()[0],25,'Chrome port')
        def new():
            p=ObservedPage(json.loads(get('http://127.0.0.1:'+port+'/json/new?about:blank','PUT')));pages.append(p)
            p.request('Page.navigate',url='http://127.0.0.1:7867/');wait(p.ready,35,'input');time.sleep(2);p.fresh();return p
        def wave(cases,level,label):
            pp=[new() for _ in cases];offset=len(lines(JOURNAL));barrier=threading.Barrier(len(cases));begin=sampler.begin(label)
            with concurrent.futures.ThreadPoolExecutor(len(cases)) as pool:
                jobs=[pool.submit(ask,p,label+'-'+str(i) if label=='transport' else 'load-c'+str(level)+'-'+case['id'],
                    case['question'],offset,barrier,case if label!='transport' else None) for i,(p,case) in enumerate(zip(pp,cases))]
                values=[j.result() for j in jobs]
            waves.append(dict(concurrency=level,label=label,resources=sampler.end(begin),names=[r['name'] for r in values],
                submission_spread_seconds=(max(r['submitted_ns'] for r in values)-min(r['submitted_ns'] for r in values))/1e9,
                all_submissions_confirmed=all(r.get('submission_confirmed') for r in values)))
            rows.extend(values);time.sleep(.7)
            for p in pp:p.close();pages.remove(p)
            return values
        transport=wave([dict(question='某联赛累计三张黄牌一定停赛几场？'),dict(question='中超累计三张黄牌停赛几场？'),dict(question='2025赛季累计三张黄牌停赛几场？'),dict(question='累计三张黄牌停多少场？')],4,'transport')
        if not all(r.get('submission_confirmed') and r.get('zero_call_gate') for r in transport):status='HARNESS_TRANSPORT_FAILED'
        else:
            for level in (4,):
                for i in range(0,4,level):
                    values=wave(plan['load_requests'][i:i+level],level,'load-c'+str(level))
                    if sampler.aborted or not all(r.get('submission_confirmed') for r in values):break
                if sampler.aborted or not all(r.get('submission_confirmed') for r in values):status='RESOURCE_STOP' if sampler.aborted else 'HARNESS_SUBMISSION_FAILED';break
    except Exception as exc:error=type(exc).__name__+': '+str(exc);status='SCRIPT_ERROR';raise
    finally:
        for p in pages:
            try:p.close()
            except Exception:pass
        if browser and browser.poll() is None:subprocess.run(['taskkill','/PID',str(browser.pid),'/T','/F'],capture_output=True);browser.wait(timeout=10)
        sampler.close()
        save(out/'browser-completed.json',dict(status=status,error=error,observations=len(rows),functional_observations=0,
            load_observations=sum(r['phase']=='load' for r in rows),waves=waves,
            hashes={r['name']+'.json':sha(out/(r['name']+'.json')) for r in rows},holdout_used=False))
    assert all(record(ROOT/n)==v for n,v in refs.items())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--server-pid',type=int,required=True)
    p.add_argument('--ui-pid',type=int,required=True);p.add_argument('--profile',required=True);main(p.parse_args())
