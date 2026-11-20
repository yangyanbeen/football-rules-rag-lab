"""Pre-register and run E7 on unchanged archived evidence, with paired live Qwen calls."""
import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'
from answer_eval_core import canonical, config, read, record, parse_selection
from answer_json_chat import generate, selection_schema
from rag_b0 import PinnedChat
from rag_langgraph import Operations, CountingChat
from citation_catalog_guard import safe_render
from e5_second_candidate import inputs, check_refs, module, BASE, RUN, sha, write
from e7_evidence_map import mapping_schema, parse_mapping

D = ROOT / 'optimization/experiments/E7_evidence_mapping'


def candidate_files():
    paths = [Path(__file__), ROOT / 'optimization/e7_evidence_map.py',
             ROOT / 'optimization/verify_e7_evidence_map.py', ROOT / 'optimization/verify_e7_graph.py', *D.glob('*')]
    return {p.relative_to(ROOT).as_posix(): record(p) for p in paths if p.is_file()}


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    cfg = config()
    assert not subprocess.check_output(['git', 'diff', BASE, '--', 'scripts', 'config'], cwd=ROOT)
    prompts = {'A': (ROOT / cfg['prompt_file']).read_text('utf8'),
               'B': (D / 'prompt_B.txt').read_text('utf8')}
    (D / 'prompt_A.txt').write_bytes(prompts['A'].encode())
    prior = ROOT / '.runtime/phase2/e6-prepared-final/prepared.json'
    reviews = copy.deepcopy(read(prior)['cases'])
    addendum_path = ROOT / 'optimization/experiments/E6_evidence_selection/review_addendum.json'
    addendum = read(addendum_path)
    for c in reviews:
        extras = addendum['cases'].get(c['case_id'], {}).get('extra_support_per_point', [[] for _ in c['necessary_points']])
        c['support_per_point'] = [list(dict.fromkeys(a + b)) for a, b in zip(c['support_per_point'], extras)]
        c['review'] = 'Pre-run E6 source review, including documented equivalent-source addendum, reused before E7 inference; Codex review, not human/expert review.'
    qs = {v['question_id']: v for v in map(json.loads, (ROOT / 'data/eval/answer_eval.jsonl').read_text('utf8').splitlines())}
    # These are scoring-only source reviews. Neither these nor any other labels
    # are included in the model's messages, schema, or deterministic selector.
    extra_supports = {'D002': [['L01-03'], ['L01-03']],
                      'D003': [['L02-02'], ['L02-02']],
                      'D012': [['L10-01'], ['L10-01', 'L10-02']]}
    for qid, supports in extra_supports.items():
        path = RUN / (qid + '.json')
        t = read(path)
        at = t['observations']['model_attempts'][0]
        reviews.append(dict(case_id=qid + '-native', question_id=qid, context='native',
            question=t['question'], necessary_points=qs[qid]['expected_answer_points'],
            support_per_point=supports, context_covers_all_points=True,
            offered_ids=t['result']['offered_ids'], source_trace=path.relative_to(ROOT).as_posix(),
            source_sha256=sha(path), messages=at['messages'], schema=at['schema'],
            retrieved_ids=t['result']['retrieved_ids'],
            review='Codex direct reading of actual offered source paragraphs before E7 inference; not human/expert review.'))
    preflight = []
    for c in reviews:
        path = ROOT / c['source_trace']
        assert sha(path) == c['source_sha256']
        at = read(path)['observations']['model_attempts'][0]
        assert c['messages'] == at['messages'] and c['schema'] == at['schema']
        ev = json.loads(at['messages'][1]['content'])['evidence']
        assert [v['chunk_id'] for v in ev] == c['offered_ids']
        assert len(ev) <= 5 and at['schema'] == selection_schema(c['offered_ids'], 3)
        for v in 'AB':
            messages = copy.deepcopy(at['messages'])
            messages[0]['content'] = prompts[v]
            schema = selection_schema(c['offered_ids'], 3) if v == 'A' else mapping_schema(c['offered_ids'], 3)
            size = len(canonical(messages))
            preflight.append(dict(case_id=c['case_id'], variant=v, prompt_bytes=size,
                schema_bytes=len(canonical(schema)), messages_plus_schema_bytes=size + len(canonical(schema)),
                within_message_budget=size <= 6200,
                archived_actual_prompt_tokens_A=at['response'].get('prompt_eval_count'),
                conservative_token_upper_bound=size + len(canonical(schema)) + cfg['chat_template_token_reserve'] + cfg['llm']['num_predict'],
                context_tokens=cfg['llm']['num_ctx']))
            assert messages[1:] == at['messages'][1:]
    write(out / 'budget_preflight.json', dict(rows=preflight,
        budget_applies_to='Existing 6200 UTF-8 byte budget covers canonical messages, not format Schema. Schema size also reported; UTF-8 bytes are only a conservative token upper bound, not tokenizer measurement.',
        overflow=[r for r in preflight if not r['within_message_budget']],
        evidence_deleted_or_reordered=False))
    assert all(r['within_message_budget'] for r in preflight), 'Budget exceeded: stop without repacking'
    # Put the primary failure and multiple full-evidence false-refusal probes first.
    order = ['T026-expanded', 'D001-native', 'D002-native', 'D003-native', 'D012-native',
             'T026-native', 'D004-native', 'D009-native', 'D017-native', 'T034-expanded',
             'T034-native', 'T014-native', 'D019-native', 'D021-native']
    by = {c['case_id']: c for c in reviews}
    assert set(order) == set(by)
    reviews = [by[k] for k in order]
    schedule = [dict(case_id=key, variant=v, repeat=rep)
                for rep in range(1, 5) for pos, key in enumerate(order)
                for v in ('AB' if (rep + pos) % 2 else 'BA')]
    review = dict(cases=[{k: v for k, v in c.items() if k not in ('messages', 'schema', 'retrieved_ids')} for c in reviews],
        inherited_review=str(prior.relative_to(ROOT)), inherited_sha256=sha(prior),
        inherited_addendum=record(addendum_path),
        scope='Independent source/point assessment; labels never supplied to answering model. Equivalent source support permitted. T034-native lacks first point.')
    (D / 'point_evidence_review.json').write_bytes((json.dumps(review, ensure_ascii=False, indent=2) + '\n').encode())
    manifest = dict(control_commit=BASE, experiment='E7: explicit requirement mapping + deterministic selection, one candidate',
        contexts=len(reviews), independent_questions=len(set(c['question_id'] for c in reviews)),
        scheduled_invocations=len(schedule), repeats_per_arm_per_context=4, schedule=schedule,
        gates={
            'T026_expanded': 'B >= 3/4 fully correct with source support',
            'T026_native': 'B 4/4 at least partial',
            'full_evidence_refusal': 'At least one of D001/D002/D003/D012: A repeatedly refuses (>=2), B correct 4/4; report all cases',
            'correct_controls': 'D004/D009/D017 B correct 4/4, no new false refusals, citation numerator/denominator ratio >= same-round A, list each newly unsupported ID',
            'T034_expanded': 'B correct 4/4; native evaluated against available scope separately',
            'technical': 'All valid, <=2 attempts each; report schema failures, retries, budget, tokens and latency',
            'D036': 'Both arms refused before retrieval/generation; zero calls',
            'overall_citation': 'Full-evidence pilot citation support >= concurrent A',
            'no_new_false_refusals': 'No B refusal where paired A answered'},
        full90_only_if_all_pilot_gates_pass=True, holdout_used=False, model=cfg['llm'],
        parser_max_requirements=8, parser_requirement_max_chars=120, selected_limit=3,
        partial_contract='At least one mapped supported point -> existing extractive answer; none -> insufficient_evidence. No additional synthesis call.',
        schema_refusal_limitation='Mapping Schema has no source_conflict/version reason field; upstream version/business gates retained. Semantic conflicts must map no support and receive insufficient_evidence; score failures independently.',
        scoring_method='Frozen point-source annotations plus Codex direct reading of model requirement text and source support. Program verifies IDs/coverage, never semantic truth. Not human/expert adjudication.',
        prompt_hashes={v:sha(D/f'prompt_{v}.txt') for v in 'AB'})
    (D / 'manifest.json').write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode())
    write(out / 'prepared.json', dict(cases=reviews, schedule=schedule, prompt_hashes=manifest['prompt_hashes'],
        source_files=inputs(), candidate_files=candidate_files(), review_sha256=sha(D/'point_evidence_review.json'),
        holdout_used=False))
    print(json.dumps(dict(contexts=len(reviews), unique_questions=manifest['independent_questions'], invocations=len(schedule),
        max_message_bytes=max(v['prompt_bytes'] for v in preflight),
        conservative_token_bound_overflows=[r for r in preflight if r['conservative_token_upper_bound'] > r['context_tokens']]), ensure_ascii=False))


