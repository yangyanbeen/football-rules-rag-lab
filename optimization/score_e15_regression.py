"""Score E15 real Worker90 by frozen source judgments, with an explicit review queue."""
import argparse,collections,csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,record,digest,canonical
from task13_audit import validate_private

def save(p,v):p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
def main(a):
    labels={v['question_id']:v for v in read(ROOT/'optimization/datasets/dev_40.json')+read(ROOT/'optimization/datasets/regression_50.json')}
    history={v['question_id']:v for v in read(ROOT/'optimization/reports/E14_live90_metrics.json')['cases'] if v['variant']=='candidate'}
    corpus={v['chunk_id']:v for v in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    known={}
    for name in ('E1_selection_prompt','E4_duplicate_repair','E5_A_candidate_window','D036_business_gate','E14_runtime','E15_lifecycle'):
        p=ROOT/'optimization/experiments'/name/'source_reviews.tsv'
        if not p.exists():continue
        for key,grade,bits,ids,note in csv.reader(p.open(encoding='utf8'),delimiter='\t'):
            qid,selected=key.split('|',1);known[qid,frozenset(selected.split(','))]=dict(grade=grade,point_mask=[b=='1' for b in bits],supported_citation_ids=[] if ids=='-' else ids.split(','),note=note,review_file=p.relative_to(ROOT).as_posix())
    for v in history.values():
        if v['selected_ids']:known.setdefault((v['question_id'],frozenset(v['selected_ids'])),{**{k:v[k] for k in ('grade','point_mask','supported_citation_ids','note')},'review_file':'optimization/reports/D036_business_gate_metrics.json'})
    queue={};cases=[];verified_implementations=set();done=read(a.run/'completed.json') if (a.run/'completed.json').exists() else None
    files=sorted(a.run.glob('[DT][0-9][0-9][0-9]-B.json'))
    for p in files:
        try:t=read(p)
        except ValueError:
            if a.partial:continue
            raise
        if done:assert digest(p.read_bytes())==done['hashes'][p.name]
        qid=t['name'];q=labels[qid];r=t['result']
        if not a.partial and r:
            identity=digest(canonical(r['implementation']));validate_private(r,q['question'],identity not in verified_implementations)
            verified_implementations.add(identity)
        if r and r.get('fact_recovery',{}).get('applied'):
            shadow=t['shared_response_control'];assert shadow['attempts']==r['attempts'] and shadow['messages']==r['messages']
            assert not shadow['selected_ids'] and shadow['status']=='refused'
        for variant,value in [('candidate',r),('shared_response_shadow',t.get('shared_response_control'))]:
            count=len(q['expected_answer_points'])
            if value is None or value['error']:
                grade=dict(grade='runtime_error',point_mask=[False]*count,supported_citation_ids=[],note=t.get('error'),review_file='Runtime result')
            elif value['status']=='refused':
                grade=dict(grade='false_refusal' if q['answerable'] else 'correct_refusal',point_mask=[False]*count,supported_citation_ids=[],note='Frozen answerability label',review_file='Frozen label')
            else:
                key=(qid,frozenset(value['selected_ids']))
                if key not in known:
                    name=qid+'|'+','.join(value['selected_ids']);queue[name]=dict(key=name,question=q['question'],answerable=q['answerable'],points=q['expected_answer_points'],sources=[dict(chunk_id=cid,content_zh=corpus[cid]['content_zh']) for cid in value['selected_ids']]);continue
                grade=dict(known[key])
                if not q['answerable']:grade.update(grade='answer_instead_of_refusal',point_mask=[False]*count)
            assert len(grade['point_mask'])==count,(qid,grade)
            selected=value['selected_ids'] if value else []
            assert set(grade['supported_citation_ids'])<=set(selected)
            if grade['grade']=='correct':assert q['answerable'] and all(grade['point_mask'])
            cases.append(dict(question_id=qid,variant=variant,answerable=q['answerable'],selected_ids=selected,status=value['status'] if value else 'runtime_error',
                recovery=value.get('fact_recovery') if value else None,**grade,
                historical_grade=history[qid]['grade'],seconds=t['seconds'] if variant=='candidate' else None,
                available_min_GiB=t['resources']['available_min_GiB'] if variant=='candidate' else None,
                calls=len(value['attempts']) if value else 0,raw_record=record(p)))
    save(ROOT/'optimization/reports/E15_live90_review_queue.json',list(queue.values()))
    summaries={}
    for variant in ('candidate','shared_response_shadow'):
        vals=[v for v in cases if v['variant']==variant];counts=collections.Counter(v['grade'] for v in vals)
        summaries[variant]=dict(scored=len(vals),counts=dict(counts),full_answerable=dict(numerator=counts['correct'],denominator=72),
            correct_refusal=dict(numerator=counts['correct_refusal'],denominator=18),technical=dict(numerator=sum(v['grade']!='runtime_error' for v in vals),denominator=90),
            citation_support=dict(numerator=sum(len(v['supported_citation_ids']) for v in vals),denominator=sum(len(v['selected_ids']) for v in vals)))
    target=[v for v in cases if v['variant']=='candidate'];full=len(files)==90 and len(target)==90 and not queue and done and done['status']=='COMPLETED'
    gates=dict(complete90=bool(full),refusal18=summaries['candidate']['counts'].get('correct_refusal')==18,
        technical90=summaries['candidate']['technical']['numerator']==90,full_at_least54=summaries['candidate']['counts'].get('correct',0)>=54,
        requests_at_most60=all(v['seconds']<=60 for v in target),available_at_least1=all(v['available_min_GiB'] is not None and v['available_min_GiB']>=1 for v in target),
        no_wrong_supplement=all(v['grade']=='correct' and set(v['selected_ids'])==set(v['supported_citation_ids']) for v in target if (v.get('recovery') or {}).get('applied')))
    n=summaries['candidate']['citation_support']['numerator'];d=summaries['candidate']['citation_support']['denominator']
    gates['citation_not_below_E14']=d>0 and n*123>=75*d
    gates['no_original_correct_regression']=not any(v['grade']!='correct' and v['historical_grade']=='correct' for v in target)
    value=dict(partial=a.partial,actual_records=len(files),pending_reviews=len(queue),summaries=summaries,gates=gates,
        reference_citations={'E14_actual':{'numerator':75,'denominator':123},'E14_same_response_pre_fallback':{'numerator':72,'denominator':120},'historical_D036':{'numerator':72,'denominator':118}},
        overall_pass=bool(full and all(gates.values())),gains=[v['question_id'] for v in target if v['grade']=='correct' and v['historical_grade']!='correct'],
        regressions=[v['question_id'] for v in target if v['grade']!='correct' and v['historical_grade']=='correct'],
        citation_changes=[dict(question_id=v['question_id'],historical_ids=history[v['question_id']]['selected_ids'],current_ids=v['selected_ids'],
            historical_supported_ids=history[v['question_id']]['supported_citation_ids'],current_supported_ids=v['supported_citation_ids'],
            added_ids=sorted(set(v['selected_ids'])-set(history[v['question_id']]['selected_ids'])),
            removed_ids=sorted(set(history[v['question_id']]['selected_ids'])-set(v['selected_ids'])),
            newly_unsupported_ids=sorted((set(v['selected_ids'])-set(history[v['question_id']]['selected_ids']))-set(v['supported_citation_ids'])))
            for v in target if v['selected_ids']!=history[v['question_id']]['selected_ids']],
        cases=cases,holdout_used=False,
        method='Frozen necessary points, prior reviewed exact question/paragraph sets and separately recorded Codex source reviews; not gold-ID exact match. Source renderer emits full original paragraphs. Shadow uses same actual model response before deterministic recovery, not independent baseline inference; no shadow wall time.',
        review_scope='Codex source audit; no new human/expert adjudication')
    save(ROOT/'optimization/reports/E15_live90_metrics.json',value)
    print(json.dumps(dict(actual_records=len(files),pending_reviews=len(queue),summaries=summaries,gates=gates),ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--partial',action='store_true');main(p.parse_args())
