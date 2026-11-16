"""Run the real StateGraph with deterministic stage adapters and controlled faults."""
import argparse
import json
import os

from answer_eval_core import ROOT, canonical, digest, now, record, write_new
from answer_eval_engine import pack
from rag_langgraph import Flow, NODES
from run_langgraph_flow import runtime_identity

QUESTION = '受控样例的足球规则是什么？'
SOURCE = {'chunk_id': 'fixture-1', 'source_url': 'https://example.org/rules', 'source_lines': [1, 2]}
EVIDENCE = {'chunk_id': SOURCE['chunk_id'], 'law_number': 1, 'content_zh': '合成规则样例。',
            'needs_rule_review': False, 'review_notes': []}
NORMAL = {'answerable': True, 'chunk_ids': [SOURCE['chunk_id']], 'reason': None}
REFUSAL = {'answerable': False, 'chunk_ids': [], 'reason': 'insufficient_evidence'}


class UnsafeIdentity(ValueError):
    retryable = False


class Fixture:
    def __init__(self, responses=(), no_evidence=False, retrieval_failure=False, wrong_source=False):
        self.queue = list(responses)
        self.no_evidence = no_evidence
        self.retrieval_failure = retrieval_failure
        self.wrong_source = wrong_source
        self.chat_calls = 0
        self.evidence = {**EVIDENCE, 'content_zh_sha256': digest(EVIDENCE['content_zh'].encode('utf-8'))}
        self.evidence['record_sha256'] = digest(canonical(self.evidence))
        self.sources = {SOURCE['chunk_id']: {
            **SOURCE, 'content_zh_sha256': self.evidence['content_zh_sha256'],
            'record_sha256': self.evidence['record_sha256'],
        }}
        self.answer_policy = {'max_generation_attempts': 2, 'max_selected_chunks': 3,
                              'input_utf8_byte_budget': 6200, 'max_context_chunks': 5}
        self.prompt = 'synthetic controlled tests'
        self.received = []

    def retrieval(self, question, depth):
        self.received.append('retrieve')
        if self.retrieval_failure:
            raise RuntimeError('Controlled retrieval failure')
        if depth != 80:
            raise ValueError('Changed retrieval depth')
        return {}

    def fusion(self, channels, k, depth):
        if (k, depth) != (60, 80):
            raise ValueError('Changed fusion settings')
        return [] if self.no_evidence else [{'chunk_id': SOURCE['chunk_id']}]

    def rerank(self, question, candidates):
        return candidates

    def expand(self, ids):
        return [self.evidence for _ in ids]

    def generate(self, messages, schema):
        item = self.queue.pop(0)
        self.received.append(('generate', messages))
        if item == 'preflight_failed':
            raise ValueError('Controlled no-call identity failure')
        self.chat_calls += 1
        if isinstance(item, Exception):
            raise item
        text = json.dumps(item) if isinstance(item, dict) else item
        return {'message': {'content': text}}

    def render(self, ids, context):
        cite = dict(self.sources[ids[0]])
        if self.wrong_source:
            cite['source_lines'] = [1, 3]
        return 'controlled test answer', [cite]


