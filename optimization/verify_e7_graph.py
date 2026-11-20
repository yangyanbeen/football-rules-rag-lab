"""Exercise E7 integration through the original graph using controlled responses."""
import copy
import json
from types import SimpleNamespace
from e7_mapping_experiment import ROOT, D, RUN, config, read, build_flow, canonical


def run():
    cfg = config()
    prep = read(ROOT / '.runtime/phase2/e7-prepared/prepared.json')
    prompts = {v: (D / f'prompt_{v}.txt').read_text('utf8') for v in 'AB'}
    corpus = {v['chunk_id']: v for v in map(json.loads, (ROOT / 'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    chat = SimpleNamespace(requests=0)
    ops, flow = build_flow(chat, cfg, prompts, corpus)
    case = next(v for v in prep['cases'] if v['case_id'] == 'T026-expanded')
    payloads = []

    def fake(messages, schema):
        chat.requests += 1
        return {'message': {'content': payloads.pop(0)}}
    ops.fake_generate = fake

    def invoke(raws, variant='B', question=None):
        ops.case = case
        ops.trace = read(ROOT / case['source_trace'])
        ops.variant = variant
        ops.prompt = prompts[variant]
        ops.obs = []
        payloads[:] = [json.dumps(v, ensure_ascii=False) for v in raws]
        result = flow.invoke(question or case['question'])
        return result, copy.deepcopy(ops.obs)

    good = {'requirements': [{'requirement': '定义', 'supporting_ids': ['L12-06']},
                             {'requirement': '处罚', 'supporting_ids': ['L12-15', 'L12-06']}]}
    result, obs = invoke([good])
    assert result['status'] == 'answered' and result['selected_ids'] == ['L12-06']
    assert result['chat_calls'] == 1 and obs[0]['mapping_validation']['covered_count'] == 2
    assert result['citations'][0]['chunk_id'] == 'L12-06'
    bad = {'requirements': [{'requirement': '定义', 'supporting_ids': ['outside']}]}
    result, obs = invoke([bad, good])
    assert result['status'] == 'answered' and result['chat_calls'] == 2
    assert 'mapping_validation_error' in obs[0] and 'mapping_validation' in obs[1]
    assert obs[1]['messages'][:-1] == obs[0]['messages']
    result, obs = invoke([bad, bad])
    assert result['status'] == 'failed' and result['chat_calls'] == 2
    assert result['selected_ids'] == [] and result['citations'] == []
    result, obs = invoke([{'requirements': [{'requirement': '未知', 'supporting_ids': []}]}])
    assert result['status'] == 'refused' and result['reason'] == 'insufficient_evidence'
    result, obs = invoke([{'requirements': [good['requirements'][0], {'requirement': '未知', 'supporting_ids': []}]}])
    assert result['status'] == 'answered' and result['selected_ids'] == ['L12-06']
    a = {'answerable': True, 'chunk_ids': ['L12-06'], 'reason': None}
    result, obs = invoke([a], 'A')
    assert result['status'] == 'answered' and result['selected_ids'] == ['L12-06']
    assert 'mapping_validation' not in obs[0]
    for v in 'AB':
        result, obs = invoke([good], v, read(RUN / 'D036.json')['question'])
        assert result['status'] == 'refused' and not obs and result['chat_calls'] == 0
        assert result['retrieved_ids'] == [] and result['embedding_queries'] == 0
        assert len(payloads) == 1
    # Corrupted source text must fail before consuming any response.
    old = corpus['L12-06']['content_zh']
    corpus['L12-06']['content_zh'] = old + '篡改'
    result, obs = invoke([good])
    assert result['status'] == 'failed' and not obs and result['chat_calls'] == 0
    corpus['L12-06']['content_zh'] = old
    print(json.dumps(dict(passed=9, calls_are_controlled=True, model_inference_calls=0)))


if __name__ == '__main__': run()
