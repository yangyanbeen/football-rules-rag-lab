"""Explicit retrieval, generation and validation graph for football rule answers."""
from dataclasses import dataclass, field
from functools import partial
import operator
import re
import time
from threading import RLock
from typing import Annotated
from typing_extensions import TypedDict
import uuid

from answer_eval_core import BOUNDARY, REFUSAL, ROOT, canonical, digest, parse_selection, read
from answer_eval_engine import pack
from answer_json_chat import generate, selection_schema
from citation_catalog_guard import safe_render
from dense_retrieval_eval import normalize_query
from rrf import SOURCE_FIELDS, fuse
from task13_core import normalize_question
from disciplinary_query_policy import evaluate_suspension_query, refusal_message, PUBLIC_REASON
from version_validity_policy import version_validity_query

CONFIG = ROOT / 'config/langgraph_flow.json'
POLICY_ERRORS = (ValueError, KeyError, TypeError, OSError, RuntimeError, TimeoutError)
REPAIR = {'role': 'user', 'content': '上次输出格式无效。重新按规定只输出一个JSON对象，不加说明；不要改变原始证据。'}
FAILURE = '本次问答校验未完成，请重试。'


def policy():
    value = read(CONFIG)
    expected = {
        'version': 'football-rag-langgraph-1.0', 'langgraph_version': '1.2.22',
        'comparison_cases': ['normal', 'outside', 'version'], 'retrieval_depth': 80, 'rrf_k': 60,
        'rerank_budget': 40, 'result_limit': 10, 'max_generation_attempts': 2,
        'recursion_limit': 24, 'trace_root': '.runtime/task17/traces',
    }
    if canonical(value) != canonical(expected):
        raise ValueError('Graph configuration differs from the evaluated policy')
    return value


class QueryState(TypedDict, total=False):
    request_id: str
    question: str
    status: str
    reason: str | None
    error_kind: str | None
    channels: dict
    fused: list
    retrieved_ids: list[str]
    evidence: list
    context: list
    messages: list
    offered_ids: list[str]
    prompt_bytes: int
    attempts: list
    selection_audits: list
    business_decision: dict
    retry: bool
    selection: dict | None
    generation_decision: dict | None
    fact_recovery: dict | None
    answer: str
    citations: list
    selected_ids: list[str]
    embedding_queries: int
    reranked_pairs: int
    fault_applied: bool
    events: Annotated[list, operator.add]


class CountingChat:
    def __init__(self, base):
        self.base = base
        self.config = base.config
        self.requests = 0

    def verify_model(self):
        return self.base.verify_model()

    def request(self, path, payload=None):
        if path == '/api/chat':
            self.requests += 1
        return self.base.request(path, payload)


@dataclass
class Operations:
    retriever: object
    chat: object
    answer_policy: dict
    prompt: str
    sources: dict
    request_lock: object = field(default_factory=RLock, repr=False)

    def retrieval(self, question, depth):
        dense = self.retriever.dense.query(normalize_query(question), depth)
        dense_rows = [
            {**{key: row['metadata'][key] for key in SOURCE_FIELDS},
             **{key: row[key] for key in ('rank', 'score', 'distance')}}
            for row in dense['results']
        ]
        return {'dense': dense_rows, 'bm25': self.retriever.bm25.query(question, depth)['results']}

    def fusion(self, channels, k, depth):
        return fuse(channels, k, depth)['rrf']

    def rerank(self, question, candidates):
        return self.retriever.reranker.score(normalize_query(question), candidates, self.retriever.dense.by_id)['results']

    def expand(self, ids):
        return [self.retriever.dense.by_id[chunk] for chunk in ids]

    def generate(self, messages, schema):
        return generate(self.chat, messages, schema)

    def render(self, ids, context):
        return safe_render(ids, {row['chunk_id']: row for row in context})

    @property
    def chat_calls(self):
        return self.chat.requests

    @property
    def completed_embeddings(self):
        return len(self.retriever.embedder.observations)


NODES = ('route', 'version_check', 'retrieve', 'fuse', 'rerank', 'expand_context',
         'check_evidence', 'answer', 'check_citations', 'refusal', 'finish')
SEQUENCE = dict(zip(NODES[:7], NODES[1:8]))


