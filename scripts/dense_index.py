"""Pinned dense-only corpus index; no evaluation question or LLM is consumed."""
from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np

from eval_dataset import CORPUS, ROOT, canonical, digest, load_jsonl, write_json, write_jsonl

CONFIG = ROOT/'config/dense_index.json'
DEFAULT_INDEX = ROOT/'data/indexes/dense'
TEMPLATE = "join(section_path, ' / ') + '\\n\\n' + content_zh"
UPSTREAM = '9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9'
_CLIENT_LOCK = threading.RLock()
_CLIENT_REFERENCES = {}


def load_config(path=CONFIG):
    cfg = json.loads(Path(path).read_text('utf-8'))
    if (type(cfg['expected_records']) is not int or cfg['expected_records'] != 99 or cfg['storage']['backend'] != 'chromadb'
            or cfg['storage']['distance'] != 'cosine'
            or cfg['storage']['hnsw_metadata']['hnsw:space'] != 'cosine'
            or cfg['text']['document_template'] != TEMPLATE
            or cfg['text']['template_version'] != 'section-path-content-zh-v1'
            or cfg['text']['query_template'] != 'query unchanged; reject blank input'
            or cfg['text']['secondary_chunking'] is not False
            or cfg['text']['unicode_normalization'] != 'none'
            or cfg['embedding']['truncate'] is not False
            or cfg['embedding']['api'] != '/api/embed'
            or cfg['embedding']['normalization'] != 'L2 float32; reject nonfinite and zero vectors'
            or cfg['model']['query_prefix'] != '' or cfg['model']['document_prefix'] != ''):
        raise ValueError('Unsupported dense B0 configuration or text/normalization policy')
    for field in ('batch_size', 'num_ctx', 'num_thread', 'timeout_seconds'):
        if type(cfg['embedding'][field]) is not int or cfg['embedding'][field] < 1:
            raise ValueError('Embedding options must be positive integers')
    if type(cfg['embedding']['num_gpu']) is not int or cfg['embedding']['num_gpu'] != 0 or type(cfg['model']['dimensions']) is not int or cfg['model']['dimensions'] < 1:
        raise ValueError('This baseline fixes CPU encoding and positive embedding dimensions')
    for package, expected in (('chromadb',cfg['storage']['version']),('numpy',cfg['storage']['numpy_version']),
                              ('chroma-hnswlib',cfg['storage']['hnswlib_version'])):
        if importlib.metadata.version(package) != expected:
            raise ValueError('Pinned dependency differs: '+package)
    return cfg


def document_text(row):
    return ' / '.join(row['section_path'])+'\n\n'+row['content_zh']


def read_corpus(cfg):
    if digest(CORPUS.read_bytes()) != cfg['corpus_sha256']:
        raise ValueError('Frozen corpus hash differs')
    rows = load_jsonl(CORPUS)
    if len(rows) != cfg['expected_records'] or len({r['chunk_id'] for r in rows}) != len(rows):
        raise ValueError('Expected 99 unique original chunk IDs')
    for row in rows:
        if (row['dataset_version'] != cfg['corpus_version'] or row['chunk_id'] != row['id']
                or not row['section_path'] or not row['content_zh']
                or digest(row['content_zh'].encode('utf-8')) != row['content_zh_sha256']
                or digest(canonical({k:v for k,v in row.items() if k!='record_sha256'})) != row['record_sha256']):
            raise ValueError('Invalid corpus record: '+row['chunk_id'])
    return rows


def mapping_for(rows):
    return [{'position':i,'chunk_id':r['chunk_id'],'record_sha256':r['record_sha256'],
             'content_zh_sha256':r['content_zh_sha256'],
             'embedding_text_sha256':digest(document_text(r).encode('utf-8'))} for i,r in enumerate(rows)]


def unit_vectors(values, dimensions, count=None):
    vectors = np.asarray(values, dtype=np.float32)
    if (vectors.ndim != 2 or vectors.shape[1] != dimensions
            or (count is not None and len(vectors) != count) or not np.isfinite(vectors).all()):
        raise ValueError('Embedding shape, count or finite-value check failed')
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if not np.isfinite(norms).all() or np.any(norms <= 1e-12):
        raise ValueError('Zero or invalid embedding norm')
    return np.ascontiguousarray(vectors/norms, dtype=np.float32)


