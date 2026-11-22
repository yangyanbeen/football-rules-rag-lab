"""One-shot sealed40, opened only after low-memory actual90 passes all gates."""
import argparse,json,os,re,subprocess,time
from pathlib import Path
from e12_browser_eval import ROOT,get,wait,save
from e12_browser_load_v3 import ObservedPage
from e15_resources import Sampler
from e14_resources import snapshot,models
from e13_live import source_refs
from task13_audit_client import call_worker
from task13_audit import public_projection,validate_public
from answer_eval_core import read,record,digest


def main(a):
    assert os.environ.get('FOOTBALL_LOW_MEMORY')=='1'
    gate=ROOT/'optimization/reports/E15_low_memory90_resource_audit.json'
    quality=ROOT/'optimization/reports/E15_low_memory_live90_metrics.json'
    assert read(gate)['overall_pass'] and read(quality)['overall_pass']
    published=ROOT/'optimization/reports/E15_low_memory_holdout_metrics.json'
    if published.exists() and read(published).get('holdout_used') is True:
        raise RuntimeError('Sealed40 has already been evaluated; recompute archived scores only, do not rerun inference.')
    refs=source_refs();freeze=read(ROOT/'optimization/datasets/freeze_manifest.json')
    dataset=ROOT/'optimization/datasets/holdout_40.json'
    sealed=next(v for v in freeze['files'] if v['path']=='datasets/holdout_40.json')
    assert digest(dataset.read_bytes())==sealed['sha256'] and dataset.stat().st_size==sealed['bytes']
    marker=ROOT/'.runtime/phase2/e15-lowmemory-holdout40-consumed.json'
    # Exclusive marker prevents tuning/repeated attempts against the sealed set.
    save(marker,dict(run=a.out.relative_to(ROOT).as_posix(),source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        gate=record(gate),quality_gate=record(quality),dataset_sha256=sealed['sha256'],policy='Once only; failures reported without tuning this candidate.'))
    labels=read(dataset);assert len(labels)==40 and len({q['question_id'] for q in labels})==40
    assert all(re.fullmatch('[A-Za-z0-9_-]+',q['question_id']) for q in labels)
    save(a.out/'metadata.json',dict(source_files=refs,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        hardware=snapshot(),dataset=record(dataset),gate=record(gate),quality_gate=record(quality),holdout_used=True,
        scope='One actual candidate run; no tuning. AI-authored/source-checked same-corpus holdout; human review pending.',
        thresholds=dict(full_answerable_ratio=.75,correct_refusal_ratio=1,technical_ratio=1,citation_support_minimum='75/123',max_seconds=60,min_available_GiB=1)))
    browser=None;page=None;sampler=Sampler(a.server_pid,a.out/'resources.jsonl',a.ui_pid,a.out/'events');rows=[];status='COMPLETED'
    try:
        profile=a.out/'chrome';log=(a.out/'chrome.log').open('wb')
        browser=subprocess.Popen(['C:/Program Files/Google/Chrome/Application/chrome.exe','--headless=new','--remote-debugging-port=0',
            '--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-sync','--disable-extensions',
            '--user-data-dir='+str(profile),'about:blank'],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);log.close()
        port=wait(lambda:(profile/'DevToolsActivePort').read_text('utf8').splitlines()[0],25,'Chrome port')
        page=ObservedPage(json.loads(get('http://127.0.0.1:'+port+'/json/new?about:blank','PUT')))
        page.request('Page.navigate',url='http://127.0.0.1:7867/');wait(page.ready,35,'resident frontend');time.sleep(2)
        for pos,q in enumerate(labels,1):
            before=snapshot();resident=models()
            if before['available_GiB']<3.25 or resident!=[]:
                status='HEADROOM_STOP';save(a.out/'admission-stop.json',dict(next_case=q['question_id'],before=before,loaded_models=resident));break
            r=None;reference=None;error=None;start=sampler.begin(q['question_id']);began=time.perf_counter()
            try:
                r,reference,_=call_worker(q['question'])
                validate_public(public_projection(r,ROOT/reference['path']),True)
            except Exception as exc:error=type(exc).__name__+': '+str(exc)
            row=dict(question_id=q['question_id'],question=q['question'],before=before,seconds=time.perf_counter()-began,result=r,
                private_trace=reference,error=error,resources=sampler.end(start))
            name=q['question_id']+'.json';save(a.out/name,row);rows.append(row)
            print(json.dumps(dict(done=pos,total=40,name=q['question_id'],status=r['status'] if r else None,selected=r['selected_ids'] if r else None,
                seconds=row['seconds'],available_min_GiB=row['resources']['available_min_GiB'],error=error),ensure_ascii=False),flush=True)
            if sampler.aborted:status='RESOURCE_STOP';break
        assert all(record(ROOT/n)==v for n,v in refs.items())
    except Exception:
        status='SCRIPT_ERROR';raise
    finally:
        if page:
            try:page.close()
            except Exception:pass
        if browser and browser.poll() is None:
            subprocess.run(['taskkill','/PID',str(browser.pid),'/T','/F'],capture_output=True);browser.wait(timeout=10)
        sampler.close();save(a.out/'completed.json',dict(status=status,observations=len(rows),
            hashes={r['question_id']+'.json':digest((a.out/(r['question_id']+'.json')).read_bytes()) for r in rows},holdout_used=True))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--server-pid',type=int,required=True);p.add_argument('--ui-pid',type=int,required=True);main(p.parse_args())
