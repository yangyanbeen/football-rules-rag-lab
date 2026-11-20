"""Experimental pair verifier contracts. Contains no question labels or oracle data."""
import json
from e7_evidence_map import unique_object

LABELS=('direct_support','partial_support','refutation','unrelated')
SCHEMA={
    'type':'object',
    'properties':{
        'relation':{'type':'string','enum':list(LABELS)},
        'quotes':{'type':'array','minItems':0,'maxItems':3,
                  'items':{'type':'string','minLength':1,'maxLength':120}},
        'reason':{'type':'string','minLength':1,'maxLength':160}},
    'required':['relation','quotes','reason'],'additionalProperties':False}


def make_messages(requirement, paragraph, prompt):
    if not isinstance(requirement,str) or not requirement.strip() or len(requirement)>120:
        raise ValueError('Invalid frozen requirement')
    if not isinstance(paragraph,dict) or set(paragraph)!={'chunk_id','content_zh'}:
        raise ValueError('Invalid single paragraph input')
    if any(not isinstance(v,str) or not v.strip() for v in paragraph.values()):
        raise ValueError('Invalid single paragraph values')
    return [{'role':'system','content':prompt},
            {'role':'user','content':json.dumps(dict(requirement=requirement,evidence=paragraph),ensure_ascii=False,separators=(',',':'))}]


def parse_verdict(content, body):
    value=json.loads(content,object_pairs_hook=unique_object)
    if not isinstance(value,dict) or set(value)!={'relation','quotes','reason'}:
        raise ValueError('Invalid pair verdict fields')
    label,quotes,reason=(value[k] for k in ('relation','quotes','reason'))
    if not isinstance(label,str) or label not in LABELS:
        raise ValueError('Unknown relation label')
    if not isinstance(reason,str) or not reason.strip() or len(reason)>160:
        raise ValueError('Invalid verdict reason')
    if not isinstance(quotes,list) or len(quotes)>3:
        raise ValueError('Invalid quote array')
    if label=='unrelated' and quotes or label!='unrelated' and not quotes:
        raise ValueError('Quote count differs from relation contract')
    if any(not isinstance(q,str) or not q.strip() or len(q)>120 or q not in body for q in quotes):
        raise ValueError('Quote is not an exact substring of this paragraph')
    return {**value,'quotes':list(dict.fromkeys(quotes)),
            'quote_substrings_verified':True,'semantic_support_verified_by_program':False}
