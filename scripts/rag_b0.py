"""Dense retrieval -> whole evidence blocks -> pinned local LLM -> checked citations."""
from __future__ import annotations

import html
import json
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from dense_index import DenseIndex
from eval_dataset import ROOT, canonical, digest

CONFIG=ROOT/'config/rag_b0.json'
REFUSAL='现有资料不足以可靠回答这个问题，无法据此给出确定结论。'
BOUNDARY='资料为固定Wikipedia快照的AI中文整理，非官方赛季规则，未经过裁判专家审校。'


def load_config(path=CONFIG):
    config=json.loads(Path(path).read_text('utf-8'))
    if (config['query_normalization']!='NFKC then trim and collapse whitespace'
            or type(config['top_k']) is not int or not 1<=config['top_k']<=99
            or config['llm']['num_gpu']!=0 or config['llm']['temperature']!=0
            or config['ui']['host']!='127.0.0.1' or config['ui']['share'] is not False
            or type(config['max_context_chunks']) is not int or config['max_context_chunks']!=1
            or type(config['max_generation_attempts']) is not int or not 1<=config['max_generation_attempts']<=2
            or config['input_utf8_byte_budget']+config['chat_template_token_reserve']+config['llm']['num_predict']>config['llm']['num_ctx']):
        raise ValueError('Unsupported B0 configuration or unsafe context budget')
    for name in ('dense_config','dense_index','prompt_file'):
        path=(ROOT/config[name]).resolve()
        if not path.is_relative_to(ROOT):raise ValueError('B0 paths must remain inside this checkout')
    return config


def normalize_query(text, config):
    if not isinstance(text,str):raise ValueError('问题必须是文本。')
    value=' '.join(unicodedata.normalize('NFKC',text).split())
    if not value:raise ValueError('请输入完整问题。')
    if len(value.encode('utf-8'))>config['max_query_utf8_bytes']:raise ValueError('问题过长，请拆成较短问题。')
    return value


def passages_for(match, config):
    # B0 provides one complete chunk. A single evidence address prevents the
    # small local model from confusing paragraph IDs within that same chunk.
    return [{'passage_id':match['chunk_id']+':full','text':match['content_zh']}]


def response_schema(matches, config):
    statement={'type':'object','additionalProperties':False,'properties':{
                'text':{'type':'string','maxLength':config['max_statement_characters']},'passage_id':{'type':'string','enum':
                    [p['passage_id'] for m in matches for p in passages_for(m,config)]}},
                'required':['text','passage_id']}
    # Encode the two valid states in the grammar, rather than allowing a false
    # answerable flag to be combined with asserted statements or a null reason.
    return {'anyOf':[
        {'type':'object','additionalProperties':False,'properties':{
            'answerable':{'const':True},'statements':{'type':'array','minItems':1,
                'maxItems':config['max_statements'],'items':statement},'refusal_reason':{'type':'null'}},
         'required':['answerable','statements','refusal_reason']},
        {'type':'object','additionalProperties':False,'properties':{
            'answerable':{'const':False},'statements':{'type':'array','maxItems':0},
            'refusal_reason':{'type':'string','minLength':1}},
         'required':['answerable','statements','refusal_reason']}]}


def evidence_row(match, config):
    meta=match['metadata']
    return {'title':meta['title_zh'],'content_zh':match['content_zh'],
            'needs_rule_review':meta['needs_rule_review'],'review_notes':meta['review_notes']}


def pack_context(query, matches, config, prompt):
    def messages_for(rows):
        return [{'role':'system','content':prompt},{'role':'user','content':
            '参考资料（JSON数据）：\n'+json.dumps({'evidence':[evidence_row(m,config) for m in rows]},ensure_ascii=False)+
            '\n\n当前问题：'+query+'\n请核对正文，按ANSWER:或REFUSE:格式简短回答。'}]
    selected=[]
    for match in matches:
        if len(selected)>=config['max_context_chunks']:break
        candidate=selected+[match]
        schema=response_schema(candidate,config)
        messages=messages_for(candidate)
        # Conservative budget also includes the application contract; only
        # messages are sent to the model, without a constrained JSON grammar.
        size=len(canonical({'messages':messages,'format':schema}))
        if size<=config['input_utf8_byte_budget']:selected=candidate
    schema=response_schema(selected,config)
    messages=messages_for(selected)
    return selected,messages,schema,len(canonical({'messages':messages,'format':schema}))


