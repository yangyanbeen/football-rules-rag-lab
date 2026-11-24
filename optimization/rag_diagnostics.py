"""Inventory, immutable snapshots, six-layer trace audit and experiment preflight.

All commands are offline. No model/index construction, subprocess Worker, or
network inference is performed. Semantic review cannot be replaced by IDs.
"""
import argparse,collections,json,re,statistics,subprocess,sys
from pathlib import Path
from six_layer_core import ROOT,read,ref,local,git,digest,canonical,policy,inventory,snapshot,normalize,diagnose,retrieval_metrics,check_plan,write_new


class TraceError(ValueError):
    def __init__(self,layer,code):self.layer=layer;self.code=code;super().__init__(layer+':'+code)


def verify_trace(wrapper,verified):
    r=normalize(wrapper)
    if r is None:return
    corpus={v['chunk_id']:v for v in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    for row in r.get('context',[]):
        if row.get('chunk_id') not in corpus or row!=corpus[row['chunk_id']]:raise TraceError('data','context_body_or_metadata_differs')
    if not set(r.get('selected_ids',[]))<=set(r.get('offered_ids',[])):raise TraceError('generation','unoffered_selection')
    if r.get('retrieval') and not r.get('error'):
        sys.path.insert(0,str(ROOT/'scripts'))
        from answer_eval_engine import pack
        from answer_eval_core import config
        cfg=config();expected=pack(r['question'],[corpus[c] for c in r['retrieved_ids']],cfg,(ROOT/cfg['prompt_file']).read_text('utf8'))
        if (r['context'],r['messages'])!=expected[:2]:raise TraceError('context','recorded_prompt_differs_from_packing')
    if r.get('_adapter'):
        # An incomplete public Graph trace is never silently treated as a full
        # Worker trace; the CLI requires original observations to normalize it.
        return
    identity=r.get('implementation')
    if identity:
        key=digest(canonical(identity))
        if key not in verified:
            producer=identity['source_commit']
            if not re.fullmatch('[a-f0-9]{40}',producer):raise TraceError('engineering','invalid_producer_commit')
            for name,record in identity['sources'].items():
                local(name)
                raw=subprocess.check_output(['git','show',producer+':'+name],cwd=ROOT)
                if digest(raw)!=record['sha256']:raise TraceError('engineering','producer_source_hash_mismatch')
            verified.add(key)
    sys.path.insert(0,str(ROOT/'scripts'))
    from task13_audit import validate_private
    validate_private(r,r['question'],False)


def load_labels(dataset_ids):
    registry={d['id']:d for d in policy()['datasets']};labels={}
    manifest=read(ROOT/'optimization/datasets/freeze_manifest.json')
    hashes={'optimization/'+r['path']:r['sha256'] for r in manifest['files']}
    for dataset_id in dataset_ids:
        item=registry[dataset_id]
        if item.get('unseen'):raise ValueError('Diagnostics cannot open a sealed unseen set; use its gated one-shot acceptance runner')
        path=local(item['path']);expected=item.get('sha256',hashes.get(item['path']))
        if not expected or digest(path.read_bytes())!=expected:raise TraceError('data','dataset_freeze_hash_mismatch')
        for row in read(path):
            if row['question_id'] in labels:raise ValueError('Duplicate dataset question ID')
            labels[row['question_id']]=row
    return labels


def checked_review(review,label,result,trace_sha):
    if review.get('question_id')!=label['question_id'] or review.get('question_sha256')!=digest(label['question'].encode('utf8')) or review.get('trace_sha256')!=trace_sha:
        raise ValueError('Review is not bound to this question/trace')
    allowed={'correct','partial','incorrect','false_refusal','correct_refusal','answer_instead_of_refusal','runtime_error'}
    mask=review.get('point_mask');support=review.get('supported_citation_ids')
    if review.get('grade') not in allowed or not isinstance(mask,list) or len(mask)!=len(label['expected_answer_points']) or any(type(b) is not bool for b in mask):raise ValueError('Review grade/point mask incomplete')
    conditions=review.get('condition_mask',[])
    if len(conditions)!=len(label.get('required_conditions',[])) or any(type(b) is not bool for b in conditions):raise ValueError('Required-condition review incomplete')
    if not isinstance(support,list) or len(support)!=len(set(support)) or not set(support)<=set(result['selected_ids']):raise ValueError('Review credits an unselected source')
    if not review.get('reviewer') or not review.get('note'):raise ValueError('Reviewer and source reasoning required; not a human approval receipt')
    if review['grade']=='correct' and (not label['answerable'] or result['status']!='answered' or not all(mask) or not all(conditions)):raise ValueError('Correct review contradicts answerability/trace/points/conditions')
    if review['grade']=='correct_refusal' and (label['answerable'] or result['status']!='refused'):raise ValueError('Correct refusal contradicts trace/label')
    return review


def audit_archive(suite):
    spec=policy()['archives'][suite];metrics=read(local(spec['metrics']));labels=load_labels(spec['datasets']);done=read(local(spec['completion']))
    if digest(local(spec['metrics']).read_bytes())!=spec['metrics_sha256']:raise TraceError('engineering','frozen_metric_report_changed')
    reviewed=[v for v in metrics['cases'] if 'variant' not in spec or v.get('variant')==spec['variant']]
    corpus_inventory=inventory()['data'];known_ids={r['chunk_id'] for r in map(json.loads,(ROOT/'data/processed/rag_chunks_zh.jsonl').read_text('utf8').splitlines())}
    verified=set();cases=[]
    for row in reviewed:
        path=local(row['raw_record']['path'])
        if ref(path)!=row['raw_record'] or digest(path.read_bytes())!=done['hashes'][path.name]:raise TraceError('engineering','archive_receipt_mismatch')
        wrapper=read(path);r=normalize(wrapper);qid=row['question_id'];label=labels[qid]
        if r and r['question']!=label['question']:raise TraceError('retrieval','question_label_mismatch')
        verify_trace(wrapper,verified)
        review=row.get('review') or {k:row[k] for k in ('grade','point_mask','supported_citation_ids')}
        if len(review['point_mask'])!=len(label['expected_answer_points']):raise ValueError('Review point-mask size differs')
        if review['grade']=='correct' and (not label['answerable'] or not r or r['status']!='answered' or not all(review['point_mask'])):raise ValueError('Correct review contradicts trace or frozen points')
        if review['grade']=='correct_refusal' and (label['answerable'] or not r or r['status']!='refused'):raise ValueError('Refusal review contradicts trace/label')
        case=diagnose(wrapper,label,review,known_ids=known_ids);case['raw_record']=ref(path);cases.append(case)
    if len(cases)!=len(labels) or {c['question_id'] for c in cases}!=set(labels):raise ValueError('Archive/labels coverage differs')
    findings=collections.Counter((f['layer'],f['code']) for c in cases for f in c['findings'] if f['severity']=='error')
    latency=[c['performance']['wall_seconds'] for c in cases if c['performance']['wall_seconds'] is not None]
    memory=[c['performance']['minimum_available_GiB'] for c in cases if c['performance']['minimum_available_GiB'] is not None]
    n=sum(len((row.get('review') or row)['supported_citation_ids']) for row in reviewed)
    d=sum(len(c['stages']['selected']) for c in cases)
    return dict(suite=suite,actual_records=len(cases),completed=done['status']=='COMPLETED',data=corpus_inventory,
        metric_source=ref(local(spec['metrics'])),completion_source=ref(local(spec['completion'])),
        primary_failure_layers=dict(collections.Counter(c['primary_layer'] or 'no_observed_failure' for c in cases)),
        error_findings=[dict(layer=l,code=k,questions=v) for (l,k),v in sorted(findings.items())],
        semantic_grades=dict(collections.Counter(c['grade'] for c in cases)),
        citation_support=dict(numerator=n,denominator=d,value=n/d if d else None),
        retrieval_metrics=[retrieval_metrics(cases,stage,k) for stage in ('union','fused','rerank_input','reranked','prompt') for k in ((5,10) if stage=='reranked' else (160,) if stage=='union' else (80,) if stage=='fused' else (40,) if stage=='rerank_input' else (5,))],
        performance=dict(wall_samples=len(latency),memory_samples=len(memory),max_wall_seconds=max(latency) if latency else None,
            min_available_GiB=min(memory) if memory else None,below1=sum(v<1 for v in memory),above60=sum(v>60 for v in latency)),
        cases=cases,new_model_calls=0,services_started=False,
        limitations=['Frozen annotated recall is distinct from exhaustive semantic relevance; precision is an annotation proxy.',
            'Correct semantic reviews override gold-ID mismatch; missing labels/resources are unknown rather than passed.',
            'Historical cohort diagnostics only, not fresh generalization or concurrent A/B evidence.'])


def freeze_committed(profile):
    value=snapshot(profile)
    names=[n for n in value['files'] if not n.startswith('data/indexes/')]
    tree={line.split('\t',1)[1]:line.split('\t',1)[0].split()[2] for line in git('ls-tree','-r','HEAD','--',*names).splitlines()}
    algorithm=git('rev-parse','--show-object-format')
    for name in names:
        data=local(name).read_bytes();blob=hashlib_blob(data,algorithm)
        if tree.get(name)!=blob:raise ValueError('Commit frozen governance/runtime sources first: '+name)
    value['source_tree_committed']=True;value['snapshot_identity']=digest(canonical(value));return value


def hashlib_blob(data,algorithm):
    import hashlib
    return hashlib.new(algorithm,b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for name in ('inventory','freeze'):
        p=sub.add_parser(name);p.add_argument('--profile',choices=tuple(policy()['profiles']),default='low_memory_facts');p.add_argument('--out',type=Path,required=True)
    p=sub.add_parser('audit');p.add_argument('--suite',choices=tuple(policy()['archives']),action='append',required=True);p.add_argument('--out',type=Path,required=True)
    p=sub.add_parser('case');p.add_argument('--trace',type=Path,required=True);p.add_argument('--dataset',choices=tuple(d['id'] for d in policy()['datasets']));p.add_argument('--qid');p.add_argument('--review',type=Path);p.add_argument('--original-question');p.add_argument('--show-content',action='store_true');p.add_argument('--out',type=Path,required=True)
    p=sub.add_parser('check-plan');p.add_argument('--plan',type=Path,required=True);p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=parser.parse_args();exit_code=0
    if a.command=='inventory':value=inventory(a.profile)
    elif a.command=='freeze':value=freeze_committed(a.profile)
    elif a.command=='audit':value=dict(version=policy()['version'],source_commit=git('rev-parse','HEAD'),suites=[audit_archive(s) for s in dict.fromkeys(a.suite)],new_model_calls=0,services_started=False)
    elif a.command=='case':
        wrapper=read(a.trace);verify_trace(wrapper,set());label=load_labels([a.dataset])[a.qid] if a.dataset and a.qid else None
        if bool(a.dataset)!=bool(a.qid):raise ValueError('Provide dataset and question ID together')
        r=normalize(wrapper) or {};review=None
        if label is not None and r:
            query=r.get('query_resolution')
            if (query and query['original_question_sha256']!=digest(label['question'].encode('utf8'))) or (not query and r['question']!=label['question']):raise TraceError('retrieval','question_label_mismatch')
        if a.review:
            if label is None:raise ValueError('A bound review requires dataset and question ID')
            review=checked_review(read(a.review),label,r,digest(a.trace.read_bytes()))
        value=diagnose(wrapper,label,review,original_question=a.original_question)
        value['integrity_scope']='missing_result' if not r else 'body_and_prompt_only_for_legacy_graph' if r.get('_adapter') else 'worker_private_contract_and_producer_sources'
        if label is not None:
            value['review_template']=dict(question_id=label['question_id'],question_sha256=digest(label['question'].encode('utf8')),
                trace_sha256=digest(a.trace.read_bytes()),expected_points=label['expected_answer_points'],required_conditions=label.get('required_conditions',[]),selected_ids=r.get('selected_ids',[]),
                point_mask=[None]*len(label['expected_answer_points']),supported_citation_ids=[],grade=None,reviewer=None,note=None,
                condition_mask=[None]*len(label.get('required_conditions',[])),
                human_approval='not established by this source-review template')
        if a.show_content:
            value['private_details']=dict(original_question=a.original_question or wrapper.get('question'),effective_question=r.get('question'),context=r.get('context'),messages=r.get('messages'),attempts=r.get('attempts'))
    else:
        baseline=read(a.snapshot);identity=baseline.pop('snapshot_identity',None)
        if identity!=digest(canonical(baseline)):raise ValueError('Snapshot hash mismatch')
        value=check_plan(read(a.plan),baseline,snapshot(baseline['profile']));exit_code=0 if value['valid'] else 2
    write_new(a.out,value)
    print(json.dumps(dict(command=a.command,out=str(a.out.resolve()),new_model_calls=0,services_started=False,valid=value.get('valid')),ensure_ascii=False))
    return exit_code


if __name__=='__main__':
    try:raise SystemExit(main())
    except TraceError as exc:
        print(json.dumps(dict(error=exc.code,layer=exc.layer,new_model_calls=0),ensure_ascii=False),file=sys.stderr);raise SystemExit(2)
