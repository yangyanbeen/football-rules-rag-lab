"""Build one fixed BM25 template index in a new ignored directory."""
import argparse,json
from pathlib import Path
from bm25_index import ROOT, TEMPLATES, build

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--template',choices=TEMPLATES,required=True)
    p.add_argument('--output',type=Path);args=p.parse_args()
    result=build(args.output or ROOT/'data/indexes/bm25'/args.template,args.template)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
