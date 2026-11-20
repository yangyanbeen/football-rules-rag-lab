"""Verify pre-prompt freeze, identical evidence, single calls and model budgets."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,record,canonical
from e9_classification_contract import SCHEMA,messages_for,parse_relation

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    d=ROOT/'optimization/experiments/E9_classification';folder=ROOT/'.runtime/phase2/e9-classification-live'
    prepared=ROOT/'.runtime/phase2/e9-classification-prepared/prepared.json';prep=read(prepared)
    meta=read(folder/'metadata.json');done=read(folder/'completed.json');sample=read(d/'samples.json')
    assert meta['source_commit'].startswith('de0a5a9') and meta['prepared_sha256']==sha(prepared)
    for path in ('samples.json','plan.json'):
        blob=subprocess.check_output(['git','show','55817a2:optimization/experiments/E9_classification/'+path],cwd=ROOT)
        assert blob==(d/path).read_bytes()
    assert not subprocess.check_output(['git','ls-tree','--name-only','55817a2','optimization/experiments/E9_classification/prompt_P.txt','optimization/experiments/E9_classification/prompt_S.txt'],cwd=ROOT)
    assert all(record(ROOT/n)==v for n,v in prep['source_files'].items())
    assert not subprocess.check_output(['git','diff','5986781','--','scripts','config'],cwd=ROOT)
    assert all(sha(folder/n)==h for n,h in done['hashes'].items())
    labels={s['sample_id']:s for s in sample['samples']};calls=0;max_msg=max_pin=max_pout=0
    corpus={r['chunk_id']:r for r in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    for item in prep['inputs']:
        sid=item['sample_id'];s=labels[sid];p=item['input'];evidence=p['evidence']
        assert hashlib.sha256(canonical(p)).hexdigest()==s['payload_sha256']
        assert evidence['content_zh']==corpus[s['chunk_id']]['content_zh']
        assert hashlib.sha256(evidence['content_zh'].encode()).hexdigest()==s['body_sha256']
        variants=[]
        for variant in 'PS':
            t=read(folder/f'{variant}-{sid}.json');variants.append(t)
            assert t['messages']==messages_for(p,prep['prompts'][variant]) and t['schema']==SCHEMA
            assert t['model_calls']==1 and t['retries']==0
            assert set(json.loads(t['messages'][1]['content']))=={'requirement','evidence'}
            assert parse_relation(t['response']['message']['content'])==t['relation']
            assert t['response']['done_reason']=='stop'
            calls+=t['model_calls'];max_msg=max(max_msg,len(canonical(t['messages'])))
            max_pin=max(max_pin,t['response']['prompt_eval_count']);max_pout=max(max_pout,t['response']['eval_count'])
            assert len(canonical(t['messages']))<=6200
            assert t['response']['prompt_eval_count']+t['response']['eval_count']+512<8192
        assert variants[0]['messages'][1:]==variants[1]['messages'][1:]
        assert variants[0]['schema']==variants[1]['schema']
    assert calls==done['model_calls']==done['observations']==32 and not done['retries'] and not done['warmup_calls']
    gate=read(folder/'D036_zero_call.json');assert gate['status']=='refused' and not gate['retrieved_ids'] and gate['chat_calls']==0
    value=dict(input_freeze_precedes_prompt_commit=True,frozen_pairs_verified=16,paired_inputs_and_schema_verified=16,
        first_answer_records_verified=32,actual_model_calls=32,retries=0,warmup=0,
        max_message_bytes=max_msg,max_input_tokens=max_pin,max_output_tokens=max_pout,
        model_and_runtime_unchanged=True,D036_zero_calls=True,holdout_used=False,full90_executed=False)
    out=ROOT/'.runtime/phase2/e9-scored/archive_verification.json';out.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(value,ensure_ascii=False))
if __name__=='__main__':main()
