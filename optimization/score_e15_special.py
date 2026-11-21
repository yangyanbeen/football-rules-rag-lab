"""Independent input/quality/lifecycle/resource gates for archived frontend pairs."""
import argparse,collections,csv,json,statistics,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from answer_eval_core import read,record,digest,canonical
from task13_audit import validate_private

def save(p,v):p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
def main(a):
    run=a.run.resolve();done=read(run/'completed.json') if (run/'completed.json').exists() else None
    labels={q['question_id']:q for q in read(ROOT/'optimization/datasets/dev_40.json')+read(ROOT/'optimization/datasets/regression_50.json')}
    old={r['question_id']:r for r in read(ROOT/'optimization/reports/E14_live90_metrics.json')['cases'] if r['variant']=='candidate'};known={}
    for name in ('E1_selection_prompt','E4_duplicate_repair','E5_A_candidate_window','D036_business_gate','E14_runtime','E15_lifecycle'):
        path=ROOT/'optimization/experiments'/name/'source_reviews.tsv'
        if path.exists():
            for key,g,bits,ids,note in csv.reader(path.open(encoding='utf8'),delimiter='\t'):
                q,c=key.split('|',1);known[q,frozenset(c.split(','))]=dict(grade=g,point_mask=[b=='1' for b in bits],supported_citation_ids=[] if ids=='-' else ids.split(','),note=note)
    for q,r in old.items():
        if r['selected_ids']:known[q,frozenset(r['selected_ids'])]={k:r[k] for k in ('grade','point_mask','supported_citation_ids','note')}
    samples=[]
    with (run/'resources.jsonl').open(encoding='utf8') as f:
        for line in f:
            try:samples.append(json.loads(line))
            except ValueError:
                if not a.partial:raise
    sample_groups={}
    for s in samples:sample_groups.setdefault(s['label'],[]).append(s)
    intervals=[b['monotonic']-aa['monotonic'] for aa,b in zip(samples,samples[1:])]
    rows=[];queue={};raw={};verified=set()
    for path in sorted(run.glob('[DT][0-9][0-9][0-9]-r?-?.json')):
        try:t=read(path)
        except ValueError:
            if a.partial:continue
            raise
        if done:assert digest(path.read_bytes())==done['hashes'][path.name]
        r=t['result'];qid=t['question_id'];q=labels[qid];raw[t['name']]=t;review=None
        if r and not a.partial:
            impl=digest(canonical(r['implementation']));validate_private(r,q['question'],False)
            if impl not in verified:
                identity=r['implementation'];producer=identity['source_commit']
                assert producer==read(run/'metadata.json')['source_commit']
                assert subprocess.run(['git','merge-base','--is-ancestor',producer,'HEAD'],cwd=ROOT,capture_output=True).returncode==0
                for filename,ref in identity['sources'].items():
                    assert digest(subprocess.check_output(['git','show',producer+':'+filename],cwd=ROOT))==ref['sha256']
                verified.add(impl)
        if r:
            if r['error']:review=dict(grade='runtime_error',point_mask=[False]*len(q['expected_answer_points']),supported_citation_ids=[])
            elif r['status']=='refused':review=dict(grade='false_refusal' if q['answerable'] else 'correct_refusal',point_mask=[False]*len(q['expected_answer_points']),supported_citation_ids=[])
            else:review=known.get((qid,frozenset(r['selected_ids'])))
            if review is None:
                queue[qid+'|'+','.join(r['selected_ids'])]=dict(question=q['question'],points=q['expected_answer_points'],context=r['context'],selected_ids=r['selected_ids'])
        ev=t['stage_events'];start=next((e for e in ev if e['stage']=='reranker_release_start'),None);end=next((e for e in ev if e['stage']=='reranker_release_end'),None)
        delta=None
        if start and end and 'available' in start.get('memory',{}) and 'available' in end.get('memory',{}):
            aa=start['memory'];bb=end['memory'];delta=dict(object_collected=end['object_collected'],seconds=end['monotonic']-start['monotonic'],
                RSS_freed_GiB=(aa['rss']-bb['rss'])/2**30,private_freed_GiB=(aa['private']-bb['private'])/2**30,available_gain_GiB=(bb['available']-aa['available'])/2**30)
        periodic=t['resources']['low_point'];stage_mem=[e for e in ev if 'available' in e.get('memory',{})];low_stage=min(stage_mem,key=lambda e:e['memory']['available']) if stage_mem else None
        if low_stage and low_stage['memory']['available']<periodic['available']:low_time=low_stage['monotonic'];low_label=low_stage['stage']
        else:
            low_time=periodic['monotonic'];prior=[e for e in ev if e['monotonic']<=low_time];low_label=max(prior,key=lambda e:e['monotonic'])['stage'] if prior else 'before_worker_entry'
        gate_zero=bool(r and qid=='D036' and r['retrieval'] is None and not r['attempts'] and not any(e['stage'] in ('lazy_retrieval_construction_start','reranker_reconstruction_start') for e in ev))
        post_release=[]
        if end:
            last=max(e['monotonic'] for e in ev)
            post_release=[e['memory']['available']/2**30 for e in stage_mem if end['monotonic']<=e['monotonic']<=last]
            post_release += [s['available']/2**30 for s in sample_groups.get(t['name'],[]) if end['monotonic']<=s['monotonic']<=last]
        rows.append(dict(name=t['name'],question_id=qid,repeat=t['repeat'],variant=t['variant'],error=t['error'],review=review,status=r['status'] if r else None,
            seconds=t['seconds'],minimum_available_GiB=t['combined_available_min_GiB'],low_stage=low_label,low_before_release=low_time<end['monotonic'] if end else None,
            post_release_min_available_GiB=min(post_release) if post_release else None,
            before_available_GiB=t['before']['available_GiB'],before_models=[m['name'] for m in (t['before_models'] or [])],delta=delta,D036_zero=gate_zero,
            actual_calls=len(r['attempts']) if r else None,selected_ids=r['selected_ids'] if r else [],raw_record=record(path)))
    pairs=[];by={(r['question_id'],r['repeat'],r['variant']):r for r in rows}
    for qid,repeat in dict.fromkeys((r['question_id'],r['repeat']) for r in rows):
        aa=by.get((qid,repeat,'A'));bb=by.get((qid,repeat,'B'))
        if not aa or not bb:continue
        ar=raw[aa['name']]['result'];br=raw[bb['name']]['result'];inputs=bool(ar and br and ar['messages']==br['messages'] and ar['context']==br['context'] and ar['retrieved_ids']==br['retrieved_ids'])
        quality=bool(aa['review'] and bb['review'] and bb['review']['grade']==aa['review']['grade'] and all(not oldbit or newbit for oldbit,newbit in zip(aa['review']['point_mask'],bb['review']['point_mask'])))
        # An improved coverage result is allowed, but losses are never hidden by grade counts.
        if aa['review'] and bb['review'] and bb['review']['grade']=='correct':quality=True
        pairs.append(dict(question_id=qid,repeat=repeat,inputs_identical=inputs,ranked_results_identical=bool(ar and br and (ar['retrieval'] or {}).get('results')==(br['retrieval'] or {}).get('results')),
            final_identity_equal=bool(ar and br and all(ar[k]==br[k] for k in ('status','answer','citations','selected_ids'))),
            quality_not_degraded=quality,A_ids=aa['selected_ids'],B_ids=bb['selected_ids'],A_grade=aa['review']['grade'] if aa['review'] else None,B_grade=bb['review']['grade'] if bb['review'] else None))
    candidates=[r for r in rows if r['variant']=='B'];summaries={}
    for v in 'AB':
        rr=[r for r in rows if r['variant']==v];judged=[r for r in rr if r['review']]
        n=sum(len(r['review']['supported_citation_ids']) for r in judged);d=sum(len(r['selected_ids']) for r in judged)
        summaries[v]=dict(requests=len(rr),grades=dict(collections.Counter(r['review']['grade'] if r['review'] else 'pending' for r in rr)),
            citations=dict(numerator=n,denominator=d,value=n/d if d else None),max_seconds=max([r['seconds'] for r in rr] or [0]),
            minimum_available_GiB=min([r['minimum_available_GiB'] for r in rr] or [0]),below1=sum(r['minimum_available_GiB']<1 for r in rr))
    gates=dict(complete28=len(rows)==28 and done is not None and done['status']=='COMPLETED' and all(not r['error'] for r in rows),
        inputs_preserved=len(pairs)==14 and all(p['inputs_identical'] and p['ranked_results_identical'] for p in pairs),
        quality_preserved=not queue and len(pairs)==14 and all(p['quality_not_degraded'] for p in pairs),
        source_facts_correct=all(r['review'] and r['review']['grade']=='correct' for r in candidates if r['question_id'] in ('D001','D002','T001','D004')),
        D036_zero=all(by.get(('D036',1,v)) and by['D036',1,v]['D036_zero'] for v in 'AB'),
        object_release=all(r['delta'] and r['delta']['object_collected'] for r in candidates if r['question_id']!='D036'),
        latency=all(r['seconds']<=60 for r in candidates),resource=all(r['minimum_available_GiB']>=1 for r in candidates),
        citations=summaries['B']['citations']['value'] is not None and summaries['A']['citations']['value'] is not None and summaries['B']['citations']['value']>=summaries['A']['citations']['value'])
    deltas=[r['delta'] for r in candidates if r['delta']];release_summary={k:dict(median=statistics.median(d[k] for d in deltas),minimum=min(d[k] for d in deltas),maximum=max(d[k] for d in deltas)) for k in ('RSS_freed_GiB','private_freed_GiB','available_gain_GiB')} if deltas else {}
    value=dict(partial=a.partial,gates=gates,all_gates_passed=not a.partial and all(gates.values()),summaries=summaries,pairs=pairs,cases=rows,
        release_summary=release_summary,pending_reviews=len(queue),full90_executed=False,holdout40_used=False,
        sampling=dict(target_wait_seconds=.2,actual_median_seconds=statistics.median(intervals) if intervals else None,actual_max_gap_seconds=max(intervals) if intervals else None),
        original_archive_audit=record(ROOT/'optimization/reports/E15_archive_memory_audit.json'),
        method='Concurrent source/body/order comparisons; reviewed necessary points and exact source sets. Object collection separate from actual Windows physical availability and process working set/private commit. Whole-request minimum includes construction; endpoints and periodic samples both counted.')
    save(ROOT/('optimization/reports/'+a.prefix+'_review_queue.json'),list(queue.values()));save(ROOT/('optimization/reports/'+a.prefix+'_special_metrics.json'),value)
    print(json.dumps(dict(gates=gates,summaries=summaries,release_summary=release_summary,pending_reviews=len(queue)),ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--prefix',default='E15');p.add_argument('--partial',action='store_true');main(p.parse_args())
