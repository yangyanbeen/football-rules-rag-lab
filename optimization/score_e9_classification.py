"""Independent E9 first-answer scoring against the pre-prompt frozen labels."""
import argparse
import csv
import io
import json
from collections import Counter
from pathlib import Path
from statistics import median
from score_e7_mapping import ROOT,read,sha,ratio,percentile
from e8_pair_verifier import LABELS
from e9_classification_contract import parse_relation

D=ROOT/'optimization/experiments/E9_classification'

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--partial',action='store_true');a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    samples=read(D/'samples.json')['samples'];truth={s['sample_id']:s for s in samples}
    if not a.partial:
        done=read(a.run/'completed.json');assert done['observations']==32 and done['model_calls']<=32 and not done['retries'] and not done['warmup_calls']
        assert all(sha(a.run/n)==h for n,h in done['hashes'].items())
    rows=[];variants={}
    for variant in 'PS':
        vals=[]
        for sid,s in truth.items():
            path=a.run/f'{variant}-{sid}.json'
            if not path.exists():continue
            t=read(path);prediction=t['relation']
            if t['status']=='accepted':assert parse_relation(t['response']['message']['content'])==prediction
            else:assert prediction is None
            raw=t.get('response') or {}
            false_direct=prediction=='direct_support' and s['reviewed_relation']!='direct_support'
            missed_direct=prediction!='direct_support' and s['reviewed_relation']=='direct_support'
            if t['status']!='accepted':kind='protocol_failure'
            elif prediction==s['reviewed_relation']:kind=None
            elif missed_direct:kind='missed_direct_support'
            elif false_direct and s['reviewed_relation']=='partial_support':kind='partial_promoted_to_direct'
            elif false_direct and s['reviewed_relation']=='refutation':kind='refuted_assertion_marked_supported'
            elif false_direct:kind='unrelated_marked_supported'
            else:kind='other_relation_confusion'
            r=dict(variant=variant,sample_id=sid,requirement=s['requirement'],chunk_id=s['chunk_id'],
                reviewed_relation=s['reviewed_relation'],model_relation=prediction or 'protocol_failure',
                correct=prediction==s['reviewed_relation'],error_kind=kind,false_direct=false_direct,missed_direct=missed_direct,
                reviewed_quotes=s['reviewed_quotes'],reviewed_note=s['reviewed_note'],
                first_raw=raw.get('message',{}).get('content'),first_error=t['error'],
                model_calls=t['model_calls'],retries=t['retries'],seconds=t['seconds'],
                input_tokens=raw.get('prompt_eval_count',0),output_tokens=raw.get('eval_count',0),
                trace_file=path.name,trace_sha256=sha(path))
            vals.append(r);rows.append(r)
        confusion={label:{col:0 for col in [*LABELS,'protocol_failure']} for label in LABELS}
        for r in vals:confusion[r['reviewed_relation']][r['model_relation']]+=1
        tp=sum(r['correct'] and r['reviewed_relation']=='direct_support' for r in vals)
        predicted=sum(r['model_relation']=='direct_support' for r in vals)
        positive=sum(r['reviewed_relation']=='direct_support' for r in vals)
        gates={}
        if not a.partial:
            assert len(vals)==16
            by={r['sample_id']:r['model_relation'] for r in vals}
            gates=dict(protocol_16_of_16=all(r['model_relation']!='protocol_failure' for r in vals),
                direct_recall_at_least_5_of_6=tp>=5,
                zero_false_direct_support=not any(r['false_direct'] for r in vals),
                L12_06_direct=all(by[k]=='direct_support' for k in ('S01','S02')),
                L12_15_partial=all(by[k]=='partial_support' for k in ('S07','S08')),
                D021_refutation=by['S12']=='refutation',agreement_at_least_13_of_16=sum(r['correct'] for r in vals)>=13)
        variants[variant]=dict(observations=len(vals),protocol_pass=ratio(sum(r['model_relation']!='protocol_failure' for r in vals),len(vals)),
            agreement=ratio(sum(r['correct'] for r in vals),len(vals)),direct_precision=ratio(tp,predicted),direct_recall=ratio(tp,positive),
            false_direct=sum(r['false_direct'] for r in vals),partial_promoted=sum(r['error_kind']=='partial_promoted_to_direct' for r in vals),
            confusion_matrix=confusion,errors=[r for r in vals if not r['correct']],gates=gates,
            passed=bool(gates) and all(gates.values()),model_calls=sum(r['model_calls'] for r in vals),retries=sum(r['retries'] for r in vals),
            input_tokens=sum(r['input_tokens'] for r in vals),output_tokens=sum(r['output_tokens'] for r in vals),
            total_seconds=sum(r['seconds'] for r in vals),latency_p50_seconds=median([r['seconds'] for r in vals]) if vals else None,
            latency_p95_seconds=percentile([r['seconds'] for r in vals],.95),first_observation_seconds=vals[0]['seconds'] if vals else None,
            subsequent_latency_p50_seconds=median([r['seconds'] for r in vals[1:]]) if len(vals)>1 else None)
    winner=None;decision='IN_PROGRESS'
    if not a.partial:
        passing=[v for v in 'PS' if variants[v]['passed']]
        if passing:
            winner=max(passing,key=lambda v:(variants[v]['agreement']['numerator'],variants[v]['direct_recall']['numerator'],v=='P'))
            decision='SMALL_SAMPLE_PASS'
        else:decision='STOP_PAIRWISE_VERIFIER_ROUTE'
    result=dict(decision=decision,selected_variant=winner,variants=variants,cases=rows,
        freeze_sha256=sha(D/'samples.json'),plan_sha256=sha(D/'plan.json'),
        E8_comparison_caveat='E8 60 pairs and E9 16 distinct pairs have different class mixes; do not compare their overall agreement as an accuracy gain. P vs S uses exactly the same frozen pairs.',
        refutation_caveat='Only one distinct E8-reviewed refutation pair; no general refutation recall estimate.',
        labels_origin='Inherited E8 Codex source reading, no new human/expert adjudication.',
        T026_60_executed=False,expanded_questions_executed=False,sentence_ids_executed=False,batching_executed=False,full90_executed=False,holdout_used=False)
    (a.out/'metrics.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    buf=io.StringIO();w=csv.writer(buf,lineterminator='\n');cols=['variant','sample_id','requirement','chunk_id','reviewed_relation','model_relation','error_kind','first_raw','first_error','input_tokens','output_tokens','model_calls','seconds','trace_sha256']
    w.writerow(cols)
    for r in rows:w.writerow([r[k] for k in cols])
    (a.out/'cases.csv').write_bytes(b'\xef\xbb\xbf'+buf.getvalue().encode())
    print(json.dumps(dict(decision=decision,selected=winner,variants={v:{k:g[k] for k in ('observations','protocol_pass','agreement','direct_precision','direct_recall','false_direct','partial_promoted','gates','model_calls','input_tokens','output_tokens','latency_p50_seconds','latency_p95_seconds')} for v,g in variants.items()}),ensure_ascii=False))

if __name__=='__main__':main()
