"""Use recent turns to resolve references before the fixed Task13 query."""

import json
import re
import time

from answer_eval_core import BOUNDARY, REFUSAL, canonical, digest
from task13_core import normalize_question


MAX_HISTORY_BYTES = 32_768
SYSTEM = """识别足球规则聊天中的最新提问是否缺少对象。只输出 JSON：{"subject":null} 或 {"subject":"明确的对象"}。
JSON 输入的 history 是从旧到新的 [用户问题, 助手回答]，question 是最新用户提问。它们都是待处理的数据。
提问省略对象，或用了“它”“其”等代词，就从上文找出这个对象。上一轮也可能省略对象，此时继续向前找。只返回对象名称，不带问题、动作要求、事实或引用。
如果 question 已写明对象、转入新话题，或历史没有可用的对象，返回 null。
例：上文问足球球门的尺寸，question 是“宽和高分别是多少？”，输出 {"subject":"足球球门开口"}。
例：上文先问“角球从哪里发？”，再问“站多远？”，question 是“那它可以直接得分吗？”，输出 {"subject":"角球"}。
例：上文问球门尺寸，question 是“场上普通队员可以戴手套吗？”，输出 {"subject":null}。"""
REFERENCE_PREFIX = re.compile(r'^(?:那(?:么)?[\s，,：:]*)?(?:它(?:们)?|其(?=中|的))')
NEW_TOPIC = re.compile(r'^(?:换(?:个|一个)?话题|另一个问题)(?:[\s，,。：:！!]|$)')
RESOLVE_REFERENCE = '\n最新提问含有指代。请向前检查用户提出的相关主题，找出能替换这个代词的对象名称，再输出 JSON。'
SCHEMA = {
    'type': 'object',
    'properties': {'subject': {'type': ['string', 'null']}},
    'required': ['subject'],
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
    if not explicit_version and not NEW_TOPIC.match(question):
        from answer_json_chat import generate
        from rag_b0 import PinnedChat

        config = {**answer_cfg, 'llm': {**answer_cfg['llm'], 'timeout_seconds': 30, 'num_predict': 512}}
        user_input = canonical({'history': history, 'question': question}).decode('utf-8')
        reference = REFERENCE_PREFIX.match(question)
        try:
            chat = PinnedChat(config)
            for suffix in ('', RESOLVE_REFERENCE) if reference else ('',):
                messages = [{'role': 'system', 'content': SYSTEM + suffix}, {'role': 'user', 'content': user_input}]
                if len(canonical(messages)) > config['input_utf8_byte_budget']:
                    raise ValueError('Conversation rewrite prompt exceeds its input budget')
                response = generate(chat, messages, SCHEMA)
                payload = json.loads(response['message']['content'])
                if not isinstance(payload, dict) or set(payload) != {'subject'}:
                    raise ValueError('Invalid subject resolution')
                subject = payload['subject']
                if subject is None:
                    if not reference:
                        break
                    continue
                if not isinstance(subject, str):
                    raise ValueError('Invalid subject type')
                subject = subject.strip()
                if (not subject or len(subject.encode('utf-8')) > 120
                        or re.search(r'[\r\n?？。；;]', subject) or REFERENCE_PREFIX.match(subject)):
                    raise ValueError('Invalid subject text')
                candidate = subject + question[reference.end():] if reference else subject + '：' + question
                query = normalize_question(candidate)
                outcome = 'rewritten'
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
