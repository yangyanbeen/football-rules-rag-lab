"""Recompute E1 metrics from raw runs and separately recorded source reviews."""
import argparse,csv,hashlib,json,math
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text('utf8'))
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')
def sha(v):return hashlib.sha256(canonical(v)).hexdigest()
def identity(r):return sha({k:r[k] for k in ('status','answer','citations','selected_ids')})
def quantile(values,q):
    values=sorted(values)
    if not values:return None
    x=(len(values)-1)*q;a=math.floor(x);b=math.ceil(x)
    return values[a]+(values[b]-values[a])*(x-a)
def ratio(n,d):return {'numerator':n,'denominator':d,'value':n/d if d else None}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--reviews',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    meta=read(a.run/'metadata.json');complete=read(a.run/'completed.json')
    for name,h in complete['hashes'].items():
        if hashlib.sha256((a.run/name).read_bytes()).hexdigest()!=h:raise ValueError('Changed raw record: '+name)
    base={r['question_id']:r for r in read(ROOT/'optimization/baseline/e8b0fd6/quality_labels.json')}
    dataset=ROOT/'optimization/datasets'/('dev_40.json' if meta['split']=='dev' else 'regression_50.json')
    assert hashlib.sha256(dataset.read_bytes()).hexdigest()==meta['dataset_sha256']
    labels={r['question_id']:r for r in read(dataset)}
    manual={}
    for row in csv.reader(a.reviews.open(encoding='utf8'),delimiter='\t'):
        if not row:continue
        key,grade,bits,cids,note=row
        assert key not in manual
        manual[key]=dict(grade=grade,point_mask=[x=='1' for x in bits],supported_citation_ids=[] if cids=='-' else cids.split(','),note=note,method='Post-run Codex source review; human review pending')
    scored=[]
    for path in sorted(a.run.glob('[DT][0-9][0-9][0-9]-?.json')):
        x=read(path);qid=x['question_id'];r=x['result'];q=labels[qid];b=base[qid];key=qid+'|'+','.join(r['selected_ids'])
        if identity(r)==b['result_identity_sha256']:
            grade={k:b[k] for k in ('grade','point_mask','supported_citation_ids','note')};grade['method']='Byte-identical answer/citations/status to frozen reviewed baseline'
        elif r['status']=='failed':grade=dict(grade='runtime_error',point_mask=[False]*len(q['expected_answer_points']),supported_citation_ids=[],note=r['error'],method='Runtime result')
        elif r['status']=='refused':grade=dict(grade='false_refusal' if q['answerable'] else 'correct_refusal',point_mask=[False]*len(q['expected_answer_points']),supported_citation_ids=[],note='Compare expected answerability; refusal reason separate',method='Frozen label')
        else:
            if key not in manual:raise ValueError('Missing independent source review: '+key)
            grade=manual[key]
        assert len(grade['point_mask'])==len(q['expected_answer_points'])
        assert set(grade['supported_citation_ids'])<=set(r['selected_ids'])
        if grade['grade']=='correct':assert q['answerable'] and all(grade['point_mask'])
        if grade['grade']=='partial':assert any(grade['point_mask']) and not all(grade['point_mask'])
        scored.append(dict(question_id=qid,question=q['question'],variant=x['variant'],answerable=q['answerable'],status=r['status'],reason=r['reason'],selected_ids=r['selected_ids'],offered_ids=x['offered_ids'],expected_chunk_ids=q['expected_chunk_ids'],**grade,input_tokens=x['input_tokens'],output_tokens=x['output_tokens'],seconds=x['seconds'],chat_calls=x['chat_calls'],pre_generation_guard=x['pre_generation_guard'],exact_baseline_reproduction=identity(r)==b['result_identity_sha256'],raw_record_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    assert len(scored)==complete['records']==len(labels)*len(meta['variants'])
    summaries={}
    for v in meta['variants']:
        rows=[x for x in scored if x['variant']==v];counts=Counter(x['grade'] for x in rows);pos=[x for x in rows if x['answerable']];neg=[x for x in rows if not x['answerable']];model=[x for x in rows if x['chat_calls']]
        summaries[v]=dict(counts=dict(counts),answerable_complete_accuracy=ratio(counts['correct'],len(pos)),overall_accuracy=ratio(counts['correct']+counts['correct_refusal'],len(rows)),correct_refusal_rate=ratio(counts['correct_refusal'],len(neg)),false_refusal_rate=ratio(counts['false_refusal'],len(pos)),citation_support_rate=ratio(sum(len(x['supported_citation_ids']) for x in rows),sum(len(x['selected_ids']) for x in rows)),requirement_coverage=ratio(sum(sum(x['point_mask']) for x in rows),sum(len(x['point_mask']) for x in rows)),technical_completion=ratio(sum(x['status']!='failed' for x in rows),len(rows)),input_tokens=sum(x['input_tokens'] for x in rows),output_tokens=sum(x['output_tokens'] for x in rows),model_calls=sum(x['chat_calls'] for x in rows),model_questions=len(model),selection_seconds_p50=quantile([x['seconds'] for x in model],.5),selection_seconds_p95=quantile([x['seconds'] for x in model],.95),selection_seconds_total=sum(x['seconds'] for x in model),exact_baseline_reproductions=sum(x['exact_baseline_reproduction'] for x in rows))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(dict(version='phase2-E1-metrics-1',run_metadata=meta,raw_completed=complete,summaries=summaries,cases=scored,review_scope='Codex AI semantic source audit; no new human review. Citation support means the full selected paragraph directly supports at least one requested point. Conditions duplicate expected points in this dataset, so counted once. Quality is judged on rendered source content, not exact gold ID matching.',holdout_used=False),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summaries,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
