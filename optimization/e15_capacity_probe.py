"""Capacity-only normal-entry probe; never dispatch a heavy ordinary question."""
import argparse,json,os
from pathlib import Path
import e14_probe

def main(a):
    os.environ['FOOTBALL_JIT_RERANKER']='1'
    e14_probe.CASES=[('D036_capacity','某联赛队员累计三张黄牌一定停赛几场？没有给联赛和赛季。',True)]
    e14_probe.main(a)
    done=json.loads((a.out/'probe-completed.json').read_text('utf8'));rows=[]
    for name in done['hashes']:
        r=json.loads((a.out/name).read_text('utf8'));v=r['result']
        rows.append(dict(entry=r['entry'],seconds=r['seconds'],before_available_GiB=r['before']['available_GiB'],
            minimum_available_GiB=r['resources']['available_min_GiB'],after_available_GiB=r['after_2s']['available_GiB'],
            before_models=r['before_models'],error=r['error'],zero_query_and_answer=bool(v and v['status']=='refused' and v['retrieval'] is None and not v['attempts']),
            heavy_constructed=any(e['stage'] in ('reranker_construction_start','jit_reranker_construction_start','lazy_retrieval_construction_start') for e in r['events'])))
    result=dict(scope='Capacity-only D036 gate and resident frontend; no ordinary answer/rerank experiment or acceptance.',
        status=done['status'],observations=rows,full28_executed=False,full90_executed=False,holdout40_used=False)
    (a.out/'capacity-result.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--server-pid',type=int,required=True);p.add_argument('--ui-pid',type=int,required=True);main(p.parse_args())
