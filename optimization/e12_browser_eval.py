"""Real browser/default-worker functional and bounded load observations."""
import argparse,base64,concurrent.futures,hashlib,json,os,socket,subprocess,sys,threading,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import canonical,read,record
from e10_resources import Sampler,snapshot
HTTP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
JOURNAL=ROOT/'.runtime/task13-audit/ui-multiturn-events.jsonl'
PLAN=ROOT/'optimization/experiments/E12_delivery/plan.json'
BASE='59867813e8eb16709b0be1946708d8c03a33b9cb'

def save(p,v):
    with p.open('x',encoding='utf8') as f:json.dump(v,f,ensure_ascii=False,indent=2)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def get(url,method=None):
    with HTTP.open(urllib.request.Request(url,method=method),timeout=3) as r:return r.read()
def lines(p):
    if not p.exists():return []
    return [json.loads(v) for v in p.read_text('utf8').splitlines() if v.strip()]
def wait(fn,timeout,label):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        try:
            value=fn()
            if value:return value
        except (OSError,ValueError,KeyError):pass
        time.sleep(.2)
    raise TimeoutError(label)

class Page:
    def __init__(self,item):
        import websocket
        self.id=item['id'];self.number=0
        self.ws=websocket.create_connection(item['webSocketDebuggerUrl'],suppress_origin=True,timeout=8)
    def request(self,method,**params):
        self.number+=1;self.ws.send(json.dumps(dict(id=self.number,method=method,params=params)))
        while True:
            msg=json.loads(self.ws.recv())
            if msg.get('id')==self.number:
                if 'error' in msg:raise RuntimeError(msg['error'])
                return msg.get('result',{})
    def js(self,code):
        r=self.request('Runtime.evaluate',expression=code,returnByValue=True)
        if r.get('exceptionDetails'):raise RuntimeError(r['exceptionDetails'])
        return r['result'].get('value')
    def answers(self):
        return self.js("""Array.from(document.querySelectorAll('#main-chat-bot [aria-label]')).map(e=>e.getAttribute('aria-label')).filter(s=>s.startsWith("bot's message:"))""")
    def ready(self):return self.js("Boolean(document.querySelector('#chat-input textarea:not(:disabled)'))")
    def submit(self,q):
        assert self.js("(()=>{const e=document.querySelector('#chat-input textarea');if(!e||e.disabled)return false;e.focus();return true})()")
        self.request('Input.insertText',text=q)
        args=dict(key='Enter',code='Enter',windowsVirtualKeyCode=13,nativeVirtualKeyCode=13)
        self.request('Input.dispatchKeyEvent',type='keyDown',text='\r',**args);self.request('Input.dispatchKeyEvent',type='keyUp',**args)
    def fresh(self):
        assert self.js("(()=>{const e=document.querySelector('button#new-conv-button, #new-conv-button button');if(!e)return false;e.click();return true})()")
        wait(lambda:self.ready() and not self.answers(),15,'fresh conversation')
    def close(self):
        try:self.request('Page.close')
        except Exception:pass
        self.ws.close()

