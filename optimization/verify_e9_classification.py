"""Strict enum parsing and no-retry orchestration checks without inference."""
import json
from types import SimpleNamespace
from e9_classification_contract import parse_relation,one_shot,messages_for

def main():
    count=0
    for label in ('direct_support','partial_support','refutation','unrelated'):
        assert parse_relation(json.dumps(dict(relation=label)))==label;count+=1
    for raw in ['null','[]','{}','"direct_support"','{"relation":true}','{"relation":1}',
                '{"relation":"support"}','{"relation":" direct_support"}',
                '{"relation":"DIRECT_SUPPORT"}','{"relation":"direct_support","quotes":[]}',
                '{"relation":"direct_support","reason":"x"}',
                '{"relation":"unrelated","relation":"direct_support"}','{']:
        try:parse_relation(raw)
        except (ValueError,TypeError):count+=1
        else:raise AssertionError(raw)
    payload=dict(requirement='需要查证什么？',evidence=dict(chunk_id='x',content_zh='完整原文。'))
    for raw in ['{"relation":"direct_support"}','{"relation":"unknown"}']:
        chat=SimpleNamespace(requests=0)
        def fake(chat,messages,schema):
            chat.requests+=1;return {'message':{'content':raw}}
        result=one_shot(chat,payload,'分类',fake)
        assert result['model_calls']==1 and result['retries']==0 and chat.requests==1
        assert (result['status']=='accepted')==('unknown' not in raw);count+=1
    try:messages_for({**payload,'expected_relation':'direct_support'},'分类')
    except ValueError:count+=1
    else:raise AssertionError('Scoring label entered model input')
    print(json.dumps(dict(passed=count,model_calls=0,no_retry_verified=True)))
if __name__=='__main__':main()
