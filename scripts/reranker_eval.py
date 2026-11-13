"""Task10 policy, metrics, truncation analysis and model-free evidence replay."""
from __future__ import annotations
import json,math,re,subprocess
from pathlib import Path
from eval_dataset import ROOT,EVAL,canonical,digest,load_jsonl
from bm25_index import record,write_new,committed
from bm25_retrieval_eval import now,statistics,instant,producer_before
from hybrid_retrieval_eval import SOURCES as OLD_SOURCES,INPUTS as OLD_INPUTS
from retrieval_metrics import compute_metrics
from dense_retrieval_eval import normalize_query
from rrf import fuse,SOURCE_FIELDS

BASE='73d5b88bede56dbf83df1c960c9c7e4861e2ef31'
CONFIG='config/reranker_experiment.json'
DIRECTORY=ROOT/'reports/retrieval/bge_reranker_b0'
LEDGER=DIRECTORY/'test_usage.jsonl'
METHODS=('no_rerank','top20','top40','top80')
BUDGETS={'no_rerank':0,'top20':20,'top40':40,'top80':80}
NATIVE=('scripts/bge_reranker.py','scripts/reranker_live.py','scripts/reranker_eval.py',
        'scripts/run_reranker_experiment.py','scripts/verify_reranker_contract.py')
SOURCES=tuple(dict.fromkeys(NATIVE+OLD_SOURCES))
INPUTS=tuple(dict.fromkeys((CONFIG,'docs/TASK_10_SCOPE.md')+OLD_INPUTS))
ARTIFACTS=('run_started.json','source_map.json','predictions.jsonl','summary.json','error_analysis.json')


def fields(value,names,what):
    if not isinstance(value,dict) or set(value)!=set(names):raise ValueError('Unexpected fields in '+what)


def number(v,positive=False):
    return type(v) in (int,float) and math.isfinite(v) and (v>0 if positive else v>=0)


def sha(v):return isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v) is not None


def config():
    cfg=json.loads((ROOT/CONFIG).read_text('utf-8'))
    fixed={'version':'bge-reranker-b0-1.0','model_id':'BAAI/bge-reranker-base',
      'revision':'2cfc18c9415c912f9d8155881c133215df768a70','precision':'official FP32 ONNX, no quantization',
      'provider':'CPUExecutionProvider','threads':8,'batch_size':8,'max_length':512,
      'tokenization':'query/passage pair; longest_first; right truncation; dynamic batch right padding; pad_id=1',
      'passage':'section_path joined by space/slash/space + two newlines + original content_zh',
      'channel_top_k':80,'fused_top_k':80,'rrf_k':60,'output_top_k':10,'bm25_template':'title_body',
      'methods':list(METHODS),'warmup_repetitions':3,'measured_repetitions':1,'concurrency':1,'cache':False,
      'warmup_question':'请查找球场球门的规定尺寸资料。',
      'variant_order':'rotate methods left by query index modulo four',
      'selection':'dev MRR@10 descending, Recall@5 descending, Recall@10 descending, total P50 ascending, method order',
      'percentile_method':'linear interpolation at q*(n-1)',
      'packages':{'numpy':'1.26.4','onnxruntime':'1.19.2','tokenizers':'0.22.1'}}
    fields(cfg,set(fixed)|{'files','download'},'reranker config')
    if canonical({k:cfg[k] for k in fixed})!=canonical(fixed):raise ValueError('Task10 fixed policy differs')
    fields(cfg['files'],('onnx/model.onnx','tokenizer.json','tokenizer_config.json','special_tokens_map.json','config.json'),'model files')
    for item in cfg['files'].values():
        fields(item,('size_bytes','sha256'),'model identity')
        if type(item['size_bytes']) is not int or item['size_bytes']<1 or not sha(item['sha256']):raise ValueError('Invalid model identity')
    if cfg['files']['onnx/model.onnx']!={'size_bytes':1112459588,'sha256':'15b9a8c3da82eddf263df571281166e00e9308fe19d077084b642ebfcaf06d2b'}:raise ValueError('Not official pinned ONNX')
    fields(cfg['download'],('official','transport','upstream_tree'),'model download source')
    if cfg['download']['official']!='https://huggingface.co/BAAI/bge-reranker-base/tree/'+cfg['revision']:raise ValueError('Wrong upstream')
    return cfg


