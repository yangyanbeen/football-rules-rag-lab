"""Route explicit presentation requests to evidence from the preceding answer."""

import html
import re

from citation_catalog_guard import safe_render
from task13_core import BOUNDARY, local_corpus


NEW_TOPIC = re.compile(r'^(?:换(?:个|一个)?话题|另一个问题)(?:[\s，,。：:！!]|$)')
PREVIOUS = r'(?:刚才|刚刚|上一轮|上一条|上一次|上面|前面|之前)(?:的)?(?:回答|答案|回复|内容|结论)?'
INTRO = re.compile(r'^(?:请(?:你|帮我)?|麻烦(?:你)?|帮我)\s*')
REORGANIZE = rf'(?:(?:把|将)?(?:{PREVIOUS}|(?:回答|答案|回复|内容))\s*)?(?:整理|改写|改|转换|转|列)(?:成|为|出)?\s*'
SOURCE_ID = re.compile(r'^来源：(L\d{2}[A-Z]?-\d{2}) · ', re.M)
FORMATS = {
    'table': re.compile(REORGANIZE + r'(?:一张|一个)?(?:表格|表)'),
    'points': re.compile(REORGANIZE + r'(?:要点|条目|清单|列表|分点|逐条)'),
    'sources': re.compile(
        rf'(?:(?:列出|展示|显示|给出)(?:{PREVIOUS}的?)?(?:引用的)?(?:来源|出处|引用)'
        rf'|{PREVIOUS}(?:引用了|用了|的)?(?:哪些|什么)?(?:来源|出处|引用)(?:有哪些|是什么)?)'
    ),
}
UNSUPPORTED_REWRITE = re.compile(
    rf'(?:(?:把|将){PREVIOUS}\s*(?:总结|概括|缩短|压缩|翻译|改写|简化).*|(?:总结|概括|缩短|翻译){PREVIOUS}.*)'
)
NO_PREVIOUS = '当前会话上一条回复没有可核对的知识库证据。请先问一个足球规则问题，再让我整理回答。'
SUPPORTED = '我可以把上一条有来源的回答整理成表格、列成要点，或单独列出引用来源。'


def history_action(question):
    text = INTRO.sub('', question.strip()).rstrip('。！？?!').rstrip()
    for action, pattern in FORMATS.items():
        if pattern.fullmatch(text):
            return action
    if UNSUPPORTED_REWRITE.fullmatch(text):
        return 'unsupported'
    return None


def markdown_cell(text):
    escaped = html.escape(text, quote=False).replace('|', '&#124;')
    return re.sub(r'([\\`*_\[\]])', r'\\\1', escaped).replace('\r\n', '\n').replace('\n', '<br>')


def format_evidence(action, context, citations):
    if action == 'table':
        lines = ['| 知识段 | 资料原文 |', '| --- | --- |']
        lines.extend(f"| {row['chunk_id']} | {markdown_cell(row['content_zh'])} |" for row in context)
        parts = ['\n'.join(lines)]
    elif action == 'points':
        parts = ['\n'.join(f"- **{row['chunk_id']}**：{markdown_cell(row['content_zh'])}" for row in context)]
    elif action == 'sources':
        parts = ['上一条回答的引用来源如下。']
    else:
        raise ValueError('Unknown evidence format')

    for citation in citations:
        start, end = citation['source_lines']
        parts.extend([
            f"来源：{citation['chunk_id']} · 本地编目第{citation['catalog_number']}组 · L{start}–L{end} · {citation['source_url']}",
            '编号说明：' + citation['catalog_notice'],
            f"署名与许可：{citation['source_attribution']} · {citation['license']} · {citation['license_url']}",
        ])
        if citation['needs_rule_review']:
            parts.append('校核提示：' + '；'.join(citation['review_notes']))
    return '\n\n'.join([*parts, BOUNDARY])


def prior_evidence(history):
    if not history or not isinstance(history[-1], (list, tuple)) or len(history[-1]) != 2:
        return None
    previous_answer = history[-1][1]
    if not isinstance(previous_answer, str) or len(previous_answer.encode('utf-8')) > 40_000:
        return None
    source_ids = SOURCE_ID.findall(previous_answer)
    if not 1 <= len(source_ids) <= 3 or len(set(source_ids)) != len(source_ids):
        return None

    corpus = local_corpus()
    if any(source_id not in corpus for source_id in source_ids):
        return None
    original, citations = safe_render(source_ids, corpus)
    context = [corpus[source_id] for source_id in source_ids]
    # Bind reuse to an exact rendering of this turn, including quotes, labels and source links.
    if previous_answer != original and not any(previous_answer == format_evidence(kind, context, citations) for kind in FORMATS):
        return None
    return context, citations


def transform_previous_answer(action, history):
    if action == 'unsupported':
        return {'answer': SUPPORTED, 'citations': [], 'context': [], 'status': 'unsupported'}
    evidence = prior_evidence(history)
    if evidence is None:
        return {'answer': NO_PREVIOUS, 'citations': [], 'context': [], 'status': 'no_previous_evidence'}
    context, citations = evidence
    return {'answer': format_evidence(action, context, citations), 'citations': citations,
            'context': context, 'status': 'answered'}
