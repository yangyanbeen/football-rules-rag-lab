"""Build 99 pinned corpus embeddings into a new local-only Chroma directory."""
import argparse
import json
from pathlib import Path
from dense_index import CONFIG, DEFAULT_INDEX, build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=DEFAULT_INDEX)
    parser.add_argument('--config',type=Path,default=CONFIG)
    args = parser.parse_args()
    result = build(args.output,args.config)
    print(json.dumps({k:result[k] for k in ('state','records','dimensions','vector_fingerprint','timing')},ensure_ascii=False))


if __name__ == '__main__': main()