def snapshots():return {p:record(ROOT/p) for p in SOURCES+INPUTS}


def validate_inputs(saved,source,current=False):
    if set(saved)!=set(SOURCES+INPUTS):raise ValueError('Incomplete inputs')
    committed((),source)
    for p in SOURCES+INPUTS:
        commit=source if p in NATIVE or p in (CONFIG,'docs/TASK_10_SCOPE.md') else BASE
        raw=subprocess.check_output(['git','show',commit+':'+p],cwd=ROOT)
        expected={'path':p,'size_bytes':len(raw),'sha256':digest(raw)}
        if canonical(expected)!=canonical(saved[p]):raise ValueError('Changed input producer: '+p)
        if current and record(ROOT/p)!=expected:raise ValueError('Current input differs: '+p)


def expanded(channels,known):
    fields(channels,('dense','bm25'),'channels')
    result={}
    for c,rows in channels.items():
        if not isinstance(rows,list) or len(rows)>80 or (c=='dense' and len(rows)!=80):raise ValueError('Wrong channel budget')
        extra=('rank','score','distance') if c=='dense' else ('rank','score')
        result[c]=[]
        for r in rows:
            fields(r,('chunk_id',)+extra,'channel result')
            if r['chunk_id'] not in known:raise ValueError('Unknown chunk')
            result[c].append({**known[r['chunk_id']],**{k:r[k] for k in extra}})
    return result


