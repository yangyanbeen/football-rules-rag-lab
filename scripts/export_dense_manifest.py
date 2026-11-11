"""Publish index hashes and stable IDs only; full corpus/vectors stay ignored."""
import json
import argparse
from pathlib import Path
from dense_index import DEFAULT_INDEX, DenseIndex
from eval_dataset import ROOT, digest, write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',type=Path,default=DEFAULT_INDEX)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'data/manifests')
    args=parser.parse_args()
    output=args.output_dir.resolve()
    if output!=ROOT/'data/manifests' and not any(output.is_relative_to(ROOT/name) for name in ('reports','.tmp')):
        raise ValueError('Use data/manifests or an isolated reports/.tmp directory')
    with DenseIndex(args.index) as index:
        metadata = {**index.manifest,'manifest_distribution':'Public hashes/config only; all index artifacts remain local-only',
                    'local_index_path':index.path.relative_to(ROOT).as_posix(),'local_manifest_sha256':digest((index.path/'index_manifest.json').read_bytes())}
        write_json(output/'dense_index_manifest.json',metadata)
        write_json(output/'dense_chunk_ids.json',index.mapping)
    print(json.dumps({'exported':'public metadata and ID/hash mapping','records':len(index.mapping),'full_corpus_or_vectors_uploaded':False}))


if __name__=='__main__': main()
