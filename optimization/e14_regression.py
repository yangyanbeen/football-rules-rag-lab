"""Real candidate Worker90 with web page and services resident; no extra model judge."""
import argparse,json,subprocess,time
from e12_browser_eval import ROOT,wait,get
from e12_browser_load_v3 import ObservedPage
from e14_resources import Sampler
import e13_live

def main(a):
    gate=ROOT/'optimization/reports/E14_E13_special_metrics.json'
    assert json.loads(gate.read_text('utf8'))['all_gates_passed']
    profile=a.out/'chrome';log=(a.out/'chrome.log').open('wb');browser=None;page=None
    try:
        browser=subprocess.Popen(['C:/Program Files/Google/Chrome/Application/chrome.exe','--headless=new','--remote-debugging-port=0','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-sync','--disable-extensions','--user-data-dir='+str(profile),'about:blank'],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);log.close()
        port=wait(lambda:(profile/'DevToolsActivePort').read_text('utf8').splitlines()[0],25,'Chrome port')
        page=ObservedPage(json.loads(get('http://127.0.0.1:'+port+'/json/new?about:blank','PUT')))
        page.request('Page.navigate',url='http://127.0.0.1:7867/');wait(page.ready,35,'resident normal UI');time.sleep(2)
        e13_live.Sampler=lambda pid,path:Sampler(pid,path,a.ui_pid)
        e13_live.run(a.out/'worker',a.server_pid,'regression',gate)
    finally:
        if page:
            try:page.close()
            except Exception:pass
        if browser and browser.poll() is None:subprocess.run(['taskkill','/PID',str(browser.pid),'/T','/F'],capture_output=True);browser.wait(timeout=10)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=__import__('pathlib').Path,required=True);p.add_argument('--server-pid',type=int,required=True);p.add_argument('--ui-pid',type=int,required=True);main(p.parse_args())