def build_flow(chat, cfg, prompts, corpus):
    from task13_audit import source_map
    graph = module(BASE, 'scripts/rag_langgraph.py', 'e7_fixed_graph')

    class Frozen(Operations):
        @property
        def completed_embeddings(self): return 0
        def retrieval(self, *args): return copy.deepcopy(self.trace['observations']['channels'])
        def fusion(self, *args): return copy.deepcopy(self.trace['observations']['fused'])
        def rerank(self, *args):
            return copy.deepcopy(self.trace['observations'].get('reranked', [{'chunk_id': c} for c in self.trace['result']['retrieved_ids']]))
        def expand(self, ids): return [corpus[c] for c in ids]
        def generate(self, messages, schema):
            item = dict(messages=messages, schema=schema)
            self.obs.append(item)
            try:
                response = self.fake_generate(messages, schema) if hasattr(self, 'fake_generate') else super().generate(messages, schema)
                item['response'] = response
                return response
            except Exception as exc:
                item['error'] = type(exc).__name__ + ': ' + str(exc)
                if hasattr(exc, 'response'): item['response'] = exc.response
                raise

    ops = Frozen(None, chat, cfg, prompts['A'], source_map())
    ops.variant = 'A'
    ops.obs = []

    def fixed_pack(q, evidence, cfg, prompt):
        assert q == ops.case['question'] and [r['chunk_id'] for r in evidence] == ops.case['retrieved_ids']
        messages = copy.deepcopy(ops.case['messages'])
        messages[0]['content'] = prompt
        size = len(canonical(messages))
        assert size <= cfg['input_utf8_byte_budget'], 'Never trim frozen evidence to fit'
        return [corpus[c] for c in ops.case['offered_ids']], messages, size

    def schema(offered, limit):
        return selection_schema(offered, limit) if ops.variant == 'A' else mapping_schema(offered, limit)

    def parse(content, offered, policy):
        if ops.variant == 'A': return parse_selection(content, offered, policy)
        try:
            selection, audit = parse_mapping(content, offered, policy['max_selected_chunks'])
            # Reuse the original selection validator before the original graph's
            # provenance/citation checks and unmodified source rendering.
            selection = parse_selection(json.dumps(selection), offered, policy)
            ops.obs[-1]['mapping_validation'] = audit
            return selection
        except (ValueError, TypeError, KeyError) as exc:
            ops.obs[-1]['mapping_validation_error'] = type(exc).__name__ + ': ' + str(exc)
            raise

    graph.pack = fixed_pack
    graph.selection_schema = schema
    graph.parse_selection = parse
    return ops, graph.Flow(ops)


