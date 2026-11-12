"""Pinned Chinese BM25 index; no model calls or evaluation-label inputs."""
from __future__ import annotations
import collections, hashlib, importlib, json, logging, math, re, subprocess, sys, time, unicodedata
from pathlib import Path
from eval_dataset import ROOT, canonical, digest, load_jsonl
from install_bm25_runtime import HOME, verify as verify_dependency

CONFIG=ROOT/'config/bm25_b0.json'
RESOURCES=('config/bm25_b0.json','config/bm25_dependency.json','config/bm25_userdict.txt','config/bm25_stopwords.txt')
SOURCES=('scripts/bm25_index.py','scripts/build_bm25_index.py','scripts/install_bm25_runtime.py','scripts/eval_dataset.py')
SOURCE_FIELDS=('chunk_id','source_url','source_lines','law_number','record_sha256','content_zh_sha256')
TEMPLATES=('body','title_body','path_body')
TIMINGS=('normalization_seconds','tokenization_seconds','scoring_seconds','total_seconds')


def record(path):
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT):raise ValueError('Path escapes checkout')
    raw=path.read_bytes();return {'path':path.relative_to(ROOT).as_posix(),'size_bytes':len(raw),'sha256':digest(raw)}


def write_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8',newline='\n') as f:
        f.write(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n')


def source_commit():return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


def committed(names,commit=None):
    commit=commit or source_commit()
    if not re.fullmatch('[a-f0-9]{40}',commit) or subprocess.run(['git','merge-base','--is-ancestor',commit,'HEAD'],cwd=ROOT,capture_output=True).returncode:
        raise ValueError('Source commit is not an ancestor')
    for name in names:
        if subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)!=(ROOT/name).read_bytes():
            raise ValueError('Commit source/resource differs: '+name)
    return commit


def config():
    cfg=json.loads(CONFIG.read_text('utf-8'))
    expected={'version':'bm25-b0-1.0.0','corpus':'data/processed/rag_chunks_zh.jsonl',
      'corpus_sha256':'05dcd08126b5c71031ebe025f1a4ed1b73e00f71007b60ac0a3e0814f386a0b3',
      'templates':list(TEMPLATES),'tokenizer':{'name':'jieba','version':'0.42.1','mode':'accurate','HMM':False},
      'userdict':'config/bm25_userdict.txt','stopwords':'config/bm25_stopwords.txt','k1':1.5,'b':0.75,
      'idf':'log(1+(N-df+0.5)/(df+0.5))','query_tf':'unique terms once','top_k':10,
      'positive_scores_only':True,'tie_break':'chunk_id ascending',
      'selection':['MRR@10','Recall@5','Recall@10','template order'],'measured_repetitions':3,
      'warmup_repetitions':3,'warmup_query':'足球比赛场地的边线如何判断球出界？','concurrency':1,
      'cache':False,'quality_repetition':1,'percentile_method':'linear interpolation at q*(n-1)'}
    if canonical(cfg)!=canonical(expected):raise ValueError('BM25 B0 policy differs; create a new experiment')
    return cfg


def normalize(text):
    if not isinstance(text,str):raise ValueError('Query must be text')
    text=' '.join(unicodedata.normalize('NFKC',text).casefold().split())
    if not text or len(text.encode('utf-8'))>1200:raise ValueError('Query is empty or exceeds 1200 UTF8 bytes')
    return text


def chinese_number(value):
    if value.isdigit():return int(value)
    digits={c:i for i,c in enumerate('零一二三四五六七八九')}
    if value=='十':return 10
    if value.startswith('十') and len(value)==2:return 10+digits.get(value[1],100)
    if value.endswith('十') and len(value)==2:return digits.get(value[0],100)*10
    if len(value)==3 and value[1]=='十':return digits.get(value[0],100)*10+digits.get(value[2],100)
    return digits.get(value,1000)


