"""Unchanged frontend/Worker; trusted local experiment file switches only release."""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--profile',required=True);a=p.parse_args()
    assert a.profile.startswith('e15-') and a.profile.replace('-','').isalnum()
    import task13_audit_client as client
    original=client.call_worker
    def call(*args,**kwargs):
        flag=json.loads((a.out/'release-flag.json').read_text('utf8'))['enabled'];assert type(flag) is bool
        if os.environ.get('FOOTBALL_E15_MODE')=='jit':
            os.environ['FOOTBALL_RELEASE_RERANKER']='1';os.environ['FOOTBALL_JIT_RERANKER']='1' if flag else '0'
        else:
            os.environ['FOOTBALL_RELEASE_RERANKER']='1' if flag else '0';os.environ['FOOTBALL_JIT_RERANKER']='0'
        return original(*args,**kwargs)
    client.call_worker=call
    import run_integrated_rag_audit as launch
    load=launch.load_config
    def config():
        c=load();c['ui']['app_data']='.runtime/task13/'+a.profile;return c
    launch.load_config=config;launch.main()
if __name__=='__main__':main()
