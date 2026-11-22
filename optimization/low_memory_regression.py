"""Fixed90 low-memory candidate; normal Worker with frontend/browser resident."""
import argparse,json,os,subprocess,time
from pathlib import Path
from e12_browser_eval import ROOT,wait,get,save
from e12_browser_load_v3 import ObservedPage
from e15_resources import Sampler
from e14_resources import snapshot,models
from answer_eval_core import record,read
import e13_live


def main(a):
    assert os.environ.get('FOOTBALL_LOW_MEMORY')=='1'
    gate=ROOT/'optimization/reports/E15_low_memory_pilot.json'
    plan=read(ROOT/'optimization/experiments/E15_low_memory/regression_plan.json')
    pilot=read(gate);assert pilot['pilot_passed'] and record(gate)==plan['pilot_report']
    identity=read(ROOT/pilot['cases'][0]['raw_record']['path'])['result']['implementation']
    assert all(record(ROOT/name)==ref for name,ref in identity['sources'].items())
    save(a.out/'regression-plan.json',dict(plan=plan,entry='Normal subprocess Worker; real UI and test browser remain resident.',
        group='Actual low-memory candidate only; E14 historical comparison and same-response pre-fact shadow separately labeled.',
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),holdout_used=False))
    profile=a.out/'chrome';log=(a.out/'chrome.log').open('wb');browser=None;page=None
    def admit():
        value=snapshot();resident=models()
        return dict(admitted=value['available_GiB']>=3.25 and resident==[],snapshot=value,loaded_models=resident,required_GiB=3.25)
    try:
        browser=subprocess.Popen(['C:/Program Files/Google/Chrome/Application/chrome.exe','--headless=new','--remote-debugging-port=0',
            '--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-sync','--disable-extensions',
            '--user-data-dir='+str(profile),'about:blank'],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);log.close()
        port=wait(lambda:(profile/'DevToolsActivePort').read_text('utf8').splitlines()[0],25,'Chrome port')
        page=ObservedPage(json.loads(get('http://127.0.0.1:'+port+'/json/new?about:blank','PUT')))
        page.request('Page.navigate',url='http://127.0.0.1:7867/');wait(page.ready,35,'resident frontend');time.sleep(2)
        e13_live.Sampler=lambda pid,path:Sampler(pid,path,a.ui_pid,a.out/'events')
        e13_live.run(a.out/'worker',a.server_pid,'regression',gate,gate_key='pilot_passed',admission=admit)
    finally:
        if page:
            try:page.close()
            except Exception:pass
        if browser and browser.poll() is None:
            subprocess.run(['taskkill','/PID',str(browser.pid),'/T','/F'],capture_output=True);browser.wait(timeout=10)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--server-pid',type=int,required=True);p.add_argument('--ui-pid',type=int,required=True);main(p.parse_args())
