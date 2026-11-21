"""Reclassify the sealed historical 90 results; no new inference or regrading."""
import argparse,collections,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
COMPARISON={'D013','D016','D021','D022','D023','D026','T007','T017','T022','T026','T029','T030','T034'}
def main(out):
    source=ROOT/'optimization/reports/D036_business_gate_metrics.json';data=read(source);rows=data['cases'];assert len(rows)==90
    trace_root=ROOT/'.runtime/phase2/d036-gate-live90-final'
    done=read(trace_root/'completed.json')
    for qid,h in done['hashes'].items():assert sha(trace_root/(qid+'.json'))==h
    result=[]
    for row in rows:
        category='must_refuse' if not row['answerable'] else 'comparison' if row['question_id'] in COMPARISON else 'single_fact' if len(row['point_mask'])==1 else 'multiple_requirements'
        reason={'must_refuse':'Frozen expected-unanswerable label takes priority.',
            'comparison':'Question explicitly contrasts objects, rules or restart circumstances; Codex intent review.',
            'single_fact':'One necessary point in the frozen rubric; not determined by answer grade.',
            'multiple_requirements':'At least two frozen necessary points, excluding reviewed comparisons.'}[category]
        result.append(dict(question_id=row['question_id'],question=row['question'],category=category,classification_reason=reason,
            necessary_points=len(row['point_mask']),grade=row['grade'],point_mask=row['point_mask'],
            selected_ids=row['selected_ids'],supported_ids=row['supported_citation_ids'],
            unsupported_ids=[c for c in row['selected_ids'] if c not in row['supported_citation_ids']],
            note=row['note'],raw_trace_sha256=done['hashes'][row['question_id']]))
    groups={}
    for category in ('single_fact','multiple_requirements','comparison','must_refuse'):
        selected=[r for r in result if r['category']==category]
        correct=sum(r['grade'] in ('correct','correct_refusal') for r in selected)
        num=sum(len(r['supported_ids']) for r in selected);den=sum(len(r['selected_ids']) for r in selected)
        groups[category]=dict(complete_or_correct_refusal=correct,total=len(selected),value=correct/len(selected),
            grades=dict(collections.Counter(r['grade'] for r in selected)),citation_support=dict(numerator=num,denominator=den,value=num/den if den else None),
            loss_ids=[r['question_id'] for r in selected if r['grade'] not in ('correct','correct_refusal')],
            citation_issue_ids=[r['question_id'] for r in selected if r['unsupported_ids']])
    assert sum(g['complete_or_correct_refusal'] for g in groups.values())==69
    assert sum(g['citation_support']['numerator'] for g in groups.values())==72
    assert sum(g['citation_support']['denominator'] for g in groups.values())==118
    save(out,dict(source=str(source.relative_to(ROOT)),source_sha256=sha(source),historical_runtime='5986781; original actual Graph producer 86a01e9',
        original_counts=data['live']['counts'],groups=groups,cases=result,new_model_calls=0,holdout_used=False,
        method='Mutually exclusive categories: frozen refusal label, reviewed explicit comparison, one frozen necessary point, remaining multiple requirements. Reuses frozen point/citation judgments; not new human/expert review.',
        limitations=['Historical per-question single observations cannot establish stability guarantees.',
            'The one-point category has only three questions; do not generalize its fraction to all simple facts.',
            'Citation support counts support of frozen necessary points, distinct from verbatim/source integrity.',
            'No rerun of the 90; new browser/load observations must retain separate denominators.']))
    print(json.dumps(groups,ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args().out)
