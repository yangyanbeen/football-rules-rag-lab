"""Task11 context assembly, conservative span metrics and model-free replay."""
import json,math,re,subprocess
from datetime import datetime,timezone
from fractions import Fraction
from pathlib import Path
from eval_dataset import ROOT,EVAL,canonical,digest,load_jsonl
from bm25_index import record,committed
from bm25_retrieval_eval import instant,producer_before
from structure_aware_chunking import CONFIG,MAP,STATS,AUDIT,config,describe

BASE='b9acb61a807bdc21b717711f3733ed238227e4a4'
DIRECTORY=ROOT/'reports/retrieval/structure_pc_b0'
LEDGER=DIRECTORY/'test_usage.jsonl'
INDEX='data/manifests/structure_index_manifest.json'
METHODS=('base','child','parent_child')
NATIVE=('scripts/structure_aware_chunking.py','scripts/structure_retrieval_eval.py','scripts/structure_retrieval_live.py',
        'scripts/run_structure_comparison.py','scripts/verify_structure_contract.py','scripts/verify_structure_delivery.py')
SOURCES=NATIVE+('scripts/eval_dataset.py','scripts/bm25_index.py','scripts/install_bm25_runtime.py','scripts/dense_index.py',
 'scripts/bm25_retrieval_eval.py','scripts/dense_retrieval_eval.py','scripts/run_bm25_retrieval.py','scripts/bge_reranker.py')
INPUTS=(CONFIG,MAP,STATS,AUDIT,INDEX,'docs/TASK_11_SCOPE.md','config/dense_index.json','config/bm25_b0.json',
        'config/bm25_dependency.json','config/bm25_userdict.txt','config/bm25_stopwords.txt',
        'data/eval/retrieval_dev.jsonl','data/eval/retrieval_test.jsonl','data/eval/dataset_manifest.json',
        'data/eval/human_review_receipt.json','data/manifests/dense_index_manifest.json','data/manifests/local_data_files.json')
ARTIFACTS=('run_started.json','predictions.jsonl','summary.json','error_analysis.json')


def fields(v,names):
    if not isinstance(v,dict) or set(v)!=set(names):raise ValueError('Unexpected/missing fields')


def integer(v,minimum=0):return type(v) is int and v>=minimum
def number(v):return type(v) in (int,float) and math.isfinite(v)
def equal(a,b):return canonical(a)==canonical(b)
def snapshots():return {p:record(ROOT/p) for p in SOURCES+INPUTS}


def mapping():
    value=json.loads((ROOT/MAP).read_text('utf-8'));validate_mapping(value);return value