def parse_generated_text(content, offered, config):
    if not isinstance(content,str):raise ValueError('Model content must be text')
    value=content.strip()
    if value.startswith('REFUSE:'):
        return {'answerable':False,'statements':[],'refusal_reason':value[len('REFUSE:'):].strip()}
    if not value.startswith('ANSWER:') or len(offered)!=1:raise ValueError('Expected ANSWER:/REFUSE: and one evidence block')
    return {'answerable':True,'statements':[{'text':value[len('ANSWER:'):].strip(),
        'passage_id':passages_for(offered[0],config)[0]['passage_id']}],'refusal_reason':None}


def validate_payload(payload, offered, config):
    if (not isinstance(payload,dict) or set(payload)!={'answerable','statements','refusal_reason'}
            or type(payload['answerable']) is not bool or not isinstance(payload['statements'],list)):
        raise ValueError('Invalid answer schema')
    statements=payload['statements']
    if not payload['answerable']:
        if statements or not isinstance(payload['refusal_reason'],str) or not payload['refusal_reason'].strip():
            raise ValueError('Refusal must have a reason and no asserted evidence')
        if re.search(r'https?://|<[^>]+>',payload['refusal_reason']):raise ValueError('Invalid refusal content')
        return []
    if payload['refusal_reason'] is not None or not 1<=len(statements)<=config['max_statements']:
        raise ValueError('Answer must have statements and no refusal reason')
    by_id={p['passage_id']:(m,p) for m in offered for p in passages_for(m,config)}
    resolved=[]
    for statement in statements:
        if not isinstance(statement,dict) or set(statement)!={'text','passage_id'}:
            raise ValueError('Invalid answer statement')
        text,pid=(statement[k] for k in ('text','passage_id'))
        if not isinstance(text,str) or not isinstance(pid,str) or not 4<=len(text.strip())<=config['max_statement_characters'] or pid not in by_id:
            raise ValueError('Unknown/unoffered evidence passage')
        if re.search(r'https?://|<[^>]+>|\[[^\]]+\]|L\d{2}-\d{2}',text):raise ValueError('Model must not invent source links or citation markup')
        if text.strip()[-1] not in '。！？.!?；;':raise ValueError('Answer ended in an incomplete sentence')
        sentences=[s.strip() for s in re.split(r'[。！？!?；;]',text) if len(s.strip())>=8]
        if len(sentences)!=len(set(sentences)):raise ValueError('Answer contains repeated sentences')
        match,passage=by_id[pid]
        # Numeric facts must occur in the particular cited paragraph. This
        # catches cross-paragraph numeric mixing, not general entailment.
        numbers=lambda value:set(re.findall(r'\d+(?:\.\d+)?',unicodedata.normalize('NFKC',value)))
        if not numbers(text)<=numbers(passage['text']):raise ValueError('Numeric facts are absent from the cited paragraph')
        resolved.append({**statement,'chunk_id':match['chunk_id'],'support_quote':passage['text']})
    return resolved


def citations_for(statements, offered):
    matches={m['chunk_id']:m for m in offered}
    citations=[]
    for qid in dict.fromkeys(s['chunk_id'] for s in statements):
        match=matches[qid];meta=match['metadata']
        citation={key:meta[key] for key in ('source_id','source_url','source_lines','law_number','title_zh',
            'source_revision_id','source_revision_status','source_revision_verified','expert_reviewed','official_translation',
            'needs_rule_review','review_notes','license','license_url','source_attribution','content_zh_sha256')}
        citation.update(chunk_id=qid,quotes=list(dict.fromkeys(s['support_quote'] for s in statements if s['chunk_id']==qid)))
        citations.append(citation)
    return citations


