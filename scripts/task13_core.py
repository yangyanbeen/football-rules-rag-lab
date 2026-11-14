"""Standard-library Task13 configuration, local data import and result contracts."""
from __future__ import annotations
import copy,html,json,math,re,subprocess,uuid
from pathlib import Path
from answer_eval_core import ROOT,BOUNDARY,REFUSAL,canonical,digest,read,record,now,write_new,config as answer_config

CONFIG='config/task13_app.json'


def app_config(path=None):
    c=read(ROOT/(path or CONFIG))
    keys={'version','answer_policy','retrieval_policy','dense_policy','catalog_policy','environment','dense_index','bm25_index','corpus','private_root','ui','worker_timeout_seconds','retrieval_method','scope'}
    if not isinstance(c,dict) or set(c)!=keys or c['version']!='task13-integrated-1.0' or c['retrieval_method']!='top40':raise ValueError('Unsupported integrated profile')
    fixed={'answer_policy':'config/answer_evaluation.json','retrieval_policy':'config/reranker_experiment.json','dense_policy':'config/dense_index.json','catalog_policy':'config/citation_catalog_notes.json','corpus':'data/processed/rag_chunks_zh.jsonl','private_root':'.runtime/task13'}
    if any(c[k]!=v for k,v in fixed.items()):raise ValueError('Changed pinned policy or corpus')
    if c['ui']!={'host':'127.0.0.1','port':7866,'share':False,'app_data':'.runtime/task13/kotaemon'}:raise ValueError('Unexpected UI or public sharing')
    if type(c['worker_timeout_seconds']) is not int or not 1<=c['worker_timeout_seconds']<=420:raise ValueError('Invalid worker timeout')
    for key,parent in (('environment','.runtime/task13'),('dense_index','data/indexes/task13'),('bm25_index','data/indexes/bm25')):
        p=(ROOT/c[key]).resolve();base=(ROOT/parent).resolve()
        if not p.is_relative_to(base) or p==base or '..' in Path(c[key]).parts:raise ValueError('Unsafe task13 path: '+key)
    if read(ROOT/c['retrieval_policy'])['rrf_k']!=60 or read(ROOT/'reports/reranker_results.json')['selected_method_on_dev']!='top40':raise ValueError('Not the dev-selected retrieval policy')
    answer_config()
    return c


def source_identity():
    paths=('config/task13_app.json','config/answer_evaluation.json','config/answer_evaluation_system.txt',
        'config/reranker_experiment.json','config/dense_index.json','config/citation_catalog_notes.json')
    return {p:record(ROOT/p) for p in paths}


def normalize_question(q):
    if not isinstance(q,str) or not q.strip() or len(q.encode('utf-8'))>1200:raise ValueError('Query must be nonblank text within1200 UTF8 bytes')
    return q.strip()


def local_corpus():
    from answer_review_v2 import source_corpus
    return source_corpus()


