"""Install the hash-pinned official jieba source into an isolated local directory."""
from __future__ import annotations
import argparse, hashlib, io, json, tarfile, urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCY = ROOT/'config/bm25_dependency.json'
HOME = ROOT/'.runtime/bm25'


def sha(raw): return hashlib.sha256(raw).hexdigest()


def verify():
    lock=json.loads(DEPENDENCY.read_text('utf-8'))
    receipt=json.loads((HOME/'dependency_manifest.json').read_text('utf-8'))
    if receipt['dependency']!=lock or receipt['archive_sha256']!=lock['sha256']:
        raise ValueError('Dependency receipt differs from lock')
    known=receipt['files']
    actual={p.relative_to(HOME).as_posix():sha(p.read_bytes()) for p in (HOME/'site-packages').rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
    if actual!=known:raise ValueError('Isolated jieba files differ from verified archive')
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--verify-only',action='store_true');args=p.parse_args()
    if (HOME/'dependency_manifest.json').exists() or args.verify_only:
        receipt=verify();print(json.dumps({'status':'PASS','version':receipt['dependency']['version'],'files':len(receipt['files'])}));return
    lock=json.loads(DEPENDENCY.read_text('utf-8'))
    HOME.mkdir(parents=True,exist_ok=True)
    archive=HOME/'jieba-0.42.1.tar.gz'
    if archive.exists():raw=archive.read_bytes()
    else:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(lock['url'],timeout=90) as response:raw=response.read(lock['size_bytes']+1)
        if len(raw)!=lock['size_bytes'] or sha(raw)!=lock['sha256']:raise ValueError('Official download checksum mismatch')
        with archive.open('xb') as f:f.write(raw)
    if len(raw)!=lock['size_bytes'] or sha(raw)!=lock['sha256']:raise ValueError('Archive checksum mismatch')
    package=HOME/'site-packages';package.mkdir(exist_ok=True)
    files={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
        for member in tar.getmembers():
            parts=PurePosixPath(member.name).parts
            if not member.isfile() or len(parts)<2 or parts[0]!='jieba-0.42.1':continue
            relative=PurePosixPath(*parts[1:])
            if not (relative.parts[0]=='jieba' or str(relative)=='LICENSE'):continue
            if '..' in relative.parts or relative.is_absolute():raise ValueError('Unsafe archive path')
            target=(package/str(relative)).resolve()
            if not target.is_relative_to(package.resolve()):raise ValueError('Archive escapes dependency directory')
            data=tar.extractfile(member).read();target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists() and target.read_bytes()!=data:raise ValueError('Refusing to replace different dependency bytes')
            target.write_bytes(data);files[target.relative_to(HOME).as_posix()]=sha(data)
    receipt={'dependency':lock,'archive_sha256':sha(raw),'files':files,
             'default_dictionary_sha256':sha((package/'jieba/dict.txt').read_bytes())}
    with (HOME/'dependency_manifest.json').open('x',encoding='utf-8') as f:f.write(json.dumps(receipt,indent=2)+'\n')
    verify();print(json.dumps({'status':'INSTALLED','version':lock['version'],'files':len(files),'dictionary_sha256':receipt['default_dictionary_sha256']}))


if __name__=='__main__':main()
