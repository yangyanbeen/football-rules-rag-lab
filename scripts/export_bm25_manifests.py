"""Export index manifests only; never export document tokens or postings."""
import json
from bm25_index import ROOT,TEMPLATES,Bm25Index,write_new

def main():
    manifests={t:Bm25Index(ROOT/'data/indexes/bm25'/t).manifest for t in TEMPLATES}
    output=ROOT/'data/manifests/bm25_indexes.json'
    write_new(output,{'version':'bm25-public-indexes-1.0','indexes':manifests,'postings_and_tokens_public':False})
    print(json.dumps({'status':'EXPORTED','indexes':3,'corpus_records_each':99,'postings_public':False}))

if __name__=='__main__':main()