class Tokenizer:
    def __init__(self):
        self.dependency=verify_dependency()
        package=HOME/'site-packages'
        if 'jieba' in sys.modules and not Path(sys.modules['jieba'].__file__).resolve().is_relative_to(package):
            raise ValueError('Foreign jieba already imported')
        sys.path.insert(0,str(package)) if str(package) not in sys.path else None
        jieba=importlib.import_module('jieba')
        if jieba.__version__!='0.42.1' or not Path(jieba.__file__).resolve().is_relative_to(package):raise ValueError('Unpinned tokenizer')
        jieba.setLogLevel(logging.ERROR)
        self.engine=jieba.Tokenizer(str(package/'jieba/dict.txt'))
        cache=HOME/'tokenizer-cache';cache.mkdir(exist_ok=True)
        self.engine.tmp_dir=str(cache);self.engine.cache_file='b0-'+self.dependency['default_dictionary_sha256']+'.cache'
        self.engine.initialize();self.engine.load_userdict(str(ROOT/'config/bm25_userdict.txt'))
        self.stop=set((ROOT/'config/bm25_stopwords.txt').read_text('utf-8').splitlines())
        if any(re.search(r'\d',v) or v in ('不','不得','必须','如果','除外','米') for v in self.stop):raise ValueError('Stopwords remove protected facts')

    def tokens(self,text):
        text=' '.join(unicodedata.normalize('NFKC',text).casefold().split())
        output=[]
        for value in re.findall(r'第\s*(?:\d+|[零一二三四五六七八九十]+)\s*条|\d+(?:\.\d+)?|[a-z]+|[\u3400-\u9fff]+',text):
            if value.startswith('第') and value.endswith('条'):
                number=chinese_number(re.sub(r'\s','',value)[1:-1])
                output.extend(['rule:'+str(number),str(number)])
            elif re.fullmatch(r'\d+(?:\.\d+)?|[a-z]+',value):output.append(value)
            else:output.extend(t for t in self.engine.cut(value,cut_all=False,HMM=False) if t.strip() and t not in self.stop)
        return output


def corpus(cfg=None):
    cfg=cfg or config();path=ROOT/cfg['corpus']
    if digest(path.read_bytes())!=cfg['corpus_sha256']:raise ValueError('Original corpus changed')
    rows=load_jsonl(path)
    if len(rows)!=99 or len({r['chunk_id'] for r in rows})!=99:raise ValueError('Expected 99 original IDs')
    for row in rows:
        if (row['chunk_id']!=row['id'] or digest(row['content_zh'].encode())!=row['content_zh_sha256']
            or digest(canonical({k:v for k,v in row.items() if k!='record_sha256'}))!=row['record_sha256']):raise ValueError('Corpus record hash differs')
    return rows


def text_for(row,template):
    if template=='body':return row['content_zh']
    if template=='title_body':return row['title_zh']+'\n'+row['content_zh']
    if template=='path_body':return ' / '.join(row['section_path'])+'\n'+row['content_zh']
    raise ValueError('Unknown document template')


def payload_for(rows,template,tokenizer):
    docs=[];df=collections.Counter()
    for row in rows:
        terms=tokenizer.tokens(text_for(row,template));tf=dict(sorted(collections.Counter(terms).items()))
        if not terms:raise ValueError('Empty tokenized document')
        docs.append({'chunk_id':row['chunk_id'],'length':len(terms),'tf':tf});df.update(tf.keys())
    return {'version':'bm25-index-1.0','template':template,'documents':docs,'df':dict(sorted(df.items())),
            'N':len(docs),'avgdl':sum(d['length'] for d in docs)/len(docs)}


def rank(payload,terms,k1=1.5,b=.75,top_k=10):
    if type(top_k) is not int or not 1<=top_k<=payload['N']:raise ValueError('Invalid TopK')
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in (k1,b)) or k1<=0 or not 0<=b<=1:raise ValueError('Invalid BM25 parameters')
    terms=sorted(set(terms));results=[]
    for doc in payload['documents']:
        score=0.0
        for term in terms:
            tf=doc['tf'].get(term,0)
            if tf:
                df=payload['df'][term];idf=math.log1p((payload['N']-df+.5)/(df+.5))
                score+=idf*(tf*(k1+1))/(tf+k1*(1-b+b*doc['length']/payload['avgdl']))
        if score>0:results.append({'chunk_id':doc['chunk_id'],'score':score})
    results.sort(key=lambda v:(-v['score'],v['chunk_id']))
    return [{**v,'rank':i} for i,v in enumerate(results[:top_k],1)]


