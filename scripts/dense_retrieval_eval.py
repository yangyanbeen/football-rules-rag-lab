"""Strict, standard-library-only replay of the fixed Dense Retrieval B0."""
from __future__ import annotations
import json, math, re, subprocess, unicodedata
from pathlib import Path
from eval_dataset import ROOT, digest, load_jsonl
from retrieval_metrics import compute_metrics

CONFIG=ROOT/'config/dense_retrieval_b0.json'
SOURCES=('scripts/dense_retrieval_eval.py','scripts/run_dense_retrieval.py',
 'scripts/recompute_dense_retrieval.py','scripts/retrieval_metrics.py',
 'scripts/verify_dense_metric_arithmetic.py','scripts/verify_dense_retrieval_contract.py',
 'scripts/dense_index.py','scripts/dense_telemetry.py','scripts/eval_dataset.py',
 'scripts/validate_eval_dataset.py','scripts/validate_eval_receipt.py')
SOURCE_FIELDS=('chunk_id','source_url','source_lines','law_number','record_sha256','content_zh_sha256')
TIMINGS=('normalization_seconds','query_embedding_seconds','vector_search_seconds','total_seconds')


def normalize_query(text):
    if not isinstance(text,str):raise ValueError('Question must be text')
    query=re.sub(r'\s+',' ',unicodedata.normalize('NFKC',text)).strip()
    if not query or len(query.encode('utf-8'))>1200:raise ValueError('Empty or oversized question')
    return query


def load_config(path=CONFIG):
    cfg=json.loads(Path(path).read_text('utf-8'))
    expected={'evaluation_version':'dense-retrieval-b0-1.0.0','dense_config':'config/dense_index.json',
      'dense_index':'data/indexes/dense','rag_config':'config/rag_b0.json','top_k':10,
      'query_normalization':'NFKC then trim and collapse whitespace','quality_repetition':1,
      'measured_repetitions':3,'warmup_repetitions':3,'warmup_query':'足球比赛场地的边线如何判断球出界？',
      'concurrency':1,'cache':False,'percentile_method':'linear interpolation at q * (n - 1)',
      'latency_unit':'seconds in raw rows; milliseconds in summary','test_purpose':'final_report',
      'used_for_parameter_selection':False}
    # Canonical JSON preserves the distinction between bool and int.
    if json.dumps(cfg,sort_keys=True)!=json.dumps(expected,sort_keys=True):
        raise ValueError('Configuration differs from the preregistered B0 policy; create a new experiment')
    return cfg


def file_record(path):
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT):raise ValueError('Evidence path outside repository')
    raw=path.read_bytes()
    return {'path':path.relative_to(ROOT).as_posix(),'size_bytes':len(raw),'sha256':digest(raw)}


def public_input_paths():
    return ['config/dense_retrieval_b0.json','config/dense_index.json','config/rag_b0.json',
      'data/eval/dataset_manifest.json','data/eval/retrieval_dev.jsonl','data/eval/retrieval_test.jsonl',
      'data/eval/answer_eval.jsonl','data/eval/hard_negatives.jsonl','data/eval/human_review_receipt.json',
      'data/manifests/dense_index_manifest.json','data/manifests/dense_chunk_ids.json',
      'data/manifests/rag_dataset_manifest.json','docs/TECHNICAL_DESIGN.md',
      'docs/DEVELOPMENT_PLAN_AND_REPORT.md']


def snapshots():return {p:file_record(ROOT/p) for p in public_input_paths()+list(SOURCES)}


def require_matching_snapshots(items):
    if not isinstance(items,dict) or set(items)!=set(public_input_paths()+list(SOURCES)):
        raise ValueError('Incomplete public data/code/config snapshot')
    if any(file_record(ROOT/p)!=r for p,r in items.items()):raise ValueError('Public data/code/config changed')