class PinnedEmbedder:
    def __init__(self, cfg, base_url=None):
        self.cfg = cfg
        self.base_url = (base_url or os.environ.get('FOOTBALL_DENSE_OLLAMA_URL','http://127.0.0.1:11434')).rstrip('/')
        parsed = urlsplit(self.base_url)
        if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1','localhost','::1')
                or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path):
            raise ValueError('Dense B0 uses an unauthenticated loopback Ollama endpoint')
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.observations = []
        self.verify_model()

    def request(self, path, value=None):
        body = None if value is None else json.dumps(value,ensure_ascii=False).encode('utf-8')
        request = urllib.request.Request(self.base_url+path,data=body,headers={'Content-Type':'application/json'})
        try:
            with self.opener.open(request,timeout=self.cfg['embedding']['timeout_seconds']) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError('Local embedding request failed at '+path+': '+str(exc)) from exc

    def verify_model(self):
        model = self.cfg['model']
        if self.request('/api/version').get('version') != model['ollama_version']:
            raise ValueError('Ollama runtime version differs from pinned baseline')
        matches = [r for r in self.request('/api/tags')['models'] if r['name'] == model['name']]
        if len(matches) != 1 or matches[0]['digest'] != model['digest']:
            raise ValueError('Embedding model digest differs; do not silently use a changed tag')
        show = self.request('/api/show',{'model':model['name']})
        info = show['model_info']
        if (info.get('bert.embedding_length') != model['dimensions']
                or info.get('bert.context_length') != self.cfg['embedding']['num_ctx']
                or show['details'].get('quantization_level') != model['quantization']):
            raise ValueError('Embedding dimensions/context/quantization differ from configuration')
        self.model_info = {'name':model['name'],'digest':model['digest'],'architecture':info.get('general.architecture'),
                           'dimensions':info['bert.embedding_length'],'context_length':info['bert.context_length'],
                           'quantization':show['details']['quantization_level'],'ollama_version':model['ollama_version']}

    def encode(self, texts):
        if not texts or any(not isinstance(t,str) or not t.strip() for t in texts):
            raise ValueError('Embedding input must contain nonblank strings')
        batches = []
        settings = self.cfg['embedding']
        for start in range(0,len(texts),settings['batch_size']):
            self.verify_model()
            batch = texts[start:start+settings['batch_size']]
            began = time.perf_counter()
            response = self.request('/api/embed',{'model':self.cfg['model']['name'],'input':batch,'truncate':False,
                'keep_alive':settings['keep_alive'],'options':{k:settings[k] for k in ('num_ctx','num_gpu','num_thread')}})
            vectors = unit_vectors(response['embeddings'],self.cfg['model']['dimensions'],len(batch))
            self.verify_model()
            self.observations.append({'inputs':len(batch),'elapsed_seconds':time.perf_counter()-began,
                'prompt_eval_count':response.get('prompt_eval_count'),'server_total_duration_ns':response.get('total_duration'),
                'server_load_duration_ns':response.get('load_duration')})
            batches.append(vectors)
        return np.concatenate(batches,axis=0)

    def runtime(self):
        models = self.request('/api/ps')['models']
        loaded = next((r for r in models if r.get('digest') == self.cfg['model']['digest']),{})
        if not loaded or loaded.get('size_vram') != 0:
            raise ValueError('Expected the pinned model to be loaded on CPU (size_vram=0)')
        return {k:loaded.get(k) for k in ('name','digest','size','size_vram','context_length','runner')}