def run():
    checks, errors, cases = {}, [], {}

    def add(name, ops, expected, reason, calls, nodes=None, question=QUESTION, fault=False):
        try:
            value = Flow(ops, citation_fault=fault).invoke(question)
            sequence = [e['node'] for e in value['events']]
            valid = (
                value['status'] == expected and value['reason'] == reason and value['chat_calls'] == calls
                and value['fault_applied'] is fault
                and (not nodes or sequence == nodes)
                and bool(value['citations']) == (expected == 'answered')
                and all(e['request_id'] == value['request_id'] and e['seq'] == i
                        for i, e in enumerate(value['events'], 1))
                and len(value['attempts']) <= 2
                and sum(a['chat_calls'] for a in value['attempts']) == calls
            )
            if not valid:
                raise ValueError(f'Unexpected contract result {value["status"]}, {value["reason"]}, {sequence}')
            checks[name] = True
            cases[name] = {k: value[k] for k in ('request_id', 'status', 'reason', 'chat_calls', 'attempts', 'events',
                                                'selected_ids', 'fault_applied')}
        except Exception as exc:
            checks[name] = False
            errors.append({'check': name, 'error': str(exc)})

    prefix = list(NODES[:7])
    add('normal', Fixture([NORMAL]), 'answered', None, 1, prefix + ['answer', 'check_citations', 'finish'])
    add('unsupported_version_skips_retrieval', Fixture(), 'refused', 'version_unverified', 0,
        ['route', 'version_check', 'refusal', 'finish'], '请核实2026/27赛季IFAB官方规则的现行有效性。')
    add('no_evidence_refuses_before_generation', Fixture(no_evidence=True), 'refused',
        'no_whole_evidence_within_budget', 0, prefix + ['refusal', 'finish'])
    add('model_refusal', Fixture([REFUSAL]), 'refused', 'insufficient_evidence', 1,
        prefix + ['answer', 'refusal', 'finish'])
    add('model_format_retry_then_success', Fixture(['{', NORMAL]), 'answered', None, 2,
        prefix + ['answer', 'answer', 'check_citations', 'finish'])
    add('format_retries_stop_at_two', Fixture(['{', 'null', NORMAL]), 'failed', 'generation_failed', 2,
        prefix + ['answer', 'answer', 'refusal', 'finish'])
    add('transport_error_is_terminal', Fixture([TimeoutError('simulation'), NORMAL]), 'failed',
        'generation_failed', 1, prefix + ['answer', 'refusal', 'finish'])
    add('post_identity_error_is_terminal', Fixture([UnsafeIdentity('simulation'), NORMAL]), 'failed',
        'generation_failed', 1, prefix + ['answer', 'refusal', 'finish'])
    add('preflight_failure_makes_no_chat_request', Fixture(['preflight_failed', NORMAL]), 'failed',
        'generation_failed', 0, prefix + ['answer', 'refusal', 'finish'])
    add('retrieval_failure_is_operational_failure', Fixture(retrieval_failure=True), 'failed', 'stage_error', 0,
        ['route', 'version_check', 'retrieve', 'refusal', 'finish'])
    add('bad_citation_is_blocked_after_generation', Fixture([NORMAL]), 'failed', 'citation_invalid', 1,
        prefix + ['answer', 'check_citations', 'refusal', 'finish'], fault=True)
    add('changed_source_metadata_is_blocked', Fixture([NORMAL], wrong_source=True), 'failed', 'citation_invalid', 1,
        prefix + ['answer', 'check_citations', 'refusal', 'finish'])

    tight = Fixture(['{', NORMAL])
    _, _, size = pack(QUESTION, [EVIDENCE], tight.answer_policy, tight.prompt)
    tight.answer_policy['input_utf8_byte_budget'] = size
    add('retry_cannot_exceed_prompt_budget', tight, 'failed', 'generation_failed', 1,
        prefix + ['answer', 'refusal', 'finish'])
    try:
        invalid = Fixture()
        Flow(invalid).invoke('   ')
    except ValueError:
        checks['invalid_input_makes_no_calls'] = not invalid.received

    repeated = Fixture([NORMAL, REFUSAL])
    graph = Flow(repeated)
    first, second = graph.invoke(QUESTION), graph.invoke(QUESTION)
    checks['repeated_invocations_have_isolated_ids_and_state'] = (
        first['request_id'] != second['request_id'] and first['status'] == 'answered'
        and second['status'] == 'refused' and second['selected_ids'] == [] and second['chat_calls'] == 1
        and second['events'][0]['seq'] == 1)
    for name, passed in checks.items():
        if not passed and not any(e['check'] == name for e in errors):
            errors.append({'check': name, 'error': 'Control predicate failed'})
    return {
        'status': 'PASS' if all(checks.values()) else 'FAIL', 'passed': sum(checks.values()),
        'total': len(checks), 'checks': checks, 'errors': errors, 'cases': cases,
        'captured_at': now(), 'producer': record(__file__), 'flow_source': record(ROOT / 'scripts/rag_langgraph.py'),
        'new_model_requests': 0, 'new_formal_test_runs': 0, 'new_human_judgments': 0,
        'scope': 'Actual compiled LangGraph. Synthetic adapters deliberately exercise control branches.',
    }


if __name__ == '__main__':
    os.environ['LANGSMITH_TRACING'] = 'false'
    os.environ['LANGCHAIN_TRACING_V2'] = 'false'
    runtime_identity()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    receipt = run()
    write_new(ROOT / args.report, receipt)
    print(json.dumps({k: receipt[k] for k in ('status', 'passed', 'total', 'errors')}))
    raise SystemExit(receipt['status'] != 'PASS')