def require_committed_sources(commit):
    if not isinstance(commit,str) or not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Invalid code commit')
    if subprocess.run(['git','merge-base','--is-ancestor',commit,'HEAD'],cwd=ROOT,capture_output=True).returncode:
        raise ValueError('Source commit is not an ancestor of this checkout')
    for p in list(SOURCES)+['config/dense_retrieval_b0.json']:
        if subprocess.check_output(['git','show',commit+':'+p],cwd=ROOT)!=(ROOT/p).read_bytes():
            raise ValueError('Source/config differs from preregistered commit: '+p)


def finite(value,nonnegative=False):
    try:return type(value) in (int,float) and math.isfinite(value) and (not nonnegative or value>=0)
    except OverflowError:return False


def percentile(values,q):
    if not isinstance(values,(list,tuple)) or not values or not finite(q) or not 0<=q<=1 or any(not finite(v,True) for v in values):
        raise ValueError('Invalid percentile input')
    ordered=sorted(values);p=q*(len(ordered)-1);lo=math.floor(p);hi=math.ceil(p)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(p-lo)


def validate_predictions(questions,predictions,cfg,source_map,split,run_id):
    if split not in ('dev','test') or not isinstance(run_id,str) or not re.fullmatch('[a-f0-9]{32}',run_id):
        raise ValueError('Invalid split/run identity')
    if not isinstance(questions,list) or not isinstance(predictions,list) or not isinstance(source_map,list):
        raise ValueError('Question/prediction/source collections must be lists')
    known={r['chunk_id']:r for r in source_map}
    if len(known)!=len(source_map) or len(known)<cfg['top_k']:raise ValueError('Incomplete or duplicate source map')
    for source in source_map:
        if set(source)!=set(SOURCE_FIELDS) or not isinstance(source['chunk_id'],str):raise ValueError('Invalid public source record')
    qs={}
    for q in questions:
        qid=q['question_id'];gold=q['expected_chunk_ids']
        if (not isinstance(qid,str) or not qid or qid in qs or type(q['answerable']) is not bool
            or not isinstance(gold,list) or any(not isinstance(g,str) or g not in known for g in gold)
            or len(gold)!=len(set(gold)) or q['answerable']!=bool(gold)):
            raise ValueError('Invalid question identity, gold or answerability')
        normalize_query(q['question']);qs[qid]=q
    if len(predictions)!=len(qs):raise ValueError('Every question must have exactly one prediction')
    seen=set()
    for row in predictions:
        if set(row)!={'question_id','question_sha256','query','split','run_id','results','measurements'}:
            raise ValueError('Unexpected or missing prediction fields; no source bodies allowed')
        qid=row['question_id']
        if not isinstance(qid,str) or qid not in qs or qid in seen:raise ValueError('Unknown or duplicate prediction question')
        seen.add(qid);q=qs[qid]
        if (row['split']!=split or row['run_id']!=run_id or row['query']!=normalize_query(q['question'])
            or row['question_sha256']!=digest(q['question'].encode('utf-8'))):raise ValueError('Prediction query/split/run mismatch')
        results=row['results']
        if not isinstance(results,list) or len(results)!=cfg['top_k']:raise ValueError('Exactly Top10 required')
        ids=[];distances=[];scores=[]
        for rank,r in enumerate(results,1):
            if not isinstance(r,dict) or set(r)!=set(SOURCE_FIELDS)|{'rank','distance','score'}:raise ValueError('Invalid result fields')
            cid=r['chunk_id']
            if not isinstance(cid,str) or cid not in known or cid in ids or type(r['rank']) is not int or r['rank']!=rank:
                raise ValueError('Invalid result ID/rank')
            if {k:r[k] for k in SOURCE_FIELDS}!=known[cid]:raise ValueError('Forged source metadata')
            if (not finite(r['distance']) or not -1e-5<=r['distance']<=2.00001 or not finite(r['score'])
                or abs(r['score']-(1-r['distance']))>1e-6):raise ValueError('Invalid distance/score')
            ids.append(cid);distances.append(r['distance']);scores.append(r['score'])
        if list(zip(distances,ids))!=sorted(zip(distances,ids)):raise ValueError('Results not sorted by distance and ID')
        measurements=row['measurements']
        if not isinstance(measurements,list) or len(measurements)!=cfg['measured_repetitions']:raise ValueError('Incomplete repeated measurements')
        for rep,m in enumerate(measurements,1):
            if (not isinstance(m,dict) or set(m)!=set(TIMINGS)|{'repetition','ranked_ids','distances','scores','embedding_observation'}
                or type(m['repetition']) is not int or m['repetition']!=rep):raise ValueError('Invalid measurement fields/repetition')
            mids=m['ranked_ids'];md=m['distances'];ms=m['scores']
            if (not all(isinstance(x,list) and len(x)==cfg['top_k'] for x in (mids,md,ms))
                or any(not isinstance(cid,str) or cid not in known for cid in mids) or len(set(mids))!=len(mids)
                or any(not finite(v) or not -1e-5<=v<=2.00001 for v in md)
                or any(not finite(v) or abs(v-(1-d))>1e-6 for v,d in zip(ms,md))
                or list(zip(md,mids))!=sorted(zip(md,mids))):raise ValueError('Invalid repeated ranking/score')
            if rep==1 and (mids!=ids or md!=distances or ms!=scores):raise ValueError('First measurement differs from quality ranking')
            if any(not finite(m[k],True) for k in TIMINGS):raise ValueError('Invalid timing sample')
            if m['total_seconds']+1e-7<sum(m[k] for k in TIMINGS[:-1]):raise ValueError('Total timing omits measured stages')
            observation=m['embedding_observation']
            if (not isinstance(observation,dict) or set(observation)!={'inputs','elapsed_seconds','prompt_eval_count','server_total_duration_ns','server_load_duration_ns'}
                or type(observation.get('inputs')) is not int or observation['inputs']!=1
                or type(observation.get('prompt_eval_count')) is not int or observation['prompt_eval_count']<1
                or not finite(observation.get('elapsed_seconds'),True)
                or any(type(observation.get(k)) is not int or observation[k]<0 for k in ('server_total_duration_ns','server_load_duration_ns'))):
                raise ValueError('Missing actual embedding request observation')
    if seen!=set(qs):raise ValueError('Missing questions')
    return True