def build(output,template):
    output=Path(output).resolve();cfg=config()
    if template not in TEMPLATES:raise ValueError('Unknown template')
    if not any(output.is_relative_to(ROOT/p) and output!=ROOT/p for p in ('data/indexes/bm25','.tmp')):raise ValueError('Use a new private BM25 or tmp subdirectory')
    if output.exists():raise ValueError('Refusing to overwrite an existing index')
    commit=committed(SOURCES+RESOURCES)
    began=time.perf_counter();tokenizer=Tokenizer();rows=corpus(cfg)
    payload=payload_for(rows,template,tokenizer)
    sources=[{k:r[k] for k in SOURCE_FIELDS} for r in rows]
    output.mkdir(parents=True,exist_ok=False)
    write_new(output/'index.json',payload);write_new(output/'source_map.json',sources)
    manifest={'version':'bm25-index-manifest-1.0','status':'COMPLETE','template':template,'records':99,
      'corpus':record(ROOT/cfg['corpus']),'inputs':{p:record(ROOT/p) for p in RESOURCES},
      'source_commit':commit,'sources':{p:record(ROOT/p) for p in SOURCES},
      'dependency':{'archive_sha256':tokenizer.dependency['archive_sha256'],
                    'default_dictionary_sha256':tokenizer.dependency['default_dictionary_sha256']},
      'artifacts':{n:{k:v for k,v in record(output/n).items() if k!='path'} for n in ('index.json','source_map.json')},
      'corpus_body_or_vectors_public':False}
    write_new(output/'index_manifest.json',manifest)
    return {'status':'COMPLETE','template':template,'records':99,'index_manifest':record(output/'index_manifest.json'),
            'build_seconds':time.perf_counter()-began,'vocabulary':len(payload['df'])}


class Bm25Index:
    def __init__(self,path):
        self.path=Path(path).resolve();self.cfg=config()
        self.manifest=json.loads((self.path/'index_manifest.json').read_text('utf-8'))
        m=self.manifest
        if (set(m)!={'version','status','template','records','corpus','inputs','source_commit','sources','dependency','artifacts','corpus_body_or_vectors_public'}
            or m['version']!='bm25-index-manifest-1.0' or m['status']!='COMPLETE' or type(m['records']) is not int or m['records']!=99
            or m['template'] not in TEMPLATES or m['corpus']!=record(ROOT/self.cfg['corpus'])
            or m['inputs']!={p:record(ROOT/p) for p in RESOURCES} or m['corpus_body_or_vectors_public'] is not False):raise ValueError('BM25 manifest differs from fixed inputs')
        if set(m['artifacts'])!={'index.json','source_map.json'} or set(m['sources'])!=set(SOURCES):raise ValueError('Incomplete index manifest')
        for name,entry in m['artifacts'].items():
            if entry!={k:v for k,v in record(self.path/name).items() if k!='path'}:raise ValueError('Index artifact checksum mismatch')
        committed((),m['source_commit'])
        for name,entry in m['sources'].items():
            raw=subprocess.check_output(['git','show',m['source_commit']+':'+name],cwd=ROOT)
            if entry!={'path':name,'sha256':digest(raw),'size_bytes':len(raw)}:raise ValueError('Index producer hash differs from Git')
        self.tokenizer=Tokenizer()
        if m['dependency']!={k:self.tokenizer.dependency[k] for k in ('archive_sha256','default_dictionary_sha256')}:raise ValueError('Tokenizer resource version changed')
        rows=corpus(self.cfg);self.sources=[{k:r[k] for k in SOURCE_FIELDS} for r in rows]
        if json.loads((self.path/'source_map.json').read_text('utf-8'))!=self.sources:raise ValueError('Index source mapping changed')
        self.payload=json.loads((self.path/'index.json').read_text('utf-8'))
        if canonical(self.payload)!=canonical(payload_for(rows,m['template'],self.tokenizer)):raise ValueError('Index tokens, TF/DF or lengths differ from fixed corpus')
        self.by_id={s['chunk_id']:s for s in self.sources}

    def query(self,text,top_k=10):
        start=time.perf_counter_ns();query=normalize(text);a=time.perf_counter_ns()
        terms=self.tokenizer.tokens(query);b=time.perf_counter_ns()
        result=rank(self.payload,terms,self.cfg['k1'],self.cfg['b'],top_k)
        result=[{**v,**self.by_id[v['chunk_id']]} for v in result];end=time.perf_counter_ns()
        return {'query':query,'tokens':terms,'results':result,'timing':dict(zip(TIMINGS,((a-start)/1e9,(b-a)/1e9,(end-b)/1e9,(end-start)/1e9)))}