class Flow:
    def __init__(self, operations, citation_fault=False):
        from langgraph.graph import END, START, StateGraph

        self.ops = operations
        self.request_lock = getattr(operations, 'request_lock', None) or RLock()
        self.cfg = policy()
        self.citation_fault = citation_fault
        if self.ops.answer_policy['max_generation_attempts'] != self.cfg['max_generation_attempts']:
            raise ValueError('Retry ceiling differs from the fixed answer policy')
        builder = StateGraph(QueryState)
        for name in NODES:
            builder.add_node(name, partial(self.traced_node, name))
        builder.add_edge(START, 'route')
        for name, successor in SEQUENCE.items():
            builder.add_conditional_edges(name, self.after_stage, {'continue': successor, 'stop': 'refusal'})
        builder.add_conditional_edges('answer', self.after_answer, {
            'retry': 'answer', 'cite': 'check_citations', 'stop': 'refusal',
        })
        builder.add_conditional_edges('check_citations', self.after_stage, {'continue': 'finish', 'stop': 'refusal'})
        builder.add_edge('refusal', 'finish')
        builder.add_edge('finish', END)
        self.compiled = builder.compile()

    @staticmethod
    def after_stage(state):
        return 'stop' if state.get('reason') else 'continue'

    @staticmethod
    def after_answer(state):
        if state.get('retry'):
            return 'retry'
        return 'stop' if state.get('reason') else 'cite'

    def traced_node(self, name, state):
        started = time.perf_counter_ns()
        try:
            update = getattr(self, name)(state)
        except POLICY_ERRORS as exc:
            update = {'status': 'failed', 'reason': 'stage_error', 'error_kind': type(exc).__name__, 'retry': False}
        event = {
            'request_id': state['request_id'], 'seq': len(state['events']) + 1, 'node': name,
            'elapsed_ns': time.perf_counter_ns() - started,
            'reason': update.get('reason'), 'retry': update.get('retry', False),
            'answer_attempts': len(update.get('attempts', state.get('attempts', []))),
        }
        return {**update, 'events': [event]}

    def route(self, state):
        question = normalize_question(state['question'])
        decision = evaluate_suspension_query(question)
        if decision:
            return {'question': question, 'status': 'refused', 'reason': PUBLIC_REASON,
                    'business_decision': decision}
        return {'question': question, 'status': 'pending'}

    def version_check(self, state):
        q = state['question']
        decision=version_validity_query(q)
        if decision:
            return {'status': 'refused', 'reason': 'version_unverified', 'version_decision': decision}
        return {}

    def retrieve(self, state):
        return {'channels': self.ops.retrieval(state['question'], self.cfg['retrieval_depth']),
                'embedding_queries': 1}

    def fuse(self, state):
        return {'fused': self.ops.fusion(state['channels'], self.cfg['rrf_k'], self.cfg['retrieval_depth'])}

    def rerank(self, state):
        candidates = state['fused'][:self.cfg['rerank_budget']]
        results = self.ops.rerank(state['question'], candidates) if candidates else []
        return {'retrieved_ids': [r['chunk_id'] for r in results[:self.cfg['result_limit']]],
                'reranked_pairs': len(results)}

    def expand_context(self, state):
        ids = state['retrieved_ids']
        evidence = self.ops.expand(ids)
        if [r['chunk_id'] for r in evidence] != ids or len(set(ids)) != len(ids):
            raise ValueError('Context does not match ranked source IDs')
        for row in evidence:
            source = self.ops.sources.get(row['chunk_id'], {})
            content = digest(row['content_zh'].encode('utf-8'))
            revision = digest(canonical({k: v for k, v in row.items() if k != 'record_sha256'}))
            if (content != row.get('content_zh_sha256') or content != source.get('content_zh_sha256')
                    or revision != row.get('record_sha256') or revision != source.get('record_sha256')):
                return {'status': 'failed', 'reason': 'context_integrity_error'}
        return {'evidence': evidence}

    def check_evidence(self, state):
        rows, messages, size = pack(state['question'], state['evidence'], self.ops.answer_policy, self.ops.prompt)
        if not rows:
            return {'status': 'refused', 'reason': 'no_whole_evidence_within_budget'}
        return {'context': rows, 'messages': messages, 'prompt_bytes': size,
                'offered_ids': [r['chunk_id'] for r in rows]}

    def answer(self, state):
        attempts = list(state.get('attempts', []))
        audits = list(state.get('selection_audits', []))
        messages = state['messages'] if not attempts else [*state['messages'], REPAIR]
        maximum = self.cfg['max_generation_attempts']
        budget = self.ops.answer_policy['input_utf8_byte_budget']
        if len(attempts) >= maximum or len(canonical(messages)) > budget:
            return {'status': 'failed', 'reason': 'generation_budget_exhausted', 'retry': False}
        schema = selection_schema(state['offered_ids'], self.ops.answer_policy['max_selected_chunks'])
        before = self.ops.chat_calls
        response = None
        try:
            response = self.ops.generate(messages, schema)
            selection = parse_selection(response['message']['content'], state['offered_ids'], self.ops.answer_policy)
        except POLICY_ERRORS as exc:
            requests = self.ops.chat_calls - before
            audits.append({'attempt': len(attempts) + 1, 'response': getattr(exc, 'response', response),
                           'normalized_selection': None, 'error': type(exc).__name__ + ': ' + str(exc)})
            attempts.append({'attempt': len(attempts) + 1, 'chat_calls': requests, 'outcome': type(exc).__name__})
            retry = (requests == 1 and getattr(exc, 'retryable', True) is True
                     and not isinstance(exc, (OSError, RuntimeError, TimeoutError))
                     and len(attempts) < maximum and len(canonical([*state['messages'], REPAIR])) <= budget)
            return {'attempts': attempts, 'selection_audits': audits, 'retry': retry, 'status': 'pending' if retry else 'failed',
                    'reason': None if retry else 'generation_failed',
                    'error_kind': None if retry else type(exc).__name__}
        audits.append({'attempt': len(attempts) + 1, 'response': response,
                       'normalized_selection': selection, 'error': None})
        attempts.append({'attempt': len(attempts) + 1, 'chat_calls': self.ops.chat_calls - before, 'outcome': 'accepted'})
        from generation_decision import (decide as apply_generation_decision,
                                          run_selection_audit,
                                          choose_audited_selection,
                                          apply_anchor_guard)
        from answer_eval_engine import request_json
        audit = run_selection_audit(
            self.ops.chat, state['messages'], self.ops.answer_policy,
            lambda s: parse_selection(s, state['offered_ids'], self.ops.answer_policy),
            schema, request_json)
        if audit is not None:
            selection = choose_audited_selection(selection, audit)
            audits.append({'selection_audit': audit})
        guarded = apply_anchor_guard(state['question'], selection, state['context'])
        selection = guarded['selection']
        if guarded['trace']['enabled']:
            audits.append({'selection_anchor_guard': guarded['trace']})
        decision=apply_generation_decision(state['question'],selection,state['context'],state['messages'])
        update={'attempts': attempts, 'selection_audits': audits, 'retry': False, 'selection': selection}
        if decision['trace']['enabled'] or decision['recovery'] is not None:
            update['generation_decision']=decision['trace']
        if decision['recovery'] is not None:
            update['fact_recovery']=decision['recovery']
            if decision['recovery']['applied']:
                selection={**selection,'answerable':True,'chunk_ids':decision['recovery']['selected_ids'],'reason':None}
                update['selection']=selection
        if not selection['answerable']:
            update.update(status='refused',reason=selection['reason'])
        return update

    def check_citations(self, state):
        ids = state['selection']['chunk_ids']
        answer, citations = self.ops.render(ids, state['context'])
        fault = self.citation_fault and bool(citations)
        if fault:
            citations = [{**citations[0], 'source_url': 'https://invalid.example/corrupted'}, *citations[1:]]
        valid = (bool(ids) and set(ids) <= set(state['offered_ids'])
                 and [c['chunk_id'] for c in citations] == ids
                 and all(canonical(c) == canonical(self.ops.sources.get(c['chunk_id'])) for c in citations))
        if not valid:
            return {'status': 'failed', 'reason': 'citation_invalid', 'fault_applied': fault}
        return {'status': 'answered', 'answer': answer, 'citations': citations,
                'selected_ids': ids, 'fault_applied': fault}

    def refusal(self, state):
        text = FAILURE if state['status'] == 'failed' else REFUSAL
        if state.get('business_decision'):
            text = refusal_message(state['business_decision'])
        return {'answer': text + '\n' + BOUNDARY, 'citations': [], 'selected_ids': []}

    def finish(self, state):
        return {}

    def invoke(self, question, request_id=None):
        if request_id is None:
            request_id = uuid.uuid4().hex
        if not isinstance(request_id, str) or not re.fullmatch('[0-9a-f]{32}', request_id):
            raise ValueError('Request ID must be 32 lowercase hex characters')
        question = normalize_question(question)
        started = time.perf_counter_ns()
        with self.request_lock:
            before = self.ops.chat_calls
            embeddings_before = getattr(self.ops, 'completed_embeddings', None)
            result = self.compiled.invoke({'request_id': request_id, 'question': question, 'events': []},
                                          {'recursion_limit': self.cfg['recursion_limit']})
            calls = self.ops.chat_calls - before
            embeddings = (result.get('embedding_queries', 0) if embeddings_before is None
                          else self.ops.completed_embeddings - embeddings_before)
        return {
            'request_id': request_id, 'question_sha256': digest(question.encode('utf-8')),
            'status': result['status'], 'reason': result.get('reason'), 'error_kind': result.get('error_kind'),
            'answer': result['answer'], 'citations': result['citations'], 'selected_ids': result['selected_ids'],
            'retrieved_ids': result.get('retrieved_ids', []), 'offered_ids': result.get('offered_ids', []),
            'attempts': result.get('attempts', []), 'fault_applied': result.get('fault_applied', False),
            'selection_audits': result.get('selection_audits', []),
            'embedding_queries': embeddings, 'reranked_pairs': result.get('reranked_pairs', 0),
            'chat_calls': calls,
            'events': result['events'], 'wall_ns': time.perf_counter_ns() - started,
            **({'business_decision': result['business_decision']} if result.get('business_decision') else {}),
        }

