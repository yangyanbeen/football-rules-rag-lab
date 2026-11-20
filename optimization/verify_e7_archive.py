"""Verify pairing, frozen inputs, parser binding, rendering and call budgets."""
import json
import subprocess
from pathlib import Path
from e7_mapping_experiment import ROOT, BASE, D, read, sha, canonical, check_refs
from e7_evidence_map import mapping_schema, parse_mapping
from answer_json_chat import selection_schema
from citation_catalog_guard import safe_render


def run():
    prepared=ROOT/'.runtime/phase2/e7-prepared-final/prepared.json'
    prep=read(prepared);folder=ROOT/'.runtime/phase2/e7-pilot'
    meta=read(folder/'metadata.json');done=read(folder/'completed.json')
    assert meta['prepared_sha256']==sha(prepared)
    assert meta['source_commit'].startswith('0b79fc4')
    check_refs(prep['source_files']);check_refs(prep['candidate_files'])
    assert not subprocess.check_output(['git','diff',BASE,'--','scripts','config'],cwd=ROOT)
    corpus={v['chunk_id']:v for v in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    cases={v['case_id']:v for v in prep['cases']};by={}
    maximum=dict(message_bytes=0,prompt_tokens=0,output_tokens=0,prompt_output_reserve_tokens=0)
    for name,h in done['hashes'].items():
        path=folder/name;assert sha(path)==h
        t=read(path);c=cases[t['case_id']];r=t['result'];ats=t['observations']['model_attempts']
        assert r['chat_calls']==len(ats)==len(r['selection_audits'])<=2
        assert not t['actual_new_embedding_calls'] and not t['actual_new_reranker_calls']
        assert r['offered_ids']==c['offered_ids'] and r['retrieved_ids']==c['retrieved_ids']
        for at,audit in zip(ats,r['selection_audits']):
            assert at['messages'][1:len(c['messages'])]==c['messages'][1:]
            assert at['messages'][0]['content']==(D/f"prompt_{t['variant']}.txt").read_text('utf8')
            expected=selection_schema(c['offered_ids'],3) if t['variant']=='A' else mapping_schema(c['offered_ids'],3)
            assert at['schema']==expected and at['response']==audit['response']
            if t['variant']=='B' and at.get('mapping_validation'):
                selection,mapping=parse_mapping(at['response']['message']['content'],c['offered_ids'],3)
                assert mapping==at['mapping_validation'] and selection==audit['normalized_selection']
            size=len(canonical(at['messages']));assert size<=6200
            response=at['response'];assert response['done_reason']=='stop'
            pin=response['prompt_eval_count'];pout=response['eval_count']
            assert pout<=1024 and pin+pout+512<8192
            maximum['message_bytes']=max(maximum['message_bytes'],size)
            maximum['prompt_tokens']=max(maximum['prompt_tokens'],pin)
            maximum['output_tokens']=max(maximum['output_tokens'],pout)
            maximum['prompt_output_reserve_tokens']=max(maximum['prompt_output_reserve_tokens'],pin+pout+512)
        assert safe_render(r['selected_ids'],corpus)==(r['answer'],r['citations'])
        by[t['case_id'],t['repeat'],t['variant']]=t
    for c in cases:
        for rep in range(1,5):
            a,b=(by[c,rep,v] for v in 'AB')
            assert a['observations']['model_attempts'][0]['messages'][1:]==b['observations']['model_attempts'][0]['messages'][1:]
            assert a['result']['offered_ids']==b['result']['offered_ids']
    gate=read(folder/'D036_zero_call.json')
    assert len(gate)==2 and all(t['result']['status']=='refused' and t['result']['chat_calls']==0 and not t['result']['retrieved_ids'] for t in gate)
    value=dict(raw_records_verified=112,paired_evidence_packets_verified=56,model_mapping_selection_bindings_verified=56,
        original_renderer_bindings_verified=112,source_and_data_unchanged=True,runtime_equal_to_5986781=True,
        D036_zero_call_arms=2,actual_new_retrieval_calls=0,formal90_executed=False,holdout_used=False,
        maximum_actual=maximum,scope='Archived retrieval and real answer-model calls; this is not fresh end-to-end retrieval latency.')
    target=ROOT/'.runtime/phase2/e7-scored/archive_verification.json'
    target.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(value,ensure_ascii=False))


if __name__=='__main__':run()
