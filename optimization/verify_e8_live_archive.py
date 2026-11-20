"""Audit E8 real requests and frozen-source binding, including failed attempts."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,record,canonical
from e8_pair_verifier import make_messages,parse_verdict,SCHEMA
from e8_live_pairs import REPAIR
from citation_catalog_guard import safe_render
from e7_evidence_map import parse_mapping

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    folder=ROOT/'.runtime/phase2/e8-live-minimal';prepared=ROOT/'.runtime/phase2/e8-minimal-prepared/prepared.json'
    prep=read(prepared);meta=read(folder/'metadata.json');done=read(folder/'completed.json')
    assert meta['source_commit'].startswith('1e74a93') and meta['prepared_sha256']==sha(prepared)
    assert all(sha(folder/n)==h for n,h in done['hashes'].items())
    assert all(record(ROOT/n)==v for n,v in prep['source_files'].items())
    assert not subprocess.check_output(['git','diff','5986781','--','scripts','config'],cwd=ROOT)
    prompt=(ROOT/'optimization/experiments/E8_pair_verification/verifier_prompt.txt').read_text('utf8')
    corpus={r['chunk_id']:r for r in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    max_msg=max_pin=max_pout=0;calls=attempts=valid=invalid=0;by={}
    for plan in prep['pairs']:
        path=folder/(plan['pair_id']+'.json');t=read(path);cid=plan['paragraph']['chunk_id']
        assert plan['paragraph']['content_zh']==corpus[cid]['content_zh']
        assert t['body_sha256']==corpus[cid]['content_zh_sha256']
        assert t['requirement']==plan['requirement'] and t['paragraph']==plan['paragraph']
        base=make_messages(plan['requirement'],plan['paragraph'],prompt)
        for at in t['attempts']:
            assert at['messages']==(base if at['attempt']==1 else [*base,REPAIR]) and at['schema']==SCHEMA
            payload=json.loads(at['messages'][1]['content'])
            assert set(payload)=={'requirement','evidence'} and set(payload['evidence'])=={'chunk_id','content_zh'}
            response=at['response'];assert response['done_reason']=='stop'
            max_msg=max(max_msg,len(canonical(at['messages'])))
            max_pin=max(max_pin,response['prompt_eval_count']);max_pout=max(max_pout,response['eval_count'])
            assert len(canonical(at['messages']))<=6200 and response['prompt_eval_count']+response['eval_count']+512<8192
            try:parsed=parse_verdict(response['message']['content'],plan['paragraph']['content_zh'])
            except (ValueError,TypeError):assert at['error'] is not None;invalid+=1
            else:assert parsed==at['verdict'] and at['error'] is None;valid+=1
            attempts+=1
        calls+=t['model_calls'];assert t['model_calls']==len(t['attempts'])<=2
        by[plan['pair_id']]=t
    e7done=read(ROOT/'.runtime/phase2/e7-pilot/completed.json')
    for c in prep['cases']:
        original=ROOT/c['source_trace'];assert sha(original)==c['source_sha256']==e7done['hashes'][original.name]
        assert c['requirements']==read(original)['observations']['model_attempts'][-1]['mapping_validation']['requirements']
        rs=[t for t in by.values() if t['case_id']==c['case_id'] and t['repeat']==c['repeat']]
        result=read(folder/f"result-{c['case_id']}-r{c['repeat']}.json")
        if any(t['verdict'] is None for t in rs):
            assert result['status']=='failed' and not result['selected_ids'] and result['requirements'] is None
        else:
            selection,audit=parse_mapping(json.dumps({'requirements':result['requirements']},ensure_ascii=False),c['offered_ids'],3)
            assert result['selected_ids']==selection['chunk_ids'] and result['selection_audit']==audit
            assert safe_render(result['selected_ids'],corpus)==(result['answer'],result['citations'])
    gate=read(folder/'D036_zero_call.json')
    assert gate['experimental_entry']['verification_calls']==0 and gate['experimental_entry']['retrieval_calls']==0
    assert gate['experimental_entry']['answer_calls']==0 and gate['original_graph']['chat_calls']==0 and not gate['original_graph']['retrieved_ids']
    assert done['pair_records']==60 and done['case_records']==4 and done['model_calls']==calls
    value=dict(single_requirement_paragraph_inputs_verified=60,frozen_requirement_rounds_verified=4,
        actual_verifier_calls=calls,attempts_verified=attempts,protocol_accepted_attempts=valid,protocol_rejected_attempts=invalid,
        max_message_bytes=max_msg,max_prompt_tokens=max_pin,max_output_tokens=max_pout,
        model_and_runtime_inputs_unchanged=True,actual_new_retrieval_calls=0,new_answer_synthesis_calls=0,
        D036_experimental_and_graph_zero_calls=True,holdout_used=False,full90_executed=False)
    out=ROOT/'.runtime/phase2/e8-minimal-scored/archive_verification.json';out.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(value,ensure_ascii=False))
if __name__=='__main__':main()
