"""Actual Task12 answer and judge requests; generation never opens evaluation labels."""
from __future__ import annotations
import json,os,re,time
from answer_eval_core import ROOT,BOUNDARY,REFUSAL,canonical,digest,config,parse_selection,render,parse_grade,normalized,write_new,record
from version_validity_policy import version_validity_query


STRICT_SELECTION_SUFFIX = """
严格证据复核（仅在实验开关开启时使用）：先在内部逐项核对问题要求的对象、数字、条件、否定、例外和多部分子问，再选择证据。每个必要要点都必须由当前已提供段落直接支持；只有同主题或间接相关不能算支持。选择能覆盖全部必要要点的最少段，避免加入不支持所问事实的段。准备拒答前，再检查所有已提供段落：只要证据直接支持所问要点，就不要以“资料不足”拒答；只有关键要点确实缺少证据、来源冲突或版本要求无法确认时才拒答。保持答案与选段一致。
"""


def selection_prompt(prompt):
    """Return the opt-in E19 instruction without changing the default prompt."""
    if os.environ.get('FOOTBALL_STRICT_SELECTION') == '1':
        return prompt + STRICT_SELECTION_SUFFIX
    return prompt


def pack(question,evidence,cfg,prompt):
    selected=[]
    def messages(rows):
        body=[{'chunk_id':r['chunk_id'],'law_number':r['law_number'],'content_zh':r['content_zh'],
               'needs_rule_review':r['needs_rule_review'],'review_notes':r['review_notes']} for r in rows]
        return [{'role':'system','content':prompt},{'role':'user','content':json.dumps({'question':question,'evidence':body},ensure_ascii=False)}]
    if len(canonical(messages([])))>cfg['input_utf8_byte_budget']:raise ValueError('Question cannot fit whole prompt')
    # The normal path examines only the configured window.  The opt-in E22
    # candidate preserves every segment selected by that pass, then scans the
    # existing Top10 only to fill unused segment/byte capacity.  It never
    # replaces or reorders an already packed segment, and remains off by
    # default so historical prompts stay byte-identical.
    consideration_window = cfg['max_context_chunks']
    if os.environ.get('FOOTBALL_PACKING_FILL_TOP10') == '1':
        consideration_window = max(consideration_window, 10)
    for r in evidence[:consideration_window]:
        if len(selected) >= cfg['max_context_chunks']:
            break
        if len(canonical(messages(selected+[r])))<=cfg['input_utf8_byte_budget']:selected.append(r)
    m=messages(selected)
    return selected,m,len(canonical(m))


def request_json(chat,messages,cfg,parser,schema):
    from answer_json_chat import generate
    attempts=[];last=None
    for i in range(cfg['max_generation_attempts']):
        current=messages if not i else messages+[{'role':'user','content':'上次输出格式无效。重新按规定只输出一个JSON对象，不加说明；不要改变原始证据。'}]
        if len(canonical(current))>cfg['input_utf8_byte_budget']:break
        a={'attempt':i+1,'messages':current,'format':schema,'response':None,'error':None,'prompt_eval_count':None,'eval_count':None,'done_reason':None};started=time.perf_counter()
        try:
            response=generate(chat,current,schema);a['response']=response
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
        from generation_decision import prompt_for as generation_prompt
        self.prompt=generation_prompt((ROOT/self.cfg['prompt_file']).read_text('utf-8'))
        self.chat.verify_model()

    def close(self):self.retriever.close()

    def answer(self,question,evidence_override=None):
        start=time.perf_counter();r={'question':question,'status':'refused','answer':REFUSAL+'\n'+BOUNDARY,'citations':[],
          'selected_ids':[],'offered_ids':[],'retrieved_ids':[],'retrieval':None,'context':[],'attempts':[],
          'refusal_reason':None,'error':None,'prompt_utf8_bytes':0,'timing':{'retrieval_seconds':0.,'generation_seconds':0.}}
        try:
            if not isinstance(question,str) or not question.strip() or len(question.encode())>1200:raise ValueError('Invalid or oversize query')
            version_decision=version_validity_query(question)
            if version_decision:
                r['version_decision']=version_decision
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
            from answer_json_chat import selection_schema
            selection,attempts,error=request_json(self.chat,messages,self.cfg,lambda s:parse_selection(s,r['offered_ids'],self.cfg),selection_schema(r['offered_ids'],self.cfg['max_selected_chunks']))
            r['attempts']=attempts;r['timing']['generation_seconds']=time.perf_counter()-begin
            if error:raise ValueError(error)
            from generation_decision import (decide as apply_generation_decision,
                                              run_selection_audit,
                                              choose_audited_selection,
                                              apply_anchor_guard)
            from answer_json_chat import selection_schema
            audit = run_selection_audit(
                self.chat, messages, self.cfg,
                lambda s: parse_selection(s, r['offered_ids'], self.cfg),
                selection_schema(r['offered_ids'], self.cfg['max_selected_chunks']),
                request_json)
            if audit is not None:
                selection = choose_audited_selection(selection, audit)
                r['selection_audit'] = audit
            guarded = apply_anchor_guard(question, selection, context)
            selection = guarded['selection']
            if guarded['trace']['enabled']:
                r['selection_anchor_guard'] = guarded['trace']
            decision=apply_generation_decision(question,selection,context,messages)
            r['generation_decision']=decision['trace']
            recovery=decision['recovery']
            if recovery is not None:
                r['fact_recovery']=recovery
                if recovery['applied']:
                    selected=recovery['selected_ids'];answer,cites=render(selected,{v['chunk_id']:v for v in context})
                    r.update(status='answered',answer=answer,citations=cites,selected_ids=selected)
                    return r
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
    mode='AI_semantic_judge'
    if p['status']=='refused':
        # No displayed rule assertions can cover an answer point. This is a
        # deterministic scoring rule, not an invented model/human judgment.
        mode='deterministic_refusal';messages=[];attempts=[];error=None
        value={'points':[False]*len(q['expected_answer_points']),'conditions':[False]*len(q['required_conditions']),
               'citations':[],'reason':'实际受控拒答没有展示规则要点、条件或引用，覆盖项按固定口径计false。'}
    elif len(canonical(messages))>cfg['input_utf8_byte_budget']:
        value=None;attempts=[];error='Judge prompt exceeds budget; no truncation or invented grade'
    else:
        from answer_json_chat import grade_schema
        value,attempts,error=request_json(chat,messages,cfg,lambda s:parse_grade(s,q,p),grade_schema(q,p))
    if value is None:value={'points':[False]*len(q['expected_answer_points']),'conditions':[False]*len(q['required_conditions']),
                           'citations':[False]*len(p['citations']),'reason':'自动评分失败；不虚构正面得分，需人工复核。'}
    write_new(path,{'question_id':q['question_id'],'mode':mode,'messages':messages,'attempts':attempts,'grade':value,'error':error})
    quotes='\n'.join(v['content_zh'] for v in private_result['context'] if v['chunk_id'] in p['selected_ids'])
    return {'question_id':q['question_id'],'judgment_kind':'AI_not_human','grade':value,'error':error,'trace':record(path),
            'literal_points':[normalized(x) in normalized(quotes) for x in q['expected_answer_points']],
            'literal_conditions':[normalized(x) in normalized(quotes) for x in q['required_conditions']]}

