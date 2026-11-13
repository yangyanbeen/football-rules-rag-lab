"""Independent exact-cosine/BM25 controls sharing one actual query embedding."""
import importlib.metadata,json,os,platform,time
from pathlib import Path
from eval_dataset import ROOT,canonical,digest,load_jsonl
from bm25_index import corpus,Tokenizer,payload_for,rank,record,write_new,committed
from structure_aware_chunking import DATA,MAP,tokenizer,derive,config
from structure_retrieval_eval import SOURCES,INDEX,fuse,mapping

HOME=ROOT/'data/indexes/structure_pc_b0'


def files():return {p.relative_to(ROOT).as_posix():record(p) for p in HOME.rglob('*') if p.is_file()}


def build():
    import numpy as np
    from dense_index import PinnedEmbedder,load_config,document_text,unit_vectors
    if HOME.exists() or (ROOT/INDEX).exists():raise FileExistsError('Use a fresh independent index version')
    source=committed(SOURCES+('config/structure_parent_child.json',MAP,'docs/TASK_11_SCOPE.md'))
    started=time.perf_counter();m=mapping();old=corpus();old_by={r['chunk_id']:i for i,r in enumerate(old)}
    original_manifest=json.loads((ROOT/'data/manifests/dense_index_manifest.json').read_text('utf-8'))
    path=ROOT/'data/indexes/dense/embeddings.npy'
    if record(path)['sha256']!=original_manifest['artifact_files']['embeddings.npy']['sha256']:raise ValueError('Original vector file differs')
    base_vectors=np.load(path,allow_pickle=False)
    if base_vectors.dtype!=np.float32 or base_vectors.shape!=(99,1024) or not np.isfinite(base_vectors).all() or not np.allclose(np.linalg.norm(base_vectors,axis=1),1,atol=1e-6):raise ValueError('Invalid original vectors')
    private=load_jsonl(ROOT/DATA);by={r['chunk_id']:r for r in private};child_ids=list(m['children']);vectors=[];changed=[]
    for cid in child_ids:
        child=m['children'][cid];orig=m['originals'][child['original_id']]
        if child['passage_sha256']==orig['passage_sha256']:vectors.append(base_vectors[old_by[child['original_id']]])
        else:changed.append(cid);vectors.append(None)
    embedder=PinnedEmbedder(load_config());observations=[]
    if changed:
        encoded=embedder.encode([' / '.join(by[c]['section_path'])+'\n\n'+by[c]['content_zh'] for c in changed]);observations=embedder.observations.copy()
        for cid,v in zip(changed,encoded):vectors[child_ids.index(cid)]=v
    else:embedder.encode([config()['warmup_question']])
    child_vectors=np.asarray(vectors,dtype=np.float32)
    token=Tokenizer();child_rows=[{'chunk_id':cid,'title_zh':m['children'][cid]['title_zh'],'content_zh':by[cid]['content_zh']} for cid in child_ids]
    lexical={'base':payload_for(old,'title_body',token),'child':payload_for(child_rows,'title_body',token)}
    original_lex=json.loads((ROOT/'data/indexes/bm25/title_body/index.json').read_text('utf-8'))
    if canonical(lexical['base'])!=canonical(original_lex):raise ValueError('Base BM25 differs from task8')
    HOME.mkdir(parents=True,exist_ok=False);np.save(HOME/'children.npy',child_vectors,allow_pickle=False)
    write_new(HOME/'lexical.json',lexical)
    value={'version':'structure-exact-index-1.0','source_commit':source,'source_sha256':{p:record(ROOT/p)['sha256'] for p in SOURCES},
           'base_ids':[r['chunk_id'] for r in old],'child_ids':child_ids,'original_vectors':record(path),'derived_corpus':record(ROOT/DATA),
           'mapping':record(ROOT/MAP),'config':record(ROOT/'config/structure_parent_child.json'),
           'embedding_config':record(ROOT/'config/dense_index.json'),'model_runtime':embedder.runtime(),
           'changed_children_embedded':changed,'reused_unchanged_child_vectors':len(child_ids)-len(changed),
           'embedding_batches':observations,'embedding_items':sum(o['inputs'] for o in observations),
           'artifact_files':files(),'build_seconds':time.perf_counter()-started,
           'backend':'Exact cosine numpy float32 for both controls; not historical Chroma timing',
           'environment':{'python':platform.python_version(),'system':platform.platform(),'logical_cpus':os.cpu_count(),
                          'packages':{p:importlib.metadata.version(p) for p in ('numpy','tokenizers')}},
           'test_queries_read_or_embedded':False,'full_data_distribution':'local-only'}
    write_new(HOME/'index_manifest.json',value);write_new(ROOT/INDEX,value);return value