def validate_mapping(value):
    original=value['originals'];children=value['children'];parents=value['parents']
    if len(original)!=99 or len(set(original)|set(children)|set(parents))!=len(original)+len(children)+len(parents):raise ValueError('ID coverage/collision')
    reference={r['chunk_id']:r for r in json.loads((ROOT/'reports/retrieval/dense_b0/dev/source_map.json').read_text('utf-8'))}
    if set(original)!=set(reference):raise ValueError('Not original99 source IDs')
    seen=[]
    for cid,row in original.items():
        if row['chunk_id']!=cid or row['source']['content_zh_sha256']!=reference[cid]['content_zh_sha256'] or row['source']['source_url']!=reference[cid]['source_url'] or row['law_number']!=reference[cid]['law_number']:raise ValueError('Original source differs')
        if (row['source']['source_lines']!=reference[cid]['source_lines'] or row['content_sha256']!=row['source']['content_zh_sha256']
            or not equal(row['spans'],[{'original_id':cid,'start':0,'end':row['characters']}] )):raise ValueError('Original source interval/hash differs')
        pieces=sorted((c['spans'][0]['start'],c['spans'][0]['end']) for c in children.values() if c['original_id']==cid)
        pos=0
        for a,b in pieces:
            if not integer(a) or not integer(b,1) or a!=pos or b<=a:raise ValueError('Child span gap/overlap/type')
            pos=b
        if pos!=row['characters']:raise ValueError('Children do not cover complete original')
    for cid,row in children.items():
        if row['chunk_id']!=cid or len(row['spans'])!=1:raise ValueError('Child identity/span differs')
        span=row['spans'][0];orig=original[row['original_id']]
        if span['original_id']!=row['original_id'] or row['parent_id']!=orig['parent_id'] or row['law_number']!=orig['law_number'] or row['section_path']!=orig['section_path']:raise ValueError('Child source/title/parent differs')
        if row['characters']!=span['end']-span['start'] or type(row['oversize_atomic']) is not bool or row['oversize_atomic']!=(row['body_tokens']>config()['child_max_body_tokens']):raise ValueError('Child length/atomic exception differs')
    for pid,row in parents.items():
        ids=row['original_ids']
        if row['chunk_id']!=pid or len(ids)!=len(set(ids)) or row['spans']!=[{'original_id':cid,'start':0,'end':original[cid]['characters']} for cid in ids]:raise ValueError('Parent members not complete')
        for cid in ids:
            o=original[cid]
            if o['parent_id']!=pid or o['section_path'][:2]!=row['section_path'] or o['law_number']!=row['law_number']:raise ValueError('Incoherent parent grouping')
        seen+=ids
    if sorted(seen)!=sorted(original):raise ValueError('Parents must partition originals')
    for group in (original,children,parents):
        for row in group.values():
            if not integer(row['law_number'],1) or row['law_number']>17:raise ValueError('Invalid rule number')
            validate_spans(row['spans'],value)
            if not all(integer(row[k],1) for k in ('characters','body_tokens','context_tokens')) or any(not isinstance(row[k],str) or len(row[k])!=64 or any(c not in '0123456789abcdef' for c in row[k]) for k in ('content_sha256','passage_sha256')):raise ValueError('Invalid length/hash')
    return True


def validate_spans(spans,m):
    if not isinstance(spans,list) or not spans:raise ValueError('Nonempty source intervals required')
    for s in spans:
        fields(s,('original_id','start','end'))
        if s['original_id'] not in m['originals'] or not integer(s['start']) or not integer(s['end'],1) or not s['start']<s['end']<=m['originals'][s['original_id']]['characters']:raise ValueError('Invalid source interval bounds/types')


def fuse(channels,known):
    fields(channels,('dense','bm25'));scores={};ranks={}
    for channel,rows in channels.items():
        if not isinstance(rows,list) or len(rows)>80 or (channel=='dense' and len(rows)!=min(80,len(known))):raise ValueError('Channel budget differs')
        ids=[];order=[]
        for rank,row in enumerate(rows,1):
            fields(row,('chunk_id','rank','score','distance') if channel=='dense' else ('chunk_id','rank','score'))
            cid=row['chunk_id']
            if cid not in known or cid in ids or type(row['rank']) is not int or row['rank']!=rank or not number(row['score']):raise ValueError('Invalid channel ID/rank/score')
            if channel=='dense':
                if not number(row['distance']) or not -1e-5<=row['distance']<=2.00001 or abs(row['score']-(1-row['distance']))>1e-6:raise ValueError('Invalid cosine distance')
                order.append((row['distance'],cid))
            else:
                if row['score']<=0:raise ValueError('BM25 zero/negative fill')
                order.append((-row['score'],cid))
            ids.append(cid);scores[cid]=scores.get(cid,Fraction())+Fraction(1,60+rank);ranks.setdefault(cid,{})[channel]=rank
        if order!=sorted(order):raise ValueError('Unsorted channel')
    return [{'chunk_id':cid,'rank':rank,'score':float(scores[cid]),'channel_ranks':ranks[cid]}
            for rank,cid in enumerate(sorted(scores,key=lambda cid:(-scores[cid],cid))[:10],1)]


