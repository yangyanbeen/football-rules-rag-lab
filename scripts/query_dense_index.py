"""Query the pinned corpus index; the default JSON omits full source text."""
import argparse
import json
from pathlib import Path
from dense_index import CONFIG, DEFAULT_INDEX, DenseIndex


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',type=Path,default=DEFAULT_INDEX)
    parser.add_argument('--config',type=Path,default=CONFIG)
    parser.add_argument('--query',required=True)
    parser.add_argument('--top-k',type=int,default=5)
    parser.add_argument('--include-content',action='store_true',help='Local terminal only; do not publish corpus text')
    args = parser.parse_args()
    with DenseIndex(args.index,args.config) as index:
        result = index.query(args.query,args.top_k)
    if not args.include_content:
        for row in result['results']: row.pop('content_zh')
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__': main()
