"""Same frozen frontend schedule; both release, only B defers construction."""
import argparse,json,os
from pathlib import Path
import e15_special

def main(a):
    assert os.environ.get('FOOTBALL_E15_MODE')=='jit'
    e15_special.save(a.out/'comparison.json',dict(control='E13+E14+post-rerank release',candidate='same plus reranker construction at score time',
        changing_flag='FOOTBALL_JIT_RERANKER',post_rerank_release_enabled_in_both=True,holdout_used=False))
    e15_special.main(a)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--server-pid',type=int,required=True);p.add_argument('--ui-pid',type=int,required=True);main(p.parse_args())
