"""Read-only actual Dense + fixed accurate BM25 query; no answer generation."""
import json,time,sys
from pathlib import Path
from eval_dataset import ROOT,canonical,digest
from bm25_index import Bm25Index,record
from dense_retrieval_eval import normalize_query
from rrf import fuse,SOURCE_FIELDS

SMOKE_QUESTIONS=('请检索第十一条下关于越位的资料段落。','请查找同时包含7.32米与2.44米的球门尺寸资料。',
                 '请检索和“间接任意球”有关的规则段落。','zzzzunknownlexicaltoken987654321')
ORIGINAL_SMOKE_SOURCE='ae3c3b5ae2b06c1896e30ccda21fb079811ae8d6'


def validate_live_smoke(value):
    """Recompute saved live evidence with stdlib only, including historical v1."""
    from hybrid_retrieval_eval import SOURCES
    from dense_retrieval_contracts import fields,number,instant,ancestor,git_blob,committed_at
    from datetime import datetime,timezone
    from rrf import candidates,CHANNELS,METHODS
    from bm25_index import normalize,TIMINGS
    base={'actual_embedding_queries','answer_llm_requests','captured_at','checks','embedding_runtime','is_accuracy_evaluation',
          'new_locked_test_queries','passed','queries','scope','source_sha256','started_at','status','total','version'}
    version=value.get('version')
    if version not in ('hybrid-live-smoke-1.0','hybrid-live-smoke-1.1'):raise ValueError('Unknown live receipt version')
    fields(value,base|({'source_commit','index_snapshots'} if version.endswith('1.1') else set()),'live receipt')
    start,end=instant(value['started_at']),instant(value['captured_at'])
    producer=value['source_commit'] if version.endswith('1.1') else ORIGINAL_SMOKE_SOURCE
    ancestor(producer)
    if not committed_at(producer)<=start<=end<=datetime.now(timezone.utc):raise ValueError('Invalid live source/capture chronology')
    names=SOURCES+('scripts/verify_hybrid_live.py',)
    if set(value['source_sha256'])!=set(names):raise ValueError('Incomplete live source coverage')
    if any(value['source_sha256'][name]!=digest(git_blob(producer,name)) for name in names):raise ValueError('Live source differs from recorded producer')
    for name,count in [('actual_embedding_queries',4),('answer_llm_requests',0),('new_locked_test_queries',0)]:
        if type(value[name]) is not int or value[name]!=count:raise ValueError('Live request count differs')
    if value['is_accuracy_evaluation'] is not False:raise ValueError('Live smoke is not accuracy evaluation')
    if value['scope']!='Four ad-hoc actual dual-channel queries; not new accuracy or latency benchmark samples':raise ValueError('Live scope differs')
    runtime=value['embedding_runtime'];fields(runtime,('name','digest','size','size_vram','context_length','runner'),'live model runtime')
    cfg=json.loads((ROOT/'config/dense_index.json').read_text('utf-8'))
    if (runtime['name']!=cfg['model']['name'] or runtime['digest']!=cfg['model']['digest'] or runtime['runner']!='llamacpp'
        or type(runtime['size']) is not int or runtime['size']<1 or type(runtime['size_vram']) is not int or runtime['size_vram']!=0
        or type(runtime['context_length']) is not int or runtime['context_length']!=cfg['embedding']['num_ctx']):raise ValueError('Live model is not the pinned CPU model')
    rows=value['queries']
    if not isinstance(rows,list) or len(rows)!=4:raise ValueError('Four live queries required')
    known={r['chunk_id']:r for r in json.loads((ROOT/'reports/retrieval/dense_b0/dev/source_map.json').read_text('utf-8'))}
    checks={};minimum=0
    for i,(question,row) in enumerate(zip(SMOKE_QUESTIONS,rows),1):
        fields(row,('channels','embedding_observation','k','llm_generation_requests','quality_evaluation','question','results','timing'),'live query')
        if (row['question']!=question or type(row['k']) is not int or row['k']!=60
            or row['quality_evaluation'] is not False or type(row['llm_generation_requests']) is not int or row['llm_generation_requests']!=0):raise ValueError('Live query identity/scope differs')
        fields(row['channels'],CHANNELS,'live channels');fields(row['results'],METHODS,'live rankings')
        for channel in CHANNELS:
            packet=row['channels'][channel]
            fields(packet,('query','results','timing')+(('tokens',) if channel=='bm25' else ()),'live channel')
            if packet['query']!=(normalize_query(question) if channel=='dense' else normalize(question)):raise ValueError('Live normalized question differs')
            if not isinstance(packet['results'],list) or len(packet['results'])>10 or (channel=='dense' and len(packet['results'])!=10):raise ValueError('Live candidate budget differs')
            if channel=='bm25' and (not isinstance(packet['tokens'],list) or any(not isinstance(t,str) or not t or len(t)>1200 for t in packet['tokens'])):raise ValueError('Invalid live query tokens')
            for result in packet['results']:
                if result['chunk_id'] not in known or canonical({p:result[p] for p in SOURCE_FIELDS})!=canonical(known[result['chunk_id']]):raise ValueError('Live source not bound to original corpus')
            timing=packet['timing'];fields(timing,('query_embedding_seconds','vector_search_seconds') if channel=='dense' else TIMINGS,'live channel timing')
            if any(not number(v,True) for v in timing.values()):raise ValueError('Nonpositive/nonfinite live channel stage')
            if channel=='bm25' and abs(timing['total_seconds']-sum(timing[k] for k in TIMINGS[:-1]))>1e-8:raise ValueError('BM25 stages do not sum')
        packet={c:row['channels'][c]['results'] for c in CHANNELS};candidates(packet)
        expected=fuse(packet,60,10)
        if canonical(row['results'])!=canonical(expected):raise ValueError('Live fusion scores/ranks/sources differ from raw channels')
        timing=row['timing'];fields(timing,('normalization_seconds','dense_seconds','bm25_seconds','fusion_and_adapter_seconds','total_seconds'),'live total timing')
        if any(not number(v,True) for v in timing.values()) or abs(timing['total_seconds']-sum(v for k,v in timing.items() if k!='total_seconds'))>1e-8:raise ValueError('Invalid live total timing containment')
        if (timing['dense_seconds']+1e-7<sum(row['channels']['dense']['timing'].values())
            or timing['bm25_seconds']+1e-7<row['channels']['bm25']['timing']['total_seconds']):raise ValueError('Live channel omitted work')
        obs=row['embedding_observation'];fields(obs,('elapsed_seconds','inputs','prompt_eval_count','server_load_duration_ns','server_total_duration_ns'),'embedding observation')
        if (type(obs['inputs']) is not int or obs['inputs']!=1 or any(type(obs[k]) is not int or obs[k]<0 for k in ('prompt_eval_count','server_load_duration_ns','server_total_duration_ns'))
            or not number(obs['elapsed_seconds'],True) or obs['elapsed_seconds']>row['channels']['dense']['timing']['query_embedding_seconds']+1e-7
            or obs['server_load_duration_ns']>obs['server_total_duration_ns'] or obs['server_total_duration_ns']/1e9>obs['elapsed_seconds']+1e-6):raise ValueError('Invalid live embedding observation')
        minimum+=timing['total_seconds']
        checks.update({f'query_{i}_fusion_recomputes':True,f'query_{i}_positive_total_and_stages':True,f'query_{i}_top10_budget_and_unique':True})
    if (end-start).total_seconds()+.1<minimum:raise ValueError('Live capture duration omits work')
    if version.endswith('1.1'):
        snapshots=value['index_snapshots'];fields(snapshots,('before','after'),'index snapshots')
        if canonical(snapshots['before'])!=canonical(snapshots['after']) or len(snapshots['before'])!=13:raise ValueError('Live index files changed or incomplete')
        dense=json.loads((ROOT/'data/manifests/dense_index_manifest.json').read_text('utf-8'))
        bm25=json.loads((ROOT/'data/manifests/bm25_indexes.json').read_text('utf-8'))['indexes']['title_body']
        expected={**{'data/indexes/dense/'+p:v for p,v in dense['artifact_files'].items()},
                  **{'data/indexes/bm25/title_body/'+p:v for p,v in bm25['artifacts'].items()},
                  'data/indexes/dense/index_manifest.json':{'sha256':dense['local_manifest_sha256']},
                  'data/indexes/bm25/title_body/index_manifest.json':{'sha256':digest((json.dumps(bm25,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode())}}
        if set(snapshots['before'])!=set(expected):raise ValueError('Index snapshot path coverage differs from original indexes')
        for path,entry in snapshots['before'].items():
            fields(entry,('path','size_bytes','sha256'),'index snapshot entry')
            if (entry['path']!=path or not path.startswith(('data/indexes/dense/','data/indexes/bm25/title_body/')) or '..' in Path(path).parts
                or type(entry['size_bytes']) is not int or entry['size_bytes']<1 or not isinstance(entry['sha256'],str) or len(entry['sha256'])!=64
                or any(c not in '0123456789abcdef' for c in entry['sha256'])):raise ValueError('Invalid index snapshot entry')
            if any(entry[k]!=v for k,v in expected[path].items()):raise ValueError('Index snapshot differs from original published artifact identity')
    checks.update(all_four_queries_completed=True,oov_bm25_empty_no_zero_fill=not rows[-1]['channels']['bm25']['results'],
                  oov_rrf_falls_to_dense_ranks=[r['chunk_id'] for r in rows[-1]['results']['rrf']]==[r['chunk_id'] for r in rows[-1]['channels']['dense']['results']],
                  pinned_embedding_cpu=True,original_index_files_unchanged=True)
    if (value['status']!='PASS' or type(value['passed']) is not int or type(value['total']) is not int
        or value['passed']!=value['total'] or value['total']!=17 or not all(checks.values())
        or canonical(checks)!=canonical(value['checks'])):raise ValueError('Live receipt checks do not recompute')
    return checks


def index_files():
    return {p.relative_to(ROOT).as_posix():record(p) for folder in ('dense','bm25/title_body')
            for p in (ROOT/'data/indexes'/folder).rglob('*') if p.is_file()}


class HybridRetriever:
    def __init__(self,k=60):
        from dense_index import DenseIndex,PinnedEmbedder
        from rrf import parameters
        parameters(k,10);self.k=k;self.dense=None;self.before=index_files()
        try:
            self.bm25=Bm25Index(ROOT/'data/indexes/bm25/title_body')
            cfg=json.loads((ROOT/'config/dense_index.json').read_text('utf-8'))
            self.embedder=PinnedEmbedder(cfg)
            self.dense=DenseIndex(embedder=self.embedder)
        except BaseException:
            if self.dense is not None:self.dense.close()
            raise

    def query(self,question):
        start=time.perf_counter_ns();query=normalize_query(question);a=time.perf_counter_ns()
        dense=self.dense.query(query,10);b=time.perf_counter_ns()
        bm25=self.bm25.query(question,10);c=time.perf_counter_ns()
        dense_rows=[{**{p:r['metadata'][p] for p in SOURCE_FIELDS},**{p:r[p] for p in ('rank','score','distance')}} for r in dense['results']]
        channels={'dense':{'query':query,'results':dense_rows,'timing':dense['timing']},
                  'bm25':{'query':bm25['query'],'tokens':bm25['tokens'],'results':bm25['results'],'timing':bm25['timing']}}
        result=fuse({name:row['results'] for name,row in channels.items()},self.k,10);end=time.perf_counter_ns()
        return {'question':question,'k':self.k,'channels':channels,'results':result,
                'timing':dict(zip(('normalization_seconds','dense_seconds','bm25_seconds','fusion_and_adapter_seconds','total_seconds'),
                                 ((a-start)/1e9,(b-a)/1e9,(c-b)/1e9,(end-c)/1e9,(end-start)/1e9))),
                'embedding_observation':self.embedder.observations[-1],
                'quality_evaluation':False,'llm_generation_requests':0}

    def close(self):
        primary=None
        try:
            if self.dense is not None:self.dense.close()
        except BaseException as exc:primary=exc
        try:
            if index_files()!=self.before:raise ValueError('Original indexes changed during actual hybrid query')
        except BaseException:
            if primary is None:raise
            print('Index preservation check also failed during cleanup',file=sys.stderr)
        if primary is not None:raise primary

    def __enter__(self):return self
    def __exit__(self,*_):
        primary=sys.exc_info()[0] is not None
        try:self.close()
        except Exception as exc:
            if primary:print('Hybrid cleanup also failed: '+type(exc).__name__,file=sys.stderr)
            else:raise
