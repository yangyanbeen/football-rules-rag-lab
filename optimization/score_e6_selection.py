"""E6 scoring from pre-registered point/source reviews, never candidate self-judging."""
import argparse,csv,hashlib,io,json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text('utf8'))
def canon(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ratio(n,d):return dict(numerator=n,denominator=d,value=n/d if d else None)
def aggregate(rows):
    return dict(invocations=len(rows),grades=dict(Counter(v['grade'] for v in rows)),
       covered_points=ratio(sum(sum(v['point_mask']) for v in rows),sum(len(v['point_mask']) for v in rows)),
       available_point_coverage=ratio(sum(sum(v['point_mask']) for v in rows),sum(sum(v['available_mask']) for v in rows)),
       false_refusals=sum(v['grade']=='false_refusal' for v in rows),
       citation_support=ratio(sum(len(v['supported_ids']) for v in rows),sum(len(v['selected_ids']) for v in rows)),
       selected_count=sum(len(v['selected_ids']) for v in rows),input_tokens=sum(v['input_tokens'] for v in rows),output_tokens=sum(v['output_tokens'] for v in rows),answer_calls=sum(v['answer_calls'] for v in rows))
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--partial',action='store_true');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    prep=read(a.prepared);source={v['case_id']:v for v in prep['cases']};files=sorted(a.run.glob('*-r?.json'));rows=[]
    addendum=read(ROOT/'optimization/experiments/E6_evidence_selection/review_addendum.json')
    assert sha(ROOT/'optimization/experiments/E6_evidence_selection/point_evidence_review.json')==addendum['original_annotation_sha256']
    assert sha(ROOT/addendum['source_ledger'])==addendum['source_ledger_sha256']
    if not a.partial:
        done=read(a.run/'completed.json');assert len(files)==done['records']==76
        for name,h in done['hashes'].items():assert sha(a.run/name)==h
    for path in files:
        t=read(path);c=source[t['case_id']];r=t['result'];ids=r['selected_ids']
        extras=addendum['cases'].get(t['case_id'],{}).get('extra_support_per_point',[[] for _ in c['support_per_point']])
        supports=[set(v)|set(extra) for v,extra in zip(c['support_per_point'],extras)]
        available=[bool(v) for v in supports]
        mask=[bool(set(ids)&v) for v in supports]
        supported=[cid for cid in ids if any(cid in v for v in supports)]
        original_mask=[bool(set(ids)&set(v)) for v in c['support_per_point']]
        original_supported=[cid for cid in ids if any(cid in v for v in c['support_per_point'])]
        if r['status']=='failed':g='runtime_error'
        elif r['status']=='refused':g='false_refusal' if all(available) else 'boundary_refusal'
        elif all(mask):g='correct'
        elif any(mask):g='partial'
        else:g='incorrect'
        ats=t['observations']['model_attempts'];first=ats[0] if ats else None
        rows.append(dict(case_id=t['case_id'],question_id=t['question_id'],context=c['context'],variant=t['variant'],repeat=t['repeat'],
             full_evidence=all(available),available_mask=available,point_mask=mask,grade=g,
             original_annotation_point_mask=original_mask,original_annotation_supported_ids=original_supported,
             selected_ids=ids,offered_ids=r['offered_ids'],supported_ids=supported,
             unsupported_ids=[cid for cid in ids if cid not in supported],
             first_raw=first['response']['message']['content'] if first else None,
             all_raw=[v['response']['message']['content'] for v in ats],body_sha256=hashlib.sha256(canon(first['messages'][1:])).hexdigest() if first else None,
             schema_sha256=hashlib.sha256(canon(first['schema'])).hexdigest() if first else None,
             prompt_bytes=len(canon(first['messages'])) if first else 0,
             answer_calls=r['chat_calls'],input_tokens=sum(v['response'].get('prompt_eval_count',0) for v in ats),output_tokens=sum(v['response'].get('eval_count',0) for v in ats),trace_file=path.name,trace_sha256=sha(path)))
    groups={}
    for key in source:
        groups[key]={}
        for variant in 'AB':
            vals=sorted([v for v in rows if v['case_id']==key and v['variant']==variant],key=lambda x:x['repeat'])
            groups[key][variant]=dict(**aggregate(vals),masks=[''.join(str(int(b)) for b in v['point_mask']) for v in vals],selected_ids=[v['selected_ids'] for v in vals])
    full={v:aggregate([r for r in rows if r['variant']==v and r['full_evidence']]) for v in 'AB'}
    boundary={v:aggregate([r for r in rows if r['variant']==v and not r['full_evidence']]) for v in 'AB'}
    gates={};decision='IN_PROGRESS'
    if not a.partial:
        b=[v for v in rows if v['variant']=='B']
        def vals(key,variant='B'):return [v for v in rows if v['case_id']==key and v['variant']==variant]
        def correct(key,variant='B'):return sum(v['grade']=='correct' for v in vals(key,variant))
        def value(v,key):return full[v][key]['value']
        gates=dict(technical=all(v['grade']!='runtime_error' for v in rows),
            T026_native_all_at_least_partial=all(v['grade'] in ('correct','partial') for v in vals('T026-native')),
            T026_expanded_recovery=correct('T026-expanded')>=3 and all(any(v['point_mask']) for v in vals('T026-expanded')),
            T034_expanded_recovery=correct('T034-expanded')>=3,
            correct_dev_controls=all(correct(q+'-native')>=correct(q+'-native','A') and sum(v['grade']!='correct' for v in vals(q+'-native'))<2 for q in ('D004','D009','D017')),
            coverage_not_lower=value('B','covered_points')>=value('A','covered_points'),
            citation_not_lower=value('B','citation_support')>=value('A','citation_support'),
            false_refusal_not_higher=full['B']['false_refusals']<=full['A']['false_refusals'],
            useful_improvement=value('B','covered_points')>value('A','covered_points') or full['B']['false_refusals']<full['A']['false_refusals'])
        decision='PILOT_PASS' if all(gates.values()) else 'STOP_E6_CANDIDATE'
    result=dict(decision=decision,pilot_gates=gates,groups=groups,full_evidence_aggregate=full,boundary_aggregate=boundary,cases=rows,
      full90_executed=False,holdout_used=False,review_addendum=addendum,review_scope='Pre-run Codex source reading plus explicitly logged equivalent-source reconciliation, not new human/expert adjudication; T034-native assessed separately because supplied context is incomplete.')
    result['addendum_sensitivity']=dict(point_masks_changed=sum(v['point_mask']!=v['original_annotation_point_mask'] for v in rows),
        original_annotation_citation={variant:ratio(sum(len(v['original_annotation_supported_ids']) for v in rows if v['variant']==variant and v['full_evidence']),sum(len(v['selected_ids']) for v in rows if v['variant']==variant and v['full_evidence'])) for variant in 'AB'})
    (a.out/'E6_selection_metrics.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    buf=io.StringIO();w=csv.writer(buf,lineterminator='\n');w.writerow(['case','variant','repeat','grade','point_mask','available_mask','selected','supported','unsupported','first_raw','body_sha256','schema_sha256','trace_sha256'])
    for v in rows:w.writerow([v['case_id'],v['variant'],v['repeat'],v['grade'],''.join(str(int(x)) for x in v['point_mask']),''.join(str(int(x)) for x in v['available_mask']),','.join(v['selected_ids']),','.join(v['supported_ids']),','.join(v['unsupported_ids']),v['first_raw'],v['body_sha256'],v['schema_sha256'],v['trace_sha256']])
    (a.out/'E6_selection_calls.csv').write_bytes(b'\xef\xbb\xbf'+buf.getvalue().encode())
    print(json.dumps(dict(decision=decision,pilot_gates=gates,groups=groups,full_evidence=full),ensure_ascii=False))
if __name__=='__main__':main()