def render_answer(statements, citations):
    by_id={c['chunk_id']:c for c in citations}
    lines=[]
    for statement in statements:
        c=by_id[statement['chunk_id']]
        label=f"{c['chunk_id']} · 第{c['law_number']}条 · L{c['source_lines'][0]}–L{c['source_lines'][1]}"
        lines.append(html.escape(statement['text'])+f" [{label}]({c['source_url']})")
    for c in citations:
        if c['needs_rule_review']:lines.append('校核提示：'+html.escape('；'.join(c['review_notes'])))
    return '\n\n'.join(lines+['资料范围：'+BOUNDARY])


def render_panel(result):
    offered={m['chunk_id']:m for m in result['context']}
    blocks=[f"<p>请求 {html.escape(result['trace_id'])} · {'已生成回答' if result['status']=='answered' else '证据不足或处理未完成'}</p>"]
    for c in result['citations']:
        match=offered[c['chunk_id']]
        blocks.append("<details open data-rag-b0-evidence='true'><summary>"+html.escape(
            f"{c['chunk_id']} · 第{c['law_number']}条 · {c['title_zh']}")+"</summary><blockquote>"+
            html.escape(match['content_zh']).replace('\n','<br>')+"</blockquote><a target='_blank' rel='noopener noreferrer' href='"+
            html.escape(c['source_url'],quote=True)+"'>"+html.escape(f"{c['source_id']} · L{c['source_lines'][0]}–L{c['source_lines'][1]}")+
            "</a><p>"+html.escape(c['source_attribution'])+' · <a href="'+html.escape(c['license_url'],quote=True)+'">'+html.escape(c['license'])+'</a></p>'+
            '<p>规则校核：'+('有待核对项' if c['needs_rule_review'] else '无额外校核标记（不代表专家通过）')+
            '；历史版本正文：'+('已核验' if c['source_revision_verified'] else '未独立核验')+'</p>'+
            '<p>'+html.escape(BOUNDARY)+('</p><p>校核提示：'+html.escape('；'.join(c['review_notes'])) if c['needs_rule_review'] else '')+'</p></details>')
    blocks.append('<p>'+html.escape(BOUNDARY)+'</p>')
    return ''.join(blocks)


class GenerationRejected(ValueError):
    def __init__(self,message,response):
        super().__init__(message)
        self.response=response


def generation_record(response, config):
    result={key:response.get(key) for key in ('model','done','done_reason','prompt_eval_count','eval_count','load_duration','total_duration')}
    result.update(raw_content=response.get('message',{}).get('content'),raw_response=response,model_digest=config['llm']['digest'])
    return result


