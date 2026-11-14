"""Actual Task12 answer and judge requests; generation never opens evaluation labels."""
from __future__ import annotations
import json,re,time
from answer_eval_core import ROOT,BOUNDARY,REFUSAL,canonical,digest,config,parse_selection,render,parse_grade,normalized,write_new,record


def pack(question,evidence,cfg,prompt):
    selected=[]
    def messages(rows):
        body=[{'chunk_id':r['chunk_id'],'law_number':r['law_number'],'content_zh':r['content_zh'],
               'source_revision_verified':r['source_revision_verified'],'needs_rule_review':r['needs_rule_review'],'review_notes':r['review_notes']} for r in rows]
        return [{'role':'system','content':prompt},{'role':'user','content':json.dumps({'question':question,'evidence':body},ensure_ascii=False)}]
    if len(canonical(messages([])))>cfg['input_utf8_byte_budget']:raise ValueError('Question cannot fit whole prompt')
    for r in evidence[:cfg['max_context_chunks']]:
        if len(canonical(messages(selected+[r])))<=cfg['input_utf8_byte_budget']:selected.append(r)
    m=messages(selected)
    return selected,m,len(canonical(m))


def request_json(chat,messages,cfg,parser):
    attempts=[];last=None
    for i in range(cfg['max_generation_attempts']):
        current=messages if not i else messages+[{'role':'user','content':'上次输出格式无效。重新按规定只输出一个JSON对象，不加说明；不要改变原始证据。'}]
        if len(canonical(current))>cfg['input_utf8_byte_budget']:break
        a={'attempt':i+1,'messages':current,'response':None,'error':None,'prompt_eval_count':None,'eval_count':None,'done_reason':None};started=time.perf_counter()
        try:
            response=chat.generate(current);a['response']=response
            for k in ('prompt_eval_count','eval_count','done_reason'):a[k]=response[k]
            parsed=parser(response['message']['content']);a['parsed']=parsed
            return parsed,attempts+[a],None
        except (ValueError,KeyError,TypeError,OSError,RuntimeError,TimeoutError) as exc:
            a['error']=type(exc).__name__+': '+str(exc);last=a['error']
            if hasattr(exc,'response'):a['response']=exc.response
        finally:a['seconds']=time.perf_counter()-started
        attempts.append(a)
    return None,attempts,last or 'No repair fits prompt budget'


class AnswerEngine:
    def __init__(self):
        from reranker_live import RerankerRetriever
        from reranker_eval import config as reranker_config
        from rag_b0 import PinnedChat
        self.cfg=config();self.retriever=RerankerRetriever(reranker_config());self.chat=PinnedChat(self.cfg)
        self.prompt=(ROOT/self.cfg['prompt_file']).read_text('utf-8')
        self.chat.verify_model()

    def close(self):self.retriever.close()

    def answer(self,question,evidence_override=None):
        start=time.perf_counter();r={'question':question,'status':'refused','answer':REFUSAL+'\n'+BOUNDARY,'citations':[],
          'selected_ids':[],'offered_ids':[],'retrieved_ids':[],'retrieval':None,'context':[],'attempts':[],
          'refusal_reason':None,'error':None,'prompt_utf8_bytes':0,'timing':{'retrieval_seconds':0.,'generation_seconds':0.}}
        try:
            if not isinstance(question,str) or not question.strip() or len(question.encode())>1200:raise ValueError('Invalid or oversize query')
            if re.search(r'官方|现行|最新|IFAB',question,re.I) and re.search(r'赛季|20\d{2}|规则',question):
                r['refusal_reason']='version_unverified';return r
            if evidence_override is None:
                packet=self.retriever.query(question,self.cfg['retrieval_method']);r['retrieval']=packet
                evidence=[self.retriever.dense.by_id[v['chunk_id']] for v in packet['results']]
                r['timing']['retrieval_seconds']=packet['timing']['total_seconds']
            else:evidence=evidence_override
            r['retrieved_ids']=[v['chunk_id'] for v in evidence]
            context,messages,size=pack(question,evidence,self.cfg,self.prompt)
            r.update(context=context,offered_ids=[v['chunk_id'] for v in context],messages=messages,prompt_utf8_bytes=size)
            if not context:r['refusal_reason']='no_whole_evidence_within_budget';return r
            begin=time.perf_counter()
            selection,attempts,error=request_json(self.chat,messages,self.cfg,lambda s:parse_selection(s,r['offered_ids'],self.cfg))
            r['attempts']=attempts;r['timing']['generation_seconds']=time.perf_counter()-begin
            if error:raise ValueError(error)
            if selection['answerable']:
                selected=selection['chunk_ids'];answer,cites=render(selected,{v['chunk_id']:v for v in context})
                r.update(status='answered',answer=answer,citations=cites,selected_ids=selected)
            else:r['refusal_reason']=selection['reason']
        except (ValueError,KeyError,TypeError,OSError,RuntimeError,TimeoutError) as exc:
            r.update(error=type(exc).__name__+': '+str(exc),refusal_reason='runtime_or_validation_error')
        finally:r['timing']['total_seconds']=time.perf_counter()-start
        return r


def judge(q,p,private_result,chat,path):
    cfg=config();prompt=(ROOT/cfg['judge_prompt_file']).read_text('utf-8')
    body={'question':q['question'],'answerable':q['answerable'],'expected_answer_points':q['expected_answer_points'],
          'required_conditions':q['required_conditions'],'status':p['status'],'actual_answer':private_result['answer'],
          'citations':[{k:c[k] for k in ('chunk_id','law_number','source_url','source_revision_verified','needs_rule_review')}
                       for c in private_result['citations']]}
    messages=[{'role':'system','content':prompt},{'role':'user','content':json.dumps(body,ensure_ascii=False)}]
    if len(canonical(messages))>cfg['input_utf8_byte_budget']:
        value=None;attempts=[];error='Judge prompt exceeds budget; no truncation or invented grade'
    else:value,attempts,error=request_json(chat,messages,cfg,lambda s:parse_grade(s,q,p))
    if value is None:value={'points':[False]*len(q['expected_answer_points']),'conditions':[False]*len(q['required_conditions']),
                           'citations':[False]*len(p['citations']),'reason':'自动评分失败；不虚构正面得分，需人工复核。'}
    write_new(path,{'question_id':q['question_id'],'messages':messages,'attempts':attempts,'grade':value,'error':error})
    quotes='\n'.join(v['content_zh'] for v in private_result['context'] if v['chunk_id'] in p['selected_ids'])
    return {'question_id':q['question_id'],'judgment_kind':'AI_not_human','grade':value,'error':error,'trace':record(path),
            'literal_points':[normalized(x) in normalized(quotes) for x in q['expected_answer_points']],
            'literal_conditions':[normalized(x) in normalized(quotes) for x in q['required_conditions']]}