def validate_packet(packet,question,method,known,cfg):
    fields(packet,('method','query','channels','before','reranker','results','timing','embedding_observation','channel_timing'),'actual packet')
    if packet['method']!=method or packet['query']!=normalize_query(question):raise ValueError('Query/method mismatch')
    candidates=fuse(expanded(packet['channels'],known),60,80)['rrf']
    before=[{'chunk_id':r['chunk_id'],'rank':r['rank'],'score':r['score']} for r in candidates]
    if canonical(before)!=canonical(packet['before']) or len(before)!=80:raise ValueError('RRF source ranks/scores not reproducible')
    rerank=packet['reranker'];budget=BUDGETS[method]
    if not budget:
        if rerank is not None or packet['results']!=before[:10]:raise ValueError('Control unexpectedly reranked')
    else:
        fields(rerank,('results','batches','timing'),'reranker output');rows=rerank['results']
        if not isinstance(rows,list) or len(rows)!=budget:raise ValueError('Wrong rerank budget')
        if {r['chunk_id'] for r in rows}!={r['chunk_id'] for r in before[:budget]}:raise ValueError('Candidate loss/injection')
        for rank,r in enumerate(rows,1):
            fields(r,('chunk_id','before_rank','rank','score','query_sha256','passage_sha256','input_ids_sha256','original_tokens','used_tokens','truncated_tokens'),'model result')
            if type(r['rank']) is not int or r['rank']!=rank or type(r['before_rank']) is not int or not 1<=r['before_rank']<=budget:raise ValueError('Rank invalid')
            if before[r['before_rank']-1]['chunk_id']!=r['chunk_id']:raise ValueError('Before rank differs')
            if type(r['score']) not in (int,float) or not math.isfinite(r['score']):raise ValueError('Nonfinite logit')
            if r['query_sha256']!=digest(packet['query'].encode()) or not sha(r['passage_sha256']) or not sha(r['input_ids_sha256']):raise ValueError('Invalid model input hashes')
            if any(type(r[k]) is not int for k in ('original_tokens','used_tokens','truncated_tokens')):raise ValueError('Token counts not integer')
            if not 1<=r['used_tokens']<=512 or r['original_tokens']<r['used_tokens'] or r['truncated_tokens']!=r['original_tokens']-r['used_tokens']:raise ValueError('Token/truncation accounting differs')
        if rows!=sorted(rows,key=lambda r:(-r['score'],r['chunk_id'])):raise ValueError('Logit sort differs')
        expected=[{'chunk_id':r['chunk_id'],'rank':r['rank'],'score':r['score']} for r in rows[:10]]
        if packet['results']!=expected:raise ValueError('Top10 differs from full reranking')
        batches=rerank['batches'];offsets=list(range(0,budget,8))
        if not isinstance(batches,list) or len(batches)!=len(offsets):raise ValueError('Missing inference batches')
        by_before={r['before_rank']:r for r in rows}
        for b,offset in zip(batches,offsets):
            fields(b,('offset','size','padded_length','tokenization_and_tensor_seconds','inference_seconds'),'batch')
            size=min(8,budget-offset)
            if any(type(b[k]) is not int for k in ('offset','size','padded_length')) or b['offset']!=offset or b['size']!=size:raise ValueError('Batch shape differs')
            if b['padded_length']!=max(by_before[i+1]['used_tokens'] for i in range(offset,offset+size)):raise ValueError('Batch padding length differs')
            if not all(number(b[k],True) for k in ('tokenization_and_tensor_seconds','inference_seconds')):raise ValueError('Invalid batch timing')
        rt=rerank['timing'];fields(rt,('tokenization_and_tensor_seconds','inference_seconds','other_seconds','total_seconds'),'rerank stages')
        if not all(number(v,True) for v in rt.values()) or abs(rt['total_seconds']-sum(v for k,v in rt.items() if k!='total_seconds'))>1e-7:raise ValueError('Rerank stage containment differs')
        for key in ('tokenization_and_tensor_seconds','inference_seconds'):
            if abs(rt[key]-sum(b[key] for b in batches))>1e-7:raise ValueError('Batch timing does not sum')
    timing=packet['timing']
    fields(timing,('normalization_seconds','dense_seconds','bm25_seconds','fusion_seconds','rerank_seconds','total_seconds'),'chain stages')
    if not all(number(v,k!='rerank_seconds' or budget>0) for k,v in timing.items()):raise ValueError('Invalid chain timing')
    if not budget and timing['rerank_seconds']!=0:raise ValueError('Control rerank cost not zero')
    if budget and timing['rerank_seconds']+1e-7<rerank['timing']['total_seconds']:raise ValueError('Outer rerank omitted work')
    if abs(timing['total_seconds']-sum(v for k,v in timing.items() if k!='total_seconds'))>1e-7:raise ValueError('Chain stages not contained')
    ct=packet['channel_timing'];fields(ct,('dense','bm25'),'channel clocks')
    fields(ct['dense'],('query_embedding_seconds','vector_search_seconds'),'dense clocks')
    fields(ct['bm25'],('normalization_seconds','tokenization_seconds','scoring_seconds','total_seconds'),'BM25 clocks')
    if not all(number(v,True) for part in ct.values() for v in part.values()):raise ValueError('Invalid channel clocks')
    if timing['dense_seconds']+1e-7<sum(ct['dense'].values()) or timing['bm25_seconds']+1e-7<ct['bm25']['total_seconds']:raise ValueError('Outer retrieval omitted work')
    if abs(ct['bm25']['total_seconds']-sum(v for k,v in ct['bm25'].items() if k!='total_seconds'))>1e-7:raise ValueError('BM25 clocks not additive')
    obs=packet['embedding_observation'];fields(obs,('inputs','elapsed_seconds','prompt_eval_count','server_load_duration_ns','server_total_duration_ns'),'embedding observation')
    if type(obs['inputs']) is not int or obs['inputs']!=1 or not number(obs['elapsed_seconds'],True):raise ValueError('Embedding count invalid')
    if any(type(obs[k]) is not int or obs[k]<0 for k in ('prompt_eval_count','server_load_duration_ns','server_total_duration_ns')):raise ValueError('Invalid model counters')
    if not obs['server_load_duration_ns']<=obs['server_total_duration_ns']<=obs['elapsed_seconds']*1e9+1e6 or obs['elapsed_seconds']>ct['dense']['query_embedding_seconds']+1e-7:raise ValueError('Embedding clocks invalid')
    return packet


