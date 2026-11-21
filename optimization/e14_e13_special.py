"""Original E13 schedule on the E14 lazy candidate; keep original E13 reports intact."""
import argparse,json
from pathlib import Path
import e13_live,e13_browser,score_e13_special
from e14_resources import Sampler

def main(a):
    root=e13_live.ROOT
    assert json.loads((root/'optimization/reports/E14_metrics.json').read_text('utf8'))['engineering_resource_gate']
    factory=lambda pid,path:Sampler(pid,path,a.ui_pid)
    e13_live.Sampler=factory;e13_browser.Sampler=factory
    e13_live.run(a.out/'worker',a.server_pid,'special')
    done=json.loads((a.out/'worker/completed.json').read_text('utf8'))
    if done['status']=='COMPLETED':
        (a.out/'fact-flag.json').write_bytes(b'{"enabled":true}')
        e13_browser.run(a.out/'browser',a.server_pid)
    score_e13_special.score(a.out/'worker',a.out/'browser/result.json',root/'optimization/reports/E14_E13_special_metrics.json')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--server-pid',type=int,required=True);p.add_argument('--ui-pid',type=int,required=True);main(p.parse_args())