def pilot(out, prepared):
    out.mkdir(parents=True, exist_ok=False)
    data = read(prepared)
    check_refs(data['source_files'])
    check_refs(data['candidate_files'])
    cfg = config()
    prompts = {v: (D / f'prompt_{v}.txt').read_text('utf8') for v in 'AB'}
    corpus = {v['chunk_id']: v for v in map(json.loads, (ROOT / 'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    from run_langgraph_flow import runtime_identity
    ops, flow = build_flow(CountingChat(PinnedChat(cfg)), cfg, prompts, corpus)
    write(out / 'metadata.json', dict(source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        control_commit=BASE, prepared_sha256=sha(prepared), candidate_files=data['candidate_files'],
        model=cfg['llm'], environment=runtime_identity(), schedule=data['schedule'],
        scope='Real answering model; frozen retrieval/body/order. Schema and selection policy are the only experimental stage. No fresh retrieval; no extra synthesis calls.', holdout_used=False))
    warm = generate(ops.chat, [{'role': 'system', 'content': '只输出一个JSON对象。'}, {'role': 'user', 'content': '返回ready为true。'}],
                    {'type': 'object', 'properties': {'ready': {'const': True}}, 'required': ['ready'], 'additionalProperties': False})
    write(out / 'warmup.json', dict(response=warm, excluded=True))
    hashes = {}
    by = {v['case_id']: v for v in data['cases']}
    for ix, item in enumerate(data['schedule'], 1):
        ops.case = by[item['case_id']]
        ops.trace = read(ROOT / ops.case['source_trace'])
        ops.variant = item['variant']
        ops.prompt = prompts[ops.variant]
        ops.obs = []
        result = flow.invoke(ops.case['question'])
        assert result['chat_calls'] == len(ops.obs) == len(result['selection_audits']) <= 2
        assert result['offered_ids'] == ops.case['offered_ids']
        for at in ops.obs:
            assert at['messages'][1:len(ops.case['messages'])] == ops.case['messages'][1:]
            expected = ops.case['schema'] if ops.variant == 'A' else mapping_schema(ops.case['offered_ids'], 3)
            assert at['schema'] == expected
        if result['status'] != 'failed':
            assert safe_render(result['selected_ids'], corpus) == (result['answer'], result['citations'])
        name = f"{item['case_id']}-{item['variant']}-r{item['repeat']}.json"
        write(out / name, dict(**item, question_id=ops.case['question_id'], question=ops.case['question'],
            result=result, observations={'model_attempts': ops.obs}, actual_new_embedding_calls=0, actual_new_reranker_calls=0))
        hashes[name] = sha(out / name)
        last = ops.obs[-1].get('mapping_validation', {}) if ops.obs else {}
        print(json.dumps(dict(done=ix, total=len(data['schedule']), **item, status=result['status'],
            selected=result['selected_ids'], requirements=last.get('requirements')), ensure_ascii=False), flush=True)
    gates = []
    for variant in 'AB':
        ops.variant = variant
        ops.prompt = prompts[variant]
        ops.obs = []
        before = ops.chat_calls
        result = flow.invoke(read(RUN / 'D036.json')['question'])
        assert result['status'] == 'refused' and result['chat_calls'] == 0 and ops.chat_calls == before and not ops.obs
        assert result['retrieved_ids'] == [] and result['embedding_queries'] == 0
        gates.append(dict(variant=variant, result=result))
    write(out / 'D036_zero_call.json', gates)
    check_refs(data['source_files'])
    check_refs(data['candidate_files'])
    write(out / 'completed.json', dict(records=len(hashes), hashes=hashes, inputs_unchanged=True))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['prepare', 'pilot'])
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--prepared', type=Path)
    args = p.parse_args()
    prepare(args.out) if args.mode == 'prepare' else pilot(args.out, args.prepared)


if __name__ == '__main__': main()
