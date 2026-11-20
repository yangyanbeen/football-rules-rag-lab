"""P then S, identical sixteen frozen pairs, exactly one attempt per observation."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
os.environ['LANGSMITH_TRACING']='false';os.environ['LANGCHAIN_TRACING_V2']='false'
from answer_eval_core import canonical,read,record,config
from answer_json_chat import generate
from rag_b0 import PinnedChat
from rag_langgraph import CountingChat,Operations,Flow
from e9_classification_contract import SCHEMA,messages_for,one_shot

D=ROOT/'optimization/experiments/E9_classification'
FROZEN=ROOT/'.runtime/phase2/e9-frozen-samples/inputs.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    with p.open('xb') as f:f.write(canonical(v))
def verify(refs):assert all(record(ROOT/n)==v for n,v in refs.items())

def prepare(out):
    out.mkdir(parents=True,exist_ok=False);data=read(FROZEN);cfg=config();verify(data['source_files'])
    assert sha(D/'samples.json')==data['sample_review_sha256'] and sha(D/'plan.json')==data['plan_sha256']
    prompts={v:(D/f'prompt_{v}.txt').read_text('utf8') for v in 'PS'}
    previous=(ROOT/'optimization/experiments/E8_pair_verification/verifier_prompt.txt').read_text('utf8').splitlines()
    assert prompts['P'].splitlines()[:3]==previous[:3]
    assert prompts['P'].splitlines()[0]==prompts['S'].splitlines()[0]
    assert prompts['P'].splitlines()[-1]==prompts['S'].splitlines()[-1]
    assert len(data['inputs'])==16 and cfg['llm']==data['model']
    budgets=[]
    for item in data['inputs']:
        packets={v:messages_for(item['input'],prompts[v]) for v in 'PS'}
        assert packets['P'][1:]==packets['S'][1:]
        for variant,packet in packets.items():
            size=len(canonical(packet));assert size<=6200
            budgets.append(dict(sample_id=item['sample_id'],variant=variant,message_bytes=size))
    refs=dict(data['source_files'])
    for p in [FROZEN,Path(__file__),ROOT/'optimization/e9_classification_contract.py',ROOT/'optimization/verify_e9_classification.py',*D.glob('*.txt'),D/'samples.json',D/'plan.json']:
        refs[p.relative_to(ROOT).as_posix()]=record(p)
    write(out/'prepared.json',dict(inputs=data['inputs'],model=cfg['llm'],schema=SCHEMA,source_files=refs,
        prompts=prompts,freeze_sha256=sha(FROZEN),sample_review_sha256=sha(D/'samples.json'),plan_sha256=sha(D/'plan.json'),
        order=['P','S'],first_answer_limit_per_variant=16,retries=0,warmup_calls=0,holdout_used=False))
    write(out/'budget_preflight.json',dict(rows=budgets,overflow=[],schema_bytes=len(canonical(SCHEMA)),evidence_trimmed=False))
    print(json.dumps(dict(observations=32,retries=0,warmup=0,maximum_messages_bytes=max(v['message_bytes'] for v in budgets))))

def run(out,prepared):
    out.mkdir(parents=True,exist_ok=False);data=read(prepared);verify(data['source_files']);cfg=config()
    assert cfg['llm']==data['model'] and data['schema']==SCHEMA
    assert not subprocess.check_output(['git','diff','5986781','--','scripts','config'],cwd=ROOT)
    from run_langgraph_flow import runtime_identity
    from task13_audit import source_map
    chat=CountingChat(PinnedChat(cfg))
    write(out/'metadata.json',dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        prepared_sha256=sha(prepared),source_files=data['source_files'],model=cfg['llm'],environment=runtime_identity(),
        budget=dict(first_answer_per_variant=16,total_model_calls_max=32,retries=0,warmup=0),
        source_label_file_used_for_model_input=False,holdout_used=False,new_retrieval_calls=0))
    # Actual Graph route gate, with no retriever and no model warmup.
    q=read(ROOT/'.runtime/phase2/d036-gate-live90-final/D036.json')['question']
    before=chat.requests;ops=Operations(None,chat,cfg,(ROOT/cfg['prompt_file']).read_text('utf8'),source_map())
    gate=Flow(ops).invoke(q)
    assert gate['status']=='refused' and gate['chat_calls']==0 and not gate['retrieved_ids'] and chat.requests==before
    write(out/'D036_zero_call.json',gate)
    hashes={};observations=[]
    for variant in data['order']:
        for item in data['inputs']:
            result=one_shot(chat,item['input'],data['prompts'][variant],generate)
            assert result['retries']==0 and result['model_calls']<=1
            name=f"{variant}-{item['sample_id']}.json"
            write(out/name,dict(variant=variant,sample_id=item['sample_id'],**result));hashes[name]=sha(out/name)
            observations.append(dict(variant=variant,sample_id=item['sample_id'],model_calls=result['model_calls'],status=result['status']))
            print(json.dumps(dict(done=len(observations),total=32,variant=variant,sample_id=item['sample_id'],relation=result['relation'],status=result['status'],calls=result['model_calls'],seconds=round(result['seconds'],3)),ensure_ascii=False),flush=True)
        write(out/f'{variant}-completed.json',dict(observations=16,model_calls=sum(v['model_calls'] for v in observations if v['variant']==variant),retries=0))
    verify(data['source_files']);assert chat.requests==sum(v['model_calls'] for v in observations)<=32
    write(out/'completed.json',dict(observations=32,model_calls=chat.requests,retries=0,warmup_calls=0,hashes=hashes,inputs_unchanged=True))

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','run']);p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);a=p.parse_args()
    prepare(a.out) if a.mode=='prepare' else run(a.out,a.prepared)
if __name__=='__main__':main()
