"""Independent paragraph-review scoring for every interleaved pilot invocation."""
import argparse,csv,hashlib,io,json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text('utf8'))
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ratio(n,d):return dict(numerator=n,denominator=d,value=n/d if d else None)
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--partial',action='store_true');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    labels={v['question_id']:v for v in map(json.loads,(ROOT/'data/eval/answer_eval.jsonl').read_text('utf8').splitlines())}
    frozen={v['question_id']:v for v in read(ROOT/'optimization/baseline/e8b0fd6/quality_labels.json')}
    ledger={};byset={}
    for line in csv.reader((ROOT/'optimization/experiments/D036_business_gate/source_reviews.tsv').open(encoding='utf8'),delimiter='\t'):
        key,g,bits,cids,note=line;value=dict(grade=g,point_mask=[b=='1' for b in bits],supported_citation_ids=[] if cids=='-' else cids.split(','),note=note)
        ledger[key]=value;q,c=key.split('|',1);byset[(q,frozenset(c.split(',')))]=value
    for v in read(ROOT/'optimization/reports/D036_business_gate_metrics.json')['cases']:
        if v['selected_ids']:byset[(v['question_id'],frozenset(v['selected_ids']))]={k:v[k] for k in ('grade','point_mask','supported_citation_ids','note')}
    corpus={v['chunk_id']:v for v in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    queue={};cases=[]
    files=sorted(a.run.glob('[DT][0-9][0-9][0-9]-*-r?.json'))
    if not a.partial:
        done=read(a.run/'completed.json');assert done['records']==len(files)==36
        for name,h in done['hashes'].items():assert sha(a.run/name)==h
    for file in files:
        t=read(file);qid=t['question_id'];q=labels[qid];r=t['result'];key=qid+'|'+','.join(r['selected_ids'])
        identity=hashlib.sha256(canonical({k:r[k] for k in ('status','answer','citations','selected_ids')})).hexdigest()
        if identity==frozen[qid]['result_identity_sha256']:
            grade={k:frozen[qid][k] for k in ('grade','point_mask','supported_citation_ids','note')};method='Frozen A0 byte-identical result review'
        elif r['status']=='refused':
            grade=dict(grade='false_refusal',point_mask=[False]*len(q['expected_answer_points']),supported_citation_ids=[],note='Fixed answerability label');method='Frozen label'
        elif r['status']=='failed':
            grade=dict(grade='runtime_error',point_mask=[False]*len(q['expected_answer_points']),supported_citation_ids=[],note=r.get('reason'));method='Runtime result'
        elif key in ledger:grade=ledger[key];method='Prior independent source-combination review'
        elif (qid,frozenset(r['selected_ids'])) in byset:grade=byset[(qid,frozenset(r['selected_ids']))];method='Same question and reviewed paragraph set, order may differ'
        else:
            queue[key]=dict(key=key,question=q['question'],points=q['expected_answer_points'],sources=[dict(chunk_id=cid,content_zh=corpus[cid]['content_zh']) for cid in r['selected_ids']]);continue
        assert len(grade['point_mask'])==len(q['expected_answer_points'])
        ats=t['observations']['model_attempts'];first=ats[0]['response']['message']['content'] if ats else None
        cases.append(dict(file=file.name,trace_sha256=sha(file),question_id=qid,variant=t['variant'],repeat=t['repeat'],status=r['status'],selected_ids=r['selected_ids'],offered_ids=r['offered_ids'],**grade,
                          review_method=method,first_raw=first,all_raw=[v['response']['message']['content'] for v in ats],
                          messages_sha256=hashlib.sha256(canonical(ats[0]['messages'])).hexdigest() if ats else None,
                          prompt_bytes=len(canonical(ats[0]['messages'])) if ats else 0,
                          calls=r['chat_calls'],input_tokens=sum(v['response'].get('prompt_eval_count',0) for v in ats),output_tokens=sum(v['response'].get('eval_count',0) for v in ats)))
    (a.out/'review_queue.json').write_bytes((json.dumps(list(queue.values()),ensure_ascii=False,indent=2)+'\n').encode())
    if queue:print(json.dumps(dict(pending=len(queue),completed=len(files))));return
    groups={}
    for qid in sorted({v['question_id'] for v in cases}):
        groups[qid]={}
        for variant in ('control','candidate'):
            vals=sorted([v for v in cases if v['question_id']==qid and v['variant']==variant],key=lambda x:x['repeat'])
            groups[qid][variant]=dict(n=len(vals),grade_counts=dict(Counter(v['grade'] for v in vals)),
                point_masks=[''.join(str(int(b)) for b in v['point_mask']) for v in vals],selected_ids=[v['selected_ids'] for v in vals],
                prompt_hashes=sorted({v['messages_sha256'] for v in vals}))
    aggregate={}
    for variant in ('control','candidate'):
        vals=[v for v in cases if v['variant']==variant]
        aggregate[variant]=dict(invocations=len(vals),counts=dict(Counter(v['grade'] for v in vals)),
           citation_support=ratio(sum(len(v['supported_citation_ids']) for v in vals),sum(len(v['selected_ids']) for v in vals)),
           input_tokens=sum(v['input_tokens'] for v in vals),output_tokens=sum(v['output_tokens'] for v in vals),model_calls=sum(v['calls'] for v in vals))
    if a.partial:decision='IN_PROGRESS'
    else:
        target=[v for v in cases if v['variant']=='candidate']
        passed=(all(v['grade']=='correct' for v in target if v['question_id']=='T034') and
                all(v['grade'] in ('partial','correct') for v in target if v['question_id']=='T026') and
                all(v['grade'] not in ('runtime_error','false_refusal') for v in target))
        decision='PILOT_PASS' if passed else 'STOP_PACKING_EXPERIMENT'
    result=dict(decision=decision,full90_executed=False,groups=groups,aggregate=aggregate,cases=cases,
                scope='Pilot six distinct questions with repetitions, not full90 metrics. Source reviews reused; no new human/expert judgments.',holdout_used=False)
    (a.out/'E5_second_refill_metrics.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    buf=io.StringIO();w=csv.writer(buf,lineterminator='\n');w.writerow(['qid','variant','repeat','grade','point_mask','offered_ids','selected_ids','supported_ids','raw_first_response','prompt_sha256','trace_sha256'])
    for v in cases:w.writerow([v['question_id'],v['variant'],v['repeat'],v['grade'],''.join(str(int(b)) for b in v['point_mask']),','.join(v['offered_ids']),','.join(v['selected_ids']),','.join(v['supported_citation_ids']),v['first_raw'],v['messages_sha256'],v['trace_sha256']])
    (a.out/'E5_second_refill_calls.csv').write_bytes(b'\xef\xbb\xbf'+buf.getvalue().encode())
    print(json.dumps(dict(decision=decision,groups=groups,aggregate=aggregate),ensure_ascii=False))
if __name__=='__main__':main()