def snapshot_inputs():
    # Validate the published review metadata, including annotation hashes.
    # Evaluation text is never passed to embedding/generation, tuned or scored.
    from validate_eval_receipt import require_receipt
    require_receipt(ROOT/'data/eval')
    names = ['docs/TECHNICAL_DESIGN.md','docs/DEVELOPMENT_PLAN_AND_REPORT.md','docs/UPSTREAM_VERSION.md',
             'data/processed/rag_chunks_zh.jsonl','data/manifests/rag_dataset_manifest.json',
             'data/eval/dataset_manifest.json','data/eval/retrieval_dev.jsonl','data/eval/retrieval_test.jsonl',
             'data/eval/answer_eval.jsonl','data/eval/hard_negatives.jsonl','data/eval/human_review_receipt.json']
    manifest = json.loads((ROOT/'data/eval/dataset_manifest.json').read_text('utf-8'))
    if (manifest['release_status'] != 'human_reviewed_and_test_locked'
            or manifest['human_review']['approved'] != 90 or manifest['test_lock']['state'] != 'locked'
            or manifest['test_lock']['used_for_parameter_selection'] is not False):
        raise ValueError('Task 4 must be human-reviewed and locked before indexing')
    for name, entry in manifest['files'].items():
        if digest((ROOT/'data/eval'/name).read_bytes()) != entry['sha256']:
            raise ValueError('Frozen task 4 input differs: '+name)
    if digest((ROOT/'data/eval/human_review_receipt.json').read_bytes()) != manifest['human_review']['receipt_sha256']:
        raise ValueError('Human review receipt integrity differs')
    upstream = subprocess.check_output(['git','-C',str(ROOT/'third_party/kotaemon-v0.12.0'),'rev-parse','HEAD'],text=True).strip()
    if upstream != UPSTREAM:
        raise ValueError('Pinned Kotaemon version differs')
    return {name:digest((ROOT/name).read_bytes()) for name in names}


def safe_output(path):
    path = Path(path).resolve()
    if not any(path.is_relative_to(base) and path != base for base in (ROOT/'data/indexes',ROOT/'.tmp')):
        raise ValueError('Index output must be a child of data/indexes/ or ignored .tmp/')
    for parent in path.parents:
        if parent == ROOT:
            break
        if (parent/'index_manifest.json').exists() or (parent/'embeddings.npy').exists():
            raise ValueError('Refusing a nested index path inside an existing or incomplete index')
    return path


def open_collection(path, cfg, create=False):
    import chromadb
    from chromadb.config import Settings
    with _CLIENT_LOCK:
        client = chromadb.PersistentClient(path=str(path/'chroma'),settings=Settings(anonymized_telemetry=False,allow_reset=False,
            chroma_product_telemetry_impl='dense_telemetry.DisabledTelemetry'))
        client._dense_system = client._system
        client._dense_released = False
        entry = _CLIENT_REFERENCES.setdefault(client._identifier,{'system':client._system,'count':0})
        entry['count'] += 1
        try:
            if create:
                collection = client.create_collection(cfg['storage']['collection'],embedding_function=None,
                    metadata={**cfg['storage']['hnsw_metadata'],'index_version':cfg['index_version']})
            else:
                collection = client.get_collection(cfg['storage']['collection'],embedding_function=None)
        except Exception:
            close_client(client)
            raise
    return client, collection


def close_client(client):
    # Chroma 0.5.16 has no public close(). Release this path's system only;
    # never reset/delete a collection or clear unrelated clients' caches.
    from chromadb.api.shared_system_client import SharedSystemClient
    with _CLIENT_LOCK:
        if getattr(client,'_dense_released',False):
            return
        key, system = client._identifier, client._dense_system
        client._dense_released = True
        entry = _CLIENT_REFERENCES[key]
        entry['count'] -= 1
        if entry['count']:
            return
        try:
            system.stop()
        finally:
            _CLIENT_REFERENCES.pop(key)
            if SharedSystemClient._identifier_to_system.get(key) is system:
                SharedSystemClient._identifier_to_system.pop(key)


def collection_metadata(row):
    return {k:row[k] for k in ('chunk_id','source_id','source_url','document_id','law_number',
                               'record_sha256','content_zh_sha256','source_revision_id','needs_rule_review','expert_reviewed')}


def inventory(path):
    return {p.relative_to(path).as_posix():{'size_bytes':p.stat().st_size,'sha256':digest(p.read_bytes())}
            for p in sorted(path.rglob('*')) if p.is_file() and p.name != 'index_manifest.json'}