def latency_summary(rows):
    samples=[m for r in rows for m in r['measurements']]
    return {'questions':len(rows),'samples':len(samples),'unit':'milliseconds',
      'percentile_method':'linear interpolation at q * (n - 1)',
      'stages':{k:{'mean':sum(m[k] for m in samples)*1000/len(samples),
        'p50':percentile([m[k] for m in samples],.5)*1000,
        'p95':percentile([m[k] for m in samples],.95)*1000,
        'min':min(m[k] for m in samples)*1000,'max':max(m[k] for m in samples)*1000} for k in TIMINGS}}


def summarize(questions,predictions,cfg,source_map,split,run_id):
    validate_predictions(questions,predictions,cfg,source_map,split,run_id)
    scored=compute_metrics(questions,predictions)
    pq={r['question_id']:r for r in scored['per_question']};pred={r['question_id']:r for r in predictions}
    answerable=[q for q in questions if q['answerable']]
    misses5=[q['question_id'] for q in answerable if pq[q['question_id']]['Recall@5']==0]
    misses10=[q['question_id'] for q in answerable if pq[q['question_id']]['Recall@10']==0]
    partial=[q['question_id'] for q in answerable if pq[q['question_id']]['all_gold_coverage@5']<1]
    multi=[q for q in answerable if len(q['expected_chunk_ids'])>1]
    groups={}
    for category in sorted({c for q in answerable for c in q.get('categories',[])}):
        members=[q for q in answerable if category in q.get('categories',[])]
        groups[category]={'answerable_questions':len(members),'miss_top5':sum(q['question_id'] in misses5 for q in members),
                         'miss_top10':sum(q['question_id'] in misses10 for q in members)}
    errors={'miss_top5':len(misses5),'miss_top10':len(misses10),'not_all_gold_in_top5':len(partial),
      'multi_gold_questions':len(multi),'multi_gold_all_covered_top5':sum(q['question_id'] not in partial for q in multi),
      'category_groups_overlap':True,'by_category':groups,'labels_may_not_be_exhaustive':True,
      'unanswerable_retrieval_is_not_refusal':'Dense always retrieves; refusal quality belongs to task12'}
    if split=='dev':
        errors['development_cases']=[{'question_id':q['question_id'],'expected_chunk_ids':q['expected_chunk_ids'],
          'retrieved_top10':[r['chunk_id'] for r in pred[q['question_id']]['results']],
          'first_relevant_rank_within_10':pq[q['question_id']]['first_relevant_rank_within_10'],
          'miss_top5':q['question_id'] in misses5,'miss_top10':q['question_id'] in misses10}
          for q in answerable if q['question_id'] in partial]
    return {'schema_version':'dense-retrieval-summary-1.0','split':split,'run_id':run_id,
      'purpose':'development' if split=='dev' else 'final_report','label_policy':'human_reviewed',
      'label_scope':'Evidence annotations for fixed community snapshots; not official rules or expert certification',
      'quality_repetition':1,'quality':scored,'latency':latency_summary(predictions),
      'latency_by_answerability':{str(flag).lower():latency_summary([pred[q['question_id']] for q in questions if q['answerable']==flag]) for flag in (True,False) if any(q['answerable']==flag for q in questions)},
      'repeated_rankings_identical':all(all(m['ranked_ids']==row['measurements'][0]['ranked_ids'] for m in row['measurements']) for row in predictions),
      'error_analysis':errors,'generation_model_requests':0,'nDCG_reason':'No graded relevance labels'}


