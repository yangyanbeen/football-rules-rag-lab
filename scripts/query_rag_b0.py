"""Run the actual Dense-to-LLM B0 chain; full local traces require an explicit output path."""
import argparse
import json
from pathlib import Path
from eval_dataset import ROOT,write_json
from rag_b0 import RagB0Engine


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--query')
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--trace',type=Path)
    args=parser.parse_args()
    if args.trace and not args.trace.resolve().is_relative_to(ROOT/'.runtime'):
        raise ValueError('Keep complete answer/evidence traces under ignored .runtime/')
    if args.trace and args.trace.exists():raise ValueError('Do not overwrite an existing trace')
    engine=RagB0Engine()
    try:
        if args.check:
            engine.chat.verify_model()
            print(json.dumps({'status':'READY','records':len(engine.index.rows),'config_sha256':engine.config_sha256}))
            return
        if args.query is None:parser.error('Provide --query or --check')
        result=engine.answer(args.query)
    finally:engine.close()
    if args.trace:write_json(args.trace,result)
    print(json.dumps({'status':result['status'],'answer':result['answer'],
        'citations':result['citations'],'trace_id':result['trace_id'],'refusal_reason':result['refusal_reason'],
        'error':result.get('error'),'timing':result['timing']},ensure_ascii=False))


if __name__=='__main__':main()
