"""Task13 private corpus import, preflight, isolated index rebuild and environment receipt."""
import argparse,importlib.metadata,os,platform,subprocess,sys,time
from task13_core import *


def import_local(source):
    source=Path(source).resolve();entries=read(ROOT/'data/manifests/local_data_files.json')['files']
    planned=[]
    # Validate the complete input set before creating any destination file.
    for r in entries:
        path=(source/r['path']).resolve();target=(ROOT/r['path']).resolve()
        if not path.is_relative_to(source) or not target.is_relative_to(ROOT/'data') or target.is_relative_to(ROOT/'data/manifests'):
            raise ValueError('Unsafe corpus input/destination')
        if path.stat().st_size!=r['size_bytes'] or digest(path.read_bytes())!=r['sha256']:raise ValueError('Source corpus file differs: '+r['path'])
        if target.exists() and (target.stat().st_size!=r['size_bytes'] or digest(target.read_bytes())!=r['sha256']):raise ValueError('Existing corpus differs; no overwrite: '+r['path'])
        planned.append((path,target,r))
    copied=[];verified=[]
    for path,target,r in planned:
        if target.exists():verified.append(r['path']);continue
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as handle:handle.write(path.read_bytes())
        if record(target)!={k:r[k] for k in ('path','size_bytes','sha256')}:raise ValueError('Copied corpus identity differs')
        copied.append(r['path'])
    corpus=local_corpus()
    return {'version':'task13-corpus-import-1.0','status':'PASS','captured_at':now(),'files':len(entries),
        'copied_files':copied,'existing_verified_files':verified,'records':len(corpus),
        'corpus':record(ROOT/'data/processed/rag_chunks_zh.jsonl'),'inventory':record(ROOT/'data/manifests/local_data_files.json'),
        'secondary_chunking':False,'new_model_requests':0}


def preflight():
    cfg=app_config();corpus=local_corpus()
    from install_bm25_runtime import verify as bm25_dependency
    from bge_reranker import HOME,file_sha
    from reranker_eval import config as reranker_config
    from rag_b0 import PinnedChat
    from dense_index import PinnedEmbedder
    from kotaemon_runtime_env import configure_local_runtime
    assets=configure_local_runtime();b=bm25_dependency();rc=reranker_config()
    for n,r in rc['files'].items():
        p=HOME/n
        if p.stat().st_size!=r['size_bytes'] or file_sha(p)!=r['sha256']:raise ValueError('Pinned reranker asset differs: '+n)
    PinnedChat(answer_config()).verify_model();e=PinnedEmbedder(read(ROOT/'config/dense_index.json'))
    # Pinning verifies identities; no document encoding or answer generation here.
    upstream=subprocess.check_output(['git','-C',str(ROOT/'third_party/kotaemon-v0.12.0'),'rev-parse','HEAD'],text=True).strip()
    if upstream!='9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9':raise ValueError('Upstream differs')
    expected={d.lower().replace('_','-'):v for d,v in read(ROOT/'.runtime/task13/before.json')['packages'].items()} if (ROOT/'.runtime/task13/before.json').exists() else None
    packages={d.metadata['Name']:d.version for d in importlib.metadata.distributions()}
    if expected is not None and {d.lower().replace('_','-'):v for d,v in packages.items()}!=expected:raise ValueError('New environment differs from accepted package versions')
    return {'version':'task13-preflight-1.0','status':'PASS','captured_at':now(),'python':platform.python_version(),
        'system':platform.platform(),'machine':platform.machine(),'logical_cpus':os.cpu_count(),
        'environment':str(Path(sys.prefix).resolve().relative_to(ROOT)),'fresh_environment':Path(sys.prefix).resolve().is_relative_to(ROOT/'.runtime/task13'),
        'packages':packages,'upstream_commit':upstream,'corpus':record(ROOT/cfg['corpus']),'records':len(corpus),
        'configuration':source_identity(),'bm25_dependency_sha256':b['archive_sha256'],
        'reranker_revision':rc['revision'],'reranker_model_files':rc['files'],'ui_assets_verified':bool(assets),
        'answer_model':answer_config()['llm'],'embedding_model':read(ROOT/'config/dense_index.json')['model'],
        'new_model_inference_requests':0}


def rebuild():
    cfg=app_config();dense=(ROOT/cfg['dense_index']).resolve();bm=(ROOT/cfg['bm25_index']).resolve()
    if dense.exists() or bm.exists():raise ValueError('New index directories required; old indexes must not be overwritten')
    start=now();from dense_index import build as dense_build
    from bm25_index import build as bm_build
    dense_result=dense_build(dense);bm_result=bm_build(bm,'title_body')
    return {'version':'task13-index-rebuild-1.0','status':'PASS','started_at':start,'completed_at':now(),
        'configuration':source_identity(),'dense_index':record(dense/'index_manifest.json'),'bm25_index':record(bm/'index_manifest.json'),
        'records':dense_result['records'],'dimensions':dense_result['dimensions'],
        'embedding_batches':dense_result['timing']['embedding_batches'],'vector_fingerprint':dense_result['vector_fingerprint'],
        'dense_seconds':dense_result['timing']['wall_seconds'],'bm25_seconds':bm_result['build_seconds'],
        'previous_indexes_overwritten':False,'new_formal_test_runs':0}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('import','preflight','rebuild'));p.add_argument('--source-root');p.add_argument('--report',required=True);a=p.parse_args()
    target=(ROOT/a.report).resolve()
    if not target.is_relative_to(ROOT) or target.exists():raise ValueError('Use a new repository-local report')
    started=now()
    try:
        if a.action=='import':
            if not a.source_root:raise ValueError('--source-root required')
            value=import_local(a.source_root)
        else:value=preflight() if a.action=='preflight' else rebuild()
        write_new(target,value);print(json.dumps({'status':value['status'],'action':a.action,'records':value.get('records'),'report':record(target)},ensure_ascii=False))
    except BaseException as exc:
        write_new(target,{'version':'task13-resource-failure-1.0','status':'FAIL','action':a.action,'started_at':started,'failed_at':now(),'error':type(exc).__name__+': '+str(exc)})
        raise


if __name__=='__main__':main()
