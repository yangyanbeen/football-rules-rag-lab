"""No model/server requests: reproduce background-tab keyboard submission."""
import concurrent.futures,json,subprocess,threading,time,sys
from pathlib import Path
from e12_browser_eval import Page,get,wait,save,ROOT
def main():
    out=ROOT/'.runtime/phase2/e12-browser-input-diagnostic';out.mkdir(exist_ok=False)
    log=(out/'chrome.log').open('wb');profile=out/'chrome'
    browser=subprocess.Popen(['C:/Program Files/Google/Chrome/Application/chrome.exe','--headless=new',
        '--remote-debugging-port=0','--no-first-run','--disable-background-networking','--user-data-dir='+str(profile),'about:blank'],
        stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);log.close()
    pages=[];results={}
    try:
        port=wait(lambda:(profile/'DevToolsActivePort').read_text('utf8').splitlines()[0],25,'Chrome port')
        for i in range(2):
            p=Page(json.loads(get('http://127.0.0.1:'+port+'/json/new?about:blank','PUT')));pages.append(p)
            p.js("document.body.innerHTML='<div id=\"chat-input\"><textarea></textarea></div>';window.received=[];document.querySelector('textarea').addEventListener('keydown',e=>window.received.push({key:e.key,value:e.target.value}));true")
        for kind in ('cdp_keyboard','dom_input'):
            for p in pages:p.js("document.querySelector('textarea').value='';window.received=[];true")
            barrier=threading.Barrier(2)
            def submit(index):
                p=pages[index];barrier.wait()
                if kind=='cdp_keyboard':p.submit('question-'+str(index))
                else:
                    q=json.dumps('question-'+str(index))
                    p.js("(()=>{const e=document.querySelector('textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(e,"+q+");e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true}));return true})()")
                return p.js("({value:document.querySelector('textarea').value,events:window.received})")
            with concurrent.futures.ThreadPoolExecutor(2) as pool:results[kind]=list(pool.map(submit,range(2)))
        save(out/'results.json',dict(model_calls=0,network_rag_requests=0,results=results))
        print(json.dumps(results,ensure_ascii=False))
    finally:
        for p in pages:p.close()
        if browser.poll() is None:subprocess.run(['taskkill','/PID',str(browser.pid),'/T','/F'],capture_output=True);browser.wait(timeout=10)
if __name__=='__main__':main()
