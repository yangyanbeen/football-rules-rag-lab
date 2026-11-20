"""Lightweight classification only. No source labels or answer references."""
import json
import time
from e7_evidence_map import unique_object
from e8_pair_verifier import LABELS

SCHEMA={'type':'object','properties':{'relation':{'type':'string','enum':list(LABELS)}},
        'required':['relation'],'additionalProperties':False}

def messages_for(payload,prompt):
    if not isinstance(payload,dict) or set(payload)!={'requirement','evidence'}:
        raise ValueError('Unexpected model input fields')
    evidence=payload['evidence']
    if not isinstance(evidence,dict) or set(evidence)!={'chunk_id','content_zh'}:
        raise ValueError('Expected one complete candidate paragraph')
    if any(not isinstance(v,str) or not v.strip() for v in (payload['requirement'],evidence['chunk_id'],evidence['content_zh'])):
        raise ValueError('Invalid pair input')
    # Match E8 user-message field order exactly despite canonical frozen JSON.
    body=dict(requirement=payload['requirement'],evidence={k:evidence[k] for k in ('chunk_id','content_zh')})
    return [{'role':'system','content':prompt},{'role':'user','content':json.dumps(body,ensure_ascii=False,separators=(',',':'))}]

def parse_relation(content):
    value=json.loads(content,object_pairs_hook=unique_object)
    if not isinstance(value,dict) or set(value)!={'relation'} or not isinstance(value['relation'],str) or value['relation'] not in LABELS:
        raise ValueError('Expected one exact relation enum and no other fields')
    return value['relation']

def one_shot(chat,payload,prompt,generate_fn):
    messages=messages_for(payload,prompt);before=chat.requests;started=time.perf_counter()
    response=None;relation=None;error=None
    try:
        size=len(json.dumps(messages,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
        if size>6200:raise ValueError('Frozen pair exceeds message budget; never truncate')
        response=generate_fn(chat,messages,SCHEMA)
        relation=parse_relation(response['message']['content'])
    except (ValueError,TypeError,KeyError,OSError,RuntimeError,TimeoutError) as exc:
        error=type(exc).__name__+': '+str(exc)
        if hasattr(exc,'response'):response=exc.response
    calls=chat.requests-before;assert calls<=1
    return dict(messages=messages,schema=SCHEMA,response=response,relation=relation,error=error,
        status='accepted' if relation is not None else 'failed',model_calls=calls,retries=0,
        seconds=time.perf_counter()-started)
