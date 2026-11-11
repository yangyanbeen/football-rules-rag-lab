"""Task-six reasoning adapter for the unchanged, pinned Kotaemon ChatPage."""
import json
import threading

from kotaemon.base import Document
from ktem.reasoning.base import BaseReasoning
from rag_b0 import ROOT, render_panel
from rag_b0_worker_client import call_worker

JOURNAL_LOCK=threading.RLock()


class FootballRagB0Pipeline(BaseReasoning):
    @classmethod
    def get_info(cls):
        # ChatPage in v0.12.0 expects the 'simple' settings namespace.
        return {'id':'simple','name':'足球规则 · RAG B0',
                'description':'根据固定足球知识库生成中文回答，并逐段显示证据来源。'}

    @classmethod
    def get_user_settings(cls):
        return {
            'llm':{'name':'本机模型','value':'ollama','component':'dropdown',
                   'choices':[('本机 Qwen2.5:3b','ollama')]},
            'highlight_citation':{'name':'来源展示','value':'inline','component':'radio',
                                  'choices':[('答案引用与原文证据','inline')]},
        }

    @classmethod
    def get_pipeline(cls, settings, states, retrievers=None):
        if settings.get('reasoning.options.simple.llm') not in ('',None,'ollama'):
            raise ValueError('该入口只使用固定的本机模型。')
        if retrievers:
            raise ValueError('该入口只读取任务五的固定足球知识库。')
        return cls()

    def stream(self, message: str, conv_id: str, history: list, **kwargs):
        # Prior conversation text is never inserted as factual context.
        yield Document(channel='info',content=None)
        result=call_worker(message)
        result['request_source']='kotaemon_ui'
        journal=ROOT/'.runtime/rag-b0/ui-events.jsonl'
        journal.parent.mkdir(parents=True,exist_ok=True)
        with JOURNAL_LOCK, journal.open('a',encoding='utf-8') as handle:
            handle.write(json.dumps(result,ensure_ascii=False)+'\n')
        # No unvalidated token is exposed to ChatPage.
        yield Document(channel='chat',content=result['answer'])
        yield Document(channel='info',content=render_panel(result))
        print('RAG B0:',result['trace_id'],result['status'],flush=True)
        return Document(text=result['answer'],metadata={'trace_id':result['trace_id'],'citations':result['citations']})
