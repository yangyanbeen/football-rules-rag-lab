"""Revised real Kotaemon adapter with explicit failure rendering and isolated audit journal."""
import os,threading
from kotaemon.base import Document
from task13_pipeline import IntegratedFootballPipeline as OriginalPipeline
from task13_audit import *
from task13_audit_client import call_worker
from task13_history_actions import history_action, transform_previous_answer

JOURNAL_LOCK=threading.RLock()


def record_ui_event(event):
    with JOURNAL_LOCK:
        path = ROOT / '.runtime/task13-audit/ui-multiturn-events.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8', newline='\n') as log:
            log.write(canonical(event).decode('utf-8') + '\n')
            log.flush()
            os.fsync(log.fileno())


class IntegratedFootballPipeline(OriginalPipeline):
    def stream(self,message:str,conv_id:str,history:list,**kwargs):
        yield Document(channel='info',content=None)
        try:
            question = normalize_question(message)
            history = history if conv_id and history else ()
            identity = {
                'captured_at': now(), 'source': 'kotaemon_integrated_audit_ui',
                'question_sha256': digest(question.encode('utf-8')),
                'conversation_sha256': digest(conv_id.encode('utf-8')) if conv_id else None,
            }
            action = history_action(question)
            if action:
                result = transform_previous_answer(action, history)
                citations = result['citations']
                record_ui_event({**identity, 'route': 'previous_answer', 'action': action,
                                 'status': result['status'], 'reused_ids': [c['chunk_id'] for c in citations]})
                yield Document(channel='chat', content=result['answer'])
                if citations:
                    yield Document(channel='info', content=panel(result))
                return Document(text=result['answer'], metadata={'citations': citations})

            result,trace,wall=call_worker(question, history=history)
            resolution = result.get('query_resolution')
            answer = result['answer']
            if resolution and resolution['outcome'] == 'fallback':
                answer = '未能结合上文，以下按本轮问题检索。\n\n' + answer
            event={**identity,'route':'knowledge','trace_id':result['trace_id'],
                   'retrieval_query_sha256':digest(result['question'].encode()),'query_resolution':resolution,
                   'private_trace':trace,'status':result['status'],'worker_wall_seconds':wall,'implementation':result['implementation']}
            record_ui_event(event)
            yield Document(channel='chat',content=answer);yield Document(channel='info',content=panel(result))
            return Document(text=answer,metadata={'trace_id':result['trace_id'],'citations':result['citations']})
        except (ValueError,KeyError,TypeError,OSError,RuntimeError,TimeoutError):
            yield Document(channel='chat',content='本次请求未能完成，请确认本机服务已启动后重试。\n\n'+BOUNDARY)
            yield Document(channel='info',content='<p>本次未生成可核对的答案与引用。</p>')