def contexts(seed_ids,method,m):
    if method not in METHODS:raise ValueError('Unknown context method')
    if not isinstance(seed_ids,list) or len(seed_ids)>10 or len(seed_ids)!=len(set(seed_ids)):raise ValueError('At most ten unique seeds required')
    known=m['originals'] if method=='base' else m['children'];out=[];seen=set()
    for i,cid in enumerate(seed_ids,1):
        source=known[cid];target=cid if method!='parent_child' else source['parent_id']
        if target in seen:continue
        seen.add(target);out.append({'context_id':target,'seed_rank':i})
    return out


def context_entry(cid,m):
    for key in ('originals','children','parents'):
        if cid in m[key]:return m[key][cid]
    raise ValueError('Unknown context ID')


def budget_contexts(rows,m,budget=4096):
    if not integer(budget,1):raise ValueError('Invalid context budget')
    selected=[];skipped=[];used=0;seen=set();previous=0
    for row in rows:
        fields(row,('context_id','seed_rank'))
        if row['context_id'] in seen or not integer(row['seed_rank'],1) or row['seed_rank']<=previous:raise ValueError('Duplicate context or invalid seed order')
        seen.add(row['context_id']);previous=row['seed_rank']
        tokens=context_entry(row['context_id'],m)['context_tokens']
        if not integer(tokens,1):raise ValueError('Invalid context token count')
        if used+tokens>budget:skipped.append(row['context_id']);continue
        selected.append(dict(row));used+=tokens
    return {'contexts':selected,'skipped_ids':skipped,'context_tokens':used}


def coverage(rows,m):
    spans={};total=0
    for row in rows:
        entry=context_entry(row['context_id'],m);validate_spans(entry['spans'],m)
        for s in entry['spans']:
            spans.setdefault(s['original_id'],[]).append((s['start'],s['end']));total+=s['end']-s['start']
    covered={};unique=0
    for cid,values in spans.items():
        intervals=[]
        for a,b in sorted(values):
            if intervals and a<=intervals[-1][1]:intervals[-1]=(intervals[-1][0],max(b,intervals[-1][1]))
            else:intervals.append((a,b))
        size=sum(b-a for a,b in intervals);unique+=size
        if size==m['originals'][cid]['characters']:covered[cid]=True
    return set(covered),{'source_characters_total':total,'source_characters_unique':unique,
                         'redundancy_rate':1-unique/total if total else 0.}


