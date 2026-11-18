"""Revised real Kotaemon adapter with explicit failure rendering and isolated audit journal."""
import os,threading
from kotaemon.base import Document
from task13_pipeline import IntegratedFootballPipeline as OriginalPipeline
from task13_audit import *
from task13_audit_client import call_worker

JOURNAL_LOCK=threading.RLock()


class IntegratedFootballPipeline(OriginalPipeline):
    def stream(self,message:str,conv_id:str,history:list,**kwargs):
        yield Document(channel='info',content=None)
        try:
            result,trace,wall=call_worker(message, history=history if conv_id and history else ())
            resolution = result.get('query_resolution')
            answer = result['answer']
            if resolution and resolution['outcome'] == 'fallback':
                answer = '未能结合上文，以下按本轮问题检索。\n\n' + answer
            event={'captured_at':now(),'source':'kotaemon_integrated_audit_ui','trace_id':result['trace_id'],
                   'question_sha256':digest(normalize_question(message).encode()),'retrieval_query_sha256':digest(result['question'].encode()),
                   'conversation_sha256':digest(conv_id.encode()) if conv_id else None,'query_resolution':resolution,
                   'private_trace':trace,'status':result['status'],'worker_wall_seconds':wall,'implementation':result['implementation']}
            with JOURNAL_LOCK:
                p=ROOT/'.runtime/task13-audit/ui-multiturn-events.jsonl';p.parent.mkdir(parents=True,exist_ok=True)
                with p.open('a',encoding='utf-8',newline='\n') as f:f.write(canonical(event).decode()+'\n');f.flush();os.fsync(f.fileno())
            yield Document(channel='chat',content=answer);yield Document(channel='info',content=panel(result))
            return Document(text=answer,metadata={'trace_id':result['trace_id'],'citations':result['citations']})
        except (ValueError,KeyError,TypeError,OSError,RuntimeError,TimeoutError):
            yield Document(channel='chat',content='本次请求未能完成，请确认本机服务已启动后重试。\n\n'+BOUNDARY)
            yield Document(channel='info',content='<p>本次未生成可核对的答案与引用。</p>')
