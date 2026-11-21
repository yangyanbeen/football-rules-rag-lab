"""Keep the real linear-worker retrieval dependencies resident during E11."""
import argparse,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from task13_engine import IntegratedEngine

def main():
    p=argparse.ArgumentParser();p.add_argument('--ready',type=Path,required=True);p.add_argument('--stop',type=Path,required=True);a=p.parse_args()
    started=time.perf_counter()
    with IntegratedEngine() as engine:
        assert engine.retriever is not None
        packet=dict(pid=os.getpid(),status='READY',seconds=time.perf_counter()-started,
            role='Actual IntegratedEngine with dense index, BM25, tokenizer and CPU ONNX reranker resident; no retrieval query or answer call.',
            indexes=engine.before,answer_model=engine.answer_cfg['llm'])
        with a.ready.open('x',encoding='utf8') as f:json.dump(packet,f,ensure_ascii=False)
        print(json.dumps(dict(status='READY',pid=os.getpid()),ensure_ascii=False),flush=True)
        while not a.stop.exists():time.sleep(.5)
    print('E11 resident worker closed; original index snapshots preserved.',flush=True)

if __name__=='__main__':main()