def quality(questions,packets,method,m,budgeted=True):
    if len(questions)!=len(packets) or len({q['question_id'] for q in questions})!=len(questions):raise ValueError('Complete unique query/prediction pairs required')
    for q,p in zip(questions,packets):
        if type(q['answerable']) is not bool or q['answerable']!=bool(q['expected_chunk_ids']) or any(cid not in m['originals'] for cid in q['expected_chunk_ids']):raise ValueError('Invalid original support labels')
    per=[];context_stats=[]
    for q,p in zip(questions,packets):
        seed=p['rankings']['base' if method=='base' else 'child'];raw=contexts([r['chunk_id'] for r in seed],method,m)
        selected=budget_contexts(raw,m) if budgeted else {'contexts':raw,'skipped_ids':[],
                   'context_tokens':sum(context_entry(r['context_id'],m)['context_tokens'] for r in raw)}
        rows=selected['contexts'];all_covered,red=coverage(rows,m)
        naive=[{'context_id':m['children'][r['chunk_id']]['parent_id'],'seed_rank':i} for i,r in enumerate(seed,1)] if method=='parent_child' else raw
        _,naive_red=coverage(naive,m)
        context_stats.append({'question_id':q['question_id'],'contexts':rows,'skipped_ids':selected['skipped_ids'],
                              'context_tokens':selected['context_tokens'],**red,'naive_expansion_redundancy':naive_red['redundancy_rate']})
        if not q['answerable']:per.append({'question_id':q['question_id'],'included':False});continue
        gold=set(q['expected_chunk_ids']);prefix=[coverage(rows[:k],m)[0] for k in range(1,11)]
        first=next((k for k,v in enumerate(prefix,1) if gold&v),None)
        per.append({'question_id':q['question_id'],'included':True,'Recall@5':float(bool(gold&prefix[4])),
                    'Recall@10':float(bool(gold&prefix[9])),'MRR@10':1/first if first else 0.,
                    'all_gold_coverage@5':len(gold&prefix[4])/len(gold),
                    'full_gold_coverage@10':len(gold&prefix[9])/len(gold),
                    'missing_gold_at_5':sorted(gold-prefix[4]),'missing_gold_at_10':sorted(gold-prefix[9])})
    valid=[r for r in per if r['included']]
    if not valid:raise ValueError('No answerable denominator')
    return {'questions':len(questions),'answerable_denominator':len(valid),'unanswerable_excluded':len(per)-len(valid),
            'metrics':{k:sum(r[k] for r in valid)/len(valid) for k in ('Recall@5','Recall@10','MRR@10','all_gold_coverage@5','full_gold_coverage@10')},
            'context':{'mean_tokens':sum(r['context_tokens'] for r in context_stats)/len(context_stats),
                       'mean_redundancy_rate':sum(r['redundancy_rate'] for r in context_stats)/len(context_stats),
                       'mean_naive_expansion_redundancy':sum(r['naive_expansion_redundancy'] for r in context_stats)/len(context_stats),
                       'over_budget_skipped_contexts':sum(len(r['skipped_ids']) for r in context_stats)},
            'per_question':per,'context_per_question':context_stats,'nDCG@10':None}


def summarize(questions,rows,split,m):
    if split not in ('dev','test') or len(rows)!=len(questions):raise ValueError('Split/count differs')
    for q,row in zip(questions,rows):
        fields(row,('question_id','question_sha256','query','embedding_observation','query_vector_sha256','channels','rankings','timing'))
        if row['question_id']!=q['question_id'] or row['question_sha256']!=digest(q['question'].encode()):raise ValueError('Query identity differs')
        from dense_retrieval_eval import normalize_query
        if row['query']!=normalize_query(q['question']):raise ValueError('Query normalization differs')
        fields(row['channels'],('base','child'));fields(row['rankings'],('base','child'))
        for method in ('base','child'):
            expected=fuse(row['channels'][method],m['originals' if method=='base' else 'children'])
            if not equal(expected,row['rankings'][method]):raise ValueError('RRF ranking differs')
        fields(row['timing'],('embedding_seconds','base_retrieval_seconds','child_retrieval_seconds','total_seconds'))
        t=row['timing']
        if any(not number(v) or v<=0 for v in t.values()) or t['total_seconds']+1e-6<sum(v for k,v in t.items() if k!='total_seconds'):raise ValueError('Invalid shared-query timing')
        obs=row['embedding_observation'];fields(obs,('elapsed_seconds','inputs','prompt_eval_count','server_load_duration_ns','server_total_duration_ns'))
        if type(obs['inputs']) is not int or obs['inputs']!=1 or not number(obs['elapsed_seconds']) or obs['elapsed_seconds']<=0 or obs['elapsed_seconds']>t['embedding_seconds']+1e-6 or any(not integer(obs[k]) for k in ('prompt_eval_count','server_load_duration_ns','server_total_duration_ns')):raise ValueError('Invalid actual embedding receipt')
        if obs['server_load_duration_ns']>obs['server_total_duration_ns'] or obs['server_total_duration_ns']/1e9>obs['elapsed_seconds']+1e-5:raise ValueError('Invalid server timing')
        if not isinstance(row['query_vector_sha256'],str) or len(row['query_vector_sha256'])!=64 or any(c not in '0123456789abcdef' for c in row['query_vector_sha256']):raise ValueError('Invalid query vector fingerprint')
    methods={method:{'budgeted':quality(questions,rows,method,m),'unbudgeted':quality(questions,rows,method,m,False)} for method in METHODS}
    selected=min(METHODS,key=lambda method:tuple(-methods[method]['budgeted']['metrics'][k] for k in ('MRR@10','Recall@5','Recall@10'))+
                 (methods[method]['budgeted']['context']['mean_tokens'],METHODS.index(method))) if split=='dev' else None
    return {'version':'structure-comparison-summary-1.0','split':split,'methods':methods,'selected_on_this_split':selected,
            'scope':'Conservative complete-original-span support; parent expansion changes context coverage and volume. Shared query embeddings, not independent latency comparisons.',
            'actual_measured_embedding_queries':len(rows),'answer_llm_requests':0}


