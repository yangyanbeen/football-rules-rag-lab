"""Check that heavy construction is deferred, single-use and cleanup-safe."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import task13_engine as engine
import rag_b0
from task13_core import validate_result

def main():
    prior=os.environ.get('FOOTBALL_LAZY_RETRIEVAL');old=engine.retriever;chat=rag_b0.PinnedChat;calls=[];closed=[]
    class FakeChat:
        def __init__(self,cfg):pass
        def verify_model(self):pass
    class FakeRetriever:
        def close(self):closed.append(1)
    def build(cfg):calls.append(1);return FakeRetriever()
    engine.retriever=build;rag_b0.PinnedChat=FakeChat
    try:
        os.environ['FOOTBALL_LAZY_RETRIEVAL']='1'
        with engine.IntegratedEngine() as obj:
            assert not calls
            result=obj.answer('某联赛累计三张黄牌停赛几场？');validate_result(result,result['question'])
            assert result['status']=='refused' and not calls and not result['attempts'] and result['retrieval'] is None
            assert '赛事' in result['answer'] and '赛季' in result['answer']
            obj.ensure_retriever();obj.ensure_retriever();assert len(calls)==1
        assert closed==[1]
        os.environ['FOOTBALL_LAZY_RETRIEVAL']='0'
        with engine.IntegratedEngine() as obj:assert len(calls)==2
        assert len(closed)==2
        print('{"lazy_gate":true,"zero_calls":true,"construction_once":true,"cleanup":true,"default_eager":true,"real_model_calls":0}')
    finally:
        engine.retriever=old;rag_b0.PinnedChat=chat
        if prior is None:os.environ.pop('FOOTBALL_LAZY_RETRIEVAL',None)
        else:os.environ['FOOTBALL_LAZY_RETRIEVAL']=prior
if __name__=='__main__':main()
