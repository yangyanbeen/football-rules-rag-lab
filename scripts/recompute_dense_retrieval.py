"""Recompute Dense Retrieval B0 from saved public ranks and timing, offline."""
import argparse,json
from pathlib import Path
from eval_dataset import ROOT,write_json
from dense_retrieval_eval import replay

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    if output.exists() or not any(output.is_relative_to(ROOT/p) for p in ('reports','.tmp')) or output.suffix!='.json':
        raise ValueError('Use a new JSON output under reports/ or ignored .tmp/')
    summary=replay(args.run_dir)
    write_json(output,summary)
    print(json.dumps({'status':'PASS_RECOMPUTED','split':summary['split'],'questions':summary['quality']['questions'],
      'metrics':summary['quality']['metrics'],'latency_samples':summary['latency']['samples']}))
    return 0

if __name__=='__main__':raise SystemExit(main())