def errors(summary):
    return {'version':'structure-errors-1.0','split':summary['split'],
            'methods':{method:[r for r in value['budgeted']['per_question'] if r['included'] and (r['missing_gold_at_5'] or r['missing_gold_at_10'])] for method,value in summary['methods'].items()},
            'definition':'Every incomplete support case retained, even if any-hit Recall remains one; no new child relevance judgements inferred.'}


def validate_saved_query(value,raw=None):
    legacy='e542340ebab150bc4a37a478f9f5e7d05027f52e'
    if value.get('version') is None:
        original=subprocess.check_output(['git','show',legacy+':reports/retrieval/structure_pc_b0/acceptance/actual-query.json'],cwd=ROOT)
        if raw!=original:raise ValueError('Unversioned query must be the exact published legacy receipt')
        question=value['packet']['query']
    else:
        fields(value,('version','started_at','completed_at','source_commit','inputs','question','packet','environment','index_snapshots','actual_embedding_queries','answer_llm_requests','is_quality_evaluation'))
        if value['version']!='structure-query-1.1':raise ValueError('Unknown query receipt format')
        producer_before(value['source_commit'],value['started_at'])
        if not instant(value['started_at'])<instant(value['completed_at'])<=datetime.now(timezone.utc):raise ValueError('Invalid query receipt chronology')
        fields(value['inputs'],SOURCES+INPUTS)
        for p,r in value['inputs'].items():
            blob=subprocess.check_output(['git','show',value['source_commit']+':'+p],cwd=ROOT)
            if r!={'path':p,'size_bytes':len(blob),'sha256':digest(blob)} or (p in INPUTS and r!=record(ROOT/p)):raise ValueError('Query producer/input differs')
        validate_environment(value['environment'])
        index=json.loads((ROOT/INDEX).read_text('utf-8'))
        before=value['index_snapshots']['before'];after=value['index_snapshots']['after']
        expected={**index['artifact_files'],'data/indexes/structure_pc_b0/index_manifest.json':{'path':'data/indexes/structure_pc_b0/index_manifest.json',**{k:v for k,v in record(ROOT/INDEX).items() if k!='path'}}}
        if not equal(before,after) or not equal(before,expected):raise ValueError('Actual query index snapshot differs')
        if (instant(value['completed_at'])-instant(value['started_at'])).total_seconds()+1e-5<value['packet']['timing']['total_seconds']:raise ValueError('Query receipt duration omits execution')
        question=value['question']
    if type(value['actual_embedding_queries']) is not int or value['actual_embedding_queries']!=1 or type(value['answer_llm_requests']) is not int or value['answer_llm_requests']!=0 or value['is_quality_evaluation'] is not False:raise ValueError('Wrong query request scope/counters')
    if value['packet']['question_id']!='ad-hoc':raise ValueError('Not a non-evaluation query packet')
    m=mapping();q={'question_id':'ad-hoc','question':question,'answerable':True,'expected_chunk_ids':[next(iter(m['originals']))]}
    summarize([q],[value['packet']],'dev',m)
    return True


