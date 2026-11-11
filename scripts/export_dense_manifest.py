"""Publish index hashes and stable IDs only; full corpus/vectors stay ignored."""
import json
from dense_index import DEFAULT_INDEX, DenseIndex
from eval_dataset import ROOT, digest, write_json


def main():
    with DenseIndex(DEFAULT_INDEX) as index:
        metadata = {**index.manifest,'manifest_distribution':'Public hashes/config only; all index artifacts remain local-only',
                    'local_index_path':'data/indexes/dense','local_manifest_sha256':digest((DEFAULT_INDEX/'index_manifest.json').read_bytes())}
        write_json(ROOT/'data/manifests/dense_index_manifest.json',metadata)
        write_json(ROOT/'data/manifests/dense_chunk_ids.json',index.mapping)
    print(json.dumps({'exported':'public metadata and ID/hash mapping','records':len(index.mapping),'full_corpus_or_vectors_uploaded':False}))


if __name__=='__main__': main()