def main(args):
    out=args.out;plan=read(PLAN);assert not (out/'browser-metadata.json').exists()
    assert not subprocess.check_output(['git','diff',BASE,'--','scripts','config'],cwd=ROOT)
    refs={p:record(ROOT/p) for p in subprocess.check_output(['git','ls-files','scripts','config'],cwd=ROOT,text=True).splitlines()}
    for p in [Path(__file__),ROOT/'optimization/e12_observed_ui.py',ROOT/'optimization/e12_quality_scope.py',ROOT/'optimization/run_e12_delivery.ps1',PLAN]:
        refs[p.relative_to(ROOT).as_posix()]=record(p)
    environment=json.loads(subprocess.check_output([sys.executable,'-B','-c',
        "import importlib.metadata as m,json;from pathlib import Path;a={d.metadata['Name']:d.version for d in m.distributions()};e=json.loads(Path('reports/task13/environment-final.json').read_text('utf8'))['actual']['packages'];assert a==e;print(json.dumps({'locked_packages':len(a),'exact_match':True}))"],cwd=ROOT,text=True))
    save(out/'browser-metadata.json',dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_files=refs,plan_sha256=sha(PLAN),hardware_at_start=snapshot(),environment=environment,profile=args.profile,
        normal_sources_unchanged=True,extra_tools='Isolated psutil for observation only; clean child verified accepted 262-package environment.',holdout_used=False))
    sampler=Sampler(args.server_pid,out/'resources.jsonl');browser=None;rows=[];waves=[];error=None;target_pages=[]
    def ask(page,name,q,turn,phase,offset,barrier=None,load_case=None):
        if barrier:barrier.wait(timeout=20)
        started=time.time_ns();mono=time.perf_counter();response=dict(name=name,phase=phase,question=q,submitted_ns=started)
        try:
            page.submit(q);qh=hashlib.sha256(q.encode()).hexdigest()
            def result_event():
                found=next((r for r in lines(JOURNAL)[offset:] if r.get('question_sha256')==qh),None)
                if found:return ('event',found)
                answers=page.answers()
                if len(answers)>=turn and '本次请求未能完成' in answers[-1]:return ('failure',None)
            kind,event=wait(result_event,120,name+' UI outcome')
            if kind=='failure':
                response.update(runtime_error='visible_operational_error',technical_complete=False,client_timeout=False)
            else:
                response['event']=event
                if event['route']=='knowledge':
                    trace_path=ROOT/event['private_trace']['path'];assert record(trace_path)==event['private_trace']
                    r=read(trace_path);response.update(trace=r,trace_record=event['private_trace'],
                        technical_complete=r['error'] is None,client_timeout=False,status=r['status'],selected_ids=r['selected_ids'],
                        effective_query=r['question'],answer_attempts=len(r['attempts']),query_resolution=r.get('query_resolution'))
                    def rendered():
                        answers=page.answers()
                        return len(answers)>=turn and r['answer'][:35] in answers[-1] and all(cid in answers[-1] for cid in r['selected_ids'])
                    wait(rendered,12,name+' rendered final answer')
                    observations=lines(out/'worker-events.jsonl')
                    returned=next(v for v in reversed(observations) if v['kind']=='worker_return' and v.get('trace_id')==r['trace_id'])
                    events={v['kind']:v for v in observations if v['request_id']==returned['request_id']}
                    response['queue_timing']=dict(
                        frontend_dispatch_seconds=max(0,(events['worker_enter']['wall_ns']-started)/1e9),
                        worker_lock_wait_seconds=(events['lock_acquired']['wall_ns']-events['lock_wait']['wall_ns'])/1e9,
                        worker_locked_service_seconds=(events['lock_released']['wall_ns']-events['lock_acquired']['wall_ns'])/1e9,
                        worker_function_seconds=(events['worker_return']['wall_ns']-events['worker_enter']['wall_ns'])/1e9)
                    response['visible_source_links']=page.js("Array.from(document.querySelectorAll('a[href]')).map(e=>e.href).filter(s=>s.includes('wikipedia.org')||s.includes('creativecommons.org'))")
                    if load_case:
                        ids=r['selected_ids'];mask=[bool(set(ids)&set(v)) for v in load_case['support_per_point']]
                        support={c for v in load_case['support_per_point'] for c in v}
                        response['semantic_score']=dict(grade='false_refusal' if r['status']=='refused' else 'correct' if all(mask) else 'partial' if any(mask) else 'incorrect',
                            point_mask=mask,citation_numerator=sum(c in support for c in ids),citation_denominator=len(ids))
                else:
                    response.update(technical_complete=True,client_timeout=False,status=event['status'],selected_ids=event['reused_ids'],answer_attempts=0)
                    wait(lambda:len(page.answers())>=turn,12,name+' presentation rendered')
                response['conversation_sha256']=event['conversation_sha256']
        except TimeoutError as exc:response.update(runtime_error=str(exc),technical_complete=False,client_timeout=True)
        except Exception as exc:response.update(runtime_error=type(exc).__name__+': '+str(exc),technical_complete=False,client_timeout=False,automation_error=True)
        response.update(seconds=time.perf_counter()-mono,completed_ns=time.time_ns(),resources=sampler.end(mono))
        save(out/(name+'.json'),response)
        print(json.dumps({k:response.get(k) for k in ('name','phase','status','technical_complete','client_timeout','seconds','selected_ids','queue_timing','semantic_score','runtime_error')},ensure_ascii=False),flush=True)
        return response
    try:
        chrome=Path('C:/Program Files/Google/Chrome/Application/chrome.exe');userdir=out/'chrome'
        log=(out/'chrome.stdout.log').open('wb')
        browser=subprocess.Popen([str(chrome),'--headless=new','--remote-debugging-port=0','--no-first-run','--no-default-browser-check',
            '--disable-background-networking','--disable-sync','--disable-extensions','--disable-component-update',
            '--user-data-dir='+str(userdir),'about:blank'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        log.close()
        port=wait(lambda:(userdir/'DevToolsActivePort').read_text('utf8').splitlines()[0],30,'Chrome DevTools port')
        def new_page():
            item=json.loads(get('http://127.0.0.1:'+port+'/json/new?about:blank','PUT'));p=Page(item);target_pages.append(p)
            p.request('Page.navigate',url='http://127.0.0.1:7867/')
            wait(p.ready,35,'normal chat input');time.sleep(.5);p.fresh();return p
        page=new_page();save(out/'chrome-version.json',page.request('Browser.getVersion'))
        for name,q,turn in [
            ('ordinary','球队最多上场多少人，其中哪个位置必须有一人？',1),
            ('sources','刚才的答案引用了哪些来源？',2),
            ('topic_switch','换个话题，球的面片可以用哪些连接方式，球胆常用什么材料？',3)]:
            sampler.begin('functional-'+name);row=ask(page,name,q,turn,'functional',len(lines(JOURNAL)));rows.append(row);time.sleep(.7)
            if name=='ordinary' and row.get('technical_complete'):
                screen=page.request('Page.captureScreenshot',format='png');(out/'ordinary-ui.png').write_bytes(base64.b64decode(screen['data']))
        page.fresh();sampler.begin('functional-isolation')
        rows.append(ask(page,'isolation_empty','把刚才的答案整理成表格',1,'functional',len(lines(JOURNAL))));time.sleep(.7)
        page.fresh()
        for name,q,turn in [
            ('parameters_explicit','中超2025赛季累计三张黄牌停赛几场？',1),
            ('parameters_followup','那累计三张停几场？',2)]:
            sampler.begin('functional-'+name);rows.append(ask(page,name,q,turn,'functional',len(lines(JOURNAL))));time.sleep(.7)
        for repeat in (1,2):
            page.fresh();sampler.begin('functional-single-fact')
            case=dict(support_per_point=[['L01-01']])
            rows.append(ask(page,'single_fact_r'+str(repeat),'人工草坪的颜色有什么限制？',1,'functional',len(lines(JOURNAL)),load_case=case));time.sleep(.7)
        page.close();target_pages.remove(page)
        if not sampler.aborted:
            for level in plan['load_schedule']['concurrency']:
                for start in range(0,4,level):
                    batch=plan['load_requests'][start:start+level];pages=[new_page() for _ in batch]
                    offset=len(lines(JOURNAL));barrier=threading.Barrier(level);begin=sampler.begin('load-'+str(level))
                    with concurrent.futures.ThreadPoolExecutor(level) as pool:
                        jobs=[pool.submit(ask,p,'load-c'+str(level)+'-'+case['id'],case['question'],1,'load',offset,barrier,case) for p,case in zip(pages,batch)]
                        values=[job.result() for job in jobs]
                    wave=dict(concurrency=level,start_index=start,resources=sampler.end(begin),names=[v['name'] for v in values],
                        submit_spread_seconds=(max(v['submitted_ns'] for v in values)-min(v['submitted_ns'] for v in values))/1e9)
                    waves.append(wave);rows.extend(values);time.sleep(.7)
                    for p in pages:p.close();target_pages.remove(p)
                    if sampler.aborted or any(v.get('automation_error') or v.get('client_timeout') for v in values):break
                if sampler.aborted or any(v.get('automation_error') or v.get('client_timeout') for v in rows):break
    except Exception as exc:
        error=type(exc).__name__+': '+str(exc);raise
    finally:
        for p in target_pages:
            try:p.close()
            except Exception:pass
        if browser and browser.poll() is None:
            subprocess.run(['taskkill','/PID',str(browser.pid),'/T','/F'],capture_output=True);browser.wait(timeout=10)
        sampler.close()
        save(out/'browser-completed.json',dict(status='SCRIPT_ERROR' if error else 'RESOURCE_STOP' if sampler.aborted else 'COMPLETED',
            error=error,observations=len(rows),functional_observations=sum(r['phase']=='functional' for r in rows),
            load_observations=sum(r['phase']=='load' for r in rows),waves=waves,
            hashes={r['name']+'.json':sha(out/(r['name']+'.json')) for r in rows},holdout_used=False))
    assert all(record(ROOT/n)==v for n,v in refs.items())
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--server-pid',type=int,required=True)
    p.add_argument('--ui-pid',type=int,required=True);p.add_argument('--profile',required=True);main(p.parse_args())