def validate_environment(environment):
    fields(environment,('python','system','logical_cpus','packages','embedding_runtime'))
    runtime=environment['embedding_runtime'];fields(runtime,('name','digest','size','size_vram','context_length','runner'))
    dense_cfg=json.loads((ROOT/'config/dense_index.json').read_text('utf-8'))
    if (environment['python']!='3.10.22' or environment['packages']!={'numpy':'1.26.4','tokenizers':'0.22.1'}
        or not integer(environment['logical_cpus'],1) or runtime['name']!=dense_cfg['model']['name']
        or runtime['digest']!=dense_cfg['model']['digest'] or type(runtime['size_vram']) is not int or runtime['size_vram']!=0
        or type(runtime['context_length']) is not int or runtime['context_length']!=8192 or not integer(runtime['size'],1) or runtime['runner']!='llamacpp'):raise ValueError('Pinned runtime/environment differs')
    return True


def validate_grant(g,directory,current=False):
    fields(g,('version','purpose','prepared_at','source_commit','inputs','development_manifest','development_summary','verification','selected_method','allowed_run_directory','test_sha256'))
    if g['version']!='structure-test-grant-1.0' or g['purpose']!='final_report' or g['allowed_run_directory']!=directory.relative_to(ROOT).as_posix() or directory!=DIRECTORY/'test':raise ValueError('Wrong test grant scope')
    producer_before(g['source_commit'],g['prepared_at'])
    if instant(g['prepared_at'])>datetime.now(timezone.utc) or g['test_sha256']!=digest((EVAL/'retrieval_test.jsonl').read_bytes()):raise ValueError('Grant time/test differs')
    dev=ROOT/g['development_manifest']['path']
    if dev.name!='run_manifest.json' or dev.parent.parent!=DIRECTORY or not dev.parent.name.startswith('dev') or g['development_manifest']!=record(dev) or g['development_summary']!=record(dev.parent/'summary.json'):raise ValueError('Grant dev evidence differs')
    s=replay(dev.parent)
    if s['split']!='dev' or s['selected_on_this_split']!=g['selected_method']:raise ValueError('Grant selection differs')
    proof=ROOT/g['verification']['path'];v=json.loads(proof.read_text('utf-8'))
    if (g['verification']!=record(proof) or v['status']!='PASS' or not integer(v['passed'],30) or not integer(v['total'],30)
        or v['passed']!=v['total'] or v['total']!=len(v['checks']) or v['errors']!=[] or not all(x is True for x in v['checks'].values())):raise ValueError('Verification not complete')
    if not instant(json.loads(dev.read_text('utf-8'))['completed_at'])<=instant(v['captured_at'])<=instant(g['prepared_at']):raise ValueError('Development must precede verification/grant')
    if v['source_sha256']!={p:g['inputs'][p]['sha256'] for p in NATIVE}:raise ValueError('Verification source identity differs')
    for r in (g['development_manifest'],g['development_summary'],g['verification']):
        if digest(subprocess.check_output(['git','show',g['source_commit']+':'+r['path']],cwd=ROOT))!=r['sha256']:raise ValueError('Development/proof not frozen in authorized commit')
    if current and (g['inputs']!=snapshots() or committed(SOURCES+INPUTS,g['source_commit'])!=g['source_commit']):raise ValueError('Frozen grant differs from current inputs')
    return True


