"""Adversarial protocol checks; substring validation is intentionally not a judge."""
import json
from e8_pair_verifier import parse_verdict,make_messages


def run():
    body='甲可能发生。乙不得发生。数值至少9.15米。'
    def dump(label,quotes,reason='原文依据'):return json.dumps(dict(relation=label,quotes=quotes,reason=reason),ensure_ascii=False)
    count=0
    for label,quotes in [('direct_support',['甲可能发生。']),('partial_support',['数值至少9.15米。']),
                         ('refutation',['乙不得发生。']),('unrelated',[])]:
        assert parse_verdict(dump(label,quotes),body)['relation']==label;count+=1
    invalid=[dump('direct_support',[]),dump('refutation',[]),dump('partial_support',[]),
             dump('unrelated',['甲可能发生。']),dump('support',['甲可能发生。']),
             dump(True,[]),dump('direct_support',['甲不会发生。']),
             dump('direct_support',['数值至少9.14米。']),dump('direct_support',['甲可能发生...']),
             dump('direct_support',[' ']),dump('direct_support',[1]),dump('direct_support',[True]),
             dump('direct_support',['甲可能发生。']*4),dump('direct_support','甲可能发生。'),
             dump('direct_support',None),dump('direct_support',['甲可能发生。'],''),
             dump('direct_support',['甲可能发生。'],' '),dump('direct_support',['甲可能发生。'],'长'*161),
             '{}','null','[]','{"relation":"unrelated","quotes":[],"reason":"x","extra":true}',
             '{"relation":"unrelated","relation":"direct_support","quotes":[],"reason":"x"}']
    for raw in invalid:
        try:parse_verdict(raw,body)
        except (ValueError,TypeError):count+=1
        else:raise AssertionError(raw)
    # A wrong semantic decision with a real quotation remains lexically valid;
    # the independent source audit must catch it, never a hidden gold filter.
    verdict=parse_verdict(dump('direct_support',['乙不得发生。']),body)
    assert not verdict['semantic_support_verified_by_program'];count+=1
    msg=make_messages('是否发生？',dict(chunk_id='x',content_zh=body),'核验')
    assert set(json.loads(msg[1]['content']))=={'requirement','evidence'};count+=1
    for req,paragraph in [('',dict(chunk_id='x',content_zh=body)),('长'*121,dict(chunk_id='x',content_zh=body)),
                          ('问题',dict(chunk_id='x',content_zh=body,expected_label='direct_support')),
                          ('问题',dict(chunk_id='x',content_zh=''))]:
        try:make_messages(req,paragraph,'核验')
        except ValueError:count+=1
        else:raise AssertionError((req,paragraph))
    print(json.dumps(dict(passed=count,model_calls=0,semantic_judging_not_faked=True)))


if __name__=='__main__':run()