def errors_for(questions,rows,split):
    cases=[];counts={m:{'miss_at_5':0,'miss_at_10':0,'no_gold_in_candidates':0,'gold_lost_vs_top80':0,'rerank_worsened_mrr':0} for m in METHODS}
    for q,row in zip(questions,rows):
        if not q['answerable']:continue
        gold=set(q['expected_chunk_ids']);variants=row['variants'];full={r['chunk_id'] for r in variants['top80']['before']};baseline=None
        for m in METHODS:
            packet=variants[m];budget=BUDGETS[m] or 80;prefix=[r['chunk_id'] for r in packet['before'][:budget]]
            ranked=[r['chunk_id'] for r in packet['results']];first=next((i for i,cid in enumerate(ranked,1) if cid in gold),None)
            mrr=1/first if first else 0.
            if m=='no_rerank':baseline=mrr
            flags={'miss_at_5':not bool(gold&set(ranked[:5])),'miss_at_10':not bool(gold&set(ranked)),
                   'no_gold_in_candidates':not bool(gold&set(prefix)),
                   'gold_lost_vs_top80':bool(gold&full) and not bool(gold&set(prefix)),
                   'rerank_worsened_mrr':m!='no_rerank' and mrr<baseline}
            for k,v in flags.items():counts[m][k]+=v
            if any(flags.values()):cases.append({'question_id':q['question_id'],'method':m,'gold_chunk_ids':sorted(gold),
                'candidate_budget':budget,'gold_in_candidates':sorted(gold&set(prefix)),
                'gold_excluded_by_prefix':sorted((gold&full)-set(prefix)),'first_gold_rank':first,'flags':flags,
                'before_top10':[r['chunk_id'] for r in packet['before'][:10]],'after_top10':ranked})
    return {'split':split,'counts':counts,'cases':cases,'interpretation':'Truncation loss: no labelled support in prefix while at least one exists in full80. Missing some gold IDs is listed separately. Test is report-only, never used to retune.'}


def summarize(questions,rows,split):
    methods={}
    for m in METHODS:
        packets=[r['variants'][m] for r in rows]
        quality=compute_metrics(questions,[{'question_id':q['question_id'],'results':p['results']} for q,p in zip(questions,packets)])
        logits=[r for p in packets if p['reranker'] for r in p['reranker']['results']]
        methods[m]={'quality':quality,'latency':{name:statistics([p['timing'][name] for p in packets]) for name in ('rerank_seconds','total_seconds')},
                    'scored_pairs':len(logits),'truncated_pairs':sum(r['truncated_tokens']>0 for r in logits),
                    'candidate_budget':BUDGETS[m] or 80,'reranker_enabled':bool(BUDGETS[m])}
    selected=sorted(METHODS,key=lambda m:(-methods[m]['quality']['metrics']['MRR@10'],
                   -methods[m]['quality']['metrics']['Recall@5'],-methods[m]['quality']['metrics']['Recall@10'],
                   methods[m]['latency']['total_seconds']['P50_ms'],METHODS.index(m)))[0] if split=='dev' else None
    base=methods['no_rerank']['quality']['metrics']
    return {'version':'reranker-summary-1.0','split':split,'methods':methods,'selected_on_this_split':selected,
            'vs_no_rerank':{m:{k:r['quality']['metrics'][k]-base[k] for k in ('Recall@5','Recall@10','MRR@10')} for m,r in methods.items()},
            'latency_scope':'One actual full chain per query per method, rotating order, serial CPU, no cache; model/index load and warmups excluded. All questions including unanswerable included. P50/P95 descriptive, not production SLA.',
            'nDCG@10':None,'nDCG_reason':'No graded relevance labels; not computed.',
            'new_embedding_queries':len(rows)*4,'new_reranker_pairs':sum(v['scored_pairs'] for v in methods.values()),'answer_llm_requests':0}