def replay(directory):
    directory=Path(directory).resolve();manifest=json.loads((directory/'run_manifest.json').read_text('utf-8'));split=manifest['split']
    start_fields=('version','split','run_id','source_commit','inputs','config','started_at','authorization','purpose')
    fields(manifest,start_fields+('status','completed_at','wall_seconds','environment','warmups','index_snapshots','actual_embedding_queries','answer_llm_requests','artifacts'))
    if not isinstance(manifest['run_id'],str) or not re.fullmatch('[0-9a-f]{32}',manifest['run_id']) or manifest['purpose']!=('development' if split=='dev' else 'final_report') or (split=='dev' and manifest['authorization'] is not None):raise ValueError('Invalid run identity/purpose')
    if directory.parent!=DIRECTORY or (directory.name!='test' if split=='test' else not directory.name.startswith('dev')) or split not in ('dev','test') or manifest['version']!='structure-run-1.0' or manifest['status']!='COMPLETE':raise ValueError('Wrong run directory/state')
    producer_before(manifest['source_commit'],manifest['started_at'])
    if not instant(manifest['started_at'])<instant(manifest['completed_at'])<=datetime.now(timezone.utc):raise ValueError('Invalid run chronology')
    if not number(manifest['wall_seconds']) or abs(manifest['wall_seconds']-(instant(manifest['completed_at'])-instant(manifest['started_at'])).total_seconds())>.5:raise ValueError('Clock disagreement')
    fields(manifest['inputs'],SOURCES+INPUTS)
    if any(manifest['inputs'][p]!=record(ROOT/p) for p in INPUTS) or not equal(manifest['config'],config()):raise ValueError('Frozen data/config changed')
    for p in SOURCES+INPUTS:
        raw=subprocess.check_output(['git','show',manifest['source_commit']+':'+p],cwd=ROOT)
        if manifest['inputs'][p]!={'path':p,'size_bytes':len(raw),'sha256':digest(raw)}:raise ValueError('Producer source/input mismatch')
    fields(manifest['artifacts'],ARTIFACTS)
    for name in ARTIFACTS:
        if manifest['artifacts'][name]!=record(directory/name):raise ValueError('Run artifact changed')
    start=json.loads((directory/'run_started.json').read_text('utf-8'))
    fields(start,start_fields)
    if not equal(start,{k:manifest[k] for k in start}):raise ValueError('Run start differs')
    if not integer(manifest['actual_embedding_queries']) or manifest['actual_embedding_queries']!=len(load_jsonl(directory/'predictions.jsonl'))+3 or type(manifest['answer_llm_requests']) is not int or manifest['answer_llm_requests']!=0 or len(manifest['warmups'])!=3:raise ValueError('Actual query counter differs')
    validate_environment(manifest['environment'])
    index=json.loads((ROOT/INDEX).read_text('utf-8'));before=manifest['index_snapshots']['before'];after=manifest['index_snapshots']['after']
    if not equal(before,after) or any(before.get(p)!=r for p,r in index['artifact_files'].items()) or len(before)!=len(index['artifact_files'])+1:raise ValueError('Independent index changed/incomplete snapshot')
    if before.get('data/indexes/structure_pc_b0/index_manifest.json')!={'path':'data/indexes/structure_pc_b0/index_manifest.json',**{k:v for k,v in record(ROOT/INDEX).items() if k!='path'}}:raise ValueError('Independent index manifest snapshot differs')
    m=mapping();warm=[{'question_id':'warmup','question':config()['warmup_question'],'answerable':True,'expected_chunk_ids':[next(iter(m['originals']))]}]
    for packet in manifest['warmups']:summarize(warm,[packet],'dev',m)
    questions=load_jsonl(EVAL/('retrieval_'+split+'.jsonl'));rows=load_jsonl(directory/'predictions.jsonl');result=summarize(questions,rows,split,m)
    if manifest['wall_seconds']+1e-5<sum(r['timing']['total_seconds'] for r in rows+manifest['warmups']):raise ValueError('Serial wall duration omits query execution')
    if not equal(result,json.loads((directory/'summary.json').read_text('utf-8'))) or not equal(errors(result),json.loads((directory/'error_analysis.json').read_text('utf-8'))):raise ValueError('Saved summary/errors differ')
    if split=='test':
        g=json.loads((ROOT/manifest['authorization']['path']).read_text('utf-8'))
        if record(ROOT/manifest['authorization']['path'])!=manifest['authorization'] or g['source_commit']!=manifest['source_commit'] or g['inputs']!=manifest['inputs']:raise ValueError('Run authorization identity differs')
        validate_grant(g,directory)
    return result