class Retriever:
    def __init__(self):
        import numpy as np
        from dense_index import PinnedEmbedder,load_config
        self.np=np;self.before=files();self.m=mapping();self.index=json.loads((ROOT/INDEX).read_text('utf-8'))
        if json.loads((HOME/'index_manifest.json').read_text('utf-8'))!=self.index:raise ValueError('Index metadata differs')
        for p,r in self.index['artifact_files'].items():
            if record(ROOT/p)!=r:raise ValueError('Independent index checksum differs')
        if self.index['mapping']!=record(ROOT/MAP) or self.index['derived_corpus']!=record(ROOT/DATA) or self.index['original_vectors']!=record(ROOT/self.index['original_vectors']['path']):raise ValueError('Index input changed')
        self.lexical=json.loads((HOME/'lexical.json').read_text('utf-8'));self.ids={'base':self.index['base_ids'],'child':self.index['child_ids']}
        self.vectors={'base':np.load(ROOT/self.index['original_vectors']['path'],allow_pickle=False),'child':np.load(HOME/'children.npy',allow_pickle=False)}
        for method,values in self.vectors.items():
            if values.dtype!=np.float32 or values.shape!=(len(self.ids[method]),1024) or not np.isfinite(values).all() or not np.allclose(np.linalg.norm(values,axis=1),1,atol=1e-6):raise ValueError('Independent vectors invalid')
        self.tokenizer=Tokenizer();self.embedder=PinnedEmbedder(load_config())

    def query(self,question,qid='warmup'):
        from dense_retrieval_eval import normalize_query
        start=time.perf_counter();query=normalize_query(question);vector=self.embedder.encode([query])[0];a=time.perf_counter()
        observation=dict(self.embedder.observations[-1]);terms=self.tokenizer.tokens(query);channels={};rankings={};times=[]
        for method in ('base','child'):
            distances=1.-self.vectors[method]@vector
            order=sorted(range(len(distances)),key=lambda i:(float(distances[i]),self.ids[method][i]))[:80]
            dense=[{'chunk_id':self.ids[method][i],'rank':j,'score':1-float(distances[i]),'distance':float(distances[i])} for j,i in enumerate(order,1)]
            bm=rank(self.lexical[method],terms,1.5,.75,80)
            channels[method]={'dense':dense,'bm25':bm};rankings[method]=fuse(channels[method],self.m['originals' if method=='base' else 'children']);times.append(time.perf_counter())
        end=time.perf_counter()
        return {'question_id':qid,'question_sha256':digest(question.encode()),'query':query,'embedding_observation':observation,
                'query_vector_sha256':digest(vector.tobytes()),'channels':channels,'rankings':rankings,
                'timing':{'embedding_seconds':a-start,'base_retrieval_seconds':times[0]-a,'child_retrieval_seconds':times[1]-times[0],'total_seconds':end-start}}

    def environment(self):
        return {'python':platform.python_version(),'system':platform.platform(),'logical_cpus':os.cpu_count(),
                'packages':{p:importlib.metadata.version(p) for p in ('numpy','tokenizers')},'embedding_runtime':self.embedder.runtime()}

    def close(self):
        if files()!=self.before:raise ValueError('Read-only independent index changed')
    def __enter__(self):return self
    def __exit__(self,*_):self.close()


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('build',));p.parse_args()
    value=build();print(json.dumps({'status':'COMPLETE','children':len(value['child_ids']),'new_embedding_items':value['embedding_items']}))