def validate_grant(grant,out,current=False):
    fields(grant,('version','purpose','used_for_parameter_selection','prepared_at','source_commit','inputs','config',
                 'development_manifest','development_summary','verification','selected_method','allowed_run_directory','test_sha256'),'test grant')
    if grant['version']!='reranker-final-report-1.0' or grant['purpose']!='final_report' or grant['used_for_parameter_selection'] is not False:raise ValueError('Wrong test purpose')
    if grant['config']!=config() or grant['allowed_run_directory']!=out.relative_to(ROOT).as_posix() or out!=DIRECTORY/'test':raise ValueError('Test config/directory differs')
    if grant['test_sha256']!=digest((EVAL/'retrieval_test.jsonl').read_bytes()):raise ValueError('Test lock differs')
    producer_before(grant['source_commit'],grant['prepared_at']);validate_inputs(grant['inputs'],grant['source_commit'],current)
    for name in ('development_manifest','development_summary','verification'):
        item=grant[name];fields(item,('path','size_bytes','sha256'),'grant artifact')
        if item!=record(ROOT/item['path']):raise ValueError('Grant artifact differs')
        raw=subprocess.check_output(['git','show',grant['source_commit']+':'+item['path']],cwd=ROOT)
        if digest(raw)!=item['sha256']:raise ValueError('Uncommitted grant artifact')
    dev=replay(ROOT/grant['development_manifest']['path'].rsplit('/',1)[0])
    if dev['selected_on_this_split']!=grant['selected_method']:raise ValueError('Selection differs from dev')
    verification=json.loads((ROOT/grant['verification']['path']).read_text('utf-8'))
    if verification['status']!='PASS' or verification['passed']!=verification['total'] or not all(v is True for v in verification['checks'].values()):raise ValueError('Development verification failed')
    if verification['development_manifest']!=grant['development_manifest']:raise ValueError('Verification is for another development run')
    if instant(grant['prepared_at'])<=instant(json.loads((ROOT/grant['development_manifest']['path']).read_text('utf-8'))['completed_at']):raise ValueError('Authorization predates development')
    return grant


