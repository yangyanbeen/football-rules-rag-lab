"""Conditional E10 fallback: original question only, no evidence or oracle text."""
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
os.environ['LANGSMITH_TRACING']='false';os.environ['LANGCHAIN_TRACING_V2']='false'
from answer_eval_core import read,record,config,canonical
from answer_json_chat import generate
from rag_b0 import PinnedChat
from rag_langgraph import CountingChat
from e7_evidence_map import unique_object

D=ROOT/'optimization/experiments/E10_decomposition'
SCHEMA={'type':'object','properties':{'questions':{'type':'array','minItems':1,'maxItems':5,'items':{
    'type':'object','properties':{'question':{'type':'string','minLength':1,'maxLength':160},
        'constraints':{'type':'array','minItems':0,'maxItems':6,'items':{'type':'string','minLength':1,'maxLength':80}}},
    'required':['question','constraints'],'additionalProperties':False}}},'required':['questions'],'additionalProperties':False}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    with p.open('xb') as f:f.write(canonical(v))
def parse(content):
    p=json.loads(content,object_pairs_hook=unique_object)
    if not isinstance(p,dict) or set(p)!={'questions'} or not isinstance(p['questions'],list) or not 1<=len(p['questions'])<=5:raise ValueError('Invalid decomposition schema')
    for q in p['questions']:
        if not isinstance(q,dict) or set(q)!={'question','constraints'}:raise ValueError('Invalid subquestion')
        if not isinstance(q['question'],str) or not q['question'].strip() or len(q['question'])>160:raise ValueError('Invalid question text')
        if not isinstance(q['constraints'],list) or len(q['constraints'])>6 or any(not isinstance(c,str) or not c.strip() or len(c)>80 for c in q['constraints']):raise ValueError('Invalid constraints')
    return p

def prepare(out):
    out.mkdir(parents=True,exist_ok=False);old=read(ROOT/'.runtime/phase2/e7-prepared-final/prepared.json')
    by={c['case_id']:c for c in old['cases']};cases=[dict(case_id=k,question=by[k]['question']) for k in ('T034-expanded','D017-native')]
    prompt=(D/'prompt.txt').read_text('utf8');refs=read(ROOT/'.runtime/phase2/e10-frozen/inputs.json')['source_files']
    for p in [Path(__file__),D/'prompt.txt',D/'plan.json']:refs[p.relative_to(ROOT).as_posix()]=record(p)
    write(out/'prepared.json',dict(cases=cases,prompt=prompt,schema=SCHEMA,model=config()['llm'],source_files=refs,holdout_used=False))
    print(json.dumps(dict(questions=2,repeats=3,maximum_first_answers=6,used_only_if_E10_candidate_unavailable_or_fails=True)))

def run(out,prepared):
    out.mkdir(parents=True,exist_ok=False);data=read(prepared);cfg=config();assert cfg['llm']==data['model']
    assert all(record(ROOT/n)==v for n,v in data['source_files'].items());chat=CountingChat(PinnedChat(cfg))
    from run_langgraph_flow import runtime_identity
    write(out/'metadata.json',dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        prepared_sha256=sha(prepared),model=cfg['llm'],environment=runtime_identity(),input_scope='Original question only; no chunks, frozen points, reviewed neutral subquestions, or answers.',first_answers_max=6,retries=0))
    hashes={}
    for repeat in range(1,4):
        for c in data['cases']:
            messages=[{'role':'system','content':data['prompt']},{'role':'user','content':json.dumps({'question':c['question']},ensure_ascii=False,separators=(',',':'))}]
            assert len(canonical(messages))<=6200
            start=time.perf_counter();before=chat.requests;response=None;parsed=None;error=None
            try:response=generate(chat,messages,SCHEMA);parsed=parse(response['message']['content'])
            except (ValueError,TypeError,KeyError,OSError,RuntimeError,TimeoutError) as exc:
                error=type(exc).__name__+': '+str(exc)
                if hasattr(exc,'response'):response=exc.response
            calls=chat.requests-before;assert calls<=1
            value=dict(**c,repeat=repeat,messages=messages,schema=SCHEMA,response=response,parsed=parsed,error=error,model_calls=calls,retries=0,seconds=time.perf_counter()-start)
            name=f"{c['case_id']}-r{repeat}.json";write(out/name,value);hashes[name]=sha(out/name)
            print(json.dumps(dict(case_id=c['case_id'],repeat=repeat,parsed=parsed,error=error),ensure_ascii=False),flush=True)
    assert all(record(ROOT/n)==v for n,v in data['source_files'].items())
    write(out/'completed.json',dict(records=6,model_calls=chat.requests,retries=0,hashes=hashes,holdout_used=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','run']);p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);a=p.parse_args()
    prepare(a.out) if a.mode=='prepare' else run(a.out,a.prepared)
