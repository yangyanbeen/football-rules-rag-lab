"""Use the unchanged default UI with an isolated E13 candidate chat database."""
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
def main():
    p=argparse.ArgumentParser();p.add_argument('--profile',required=True);a=p.parse_args()
    assert a.profile.startswith('e13-') and a.profile.replace('-','').isalnum()
    import run_integrated_rag_audit as launch
    load=launch.load_config
    def config():
        c=load();c['ui']['app_data']='.runtime/task13/'+a.profile;return c
    launch.load_config=config;launch.main()
if __name__=='__main__':main()