def replay(directory):
    """Recompute from public raw results; no corpus, model, vector or network needed."""
    directory=Path(directory).resolve();manifest=json.loads((directory/'run_manifest.json').read_text('utf-8'))
    if manifest.get('status')!='COMPLETE' or manifest.get('manifest_version')!='dense-retrieval-run-1.0':raise ValueError('Run is not complete')
    cfg=load_config();require_matching_snapshots(manifest['input_snapshots'])
    if manifest['config']!=cfg:raise ValueError('Run config differs')
    require_committed_sources(manifest['source_commit'])
    split=manifest['split']
    if split not in ('dev','test') or manifest.get('purpose')!=('development' if split=='dev' else 'final_report'):
        raise ValueError('Run split/purpose differs')
    count=40 if split=='dev' else 50
    if (manifest.get('used_for_parameter_selection') is not False or manifest.get('gold_passed_to_retrieval') is not False
        or type(manifest.get('llm_generation_requests')) is not int or manifest['llm_generation_requests']!=0
        or manifest.get('formal_index_artifacts_unchanged') is not True or manifest.get('query_request_count')!=count*cfg['measured_repetitions']
        or manifest.get('warmup_request_count')!=cfg['warmup_repetitions']):raise ValueError('Incorrect run scope or request counts')
    original=json.loads((ROOT/'data/manifests/dense_index_manifest.json').read_text('utf-8'))
    release=json.loads((ROOT/'data/eval/dataset_manifest.json').read_text('utf-8'))
    if (manifest['model_artifact']!=original['model_artifact'] or manifest['index_version']!=original['index_version']
        or manifest['index_manifest_sha256']!=original['local_manifest_sha256']
        or manifest['index_vector_fingerprint']!=original['vector_fingerprint']
        or manifest['corpus_sha256']!=original['config']['corpus_sha256']
        or manifest['corpus_version']!=original['config']['corpus_version']
        or manifest['dataset_version']!=release['dataset_version']
        or manifest['index_producer_implementation_sha256']!=original['implementation_sha256']):
        raise ValueError('Run data/model/index declaration differs from frozen baseline')
    for runtime in (manifest['model_runtime_before'],manifest['model_runtime_after']):
        if runtime.get('digest')!=original['model_artifact']['digest'] or type(runtime.get('size_vram')) is not int or runtime['size_vram']!=0:
            raise ValueError('Model runtime is not the pinned CPU model')
    if not finite(manifest.get('startup_loading_seconds'),True) or not finite(manifest.get('whole_run_wall_seconds'),True):
        raise ValueError('Invalid startup/run timing')
    warmups=manifest['warmups']
    if not isinstance(warmups,list) or len(warmups)!=cfg['warmup_repetitions']:raise ValueError('Incomplete warmup')
    for rep,w in enumerate(warmups,1):
        if (w.get('repetition')!=rep or w.get('query')!=cfg['warmup_query'] or not finite(w.get('total_seconds'),True)
            or set(w.get('timing',{}))!={'query_embedding_seconds','vector_search_seconds'}
            or any(not finite(v,True) for v in w['timing'].values())):raise ValueError('Invalid warmup record')
    required={'predictions.jsonl','requests.jsonl','run_started.json','source_map.json','summary.json','error_analysis.json'}
    if set(manifest['artifacts'])!=required:raise ValueError('Incomplete run artifact inventory')
    for name in required:
        if file_record(directory/name)!=manifest['artifacts'][name]:raise ValueError('Run artifact hash differs: '+name)
    started=json.loads((directory/'run_started.json').read_text('utf-8'))
    if any(started[k]!=manifest[k] for k in ('run_id','split','source_commit','input_snapshots','started_at','authorization')):
        raise ValueError('Started record differs from completed manifest')
    if split=='test':
        auth=manifest['authorization']
        if not isinstance(auth,dict) or file_record(ROOT/auth['path'])!=auth:raise ValueError('Test authorization changed')
        grant=json.loads((ROOT/auth['path']).read_text('utf-8'))
        if (grant.get('purpose')!='final_report' or grant.get('used_for_parameter_selection') is not False
            or grant.get('test_sha256')!=release['test_lock']['sha256'] or grant.get('config_sha256')!=digest(CONFIG.read_bytes())
            or grant.get('input_snapshots')!=manifest['input_snapshots']
            or grant.get('allowed_run_directory')!=directory.relative_to(ROOT).as_posix()):raise ValueError('Test grant/data/config mismatch')
        require_committed_sources(grant['source_commit'])
        for record in [grant['development_manifest'],grant['development_summary']]+grant['development_verification']:
            if file_record(ROOT/record['path'])!=record:raise ValueError('Authorized development evidence changed')
    elif manifest['authorization'] is not None:raise ValueError('Development run claims test authorization')
    source_map=json.loads((directory/'source_map.json').read_text('utf-8'))
    public_ids=json.loads((ROOT/'data/manifests/dense_chunk_ids.json').read_text('utf-8'))
    if (len(source_map)!=99 or {r['chunk_id']:(r['record_sha256'],r['content_zh_sha256']) for r in source_map}
        !={r['chunk_id']:(r['record_sha256'],r['content_zh_sha256']) for r in public_ids}):raise ValueError('Source map not bound to original corpus IDs/hashes')
    questions=load_jsonl(ROOT/f'data/eval/retrieval_{split}.jsonl');predictions=load_jsonl(directory/'predictions.jsonl')
    result=summarize(questions,predictions,cfg,source_map,split,manifest['run_id'])
    requests=load_jsonl(directory/'requests.jsonl')
    expected_requests=[{'question_id':r['question_id'],'query':r['query'],'run_id':r['run_id'],'split':split,'measurement':m}
                       for r in predictions for m in r['measurements']]
    if requests!=expected_requests:raise ValueError('Per-request journal differs from completed predictions')
    if json.loads((directory/'summary.json').read_text('utf-8'))!=result:raise ValueError('Stored summary differs from raw prediction recomputation')
    if json.loads((directory/'error_analysis.json').read_text('utf-8'))!=result['error_analysis']:
        raise ValueError('Stored error analysis differs from raw predictions')
    return result
