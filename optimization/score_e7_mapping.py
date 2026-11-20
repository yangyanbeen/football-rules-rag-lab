"""Independent E7 source scoring and explicit, separately reviewed mapping audit."""
import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]


def read(path): return json.loads(path.read_text('utf8'))
def canonical(v): return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def digest(value): return hashlib.sha256(canonical(value)).hexdigest()
def ratio(n, d): return dict(numerator=n, denominator=d, value=n/d if d else None)


def percentile(values, p):
    if not values: return None
    values = sorted(values)
    x = (len(values)-1)*p
    low = int(x)
    return values[low] + (values[min(low+1, len(values)-1)]-values[low])*(x-low)


def aggregate(rows):
    return dict(invocations=len(rows), independent_questions=len(set(r['question_id'] for r in rows)),
        contexts=len(set(r['case_id'] for r in rows)), grades=dict(Counter(r['grade'] for r in rows)),
        point_coverage=ratio(sum(sum(r['point_mask']) for r in rows), sum(len(r['point_mask']) for r in rows)),
        citation_support=ratio(sum(len(r['supported_ids']) for r in rows), sum(len(r['selected_ids']) for r in rows)),
        input_tokens=sum(r['input_tokens'] for r in rows), output_tokens=sum(r['output_tokens'] for r in rows),
        model_calls=sum(r['answer_calls'] for r in rows), retries=sum(max(0,r['answer_calls']-1) for r in rows),
        rejected_attempts=sum(r['rejected_attempts'] for r in rows),
        mapping_validation_failures=sum(r['mapping_validation_failures'] for r in rows),
        latency_p50_seconds=median([r['wall_seconds'] for r in rows]) if rows else None,
        latency_p95_seconds=percentile([r['wall_seconds'] for r in rows], .95))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--review', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--partial', action='store_true')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    prep = read(a.prepared)
    cases = {c['case_id']:c for c in prep['cases']}
    mapping_review = read(a.review) if a.review else {'reviews': {}}
    files = sorted(a.run.glob('*-r?.json'))
    if not a.partial:
        done = read(a.run/'completed.json')
        assert len(files) == done['records'] == len(prep['schedule']) == 112
        assert all(sha(a.run/name)==h for name,h in done['hashes'].items())
    rows, missing_reviews = [], set()
    for path in files:
        t = read(path)
        c, r = cases[t['case_id']], t['result']
        ids = r['selected_ids']
        supports = [set(v) for v in c['support_per_point']]
        available = [bool(v) for v in supports]
        mask = [bool(set(ids)&v) for v in supports]
        supported = [cid for cid in ids if any(cid in v for v in supports)]
        if r['status']=='failed': grade='runtime_error'
        elif r['status']=='refused': grade='false_refusal' if all(available) else 'boundary_refusal'
        elif all(mask): grade='correct'
        elif any(mask): grade='partial'
        else: grade='incorrect'
        ats = t['observations']['model_attempts']
        first = ats[0] if ats else None
        accepted = [at.get('mapping_validation') for at in ats if at.get('mapping_validation')]
        audit = accepted[-1] if accepted else None
        semantic, per_point = None, None
        if audit:
            key = t['case_id']+':'+digest(audit['requirements'])
            semantic = mapping_review['reviews'].get(key)
            if not semantic: missing_reviews.add(key)
            else:
                assert semantic['requirements'] == audit['requirements']
                matched = semantic['frozen_point_to_model_requirements']
                assert len(matched) == len(c['necessary_points'])
                edges = semantic['edge_support']
                expected_edges={(i,cid) for i,req in enumerate(audit['requirements']) for cid in req['supporting_ids']}
                assert {(v['requirement_index'],v['chunk_id']) for v in edges} == expected_edges
                assert len(edges) == len(expected_edges)
                truth={(v['requirement_index'],v['chunk_id']):v['supports'] for v in edges}
                partial={(v['requirement_index'],v['chunk_id']):v.get('partially_supports_frozen_points',[]) for v in edges}
                valid_decomposition=semantic.get('point_decomposition_valid',[bool(v) for v in matched])
                assert len(valid_decomposition)==len(matched)
                per_point=[]
                for index, (point, indices, valid_ids) in enumerate(zip(c['necessary_points'],matched,supports)):
                    assert all(type(i) is int and 0<=i<len(audit['requirements']) for i in indices)
                    mapped_ids=sorted({cid for i in indices for cid in audit['requirements'][i]['supporting_ids']
                                       if cid in valid_ids and valid_decomposition[index]
                                       and (truth[(i,cid)] or index in partial[(i,cid)])})
                    selected = [cid for cid in ids if cid in mapped_ids]
                    per_point.append(dict(necessary_point=point, available=available[index],
                        decomposed=bool(indices) and valid_decomposition[index], model_requirement_indices=indices,
                        truly_supporting_mapped_ids=mapped_ids, truly_supporting_segment_mapped=bool(mapped_ids),
                        mapped_support_selected=bool(selected), selected_support_ids=selected,
                        final_render_covers_point=mask[index]))
        row = dict(case_id=t['case_id'], question_id=t['question_id'], context=c['context'], variant=t['variant'], repeat=t['repeat'],
            grade=grade, full_evidence=all(available), point_mask=mask, available_mask=available,
            selected_ids=ids, supported_ids=supported, unsupported_ids=[cid for cid in ids if cid not in supported],
            offered_ids=r['offered_ids'], answer_calls=r['chat_calls'],
            rejected_attempts=sum(at['error'] is not None for at in r['selection_audits']),
            mapping_validation_failures=sum('mapping_validation_error' in at for at in ats),
            input_tokens=sum(at.get('response',{}).get('prompt_eval_count',0) for at in ats),
            output_tokens=sum(at.get('response',{}).get('eval_count',0) for at in ats),
            wall_seconds=r['wall_ns']/1e9,
            body_sha256=digest(first['messages'][1:len(c['messages'])]) if first else None,
            schema_sha256=digest(first['schema']) if first else None,
            prompt_bytes=len(canonical(first['messages'])) if first else 0,
            first_raw=first.get('response',{}).get('message',{}).get('content') if first else None,
            mapping=audit, mapping_review=semantic, point_mapping_audit=per_point,
            trace_file=path.name, trace_sha256=sha(path))
        rows.append(row)
    groups = {}
    for key in cases:
        groups[key] = {}
        for v in 'AB':
            vals=sorted([r for r in rows if r['case_id']==key and r['variant']==v],key=lambda r:r['repeat'])
            groups[key][v]=dict(**aggregate(vals),point_masks=[''.join(str(int(b)) for b in r['point_mask']) for r in vals],
                selected_ids=[r['selected_ids'] for r in vals])
    full={v:aggregate([r for r in rows if r['variant']==v and r['full_evidence']]) for v in 'AB'}
    boundary={v:aggregate([r for r in rows if r['variant']==v and not r['full_evidence']]) for v in 'AB'}
    paired={(r['case_id'],r['repeat'],r['variant']):r for r in rows}
    new_false, regressions, new_unsupported = [], [], []
    for b in [r for r in rows if r['variant']=='B']:
        control=paired.get((b['case_id'],b['repeat'],'A'))
        if not control: continue
        assert control['body_sha256']==b['body_sha256']
        if b['full_evidence'] and b['grade']=='false_refusal' and control['grade'] not in ('false_refusal','runtime_error'):
            new_false.append(dict(case_id=b['case_id'],repeat=b['repeat'],A=control['grade'],B=b['grade']))
        if control['grade']=='correct' and b['grade']!='correct':
            regressions.append(dict(case_id=b['case_id'],repeat=b['repeat'],A=control['grade'],B=b['grade']))
        ids=[cid for cid in b['unsupported_ids'] if cid not in control['unsupported_ids']]
        if ids: new_unsupported.append(dict(case_id=b['case_id'],repeat=b['repeat'],ids=ids))
    decision='IN_PROGRESS'
    gates={}
    recoveries=[]
    if not a.partial:
        def vals(key,v='B'): return [r for r in rows if r['case_id']==key and r['variant']==v]
        def correct(key,v='B'): return sum(r['grade']=='correct' for r in vals(key,v))
        for qid in ('D001','D002','D003','D012'):
            if sum(r['grade']=='false_refusal' for r in vals(qid+'-native','A'))>=2 and correct(qid+'-native')==4:
                recoveries.append(qid)
        gate_trace=read(a.run/'D036_zero_call.json')
        gates=dict(T026_expanded=correct('T026-expanded')>=3,
            T026_native=all(r['grade'] in ('correct','partial') for r in vals('T026-native')),
            repeated_false_refusal_recovery=bool(recoveries),
            correct_controls=all(correct(q+'-native')==4 for q in ('D004','D009','D017')),
            correct_controls_citation=all(groups[q+'-native']['B']['citation_support']['value'] is not None and groups[q+'-native']['B']['citation_support']['value']>=groups[q+'-native']['A']['citation_support']['value'] for q in ('D004','D009','D017')),
            T034_expanded=correct('T034-expanded')==4,
            technical=all(r['grade']!='runtime_error' and r['answer_calls']<=2 for r in rows),
            D036=all(t['result']['status']=='refused' and t['result']['chat_calls']==0 and not t['result']['retrieved_ids'] and t['result']['embedding_queries']==0 for t in gate_trace),
            citation_not_lower=full['B']['citation_support']['value'] is not None and full['B']['citation_support']['value']>=full['A']['citation_support']['value'],
            no_new_false_refusals=not new_false,
            mapping_source_review_complete=not missing_reviews)
        decision='PILOT_PASS' if all(gates.values()) else 'STOP_E7_CANDIDATE'
    result=dict(decision=decision,pilot_gates=gates,groups=groups,full_evidence_aggregate=full,boundary_aggregate=boundary,
        repeated_false_refusal_recoveries=recoveries,new_false_refusals=new_false,paired_correct_regressions=regressions,
        newly_unsupported_citations=new_unsupported,missing_mapping_reviews=sorted(missing_reviews),cases=rows,
        formal90_executed=False,holdout_used=False,scoring_scope='Pilot repetitions are observations, not independent question accuracy. Fixed source/point labels and Codex source reading; not human/expert review. Semantic mapping review is separate from model self-coverage.')
    mapped=[p for r in rows if r['variant']=='B' and r['point_mapping_audit'] for p in r['point_mapping_audit']]
    edges=[e for r in rows if r['variant']=='B' and r['mapping_review'] for e in r['mapping_review']['edge_support']]
    result['mapping_audit_aggregate']=dict(reviewed_point_observations=len(mapped),
        available_point_observations=sum(p['available'] for p in mapped),
        decomposed=sum(p['decomposed'] for p in mapped),
        supporting_segment_truly_mapped=sum(p['truly_supporting_segment_mapped'] for p in mapped),
        mapped_support_selected=sum(p['mapped_support_selected'] for p in mapped),
        final_render_coverage=sum(p['final_render_covers_point'] for p in mapped),
        source_relation_support=ratio(sum(e['supports'] for e in edges),len(edges)),
        caveat='Whole-requirement edge support is strict: a paragraph only answering one part of a compound requirement is marked partial, not full. Final source-derived point scores remain independent.')
    (a.out/'E7_mapping_metrics.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    buf=io.StringIO();w=csv.writer(buf,lineterminator='\n')
    cols=['case_id','variant','repeat','grade','point_mask','selected_ids','supported_ids','unsupported_ids','first_raw','input_tokens','output_tokens','wall_seconds','body_sha256','schema_sha256','trace_sha256']
    w.writerow(cols)
    for r in rows:w.writerow([json.dumps(r[k],ensure_ascii=False) if isinstance(r[k],(list,dict)) else r[k] for k in cols])
    (a.out/'E7_mapping_calls.csv').write_bytes(b'\xef\xbb\xbf'+buf.getvalue().encode())
    print(json.dumps(dict(decision=decision,records=len(rows),pilot_gates=gates,full_evidence=full,missing_mapping_reviews=len(missing_reviews)),ensure_ascii=False))


if __name__=='__main__':main()
