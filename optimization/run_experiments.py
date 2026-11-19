"""E1 only: replay sealed graph contexts, varying only the system prompt."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import canonical, config, parse_selection
from answer_eval_engine import request_json
from answer_json_chat import generate
from citation_catalog_guard import safe_render
from rag_b0 import PinnedChat

def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(p):return json.loads(p.read_text('utf8'))
def now():return datetime.now(timezone.utc).isoformat()
def write(p,v):
    with p.open('x',encoding='utf8',newline='\n') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trace-manifest',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--split',choices=['dev','test'],default='dev')
    p.add_argument('--variants',nargs='+',choices=['A','B','C'],default=['A','B','C'])
    args=p.parse_args()
    if len(set(args.variants))!=len(args.variants):raise ValueError('Duplicate variants')
    cfg=config();base=ROOT/'optimization';freeze=read(base/'datasets/freeze_manifest.json')
    # Validate all sealed hashes without opening the holdout questions.
    for ref in freeze['files']:
        if sha((base/ref['path']).read_bytes())!=ref['sha256']:raise ValueError('Changed sealed dataset')
    dataset=base/'datasets'/('dev_40.json' if args.split=='dev' else 'regression_50.json')
    labels=read(dataset);traces={x['question_id']:x for x in read(args.trace_manifest)}
    original=(base/'baseline/e8b0fd6/prompt_A.txt').read_text('utf8')
    prompts={'A':original,**{k:(base/f'experiments/E1_selection_prompt/prompt_{k}.txt').read_text('utf8') for k in 'BC'}}
    assert all(len(prompts[k].encode())<=len(original.encode()) for k in args.variants)
    # This runner must not replace the live system prompt.
    assert (ROOT/cfg['prompt_file']).read_bytes()==(base/'baseline/e8b0fd6/prompt_A.txt').read_bytes()
    corpus={x['chunk_id']:x for x in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    if sha((ROOT/'data/processed/rag_chunks_zh.jsonl').read_bytes())!=freeze['corpus_sha256']:raise ValueError('Changed corpus')
    refs=[]
    prepared={}
    for q in labels:
        qid=q['question_id'];ref=traces[qid];raw=Path(ref['private_path']).read_bytes()
        if sha(raw)!=ref['sha256']:raise ValueError('Changed baseline trace '+qid)
        t=json.loads(raw);assert t['question']==q['question']
        ats=t['observations'].get('model_attempts',[])
        if ats:
            m=ats[0]['messages'];assert m[0]=={'role':'system','content':original}
            evidence=json.loads(m[1]['content'])['evidence']
            offered=[x['chunk_id'] for x in evidence]
            assert offered==t['result']['offered_ids']
            for x in evidence:assert x['content_zh']==corpus[x['chunk_id']]['content_zh']
            for k in args.variants:
                trial=copy.deepcopy(m);trial[0]['content']=prompts[k]
                assert len(canonical(trial))<=cfg['input_utf8_byte_budget']
        prepared[qid]=t;refs.append({'question_id':qid,'trace_sha256':ref['sha256'],'retrieved_ids':t['result']['retrieved_ids'],'offered_ids':t['result']['offered_ids']})
    args.out.mkdir(parents=True,exist_ok=False)
    source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tracked=subprocess.run(['git','diff','--exit-code','HEAD','--','optimization/run_experiments.py','optimization/experiments'],cwd=ROOT,capture_output=True)
    if tracked.returncode:raise ValueError('Commit experiment implementation first')
    write(args.out/'metadata.json',dict(started_at=now(),source_commit=source,baseline_commit=freeze['baseline_commit'],split=args.split,variants=args.variants,dataset_sha256=sha(dataset.read_bytes()),corpus_sha256=freeze['corpus_sha256'],prompt_hashes={k:sha(v.encode()) for k,v in prompts.items()},prompt_bytes={k:len(v.encode()) for k,v in prompts.items()},runner_sha256=sha(Path(__file__).read_bytes()),model=cfg['llm'],answer_policy=cfg,input_traces=refs,order='rotate by question index; one sequential request at a time',holdout_used=False,scope='Frozen actual context replay; latency is selection stage, not full graph or UI',grading='Independent post-run Codex source review; no candidate model self-grading; no human review claimed'))
    chat=PinnedChat(cfg);chat.verify_model()
    started=time.perf_counter()
    warm=generate(chat,[{'role':'system','content':'只输出一个JSON对象。'},{'role':'user','content':'返回ready为true。'}],{'type':'object','properties':{'ready':{'const':True}},'required':['ready'],'additionalProperties':False})
    write(args.out/'warmup.json',dict(response=warm,seconds=time.perf_counter()-started,excluded=True))
    count=0;start=time.perf_counter()
    for ix,q in enumerate(labels):
        qid=q['question_id'];trace=prepared[qid];base_result=trace['result']
        order=args.variants[ix%len(args.variants):]+args.variants[:ix%len(args.variants)]
        for variant in order:
            started=time.perf_counter();ats=trace['observations'].get('model_attempts',[])
            if ats:
                messages=copy.deepcopy(ats[0]['messages']);messages[0]['content']=prompts[variant]
                selection,attempts,error=request_json(chat,messages,cfg,lambda s:parse_selection(s,base_result['offered_ids'],cfg),ats[0]['schema'])
                if selection is None:
                    result=dict(status='failed',reason=None,selected_ids=[],answer='本次问答校验未完成，请重试。',citations=[],error=error)
                else:
                    ids=selection['chunk_ids'];answer,cites=safe_render(ids,corpus)
                    result=dict(status='answered' if selection['answerable'] else 'refused',reason=selection['reason'],selected_ids=ids,answer=answer,citations=cites,error=None)
            else:
                assert base_result['status']=='refused'
                messages=[];attempts=[]
                result={k:base_result[k] for k in ('status','reason','selected_ids','answer','citations')};result['error']=None
            seconds=time.perf_counter()-started
            item=dict(question_id=qid,variant=variant,question=q['question'],completed_at=now(),input_trace_sha256=traces[qid]['sha256'],retrieved_ids=base_result['retrieved_ids'],offered_ids=base_result['offered_ids'],messages=messages,prompt_utf8_bytes=len(canonical(messages)) if messages else 0,attempts=attempts,result=result,seconds=seconds,chat_calls=len(attempts),input_tokens=sum((a.get('response') or {}).get('prompt_eval_count',0) for a in attempts),output_tokens=sum((a.get('response') or {}).get('eval_count',0) for a in attempts),pre_generation_guard=not bool(ats))
            write(args.out/f'{qid}-{variant}.json',item);count+=1
            print(json.dumps(dict(done=count,total=len(labels)*len(args.variants),qid=qid,variant=variant,status=result['status'],ids=result['selected_ids'],seconds=round(seconds,3),input_tokens=item['input_tokens'],output_tokens=item['output_tokens']),ensure_ascii=False),flush=True)
    write(args.out/'completed.json',dict(finished_at=now(),seconds=time.perf_counter()-start,records=count,hashes={p.name:sha(p.read_bytes()) for p in sorted(args.out.glob('[DT]*-?.json'))}))
if __name__=='__main__':main()
