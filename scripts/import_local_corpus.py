"""Copy hash-locked local corpus files into this checkout, without overwriting."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    if source == ROOT:
        raise ValueError('Choose the original local project, not this checkout')
    manifest = json.loads((ROOT/'data/manifests/local_data_files.json').read_text('utf-8'))
    planned, seen = [], set()
    for item in manifest['files']:
        rel = Path(item['path'])
        if rel.is_absolute() or '..' in rel.parts or rel.as_posix() in seen:
            raise ValueError('Unsafe or duplicate path in data inventory')
        if rel.parts[:2] not in [('data','raw'),('data','processed')]:
            raise ValueError('Inventory may only contain raw and processed data')
        seen.add(rel.as_posix())
        src, dst = (source/rel).resolve(strict=True), (ROOT/rel).resolve()
        if not src.is_relative_to(source) or not dst.is_relative_to(ROOT):
            raise ValueError('A data path escapes its project root')
        if not src.is_file() or src.stat().st_size != item['size_bytes'] or digest(src) != item['sha256']:
            raise ValueError(f'Original data does not match the locked corpus: {rel}')
        if dst.exists() and (not dst.is_file() or digest(dst) != item['sha256']):
            raise ValueError(f'Refusing to overwrite different local data: {rel}')
        planned.append((src,dst,item))
    copied = 0
    for src,dst,item in planned:
        if not dst.exists():
            dst.parent.mkdir(parents=True,exist_ok=True)
            # Exclusive create preserves an existing destination even on a race.
            with src.open('rb') as original, dst.open('xb') as out:
                shutil.copyfileobj(original,out)
            copied += 1
        if digest(dst) != item['sha256']:
            raise ValueError(f'Copied data hash mismatch: {dst.relative_to(ROOT)}')
    print(json.dumps({'status':'IMPORTED','files':len(planned),'copied':copied,
                      'source_modified':False,'full_text_tracked_by_git':False}))

if __name__ == '__main__':
    main()