def validate_result(value,question):
    from answer_eval_engine import pack
    from answer_eval_core import parse_selection
    from citation_catalog_guard import safe_render
    cfg=app_config();q=normalize_question(question);corpus=local_corpus()
    if value['profile']!=cfg['version'] or value['question']!=q or value['configuration']!=source_identity():raise ValueError('Integrated result identity differs')
    if not re.fullmatch('[a-f0-9]{32}',value['trace_id']) or value['status'] not in ('answered','refused'):raise ValueError('Invalid request identity or status')
    expected_indexes={n:record(ROOT/cfg[n]/'index_manifest.json') for n in ('dense_index','bm25_index')}
    if value['indexes']!=expected_indexes:raise ValueError('Result did not use current rebuilt indexes')
    for k,limit in (('retrieved_ids',10),('offered_ids',5),('selected_ids',3)):
        ids=value[k]
        if not isinstance(ids,list) or len(ids)>limit or any(not isinstance(cid,str) or cid not in corpus for cid in ids) or len(set(ids))!=len(ids):raise ValueError('Invalid '+k)
    if not set(value['selected_ids'])<=set(value['offered_ids'])<=set(value['retrieved_ids']):raise ValueError('Unoffered/unretrieved source')
    if (value['status']=='answered')!=bool(value['selected_ids']):raise ValueError('Answer selection differs')
    if value['status']=='answered' and (value['error'] is not None or value['refusal_reason'] is not None):raise ValueError('Failure asserted answer')
    if safe_render(value['selected_ids'],corpus)!=(value['answer'],value['citations']):raise ValueError('Answer quote/citation/render differs')
    if value['status']=='refused' and (not isinstance(value['refusal_reason'],str) or not value['refusal_reason']):raise ValueError('Missing refusal reason')
    if not value['answer'].endswith(BOUNDARY):raise ValueError('Lost source/version boundary')
    if value['retrieval'] is not None:
        from reranker_eval import validate_packet,config as reranker_config
        from rrf import SOURCE_FIELDS
        known={cid:{k:r[k] for k in SOURCE_FIELDS} for cid,r in corpus.items()}
        validate_packet(value['retrieval'],q,'top40',known,reranker_config())
        if value['retrieved_ids']!=[r['chunk_id'] for r in value['retrieval']['results']]:raise ValueError('Retrieved order differs')
        context,messages,size=pack(q,[corpus[c] for c in value['retrieved_ids']],answer_config(),(ROOT/'config/answer_evaluation_system.txt').read_text('utf-8'))
        if (value['context'],value['messages'],value['prompt_utf8_bytes'])!=(context,messages,size):raise ValueError('Actual offered context differs')
    elif not value['error'] and value['refusal_reason']!='version_unverified':raise ValueError('Unexpected missing retrieval')
    attempts=value['attempts']
    if not isinstance(attempts,list) or len(attempts)>2:raise ValueError('Attempt budget differs')
    if value['status']=='answered':
        from answer_audit_v2 import validate_attempts
        from answer_json_chat import selection_schema
        selected=validate_attempts(attempts,value['messages'],selection_schema(value['offered_ids'],3),lambda s:parse_selection(s,value['offered_ids'],answer_config()))
        if selected is None or selected['chunk_ids']!=value['selected_ids'] or selected['answerable'] is not True:raise ValueError('Actual generation did not select displayed evidence')
    if set(value['timing'])!={'retrieval_seconds','generation_seconds','total_seconds'} or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in value['timing'].values()):raise ValueError('Invalid timing')
    if value['timing']['total_seconds']+0.01<sum(value['timing'][k] for k in ('retrieval_seconds','generation_seconds')):raise ValueError('Incomplete stage clock')
    return True


def public_result(value,path):
    validate_result(value,value['question'])
    return {'trace_id':value['trace_id'],'question':value['question'],'profile':value['profile'],'status':value['status'],
        'selected_ids':value['selected_ids'],'offered_ids':value['offered_ids'],'retrieved_ids':value['retrieved_ids'],
        'refusal_reason':value['refusal_reason'],'error':value['error'],'answer_sha256':digest(value['answer'].encode()),
        'citations':value['citations'],'configuration':value['configuration'],'indexes':value['indexes'],'timing':value['timing'],
        'prompt_utf8_bytes':value['prompt_utf8_bytes'],'attempts':[{k:a.get(k) for k in ('attempt','error','prompt_eval_count','eval_count','done_reason')} for a in value['attempts']],
        'private_trace':record(path),'new_formal_test_runs':0}


def render_panel(value):
    blocks=['<h3>来源与完整证据</h3>']
    by_id={r['chunk_id']:r for r in value.get('context',[])}
    for c in value.get('citations',[]):
        cid=c['chunk_id'];r=by_id[cid]
        blocks.append('<details><summary>'+html.escape(cid+' · 本地编目第'+str(c['catalog_number'])+'组')+'</summary><pre style="white-space:pre-wrap">'+html.escape(r['content_zh'])+'</pre><p><a target="_blank" rel="noopener noreferrer" href="'+html.escape(c['source_url'],quote=True)+'">原始来源</a> · '+html.escape(str(c['source_lines']))+'</p><p>'+html.escape(c['catalog_notice'])+'</p><p>'+html.escape(str(c['source_attribution'])+' · '+str(c['license']))+'</p></details>')
    blocks.append('<p>'+html.escape(BOUNDARY)+'</p>')
    return ''.join(blocks)
