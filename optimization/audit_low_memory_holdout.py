"""Post-acceptance trace diagnosis only; no tuning or new inference."""
import argparse,collections,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,record,digest


def main(run):
    metrics=read(ROOT/'optimization/reports/E15_low_memory_holdout_metrics.json')
    labels={q['question_id']:q for q in read(ROOT/'optimization/datasets/holdout_40.json')}
    raw={q['question_id']:read(ROOT/q['raw_record']['path']) for q in metrics['cases']}
    rows=[];failures=[];normal=[]
    for c in metrics['cases']:
        t=raw[c['question_id']];r=t['result'];q=labels[c['question_id']];events=t['resources']['stage_events'];by={e['stage']:e for e in events}
        expected=q['expected_chunk_ids'];review=c['review'];is_normal=bool(r and r['attempts'])
        if is_normal:
            wanted=['answer_before_retrieval_unload_end','embedding_unload_end','jit_reranker_construction_start',
                    'reranker_release_end','answer_model_start','answer_after_generation_unload_end']
            order=all(e in by for e in wanted) and all(by[a]['monotonic']<by[b]['monotonic'] for a,b in zip(wanted,wanted[1:]))
            order=order and by['reranker_release_end'].get('object_collected') is True
            normal.append(c['question_id'])
        else:order=not any(e in by for e in ('lazy_retrieval_construction_start','answer_model_start'))
        row=dict(question_id=c['question_id'],answerable=q['answerable'],grade=review['grade'],
            expected_evidence_in_top10=bool(r) and set(expected)<=set(r['retrieved_ids']),
            expected_evidence_in_prompt=bool(r) and set(expected)<=set(r['offered_ids']),
            expected_prompt_positions={cid:r['offered_ids'].index(cid)+1 if cid in r['offered_ids'] else None for cid in expected} if r else {},
            selected_ids=r['selected_ids'] if r else [],supported_citation_ids=review['supported_citation_ids'],
            unsupported_citation_ids=[cid for cid in c['selected_ids'] if cid not in review['supported_citation_ids']],residency_order=order)
        rows.append(row)
        if q['answerable'] and review['grade']!='correct':
            if not row['expected_evidence_in_top10']:reason='annotated_evidence_missing_from_top10'
            elif not row['expected_evidence_in_prompt']:reason='annotated_evidence_not_packed'
            elif r['status']=='refused':reason='evidence_in_prompt_false_refusal'
            else:reason='evidence_in_prompt_wrong_selection'
            failures.append(dict(**row,first_observed_failure=reason))
    samples=[json.loads(line) for line in (run/'resources.jsonl').read_text('utf8').splitlines()]
    gaps=[b['monotonic']-a['monotonic'] for a,b in zip(samples,samples[1:])]
    all_events=[json.loads(line) for p in (run/'events').glob('*.jsonl') for line in p.read_text('utf8').splitlines() if line.strip()]
    all_stage=[e['memory']['available']/2**30 for e in all_events if 'available' in e.get('memory',{})]
    correct=[r for r in rows if r['grade']=='correct'];answerable=[r for r in rows if r['answerable']]
    value=dict(source_commit=read(run/'metadata.json')['source_commit'],metrics=record(ROOT/'optimization/reports/E15_low_memory_holdout_metrics.json'),
        normal_requests=len(normal),zero_inference_requests=[r['question_id'] for r in rows if r['question_id'] not in normal],
        all_residency_order=all(r['residency_order'] for r in rows),
        expected_evidence_coverage=dict(scope='Frozen annotated IDs for this32-item same-corpus set; equivalent actual support allowed in scoring.',
            denominator=len(answerable),top10_all=sum(r['expected_evidence_in_top10'] for r in answerable),prompt_all=sum(r['expected_evidence_in_prompt'] for r in answerable)),
        failures=failures,first_observed_failure_counts=dict(collections.Counter(r['first_observed_failure'] for r in failures)),
        correct_answers_with_unsupported_citations=sum(bool(r['unsupported_citation_ids']) for r in correct),
        unsupported_citations_within_correct_answers=sum(len(r['unsupported_citation_ids']) for r in correct),
        equivalent_complete_support_without_reference_ids=[r['question_id'] for r in correct if not set(labels[r['question_id']]['expected_chunk_ids'])&set(r['selected_ids'])],
        resource_only_pass=all(r['residency_order'] for r in rows) and min(all_stage)>=1 and metrics['gates']['maximum_seconds'] and metrics['gates']['minimum_available_GiB'],
        all_stage_minimum_including_UI_readiness_GiB=min(all_stage),
        peak_task_tree_rss_GiB=max(t['resources']['process_rss_peak_GiB'] for t in raw.values()),
        sampling=dict(target_seconds=.2,actual_median_seconds=statistics.median(gaps),maximum_gap_seconds=max(gaps)),
        calls=dict(answer=sum(len(t['result']['attempts']) for t in raw.values()),
            input_tokens=sum(a.get('prompt_eval_count') or 0 for t in raw.values() for a in t['result']['attempts']),
            output_tokens=sum(a.get('eval_count') or 0 for t in raw.values() for a in t['result']['attempts'])),
        conservative_review_sensitivity=dict(note='Even granting H008 L06-02 and H009 L06-01 as broadly supportive would not alter the failed citation gate or full-answer count.',
            upper_numerator_if_both_added=metrics['citation_support']['numerator']+2,denominator=metrics['citation_support']['denominator']),
        cases=rows,holdout_used=True,no_new_model_calls=True,no_tuning_after_holdout=True)
    path=ROOT/'optimization/reports/E15_low_memory_holdout_trace_audit.json';path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
    print(json.dumps({k:v for k,v in value.items() if k not in ('cases','failures')},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);main(p.parse_args().run)
