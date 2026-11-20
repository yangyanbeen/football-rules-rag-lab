"""Contract and independent bit-mask oracle checks for the E7 selector."""
import itertools
import json
import random
from e7_evidence_map import mapping_schema, parse_mapping


def run():
    offered = ['a', 'b', 'c', 'd', 'e']
    count = 0

    def parse(reqs):
        return parse_mapping(json.dumps({'requirements': reqs}), offered)

    def req(text, ids):
        return dict(requirement=text, supporting_ids=ids)

    assert parse([req('x', ['a', 'b']), req('y', ['b'])])[0]['chunk_ids'] == ['b']
    assert parse([req('x', ['b', 'a'])])[0]['chunk_ids'] == ['a']
    assert parse([req('x', ['e']), req('y', ['b'])])[0]['chunk_ids'] == ['b', 'e']
    assert parse([req('x', []), req('y', [])])[0] == dict(answerable=False, chunk_ids=[], reason='insufficient_evidence')
    assert parse([req('x', []), req('y', ['c', 'c'])])[0]['chunk_ids'] == ['c']
    assert parse([req(str(i), [c]) for i, c in enumerate(offered)])[0]['chunk_ids'] == ['a', 'b', 'c']
    count += 6
    invalid = [None, [], {}, {'requirements': []}, {'requirements': 'x'},
        {'requirements': [req('x', ['outside'])]}, {'requirements': [req('', [])]},
        {'requirements': [req(' ', [])]}, {'requirements': [req('x', None)]},
        {'requirements': [req('x', [1])]}, {'requirements': [req('x', [True])]},
        {'requirements': [req('x', ['a'] * 6)]},
        {'requirements': [req('x', []), req(' x ', [])]},
        {'requirements': [req('x' * 121, [])]},
        {'requirements': [req(str(i), []) for i in range(9)]},
        {'requirements': [dict(requirement='x', supporting_ids=[], answerable=True)]},
        {'requirements': [req('x', [])], 'answerable': True},
        {'requirements': [{'supporting_ids': []}]}]
    for value in invalid:
        try: parse_mapping(json.dumps(value), offered)
        except (ValueError, TypeError): count += 1
        else: raise AssertionError(value)
    for value in ['{"requirements":[],"requirements":[]}', '{', 'null']:
        try: parse_mapping(value, offered)
        except ValueError: count += 1
        else: raise AssertionError(value)
    for ids, cap in [([], 3), (['a'] * 2, 3), (offered + ['f'], 3), (offered, 4), (offered, True)]:
        try: mapping_schema(ids, cap)
        except ValueError: count += 1
        else: raise AssertionError((ids, cap))
    rng = random.Random(42)
    for _ in range(600):
        masks = [rng.randrange(32) for _ in range(rng.randrange(1, 9))]
        reqs = [req(str(i), [c for j, c in enumerate(offered) if mask & (1 << j)]) for i, mask in enumerate(masks)]
        selection, audit = parse(reqs)
        choices = []
        for subset in range(32):
            if subset.bit_count() > 3: continue
            indices = tuple(i for i in range(5) if subset & (1 << i))
            choices.append((-sum(bool(subset & m) for m in masks), len(indices), indices))
        best = min(choices)
        assert selection['chunk_ids'] == [offered[i] for i in best[2]]
        assert audit['covered_count'] == -best[0]
        assert selection['answerable'] == bool(best[2])
        count += 1
    print(json.dumps(dict(passed=count, randomized_oracle_cases=600)))


if __name__ == '__main__': run()
