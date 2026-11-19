"""Offline E4 contracts and original-response replays; no model calls."""
import argparse,copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import canonical,config,parse_selection,now,record
from answer_json_chat import selection_schema
from answer_eval_engine import request_json
from answer_audit_v2 import validate_attempts
from rag_langgraph import Flow,Operations
from task13_audit import source_map
from verify_langgraph_controls import Fixture,NORMAL,QUESTION

def read(p):return json.loads(p.read_text('utf8'))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    cfg=config();checks={};details={}
    def check(name,test):
        try:test();checks[name]=True
        except Exception as exc:checks[name]=False;details[name]={'error':type(exc).__name__+': '+str(exc)}
    def assert_equal(a,b):assert a==b,(a,b)
    def payload(ids,**kw):return {'answerable':True,'chunk_ids':ids,'reason':None,**kw}
    def parsed(v,offered=('a','b','c','d')):return parse_selection(json.dumps(v),offered,cfg)
    def rejects(v,offered=('a','b','c','d')):
        try:parsed(v,offered)
        except (ValueError,TypeError):return
        raise AssertionError('Unsafe selection accepted')
    check('normal_ids_unchanged',lambda:assert_equal(parsed(payload(['b','a']))['chunk_ids'],['b','a']))
    check('legal_duplicates_stable_order',lambda:assert_equal(parsed(payload(['b','a','b']))['chunk_ids'],['b','a']))
    check('all_duplicates_one_id',lambda:assert_equal(parsed(payload(['a','a','a']))['chunk_ids'],['a']))
    check('raw_object_not_mutated',lambda:assert_equal((lambda v:(parsed(v),v['chunk_ids']))(payload(['a','a']))[1],['a','a']))
    for name,v in [('unknown_id',payload(['a','unknown','a'])),('empty_id',payload([''])),('whitespace_id',payload([' '])),('nonstring_id',payload([1])),('null_id',payload([None])),('bool_id',payload([True])),('list_type',payload('a')),('too_many_distinct',payload(['a','b','c','d'])),('too_many_raw_even_if_duplicates',payload(['a','a','a','a'])),('empty_answer',payload([])),('unknown_field',payload(['a'],extra=True)),('wrong_answerable_type',payload(['a'],answerable='true')),('non_null_answer_reason',payload(['a'],reason='insufficient_evidence')),('refusal_cannot_select',payload(['a','a'],answerable=False,reason='insufficient_evidence'))]:check(name,lambda v=v:rejects(v))
    check('retrieved_but_not_offered_rejected',lambda:rejects(payload(['b']),offered=['a']))
    check('no_trimming_of_source_ids',lambda:rejects(payload([' a '])))
    check('controlled_refusal_unchanged',lambda:assert_equal(parsed({'answerable':False,'chunk_ids':[],'reason':'source_conflict'}),{'answerable':False,'chunk_ids':[],'reason':'source_conflict'}))
    for name,text in [('malformed_json','{'),('not_object','[]'),('missing_field','{"answerable":true,"chunk_ids":["a"]}')]:
        def invalid(text=text):
            try:parse_selection(text,['a'],cfg)
            except ValueError:return
            raise AssertionError('Invalid structure accepted')
        check(name,invalid)
    dup={'answerable':True,'chunk_ids':['fixture-1','fixture-1'],'reason':None}
    def graph_test(name,ops,status,reason,calls):
        def run():
            r=Flow(ops).invoke(QUESTION);assert_equal((r['status'],r['reason'],r['chat_calls']),(status,reason,calls));assert len(r['attempts'])<=2;details[name]=r
        check(name,run)
    repeated=Fixture([dup,dup]);graph_test('two_duplicate_responses_stop_after_first',repeated,'answered',None,1)
    def queue_unused():assert len(repeated.queue)==1
    check('second_duplicate_response_not_requested',queue_unused)
    graph_test('unknown_ids_retries_stop_at_two',Fixture([payload(['unknown']),payload(['unknown']),NORMAL]),'failed','generation_failed',2)
    graph_test('source_mismatch_after_normalization_rejected',Fixture([dup],wrong_source=True),'failed','citation_invalid',1)
    tampered=Fixture([dup]);tampered.evidence['content_zh']='tampered'
    graph_test('body_hash_mismatch_before_generation_rejected',tampered,'failed','context_integrity_error',0)
    graph_test('source_conflict_still_refuses',Fixture([{'answerable':False,'chunk_ids':[],'reason':'source_conflict'}]),'refused','source_conflict',1)
    refs={x['question_id']:x for x in read(ROOT/'optimization/baseline/e8b0fd6/trace_manifest.local.json')}
    corpus={x['chunk_id']:x for x in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    class Chat:
        def __init__(self,responses):self.config=cfg;self.queue=copy.deepcopy(responses);self.requests=0
        def verify_model(self):pass
        def request(self,path,payload=None):assert path=='/api/chat';self.requests+=1;return self.queue.pop(0)
    class Replay(Operations):
        def retrieval(self,*a):return {}
        def fusion(self,*a):return [{'chunk_id':cid} for cid in self.ids]
        def rerank(self,*a):return [{'chunk_id':cid} for cid in self.ids]
        def expand(self,ids):return [corpus[cid] for cid in ids]
        @property
        def completed_embeddings(self):return None
    replay_specs=[]
    d016=read(Path(refs['D016']['private_path']))
    replay_specs.append(('D016',d016,d016['observations']['model_attempts'][0]['response'],['L13-05','L17-01']))
    d010=read(Path(refs['D010']['private_path']));d010b=read(ROOT/'.runtime/phase2/e1-dev-1795089536973/D010-B.json')
    replay_specs.append(('D010_B_first_response',d010,d010b['attempts'][0]['response'],['L08B-02']))
    for name,trace,response,expected in replay_specs:
        def replay(name=name,trace=trace,response=response,expected=expected):
            chat=Chat([response,response]);ops=Replay(None,chat,cfg,(ROOT/cfg['prompt_file']).read_text('utf8'),source_map());ops.ids=trace['result']['retrieved_ids']
            r=Flow(ops).invoke(trace['question']);assert_equal((r['status'],r['selected_ids'],r['chat_calls']),('answered',expected,1))
            audit=r['selection_audits'][0];assert_equal(audit['response'],response);assert_equal(audit['normalized_selection']['chunk_ids'],expected);assert chat.queue
            details[name+'_graph']=r
            # The audited worker already keeps response+parsed; validate that contract too.
            messages=trace['observations']['model_attempts'][0]['messages'];offered=trace['result']['offered_ids'];schema=selection_schema(offered,3)
            c=Chat([response,response]);value,attempts,error=request_json(c,messages,cfg,lambda s:parse_selection(s,offered,cfg),schema)
            assert_equal((error,c.requests,value['chunk_ids']),(None,1,expected));assert_equal(attempts[0]['response'],response)
            assert_equal(validate_attempts(attempts,messages,schema,lambda s:parse_selection(s,offered,cfg)),value)
            details[name+'_linear']={'attempts':attempts,'normalized':value,'offline_only':True}
        check(name+'_original_graph_and_linear_replay',replay)
    result=dict(created_at=now(),status='PASS' if all(checks.values()) else 'FAIL',passed=sum(checks.values()),total=len(checks),checks=checks,details=details,sources=[record(ROOT/'scripts/answer_eval_core.py'),record(ROOT/'scripts/rag_langgraph.py')],scope='Offline contracts and captured-response replay. Synthetic adapters and recorded responses; zero live model requests. Live verification is separate.')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open('x',encoding='utf8',newline='\n') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:result[k] for k in ('status','passed','total')},ensure_ascii=False))
    if not all(checks.values()):print(json.dumps({k:v for k,v in details.items() if not checks.get(k,True)},ensure_ascii=False));sys.exit(1)
if __name__=='__main__':main()
