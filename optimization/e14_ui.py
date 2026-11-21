"""Normal UI; trusted experiment control toggles only the E13 environment flag."""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--profile',required=True);a=p.parse_args()
    assert a.profile.startswith('e14-') and a.profile.replace('-','').isalnum()
    import task13_audit_client as client
    original=client.call_worker
    def call(*args,**kwargs):
        flag=json.loads((a.out/'fact-flag.json').read_text('utf8'))['enabled'];assert type(flag) is bool
        os.environ['FOOTBALL_SOURCE_FACTS']='1' if flag else '0';return original(*args,**kwargs)
    client.call_worker=call
    import run_integrated_rag_audit as launch
    load=launch.load_config
    def config():
        c=load();c['ui']['app_data']='.runtime/task13/'+a.profile;return c
    launch.load_config=config;launch.main()
if __name__=='__main__':main()
