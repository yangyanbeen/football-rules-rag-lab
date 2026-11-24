"""Offline E22 packing candidate check; no retrieval or model calls."""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from answer_eval_core import config
from answer_eval_engine import pack


def rows():
    return {r['chunk_id']: r for r in map(json.loads, (ROOT / 'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}


def one(trace, corpus, cfg, prompt):
    result = trace['result']
    ids = [r['chunk_id'] for r in result['retrieval']['reranker']['results']]
    evidence = [corpus[i] for i in ids]
    os.environ.pop('FOOTBALL_PACKING_FILL_TOP10', None)
    base, _, base_bytes = pack(result['question'], evidence, cfg, prompt)
    os.environ['FOOTBALL_PACKING_FILL_TOP10'] = '1'
    candidate, _, candidate_bytes = pack(result['question'], evidence, cfg, prompt)
    return [r['chunk_id'] for r in base], [r['chunk_id'] for r in candidate], base_bytes, candidate_bytes


def main():
    corpus = rows(); cfg = config(); prompt = (ROOT / cfg['prompt_file']).read_text('utf8')
    t034 = json.loads((ROOT / '.runtime/phase2/e15-lowmemory90-01/worker/T034-B.json').read_text('utf8'))
    base, candidate, base_bytes, candidate_bytes = one(t034, corpus, cfg, prompt)
    assert base == ['L01-07', 'L07-03', 'L14-03', 'L05-03']
    assert candidate == ['L01-07', 'L07-03', 'L14-03', 'L05-03', 'L14-01']
    assert candidate_bytes == 6069 and candidate_bytes <= 6200

    audit = json.loads((ROOT / '.runtime/six-layer/e21-full-regression-audit.json').read_text('utf8'))
    changed = []; missing = []; max_bytes = 0; checked = 0
    for case in audit['suites'][0]['cases']:
        trace = json.loads((ROOT / case['raw_record']['path']).read_text('utf8'))
        if not trace['result'].get('retrieval'):
            continue
        checked += 1
        old, new, _, nbytes = one(trace, corpus, cfg, prompt)
        assert len(new) <= cfg['max_context_chunks'] and nbytes <= cfg['input_utf8_byte_budget']
        pos = [new.index(v) for v in old]
        assert pos == sorted(pos) and new[:len(old)] == old
        if old != new:
            changed.append(case['question_id'])
        for expected in case.get('annotated_expected_ids', []):
            if expected not in new:
                missing.append((case['question_id'], expected))
        max_bytes = max(max_bytes, nbytes)
    os.environ.pop('FOOTBALL_PACKING_FILL_TOP10', None)
    assert checked == 86
    assert changed == ['D002', 'D013', 'D026', 'D033', 'T002', 'T004', 'T006', 'T013', 'T017', 'T023', 'T026', 'T034', 'T048']
    assert missing == [('T022', 'L09-03')]
    print(json.dumps(dict(passed=True, t034=dict(base=base, candidate=candidate, bytes=candidate_bytes),
                          checked=checked, changed=changed, missing=missing, max_bytes=max_bytes,
                          new_model_calls=0, services_started=False), ensure_ascii=False))


if __name__ == '__main__':
    main()
