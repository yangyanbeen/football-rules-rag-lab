"""Kotaemon ChatPage adapter for the integrated, isolated task13 worker."""
import threading
from kotaemon.base import Document
from ktem.reasoning.base import BaseReasoning
from task13_core import *
from task13_worker_client import call_worker

JOURNAL_LOCK=threading.RLock()


class IntegratedFootballPipeline(BaseReasoning):
    @classmethod
    def get_info(cls):
        return {'id':'simple','name':'足球规则 · 混合检索问答','description':'依据固定资料回答，附完整证据、来源和适用范围。'}

    @classmethod
    def get_user_settings(cls):
        return {'llm':{'name':'本机模型','value':'ollama','component':'dropdown','choices':[('本机 Qwen2.5:3b','ollama')]},
            'highlight_citation':{'name':'来源展示','value':'inline','component':'radio','choices':[('答案引用与完整原文','inline')]}}

    @classmethod
    def get_pipeline(cls,settings,states,retrievers=None):
        if settings.get('reasoning.options.simple.llm') not in ('',None,'ollama') or retrievers:raise ValueError('该入口使用固定本机知识库和模型。')
        return cls()

    def stream(self,message:str,conv_id:str,history:list,**kwargs):
        yield Document(channel='info',content=None)
        try:
            result,trace,wall=call_worker(message)
            event={'captured_at':now(),'source':'kotaemon_integrated_ui','trace_id':result['trace_id'],
                'question_sha256':digest(result['question'].encode()),'private_trace':trace,'status':result['status'],
                'worker_wall_seconds':wall,'profile':result['profile']}
            with JOURNAL_LOCK:
                p=ROOT/'.runtime/task13/ui-events.jsonl';p.parent.mkdir(parents=True,exist_ok=True)
                with p.open('a',encoding='utf-8',newline='\n') as f:f.write(canonical(event).decode()+'\n');f.flush()
            yield Document(channel='chat',content=result['answer'])
            yield Document(channel='info',content=render_panel(result))
            return Document(text=result['answer'],metadata={'trace_id':result['trace_id'],'citations':result['citations']})
        except (ValueError,KeyError,TypeError,OSError,RuntimeError,TimeoutError) as exc:
            # Failure text is not a successful rules answer or a fabricated source.
            yield Document(channel='chat',content='本次请求未能完成，请确认本机服务已启动后重试。\n\n'+BOUNDARY)
            yield Document(channel='info',content='<p>本次未生成可核对的答案与引用。</p>')
            print('Task13 UI request failed: '+type(exc).__name__,flush=True)