def build(output=DEFAULT_INDEX, config_path=CONFIG):
    # Import the configured telemetry component before costly model encoding;
    # Chroma's Component metaclass validates overrides at import time.
    from dense_telemetry import DisabledTelemetry
    began = time.perf_counter()
    cfg, output = load_config(config_path), safe_output(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Refusing to overwrite a nonempty index directory; use a new version/path')
    inputs = snapshot_inputs()
    rows = read_corpus(cfg)
    config_sha = digest(Path(config_path).read_bytes())
    embedder = PinnedEmbedder(cfg)
    output.mkdir(parents=True,exist_ok=True)
    encoding_started = time.perf_counter()
    vectors = embedder.encode([document_text(row) for row in rows])
    encoding_seconds = time.perf_counter()-encoding_started
    np.save(output/'embeddings.npy',vectors,allow_pickle=False)
    write_jsonl(output/'records.jsonl',rows)
    mapping = mapping_for(rows)
    write_json(output/'id_mapping.json',mapping)
    client, collection = open_collection(output,cfg,create=True)
    try:
        for start in range(0,len(rows),32):
            batch = rows[start:start+32]
            collection.add(ids=[r['chunk_id'] for r in batch],embeddings=vectors[start:start+32].tolist(),
                           metadatas=[collection_metadata(r) for r in batch])
        if collection.count() != len(rows):
            raise ValueError('Persisted collection count differs from corpus')
    finally:
        close_client(client)
    if snapshot_inputs() != inputs or digest(Path(config_path).read_bytes()) != config_sha:
        raise ValueError('Input/configuration changed during build; incomplete output must not be used')
    manifest = {'manifest_version':'dense-index-1.0','index_version':cfg['index_version'],'state':'READY',
        'built_at':datetime.now(timezone.utc).isoformat(),'records':len(rows),'dimensions':vectors.shape[1],
        'config':cfg,'config_sha256':config_sha,'input_sha256':inputs,'upstream_commit':UPSTREAM,
        'model_artifact':embedder.model_info,'model_runtime':embedder.runtime(),
        'vector_fingerprint':digest(vectors.tobytes(order='C')),'artifact_files':inventory(output),
        'environment':{'python':platform.python_version(),'platform':platform.platform(),'logical_cpus':os.cpu_count(),
            'packages':{p:importlib.metadata.version(p) for p in ('numpy','chromadb','chroma-hnswlib')}},
        'implementation_sha256':{name:digest((ROOT/'scripts'/name).read_bytes()) for name in
                                  ('dense_index.py','dense_telemetry.py','build_dense_index.py')},
        'timing':{'wall_seconds':time.perf_counter()-began,'embedding_seconds':encoding_seconds,
                  'embedding_batches':embedder.observations},
        'scope':'Dense index usability only; no retrieval benchmark, model answer or quality metric',
        'test_labels_parsed_or_scored':False,'full_corpus_distribution':'local-only'}
    write_json(output/'index_manifest.json',manifest)
    return manifest


class DenseIndex:
    def __init__(self, path=DEFAULT_INDEX, config_path=CONFIG, embedder=None):
        self.client = None
        self.path = safe_output(path)
        self.cfg = load_config(config_path)
        if embedder is not None and (not isinstance(embedder,PinnedEmbedder) or embedder.cfg != self.cfg):
            raise ValueError('A supplied embedder must use the exact pinned index configuration')
        self.manifest = json.loads((self.path/'index_manifest.json').read_text('utf-8'))
        if (self.manifest['state'] != 'READY' or self.manifest['records'] != self.cfg['expected_records']
                or self.manifest['dimensions'] != self.cfg['model']['dimensions']
                or self.manifest['index_version'] != self.cfg['index_version']
                or self.manifest['config_sha256'] != digest(Path(config_path).read_bytes())
                or self.manifest['config'] != self.cfg or self.manifest['input_sha256'] != snapshot_inputs()):
            raise ValueError('Index configuration, completion state or frozen inputs differ; rebuild a new version')
        expected = self.manifest['artifact_files']
        if inventory(self.path) != expected:
            raise ValueError('Index artifact integrity differs')
        self.rows = read_corpus(self.cfg)
        if load_jsonl(self.path/'records.jsonl') != self.rows:
            raise ValueError('Index source metadata differs from corpus')
        self.mapping = json.loads((self.path/'id_mapping.json').read_text('utf-8'))
        if self.mapping != mapping_for(self.rows):
            raise ValueError('Stable ID mapping differs from corpus')
        self.vectors = np.load(self.path/'embeddings.npy',allow_pickle=False)
        if (self.vectors.shape != (len(self.rows),self.cfg['model']['dimensions']) or self.vectors.dtype != np.float32
                or not np.isfinite(self.vectors).all() or not np.allclose(np.linalg.norm(self.vectors,axis=1),1,atol=1e-6)
                or digest(self.vectors.tobytes(order='C')) != self.manifest['vector_fingerprint']):
            raise ValueError('Stored normalized vectors differ')
        self.by_id = {r['chunk_id']:r for r in self.rows}
        self.vector_positions = {r['chunk_id']:i for i,r in enumerate(self.rows)}
        self.client, self.collection = open_collection(self.path,self.cfg)
        try:
            actual = self.collection.get(include=['embeddings','metadatas'])
            positions = {value:i for i,value in enumerate(actual['ids'])}
            if (self.collection.count() != len(self.rows) or set(positions) != set(self.by_id)
                    or self.collection.metadata != {**self.cfg['storage']['hnsw_metadata'],'index_version':self.cfg['index_version']}):
                raise ValueError('Collection ID count or configuration differs')
            for row, vector in zip(self.rows,self.vectors):
                i = positions[row['chunk_id']]
                if actual['metadatas'][i] != collection_metadata(row) or not np.allclose(actual['embeddings'][i],vector,atol=1e-7,rtol=0):
                    raise ValueError('Stored collection vector or provenance differs: '+row['chunk_id'])
        except Exception:
            close_client(self.client)
            raise
        self.embedder = embedder

    def close(self):
        if self.client is not None:
            close_client(self.client)
            self.client = None

    def __enter__(self): return self
    def __exit__(self, *_): self.close()

    def query_vector(self, vector, top_k=5):
        if self.client is None:
            raise ValueError('DenseIndex is closed')
        if type(top_k) is not int or not 1 <= top_k <= len(self.rows):
            raise ValueError('top_k must be an integer between 1 and corpus size')
        normalized = unit_vectors([vector],self.cfg['model']['dimensions'],1)[0]
        raw = self.collection.query(query_embeddings=[normalized.tolist()],n_results=top_k,include=['distances','metadatas'])
        try:
            if (any(len(raw[key]) != 1 or len(raw[key][0]) != top_k for key in ('ids','distances','metadatas'))
                    or len(set(raw['ids'][0])) != top_k):
                raise ValueError('Query results are incomplete, duplicate or misaligned')
        except (KeyError,TypeError) as exc:
            raise ValueError('Malformed query result packet') from exc
        matches = []
        for qid, distance, metadata in zip(raw['ids'][0],raw['distances'][0],raw['metadatas'][0]):
            if qid not in self.by_id or not np.isfinite(distance) or metadata != collection_metadata(self.by_id[qid]):
                raise ValueError('Query result ID/score/source integrity differs')
            row = self.by_id[qid]
            expected_distance = 1.0-float(np.dot(normalized,self.vectors[self.vector_positions[qid]]))
            if not np.isclose(distance,expected_distance,atol=3e-6,rtol=0):
                raise ValueError('Query distance differs from the stored normalized vector')
            matches.append({'chunk_id':qid,'distance':float(distance),'score':1.0-float(distance),
                            'content_zh':row['content_zh'],'metadata':{k:v for k,v in row.items() if k!='content_zh'}})
        matches.sort(key=lambda r:(r['distance'],r['chunk_id']))
        for rank,row in enumerate(matches,1): row['rank'] = rank
        return matches

    def query(self, text, top_k=5):
        if self.client is None:
            raise ValueError('DenseIndex is closed')
        if not isinstance(text,str) or not text.strip():
            raise ValueError('Query must be a nonblank string')
        if type(top_k) is not int or not 1 <= top_k <= len(self.rows):
            raise ValueError('top_k must be an integer between 1 and corpus size')
        if self.embedder is None:
            self.embedder = PinnedEmbedder(self.cfg)
        elif self.embedder.cfg != self.cfg:
            raise ValueError('Query embedder configuration differs from the index')
        began = time.perf_counter()
        vector = self.embedder.encode([text])[0]
        embed_seconds = time.perf_counter()-began
        search_started = time.perf_counter()
        matches = self.query_vector(vector,top_k)
        return {'index_version':self.cfg['index_version'],'query':text,'results':matches,
                'timing':{'query_embedding_seconds':embed_seconds,'vector_search_seconds':time.perf_counter()-search_started},
                'score_definition':self.cfg['storage']['score'],'is_quality_evaluation':False}
