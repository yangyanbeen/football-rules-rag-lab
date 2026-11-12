"""Recompute saved BM25 metrics without jieba, corpus text or model/index runtime."""
import argparse,json
from pathlib import Path
from bm25_index import ROOT, write_new
from bm25_retrieval_eval import replay

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    output=a.output.resolve()
    if output.exists() or output.suffix!='.json' or not output.is_relative_to(ROOT/'reports'):raise ValueError('Use a new reports JSON')
    s=replay(a.run_dir);write_new(output,s)
    print(json.dumps({'status':'PASS','split':s['split'],'template':s['template'],'metrics':s['quality']['metrics']}))

if __name__=='__main__':main()
