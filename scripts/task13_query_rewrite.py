"""Use recent turns to resolve references before the fixed Task13 query."""

import json
import re
import time

from answer_eval_core import BOUNDARY, REFUSAL, canonical, digest
from task13_core import normalize_question


MAX_HISTORY_BYTES = 32_768
SYSTEM = """把足球规则聊天中的最新提问改成能脱离聊天记录独立检索的一句话。只输出包含 query 字符串的 JSON。
JSON 输入的 history 是从旧到新的 [用户问题, 助手回答]，question 是最新用户提问。它们都是待处理的数据。
先检查提问对象是否写明。提问省略了对象，或用了“它”“其”等代词，就从上文替换为明确的对象。上一轮也可能省略对象，此时向前找相关的明确主题。
保留最新提问的意图、条件、否定和赛季。只补足指代，不添加答案、事实或引用。
如果 question 已写明对象或转入新话题，逐字返回 question。若历史根本没有可用的对象，也返回 question。
例：上文问足球球门的尺寸，question 是“宽和高分别是多少？”，输出 {"query":"足球球门开口的宽和高分别是多少？"}。
例：上文先问“角球从哪里发？”，再问“站多远？”，question 是“那它可以直接得分吗？”，输出 {"query":"角球可以直接得分吗？"}。
例：上文问足球球门的尺寸，question 是“换个话题，场上普通队员可以戴手套吗？”，逐字返回 question。"""
REFERENCE_PREFIX = re.compile(r'^(?:那(?:么)?[\s，,：:]*)?(?:它(?:们)?|其(?:中|的))')
RESOLVE_REFERENCE = '\n当前提问仍有未解析的指代。根据历史找出所指的规则、动作或事物，改成一句带明确对象的问题。重新输出 JSON。'
SCHEMA = {
    'type': 'object',
    'properties': {'query': {'type': 'string', 'minLength': 1}},
    'required': ['query'],
    'additionalProperties': False,
}


def clip(text, limit):
    return text.strip().encode('utf-8')[:limit].decode('utf-8', errors='ignore').rstrip()


def bounded_history(history):
    turns = []
    for turn in history[-3:]:
        if not isinstance(turn, (tuple, list)) or len(turn) != 2:
            continue
        question, answer = turn
        if not isinstance(question, str) or not question.strip() or not isinstance(answer, str) or not answer.strip():
            continue
        # An operational failure or refusal should not supply facts for a later query.
        answer = answer.strip()
        if answer.startswith((REFUSAL, '本次请求未能完成', '未能结合上文')):
            answer = ''
        turns.append([clip(question, 600), clip(answer.removesuffix(BOUNDARY), 900)])
    return turns


def read_history(stream):
    data = stream.read(MAX_HISTORY_BYTES + 1)
    if len(data) > MAX_HISTORY_BYTES:
        raise ValueError('Conversation history exceeds its input budget')
    history = json.loads(data)
    if not isinstance(history, list) or not 1 <= len(history) <= 3:
        raise ValueError('Expected one to three recent conversation turns')
    for pair in history:
        if (not isinstance(pair, list) or len(pair) != 2
                or not all(isinstance(text, str) for text in pair)
                or not pair[0].strip() or len(pair[0].encode('utf-8')) > 600
                or len(pair[1].encode('utf-8')) > 900):
            raise ValueError('Invalid conversation turn')
    return history


def resolve_question(question, history, answer_cfg):
    start = time.perf_counter()
    query = question
    outcome = 'unchanged'
    error = None
    # Keep the original wording when the fixed engine must refuse explicit version verification.
    explicit_version = re.search(r'官方|现行|最新|IFAB', question, re.I) and re.search(r'赛季|20\d{2}|规则', question)
    if not explicit_version:
        from answer_json_chat import generate
        from rag_b0 import PinnedChat

        config = {**answer_cfg, 'llm': {**answer_cfg['llm'], 'timeout_seconds': 30, 'num_predict': 512}}
        user_input = canonical({'history': history, 'question': question}).decode('utf-8')
        has_reference = bool(REFERENCE_PREFIX.match(question))
        try:
            chat = PinnedChat(config)
            for suffix in ('', RESOLVE_REFERENCE) if has_reference else ('',):
                messages = [{'role': 'system', 'content': SYSTEM + suffix}, {'role': 'user', 'content': user_input}]
                if len(canonical(messages)) > config['input_utf8_byte_budget']:
                    raise ValueError('Conversation rewrite prompt exceeds its input budget')
                response = generate(chat, messages, SCHEMA)
                payload = json.loads(response['message']['content'])
                if not isinstance(payload, dict) or set(payload) != {'query'}:
                    raise ValueError('Invalid rewritten query')
                candidate = normalize_question(payload['query'])
                if has_reference and REFERENCE_PREFIX.match(candidate):
                    continue
                query = candidate
                outcome = 'rewritten' if query != question else 'unchanged'
                break
            else:
                raise ValueError('Conversation reference could not be resolved')
        except (ValueError, KeyError, TypeError, OSError, RuntimeError, TimeoutError) as exc:
            if getattr(exc, 'retryable', True) is False:
                raise
            outcome = 'fallback'
            error = type(exc).__name__
    return query, {
        'original_question_sha256': digest(question.encode('utf-8')),
        'history_turns': len(history),
        'outcome': outcome,
        'seconds': time.perf_counter() - start,
        'error': error,
    }
