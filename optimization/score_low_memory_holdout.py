"""One-shot holdout scoring from frozen labels and explicit source audits."""
import argparse,collections,csv,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,record,digest,canonical
from task13_audit import validate_private


def main(run):
    assert read(ROOT/'optimization/reports/E15_low_memory90_resource_audit.json')['overall_pass']
    meta=read(run/'metadata.json');done=read(run/'completed.json')
    labels=read(ROOT/'optimization/datasets/holdout_40.json')
    assert record(ROOT/'optimization/datasets/holdout_40.json')==meta['dataset']
    reviews={};ledger=ROOT/'optimization/experiments/E15_low_memory/holdout_source_reviews.tsv'
    if ledger.exists():
        for key,grade,bits,support,note in csv.reader(ledger.open(encoding='utf8'),delimiter='\t'):
            qid,ids=key.split('|',1)
            reviews[qid,frozenset(ids.split(','))]=dict(grade=grade,point_mask=[v=='1' for v in bits],
                supported_citation_ids=[] if support=='-' else support.split(','),note=note)
    corpus={r['chunk_id']:r for r in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    rows=[];queue=[];verified=set()
    for q in labels:
        filename=q['question_id']+'.json'
        if filename not in done['hashes']:continue
        path=run/filename;assert digest(path.read_bytes())==done['hashes'][filename]
        t=read(path);r=t['result'];count=len(q['expected_answer_points'])
        if r:
            identity=digest(canonical(r['implementation']));validate_private(r,q['question'],identity not in verified);verified.add(identity)
        selected=r['selected_ids'] if r else []
        if r is None or r['error'] or t['error']:
            review=dict(grade='runtime_error',point_mask=[False]*count,supported_citation_ids=[],note=t['error'])
        elif r['status']=='refused':
            review=dict(grade='false_refusal' if q['answerable'] else 'correct_refusal',point_mask=[False]*count,supported_citation_ids=[],note='Frozen answerability label')
        else:
            review=reviews.get((q['question_id'],frozenset(selected)))
            if review is None:
                queue.append(dict(key=q['question_id']+'|'+','.join(selected),question=q['question'],answerable=q['answerable'],
                    points=q['expected_answer_points'],conditions=q.get('required_conditions',[]),
                    selected_sources=[dict(chunk_id=cid,content_zh=corpus[cid]['content_zh']) for cid in selected]))
            elif not q['answerable']:review=dict(review,grade='answer_instead_of_refusal',point_mask=[False]*count)
        if review:
            assert len(review['point_mask'])==count and set(review['supported_citation_ids'])<=set(selected)
            if review['grade']=='correct':assert q['answerable'] and all(review['point_mask'])
        rows.append(dict(question_id=q['question_id'],answerable=q['answerable'],selected_ids=selected,
            review=review,seconds=t['seconds'],minimum_available_GiB=t['resources']['available_min_GiB'],
            calls=len(r['attempts']) if r else 0,retries=max(0,len(r['attempts'])-1) if r else 0,raw_record=record(path)))
    counts=collections.Counter(r['review']['grade'] if r['review'] else 'pending_source_review' for r in rows)
    answers=sum(q['answerable'] for q in labels);refusals=len(labels)-answers
    cited=sum(len(r['selected_ids']) for r in rows);supported=sum(len(r['review']['supported_citation_ids']) for r in rows if r['review'])
    gates=dict(complete40=done['status']=='COMPLETED' and len(rows)==40,source_reviews_complete=not queue,
        full_at_least75percent=counts['correct']*4>=answers*3,refusals_all_correct=counts['correct_refusal']==refusals,
        technical40=len(rows)==40 and counts['runtime_error']==0,citations_at_least_E14=cited>0 and supported*123>=75*cited,
        maximum_seconds=all(r['seconds']<=60 for r in rows),minimum_available_GiB=all(r['minimum_available_GiB']>=1 for r in rows))
    times=sorted(r['seconds'] for r in rows)
    result=dict(scope=meta['scope'],source_commit=meta['source_commit'],gates=gates,overall_pass=all(gates.values()),
        actual_records=len(rows),pending_reviews=len(queue),counts=dict(counts),
        full_answerable=dict(numerator=counts['correct'],denominator=answers),
        correct_refusal=dict(numerator=counts['correct_refusal'],denominator=refusals),
        technical=dict(numerator=sum(r['review'] is None or r['review']['grade']!='runtime_error' for r in rows),denominator=40),
        citation_support=dict(numerator=supported,denominator=cited),
        resources=dict(minimum_available_GiB=min(r['minimum_available_GiB'] for r in rows) if rows else None,
            below1=sum(r['minimum_available_GiB']<1 for r in rows),maximum_seconds=max(times) if times else None,
            median_seconds=statistics.median(times) if times else None,p95_nearest_rank_seconds=times[max(0,(95*len(times)+99)//100-1)] if times else None),
        calls=sum(r['calls'] for r in rows),retries=sum(r['retries'] for r in rows),cases=rows,holdout_used=True,
        review_scope='Codex source/necessary-point audit. No new human or expert adjudication. Equivalent supporting paragraphs allowed; gold-ID equality is not the scoring rule.',
        no_tuning_after_holdout=True)
    for name,value in [('E15_low_memory_holdout_review_queue.json',queue),('E15_low_memory_holdout_metrics.json',result)]:
        (ROOT/'optimization/reports'/name).write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases',)},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);main(p.parse_args().run)