class PinnedChat:
    def __init__(self, config, base_url='http://127.0.0.1:11434'):
        self.config=config;self.base_url=base_url.rstrip('/')
        parsed=urlsplit(self.base_url)
        if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.path or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('B0 chat is restricted to a loopback model service')
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self,path,payload=None):
        request=urllib.request.Request(self.base_url+path,data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type':'application/json'})
        with self.opener.open(request,timeout=self.config['llm']['timeout_seconds']) as response:return json.load(response)

    def verify_model(self):
        cfg=self.config['llm']
        if self.request('/api/version')['version']!=cfg['ollama_version']:raise ValueError('Pinned Ollama version differs')
        matches=[m for m in self.request('/api/tags')['models'] if m['name']==cfg['name']]
        if len(matches)!=1 or matches[0]['digest']!=cfg['digest']:raise ValueError('Pinned answer-model digest differs')

    def generate(self,messages):
        self.verify_model()
        cfg=self.config['llm']
        response=self.request('/api/chat',{'model':cfg['name'],'messages':messages,'stream':False,
            'keep_alive':cfg['keep_alive'],'options':{key:cfg[key] for key in
                ('num_ctx','num_predict','num_gpu','num_thread','temperature','seed')}})
        self.verify_model()
        if response.get('done') is not True or response.get('done_reason')!='stop':raise GenerationRejected('Model response was incomplete or truncated',response)
        if response.get('prompt_eval_count',0)+cfg['num_predict']+self.config['chat_template_token_reserve']>cfg['num_ctx']:
            raise GenerationRejected('Actual model input exceeded context policy',response)
        return response


class RagB0Engine:
    def __init__(self, config_path=CONFIG):
        self.config=load_config(config_path)
        self.config_sha256=digest(Path(config_path).read_bytes())
        self.prompt=(ROOT/self.config['prompt_file']).read_text('utf-8')
        self.prompt_sha256=digest(self.prompt.encode('utf-8'))
        self.index=DenseIndex(ROOT/self.config['dense_index'],ROOT/self.config['dense_config'])
        self.chat=PinnedChat(self.config)
        self.lock=threading.RLock()

    def close(self):self.index.close()

    def answer(self, question):
        started=time.perf_counter()
        result={'trace_id':uuid.uuid4().hex,'captured_at':datetime.now(timezone.utc).isoformat(),'question':question,
            'normalized_query':None,'version':self.config['version'],'config_sha256':self.config_sha256,
            'prompt_version':self.config['prompt_version'],
            'prompt_sha256':self.prompt_sha256,'index_manifest_sha256':digest((self.index.path/'index_manifest.json').read_bytes()),
            'status':'refused','answer':REFUSAL,'citations':[],'retrieval':None,'context':[],
            'generation':None,'generation_attempted':False,'attempts':[],'refusal_reason':None,'timing':{}}
        with self.lock:
            try:
                query=normalize_query(question,self.config);result['normalized_query']=query
                if re.search(r'官方|现行|最新|IFAB',query,re.I) and re.search(r'赛季|20\d{2}|规则',query):
                    result['refusal_reason']='official_version_not_verified'
                    result['answer']='现有资料未核验为指定赛季的IFAB官方规则，无法确认其现行适用性。'
                    return result
                retrieval=self.index.query(query,self.config['top_k']);result['retrieval']=retrieval
                for number in range(self.config['max_generation_attempts']):
                    prompt=self.prompt+('' if number==0 else '\n上次输出未通过格式、完整性或事实数值检查。请从头重新简短回答，以ANSWER:或REFUSE:开头，以完整句号结束；不写编号，不重复句子，不补充资料外事实。')
                    context,messages,schema,byte_count=pack_context(query,retrieval['results'],self.config,prompt)
                    result.update(context=context,messages=messages,application_response_schema=schema,prompt_utf8_bytes=byte_count)
                    if not context:
                        result['refusal_reason']='no_whole_evidence_within_budget';return result
                    attempt={'attempt':number+1,'messages':messages,'application_response_schema':schema,'prompt_utf8_bytes':byte_count,
                        'effective_prompt_sha256':digest(prompt.encode()),'context_ids':[m['chunk_id'] for m in context],
                        'generation':None,'validation_error':None}
                    generation_started=time.perf_counter();result['generation_attempted']=True
                    try:
                        response=self.chat.generate(messages)
                        result['generation']=attempt['generation']=generation_record(response,self.config)
                        payload=parse_generated_text(response['message']['content'],context,self.config);result['generation']['parsed_payload']=payload
                        statements=validate_payload(payload,context,self.config)
                        result['generation']['validated_statements']=statements
                        if not statements:
                            result['refusal_reason']='model_found_no_direct_support'
                            result['answer']=REFUSAL+'\n\n原因：'+html.escape(payload['refusal_reason'])
                            return result
                        result['citations']=citations_for(statements,context)
                        result['answer']=render_answer(statements,result['citations']);result['status']='answered'
                        break
                    except (ValueError,KeyError,TypeError) as exc:
                        if isinstance(exc,GenerationRejected):
                            result['generation']=attempt['generation']=generation_record(exc.response,self.config)
                        attempt['validation_error']=type(exc).__name__+': '+str(exc)
                        if number+1==self.config['max_generation_attempts']:raise
                    finally:
                        attempt['generation_seconds']=time.perf_counter()-generation_started
                        result['attempts'].append(attempt)
                        result['timing']['generation_seconds']=sum(a['generation_seconds'] for a in result['attempts'])
            except (ValueError,KeyError,TypeError,OSError,RuntimeError,urllib.error.URLError,TimeoutError) as exc:
                result.update(status='refused',answer=REFUSAL,citations=[],refusal_reason='generation_or_evidence_validation_failed',
                              error=type(exc).__name__+': '+str(exc))
            finally:
                result['timing']['total_seconds']=time.perf_counter()-started
        return result


_ENGINE=None
_ENGINE_LOCK=threading.RLock()
def get_engine():
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:_ENGINE=RagB0Engine()
        return _ENGINE