def replay(directory):
    directory=Path(directory).resolve()
    if not directory.is_relative_to(ROOT/'reports/retrieval'):raise ValueError('Unsafe run path')
    manifest=json.loads((directory/'run_manifest.json').read_text('utf-8'))
    fields(manifest,('version','run_id','split','purpose','source_commit','inputs','config','started_at','authorization',
                     'status','completed_at','wall_seconds','environment','load_seconds','warmups','index_snapshots','artifacts'),'run manifest')
    if manifest['version']!='reranker-run-1.0' or manifest['status']!='COMPLETE' or manifest['split'] not in ('dev','test'):raise ValueError('Incomplete run')
    split=manifest['split'];cfg=config()
    if manifest['config']!=cfg or manifest['purpose']!=('development' if split=='dev' else 'final_report'):raise ValueError('Policy/purpose differs')
    validate_inputs(manifest['inputs'],manifest['source_commit'])
    producer_before(manifest['source_commit'],manifest['started_at'])
    if not instant(manifest['started_at'])<instant(manifest['completed_at']) or not number(manifest['wall_seconds'],True):raise ValueError('Invalid chronology')
    fields(manifest['artifacts'],ARTIFACTS,'run artifacts')
    for name,item in manifest['artifacts'].items():
        expected={k:v for k,v in record(directory/name).items() if k!='path'}
        if item!=expected:raise ValueError('Artifact hash mismatch: '+name)
    start=json.loads((directory/'run_started.json').read_text('utf-8'))
    if start!={k:manifest[k] for k in ('version','run_id','split','purpose','source_commit','inputs','config','started_at','authorization')}:raise ValueError('Start identity differs')
    if split=='test':
        auth=manifest['authorization']
        if auth!=record(ROOT/auth['path']):raise ValueError('Authorization hash differs')
        grant=json.loads((ROOT/auth['path']).read_text('utf-8'));validate_grant(grant,directory)
        if grant['source_commit']!=manifest['source_commit'] or not instant(grant['prepared_at'])<instant(manifest['started_at']):raise ValueError('Test outside source/time freeze')
    elif manifest['authorization'] is not None:raise ValueError('Unexpected dev test authorization')
    questions=load_jsonl(EVAL/('retrieval_'+split+'.jsonl'));rows=load_jsonl(directory/'predictions.jsonl')
    if len(rows)!=len(questions):raise ValueError('Question count differs')
    source=json.loads((directory/'source_map.json').read_text('utf-8'))
    reference=json.loads((ROOT/'reports/retrieval/dense_b0/dev/source_map.json').read_text('utf-8'))
    if canonical(source)!=canonical(reference):raise ValueError('Original99 source map differs')
    known={r['chunk_id']:r for r in source};total=0.
    for i,(q,row) in enumerate(zip(questions,rows)):
        fields(row,('question_id','question_sha256','run_id','split','order','variants'),'question evidence')
        if row['question_id']!=q['question_id'] or row['question_sha256']!=digest(q['question'].encode()) or row['run_id']!=manifest['run_id'] or row['split']!=split:raise ValueError('Question identity/order differs')
        order=list(METHODS[i%4:]+METHODS[:i%4])
        if row['order']!=order:raise ValueError('Measurement order differs')
        fields(row['variants'],METHODS,'variants')
        first=None
        for method in METHODS:
            packet=validate_packet(row['variants'][method],q['question'],method,known,cfg)
            ids=[r['chunk_id'] for r in packet['before']]
            if first is not None and ids!=first:raise ValueError('Unstable before candidates across variants')
            first=ids;total+=packet['timing']['total_seconds']
    warm=manifest['warmups'];fields(warm,METHODS,'warmups')
    for method,packets in warm.items():
        if not isinstance(packets,list) or len(packets)!=3:raise ValueError('Missing actual warmups')
        for packet in packets:validate_packet(packet,cfg['warmup_question'],method,known,cfg);total+=packet['timing']['total_seconds']
    snapshots=manifest['index_snapshots'];fields(snapshots,('before','after'),'read-only indexes')
    if snapshots['before']!=snapshots['after'] or len(snapshots['before'])!=13:raise ValueError('Index changed')
    if manifest['wall_seconds']+.1<total or (instant(manifest['completed_at'])-instant(manifest['started_at'])).total_seconds()+.2<total:raise ValueError('Wall clock omits measured work')
    if not number(manifest['load_seconds'],True):raise ValueError('Load clock invalid')
    environment=manifest['environment']
    fields(environment,('captured_at','python','system','machine','processor','logical_cpus','physical_memory_bytes','packages','providers','model_inputs','embedding_runtime'),'environment')
    if environment['packages']!=cfg['packages'] or environment['providers']!=['CPUExecutionProvider'] or environment['model_inputs']!=['input_ids','attention_mask']:raise ValueError('Runtime differs')
    if not instant(manifest['started_at'])<=instant(environment['captured_at'])<instant(manifest['completed_at']):raise ValueError('Environment not captured before measurements')
    summary=summarize(questions,rows,split);errors=errors_for(questions,rows,split)
    if canonical(summary)!=canonical(json.loads((directory/'summary.json').read_text('utf-8'))):raise ValueError('Summary not reproducible')
    if canonical(errors)!=canonical(json.loads((directory/'error_analysis.json').read_text('utf-8'))):raise ValueError('Error analysis differs')
    return summary
