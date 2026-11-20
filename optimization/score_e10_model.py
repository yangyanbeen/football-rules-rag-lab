"""Independent source/point scoring of E10, retaining primary and confirmation."""
import argparse,csv,io,json
from collections import Counter
from pathlib import Path
from statistics import median
from score_e7_mapping import ROOT,read,sha,ratio,percentile

def aggregate(rows):
    return dict(observations=len(rows),grades=dict(Counter(r['score']['grade'] for r in rows)),
        point_coverage=ratio(sum(sum(r['score']['point_mask']) for r in rows),sum(len(r['score']['point_mask']) for r in rows)),
        citation_support=ratio(sum(r['score']['citation_numerator'] for r in rows),sum(r['score']['citation_denominator'] for r in rows)),
        first_protocol=ratio(sum(bool(r['result']['selection_audits']) and r['result']['selection_audits'][0]['normalized_selection'] is not None for r in rows),len(rows)),
        model_calls=sum(r['result']['chat_calls'] for r in rows),retries=sum(max(0,r['result']['chat_calls']-1) for r in rows),
        input_tokens=sum(at.get('response',{}).get('prompt_eval_count',0) for r in rows for at in r['observations']['model_attempts']),
        output_tokens=sum(at.get('response',{}).get('eval_count',0) for r in rows for at in r['observations']['model_attempts']),
        wall_p50_seconds=median([r['result']['wall_ns']/1e9 for r in rows]) if rows else None,
        wall_p95_seconds=percentile([r['result']['wall_ns']/1e9 for r in rows],.95),
        max_wall_seconds=max([r['result']['wall_ns']/1e9 for r in rows] or [0]),
        rss_peak_GiB=max([r['resources']['process_rss_peak_GiB'] for r in rows] or [0]),
        available_min_GiB=min([r['resources']['available_min_GiB'] for r in rows if r['resources']['available_min_GiB'] is not None] or [0]))

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--partial',action='store_true');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    done=read(a.run/'completed.json') if (a.run/'completed.json').exists() else None
    meta=read(a.run/'metadata.json');probe=read(a.run/'deployment_probe.json') if (a.run/'deployment_probe.json').exists() else None
    if done and done['status']=='DEPLOYMENT_PREFLIGHT_FAILED':
        result=dict(decision='NO_DEPLOYABLE_CANDIDATE',quality_evaluated=False,primary_observations=0,probe=probe,model_identity=meta['models'],
            quality_gates=None,cost_gates=dict(deployment_preflight=False),full90_executed=False,holdout_used=False)
    else:
        files=sorted([*a.run.glob('primary-*.json'),*a.run.glob('confirmation-*.json')]);records=[read(p) for p in files]
        if not a.partial:
            assert done and done['status']=='COMPLETED' and sum(r['phase']=='primary' for r in records)==36
            assert all(sha(a.run/n)==h for n,h in done['hashes'].items())
        primary={v:[r for r in records if r['phase']=='primary' and r['variant']==v] for v in 'AB'}
        confirmation={v:[r for r in records if r['phase']=='confirmation' and r['variant']==v] for v in 'AB'}
        stats={v:aggregate(primary[v]) for v in 'AB'};confirm_stats={v:aggregate(confirmation[v]) for v in 'AB'}
        group={}
        for key in dict.fromkeys(r['case_id'] for r in records):
            group[key]={v:dict(**aggregate([r for r in primary[v] if r['case_id']==key]),
                selected_ids=[r['result']['selected_ids'] for r in primary[v] if r['case_id']==key]) for v in 'AB'}
        recoveries=[];regressions=[];new_false=[]
        for r in primary['B']:
            base=next(v for v in primary['A'] if v['case_id']==r['case_id'] and v['repeat']==r['repeat'])
            if base['score']['grade']=='correct' and r['score']['grade']!='correct':regressions.append(dict(case_id=r['case_id'],repeat=r['repeat'],A=base['score']['grade'],B=r['score']['grade']))
            if r['score']['grade']=='false_refusal' and base['score']['grade']!='false_refusal':new_false.append(dict(case_id=r['case_id'],repeat=r['repeat']))
        for key in [q+'-native' for q in ('D001','D002','D003','D012')]:
            av=[r for r in records if r['case_id']==key and r['variant']=='A'];bv=[r for r in records if r['case_id']==key and r['variant']=='B']
            stable=len(bv)==3 and all(r['score']['grade']=='correct' for r in bv) and sum(r['score']['grade']=='false_refusal' for r in av)>=2
            recoveries.append(dict(case_id=key,A_grades=[r['score']['grade'] for r in av],B_grades=[r['score']['grade'] for r in bv],stable_recovery=stable))
        qg={};cg={};decision='IN_PROGRESS'
        if not a.partial:
            def correct(key):return group[key]['B']['grades'].get('correct',0)
            original=('D004-native','D009-native')
            qg=dict(T026_at_least_2_of_3=correct('T026-expanded')>=2,T034_3_of_3=correct('T034-expanded')==3,
                D017_3_of_3=correct('D017-native')==3,D021_3_of_3=correct('D021-native')==3,
                stable_recovered_questions_at_least_2=sum(v['stable_recovery'] for v in recoveries)>=2,
                original_controls_complete=all(correct(k)==1 for k in original),
                original_control_citations_not_worse=all(group[k]['B']['citation_support']['value'] is not None and group[k]['B']['citation_support']['value']>=group[k]['A']['citation_support']['value'] for k in original),
                primary_citations_not_worse=stats['B']['citation_support']['value'] is not None and stats['B']['citation_support']['value']>=stats['A']['citation_support']['value'],
                technical_36_of_36=all(r['result']['status']!='failed' for r in records if r['phase']=='primary'))
            allb=primary['B']+confirmation['B'];resources=[r['resources'] for r in allb]+([probe['resources']] if probe else [])
            cg=dict(candidate_p95_at_most_60s=stats['B']['wall_p95_seconds']<=60,
                candidate_max_at_most_90s=max([r['result']['wall_ns']/1e9 for r in allb])<=90,
                peak_rss_at_most_6_5GiB=max(r['process_rss_peak_GiB'] for r in resources)<=6.5,
                available_at_least_1GiB=all(r['available_min_GiB'] is not None and r['available_min_GiB']>=1 for r in resources))
            gate=read(a.run/'D036_zero_call.json');qg['D036_zero_calls']=all(v['graph']['chat_calls']==0 and not v['graph']['retrieved_ids'] and not v['linear']['attempts'] for v in gate.values())
            decision='READY_FOR_90' if all(qg.values()) and all(cg.values()) else 'QUALITY_PASS_COST_FAIL' if all(qg.values()) else 'STOP_MODEL_CANDIDATE'
        result=dict(decision=decision,quality_evaluated=True,quality_gates=qg,cost_gates=cg,primary=stats,confirmation=confirm_stats,
            groups=group,stable_recovery_audit=recoveries,primary_correct_regressions=regressions,new_false_refusals=new_false,
            observations=records,model_identity=meta['models'],probe=probe,full90_executed=False,holdout_used=False,
            scoring='Frozen E7/E8 whole-point support and final extractive answers; primary metrics are not overwritten by adaptive confirmation. Not new human/expert adjudication.')
        buf=io.StringIO();w=csv.writer(buf,lineterminator='\n');w.writerow(['phase','case','repeat','variant','grade','point_mask','selected','supported','calls','seconds','rss_GiB','available_GiB'])
        for r in records:w.writerow([r['phase'],r['case_id'],r['repeat'],r['variant'],r['score']['grade'],''.join(str(int(v)) for v in r['score']['point_mask']),','.join(r['result']['selected_ids']),','.join(r['score']['supported_ids']),r['result']['chat_calls'],r['result']['wall_ns']/1e9,r['resources']['process_rss_peak_GiB'],r['resources']['available_min_GiB']])
        (a.out/'cases.csv').write_bytes(b'\xef\xbb\xbf'+buf.getvalue().encode())
    (a.out/'metrics.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps({k:result[k] for k in ('decision','quality_evaluated','quality_gates','cost_gates')},ensure_ascii=False))
if __name__=='__main__':main()
