"""Verify/download pinned public BGE files without changing application packages."""
import argparse,json,time,urllib.request
from pathlib import Path
from eval_dataset import ROOT
from reranker_eval import config
from bge_reranker import HOME,file_sha


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--download',action='store_true');a=p.parse_args();cfg=config()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for name,identity in cfg['files'].items():
        dest=HOME/name
        if not dest.exists():
            if not a.download:raise FileNotFoundError('Missing pinned model file: '+name+'; use --download explicitly')
            dest.parent.mkdir(parents=True,exist_ok=True)
            if name in ('onnx/model.onnx','tokenizer.json'):
                url='https://hf-mirror.com/BAAI/bge-reranker-base/resolve/'+cfg['revision']+'/'+name
            else:
                url='https://www.modelscope.cn/api/v1/models/BAAI/bge-reranker-base/repo?Revision=313e6ba57eab108a5b2e9e3c6810840755528349&FilePath='+name
            partial=dest.with_name(dest.name+'.partial')
            # Never silently reuse partial bytes or overwrite an existing file.
            with partial.open('xb') as f,opener.open(url,timeout=60) as response:
                size=0;last=time.monotonic()
                for block in iter(lambda:response.read(1024*1024),b''):
                    f.write(block);size+=len(block)
                    if size>identity['size_bytes']:raise ValueError('Download exceeds pinned size')
                    if time.monotonic()-last>=15:print(json.dumps({'file':name,'downloaded':size}),flush=True);last=time.monotonic()
            if partial.stat().st_size!=identity['size_bytes'] or file_sha(partial)!=identity['sha256']:raise ValueError('Downloaded file SHA/size mismatch: '+name)
            if dest.exists():raise FileExistsError('Another process installed '+name)
            partial.rename(dest)
        if dest.stat().st_size!=identity['size_bytes'] or file_sha(dest)!=identity['sha256']:raise ValueError('Existing model file differs: '+name)
        print(json.dumps({'status':'VERIFIED','file':name,**identity}),flush=True)
    print(json.dumps({'status':'PASS','revision':cfg['revision'],'package_changes':0}))


if __name__=='__main__':main()
