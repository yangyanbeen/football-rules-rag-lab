"""Four explicit Task12 robustness probes; never counted as formal quality samples."""
import argparse,copy,json
from answer_eval_core import *


def main():
    from answer_eval_engine import AnswerEngine
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True);a=p.parse_args()
    source=git('rev-parse','HEAD');source_records=committed_inputs(source)
    engine=AnswerEngine();cases=[]
    try:
        corpus=engine.retriever.dense.by_id
        real_negative=copy.deepcopy(corpus['L01-03'])
        conflict=[]
        for cid,value in [('L01-03','7.32'),('L01-04','8.00')]:
            r=copy.deepcopy(corpus[cid]);r['content_zh']=f'受控测试资料，同一实验规则版本X、同一成人球门的内侧宽度必须为{value}米。两份资料权威等级相同，未提供优先关系。'
            r['content_zh_sha256']=digest(r['content_zh'].encode());r['needs_rule_review']=True;r['review_notes']=['Synthetic conflict fixture, not a real football rule or source claim'];conflict.append(r)
        definitions=[('outside','这份资料能告诉我此刻某场比赛的实时比分吗？',None,'real query against fixed corpus'),
          ('version','请确认2026赛季IFAB最新官方足球规则。',None,'real official-version request'),
          ('similar_negative','人造草坪的颜色有什么限制？',[real_negative],'real human-approved D001 hard negative L01-03 only; no positive evidence'),
          ('source_conflict','同一实验规则版本X的成人球门内侧宽度到底是多少？',conflict,'synthetic contradictory same-version sources, not a football quality sample')]
        for name,question,evidence,scope in definitions:
            result=engine.answer(question,evidence);trace=PRIVATE/'probes'/(name+'.json');write_new(trace,result)
            row={'id':name,'question':question,'scope':scope,'status':result['status'],'refusal_reason':result['refusal_reason'],'error':result['error'],
              'passed':result['status']=='refused' and result['error'] is None,'trace':record(trace),'selected_ids':result['selected_ids'],
              'answer_sha256':digest(result['answer'].encode()),'generation_attempts':len(result['attempts'])}
            cases.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    finally:engine.close()
    value={'version':'answer-probes-1.0','captured_at':now(),'source_commit':source,'inputs':source_records,'cases':cases,
      'status':'PASS' if all(r['passed'] for r in cases) else 'FAIL','passed':sum(r['passed'] for r in cases),'total':4,
      'scope':'Robustness diagnostics; not formal dataset scores or human reviews. Any failed case remains visible.'}
    write_new(ROOT/a.report,value);return value['status']!='PASS'


if __name__=='__main__':raise SystemExit(main())
