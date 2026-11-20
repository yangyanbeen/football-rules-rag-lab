"""Score verifier outputs after inference, without using labels to fix selections."""
import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from statistics import median
from score_e7_mapping import ROOT,read,sha,ratio,percentile
from e7_evidence_map import parse_mapping
from e8_pair_verifier import parse_verdict


def score(ids,c,status):
    mask=[bool(set(ids)&set(v)) for v in c['support_per_point']]
    supported=[cid for cid in ids if any(cid in v for v in c['support_per_point'])]
    grade=('runtime_error' if status=='failed' else 'false_refusal' if status=='refused'
           else 'correct' if all(mask) else 'partial' if any(mask) else 'incorrect')
    return dict(grade=grade,point_mask=mask,supported_ids=supported,unsupported_ids=[cid for cid in ids if cid not in supported])


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--review',type=Path,default=ROOT/'.runtime/phase2/e8-offline/source_review_matrix.json')
    p.add_argument('--out',type=Path,required=True);p.add_argument('--partial',action='store_true');a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    prep=read(a.prepared);old=read(ROOT/'.runtime/phase2/e7-prepared-final/prepared.json');cases={c['case_id']:c for c in old['cases']}
    review=read(a.review)
    truth={(r['case_id'],r['repeat'],r['requirement_index'],r['chunk_id']):r for r in review['reviewed_pairs'] if r['group']=='relations_only'}
    if not a.partial:
        done=read(a.run/'completed.json')
        assert all(sha(a.run/n)==h for n,h in done['hashes'].items())
        assert read(a.run/'metadata.json')['prepared_sha256']==sha(a.prepared)
    pairs=[];confusion=Counter();cost=dict(input_tokens=0,output_tokens=0,model_calls=0,rejected_attempts=0,retries=0,total_pair_seconds=0,unknown_token_calls=0)
    for planned in prep['pairs']:
        path=a.run/(planned['pair_id']+'.json')
        if not path.exists():continue
        t=read(path);expected=truth[(t['case_id'],t['repeat'],t['requirement_index'],t['paragraph']['chunk_id'])]
        assert expected['requirement']==t['requirement']
        actual=t['verdict']['relation'] if t['verdict'] else 'protocol_failure'
        if t['verdict']:
            response=t['attempts'][-1]['response']
            assert parse_verdict(response['message']['content'],t['paragraph']['content_zh'])==t['verdict']
        confusion[expected['label'],actual]+=1
        rs=[at.get('response') for at in t['attempts']]
        pin=sum((r or {}).get('prompt_eval_count',0) for r in rs);pout=sum((r or {}).get('eval_count',0) for r in rs)
        rejects=sum(at['error'] is not None for at in t['attempts'])
        row=dict(pair_id=t['pair_id'],case_id=t['case_id'],repeat=t['repeat'],requirement_index=t['requirement_index'],
            requirement=t['requirement'],chunk_id=t['paragraph']['chunk_id'],profile=expected['profile'],
            reviewed_relation=expected['label'],model_relation=actual,agrees=actual==expected['label'],
            false_direct_support=actual=='direct_support' and expected['label']!='direct_support',
            missed_direct_support=actual!='direct_support' and expected['label']=='direct_support',
            quotes=t['verdict']['quotes'] if t['verdict'] else [],reason=t['verdict']['reason'] if t['verdict'] else None,
            reviewed_quotes=expected['quotes'],reviewed_note=expected['note'],model_calls=t['model_calls'],
            retries=max(0,len(t['attempts'])-1),rejected_attempts=rejects,input_tokens=pin,output_tokens=pout,
            seconds=t['seconds'],trace_file=path.name,trace_sha256=sha(path))
        pairs.append(row)
        for key in ('input_tokens','output_tokens','model_calls','rejected_attempts','retries'):cost[key]+=row[key]
        cost['total_pair_seconds']+=t['seconds'];cost['unknown_token_calls']+=sum(r is None for r in rs)
    cost.update(pair_latency_p50_seconds=median([v['seconds'] for v in pairs]) if pairs else None,
        pair_latency_p95_seconds=percentile([v['seconds'] for v in pairs],.95))
    rows=[]
    for c in prep['cases']:
        path=a.run/f"result-{c['case_id']}-r{c['repeat']}.json"
        if not path.exists():continue
        t=read(path);oldcase=cases[c['case_id']]
        if t['requirements'] is not None:
            assert [r['requirement'] for r in t['requirements']]==[r['requirement'] for r in c['requirements']]
            selection,audit=parse_mapping(json.dumps({'requirements':t['requirements']},ensure_ascii=False),c['offered_ids'],3)
            assert t['selected_ids']==selection['chunk_ids'] and t['selection_audit']==audit
            for i,req in enumerate(t['requirements']):
                accepted=[v['chunk_id'] for v in pairs if v['case_id']==c['case_id'] and v['repeat']==c['repeat']
                          and v['requirement_index']==i and v['model_relation']=='direct_support']
                assert req['supporting_ids']==accepted
        base=score(c['original_selected_ids'],oldcase,'answered' if c['original_selected_ids'] else 'refused')
        candidate=score(t['selected_ids'],oldcase,t['status'])
        rows.append(dict(case_id=c['case_id'],repeat=c['repeat'],control=base,candidate=candidate,
            control_selected_ids=c['original_selected_ids'],selected_ids=t['selected_ids'],requirements=t['requirements'],
            verifier_calls=t['verifier_calls'],verifier_seconds=t['verifier_seconds'],trace_file=path.name,trace_sha256=sha(path)))
    groups={}
    for key in dict.fromkeys(c['case_id'] for c in prep['cases']):
        vals=[r for r in rows if r['case_id']==key]
        groups[key]={arm:dict(grades=dict(Counter(r[arm]['grade'] for r in vals)),
            point_masks=[r[arm]['point_mask'] for r in vals]) for arm in ('control','candidate')}
    definitions=[v for v in pairs if v['chunk_id']=='L12-15' and v['profile'] in ('technical_misconduct','technical_physical')]
    gates={};decision='IN_PROGRESS'
    if not a.partial:
        gate=read(a.run/'D036_zero_call.json')
        zero=(gate['experimental_entry']['verification_calls']==0 and gate['experimental_entry']['retrieval_calls']==0
              and gate['experimental_entry']['answer_calls']==0 and gate['original_graph']['chat_calls']==0 and not gate['original_graph']['retrieved_ids'])
        if prep['stage']=='minimal':
            assert len(pairs)==60 and len(rows)==4
            gates=dict(T026_expanded_at_least_3_correct=sum(r['candidate']['grade']=='correct' for r in rows)>=3,
                L12_15_not_direct_for_concept=not any(v['model_relation']=='direct_support' for v in definitions),
                technical_completion=all(v['model_relation']!='protocol_failure' for v in pairs),D036_zero_calls=zero)
        else:
            gates=dict(four_false_refusal_recoveries=all(groups[q+'-native']['candidate']['grades'].get('correct',0)==4 for q in ('D001','D002','D003','D012')),
                D021_reverse_claim_refuted=all(v['model_relation']=='refutation' for v in pairs if v['profile']=='free_negative' and v['chunk_id']=='L13-05'),
                D021_reverse_claim_never_direct=not any(v['model_relation']=='direct_support' for v in pairs if v['profile']=='free_negative'),
                technical_completion=all(v['model_relation']!='protocol_failure' for v in pairs),D036_zero_calls=zero)
        decision='STAGE_PASS' if all(gates.values()) else 'STOP_E8_VERIFIER'
    result=dict(stage=prep['stage'],decision=decision,gates=gates,groups=groups,cost=cost,
        pair_observations=len(pairs),distinct_requirement_paragraph_pairs=len(set((v['requirement'],v['chunk_id']) for v in pairs)),
        relation_agreement=ratio(sum(v['agrees'] for v in pairs),len(pairs)),
        false_direct_support=sum(v['false_direct_support'] for v in pairs),missed_direct_support=sum(v['missed_direct_support'] for v in pairs),
        confusion_matrix=[dict(reviewed=k[0],model=k[1],count=n) for k,n in sorted(confusion.items())],
        L12_15_definition_observations=definitions,
        new_false_refusals=[dict(case_id=r['case_id'],repeat=r['repeat']) for r in rows if r['candidate']['grade']=='false_refusal' and r['control']['grade']!='false_refusal'],
        case_results=rows,pair_results=pairs,new_requirement_generation_calls=0,new_answer_synthesis_calls=0,
        holdout_used=False,full90_executed=False,review='Codex source reading, not new human/expert adjudication; semantic labels scored after inference and never repair the live coverage matrix.')
    (a.out/'metrics.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    buf=io.StringIO();w=csv.writer(buf,lineterminator='\n')
    cols=['pair_id','requirement','chunk_id','reviewed_relation','model_relation','false_direct_support','missed_direct_support','quotes','reviewed_note','input_tokens','output_tokens','model_calls','seconds','trace_sha256']
    w.writerow(cols)
    for r in pairs:w.writerow([json.dumps(r[k],ensure_ascii=False) if isinstance(r[k],list) else r[k] for k in cols])
    (a.out/'pair_audit.csv').write_bytes(b'\xef\xbb\xbf'+buf.getvalue().encode())
    print(json.dumps({k:result[k] for k in ('stage','decision','gates','groups','cost','pair_observations','relation_agreement','false_direct_support','missed_direct_support')},ensure_ascii=False))

if __name__=='__main__':main()
