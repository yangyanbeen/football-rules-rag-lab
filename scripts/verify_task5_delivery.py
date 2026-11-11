"""Exercise task 5 with real re-encoding, fresh processes and isolated corrupt indexes."""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from dense_index import (CONFIG, DEFAULT_INDEX, DenseIndex, PinnedEmbedder, build, close_client,
                         document_text, inventory, load_config, mapping_for, open_collection,
                         read_corpus, safe_output, snapshot_inputs, unit_vectors)
from eval_dataset import ROOT, digest, load_jsonl, write_json, write_jsonl

BASE = '8e8b93c6556943b4d08ee82f2620a5bc21ee759a'
SMOKE_QUERIES = ['足球场的边界标线如何判定球出界？','裁判出示黄牌和红牌分别表示什么？','足球比赛中，角旗附近的弧线有什么用途？']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',type=Path,default=DEFAULT_INDEX)
    parser.add_argument('--original-root',type=Path)
    parser.add_argument('--original-snapshot',type=Path)
    args = parser.parse_args()
    if bool(args.original_root) != bool(args.original_snapshot):
        raise ValueError('Provide original root and prior snapshot together')
    cfg = load_config()
    rows = read_corpus(cfg)
    before = snapshot_inputs()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    fixture = ROOT/'.tmp'/('task5-'+stamp)
    fixture.mkdir(parents=True)
    checks, smoke, negative = [], [], []
    environment = os.environ.copy()
    environment.update(PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')

    def record(name, passed, detail=None):
        checks.append({'check':name,'passed':bool(passed),'detail':detail})

    def child(script, *arguments):
        proc = subprocess.run([sys.executable,str(ROOT/'scripts'/script),*map(str,arguments)],cwd=ROOT,
                              env=environment,capture_output=True,text=True,encoding='utf-8',timeout=360)
        if proc.returncode:
            raise RuntimeError(script+' failed: '+proc.stderr[-1800:])
        if proc.stderr.strip():
            raise RuntimeError(script+' emitted unexpected stderr: '+proc.stderr[-1200:])
        return json.loads(proc.stdout)

    with DenseIndex(args.index) as index:
        original = index.manifest
        record('99_original_ids_and_complete_source_metadata', len(index.rows)==99 and index.mapping==mapping_for(rows))
        record('1024_finite_unit_vectors', index.vectors.shape==(99,1024) and np.isfinite(index.vectors).all()
               and np.allclose(np.linalg.norm(index.vectors,axis=1),1,atol=1e-6))
        record('full_title_path_and_original_body_used', all(document_text(r)==' / '.join(r['section_path'])+'\n\n'+r['content_zh'] for r in rows))
        record('table_kept_as_one_original_unit', sum(r['chunk_type']=='table' for r in rows)==1
               and index.by_id['L14-04']['content_zh']==next(r['content_zh'] for r in rows if r['chunk_id']=='L14-04'))
        record('collection_persistence_matches_vectors_and_ids', index.collection.count()==99)
        record('pinned_model_cpu_runtime', original['model_runtime']['digest']==cfg['model']['digest']
               and original['model_runtime']['size_vram']==0 and original['model_artifact']['dimensions']==1024)
        self_results = [index.query_vector(index.vectors[i],1)[0] for i in (0,44,98)]
        record('stored_vector_lookup_contract_not_quality_metric', all(r['chunk_id']==rows[i]['chunk_id'] and r['score']>0.9999
               for i,r in zip((0,44,98),self_results)))
        positions = {r['chunk_id']:i for i,r in enumerate(rows)}
        score_checks = []
        for vector in index.vectors[[0,44,98]]:
            for result in index.query_vector(vector,5):
                score_checks.append(abs(result['score']-float(np.dot(vector,index.vectors[positions[result['chunk_id']]])))<2e-6)
        record('cosine_score_matches_stored_vectors', all(score_checks))

    for query in SMOKE_QUERIES:
        first = child('query_dense_index.py','--index',args.index,'--query',query,'--top-k',3)
        second = child('query_dense_index.py','--index',args.index,'--query',query,'--top-k',3)
        valid = len(first['results'])==3 and [r['rank'] for r in first['results']]==[1,2,3]
        stable = [r['chunk_id'] for r in first['results']]==[r['chunk_id'] for r in second['results']]
        stable = stable and np.allclose([r['score'] for r in first['results']],[r['score'] for r in second['results']],atol=2e-6,rtol=0)
        for result in first['results']:
            row = next(r for r in rows if r['chunk_id']==result['chunk_id'])
            valid = valid and result['metadata']=={k:v for k,v in row.items() if k!='content_zh'}
            valid = valid and 'content_zh' not in result and np.isfinite(result['score']) and np.isclose(result['score'],1-result['distance'])
        record('fresh_process_query_contract_'+str(len(smoke)+1),valid and stable)
        smoke.append({'query':query,'top_k':3,'two_fresh_processes_consistent':bool(stable),
            'timing':first['timing'],'results':[{k:r[k] for k in ('chunk_id','rank','distance','score')} |
                {'source_url':r['metadata']['source_url'],'source_id':r['metadata']['source_id'],
                 'source_lines':r['metadata']['source_lines'],'content_zh_sha256':r['metadata']['content_zh_sha256'],
                 'source_revision_verified':r['metadata']['source_revision_verified'],'expert_reviewed':r['metadata']['expert_reviewed']}
                for r in first['results']]})

    rebuild_path = fixture/'real-empty-rebuild'
    child('build_dense_index.py','--output',rebuild_path)
    with DenseIndex(args.index) as first, DenseIndex(rebuild_path) as second:
        difference = float(np.max(np.abs(first.vectors-second.vectors)))
        record('real_reencoding_from_empty_directory', second.manifest['records']==99 and second.mapping==first.mapping)
        record('rebuild_vectors_match_with_explicit_float32_tolerance', np.allclose(first.vectors,second.vectors,atol=2e-6,rtol=1e-5),
               {'max_absolute_difference':difference,'atol':2e-6,'rtol':1e-5,
                'byte_identical_vectors':bool(np.array_equal(first.vectors,second.vectors))})
        rebuild_manifest = second.manifest

    def reject(name, callback):
        try:
            callback()
            value = False
        except ValueError:
            value = True
        negative.append({'case':name,'rejected':value})

    def inspect(target, config_path=CONFIG):
        with DenseIndex(target,config_path): pass

    def cloned(name):
        target = fixture/name
        shutil.copytree(args.index,target)
        return target

    def resign(target, vector_changed=False):
        path = target/'index_manifest.json'
        manifest = json.loads(path.read_text('utf-8'))
        manifest['artifact_files'] = inventory(target)
        if vector_changed:
            manifest['vector_fingerprint']=digest(np.load(target/'embeddings.npy',allow_pickle=False).tobytes(order='C'))
        write_json(path,manifest)

    target = cloned('bad-physical-hash')
    with (target/'embeddings.npy').open('ab') as handle: handle.write(b'corruption')
    reject('physical_artifact_hash_changed',lambda:inspect(target))
    target = cloned('bad-id-map')
    changed = json.loads((target/'id_mapping.json').read_text('utf-8'))
    changed[0]['chunk_id']=changed[1]['chunk_id']
    write_json(target/'id_mapping.json',changed);resign(target)
    reject('duplicate_id_even_after_resigning_outer_hash',lambda:inspect(target))
    target = cloned('bad-vector-dimension')
    np.save(target/'embeddings.npy',np.ones((99,3),dtype=np.float32),allow_pickle=False);resign(target,True)
    reject('wrong_vector_dimension_after_resigning',lambda:inspect(target))
    target = cloned('zero-vector')
    values = np.load(target/'embeddings.npy',allow_pickle=False);values[0]=0
    np.save(target/'embeddings.npy',values,allow_pickle=False);resign(target,True)
    reject('zero_vector_after_resigning',lambda:inspect(target))
    target = cloned('forged-source-record')
    altered = load_jsonl(target/'records.jsonl');altered[0]['source_url']='https://invalid.example/'
    write_jsonl(target/'records.jsonl',altered);resign(target)
    reject('forged_source_after_resigning',lambda:inspect(target))
    target = cloned('forged-stored-vector')
    client, collection = open_collection(target,cfg)
    try:
        collection.update(ids=[rows[0]['chunk_id']],embeddings=[unit_vectors(np.ones((1,1024)),1024,1)[0].tolist()])
    finally:close_client(client)
    resign(target)
    reject('database_vector_differs_from_npy_after_resigning',lambda:inspect(target))
    target = cloned('wrong-count')
    altered = json.loads((target/'index_manifest.json').read_text('utf-8'));altered['records']=98
    write_json(target/'index_manifest.json',altered)
    reject('manifest_wrong_record_count',lambda:inspect(target))
    target = cloned('incomplete-build')
    altered['records']=99;altered['state']='BUILDING'
    write_json(target/'index_manifest.json',altered)
    reject('incomplete_build_never_loaded',lambda:inspect(target))
    changed_cfg=copy.deepcopy(cfg);changed_cfg['model']['digest']='0'*64
    reject('changed_live_model_digest_before_encoding',lambda:PinnedEmbedder(changed_cfg))
    changed_config_path=fixture/'changed-config.json'
    changed_cfg=copy.deepcopy(cfg);changed_cfg['embedding']['batch_size']=2;write_json(changed_config_path,changed_cfg)
    reject('different_build_configuration',lambda:inspect(args.index,changed_config_path))
    reject('output_outside_allowed_index_roots',lambda:safe_output(ROOT/'docs/unsafe-index'))
    reject('nonempty_output_not_overwritten',lambda:build(args.index))
    reject('nan_embedding',lambda:unit_vectors([[float('nan')]*1024],1024,1))
    reject('zero_embedding',lambda:unit_vectors([[0]*1024],1024,1))
    with DenseIndex(args.index) as index:
        reject('blank_query',lambda:index.query('   '))
        reject('invalid_top_k_before_encoding',lambda:index.query('足球',0))
        reject('query_vector_wrong_dimension',lambda:index.query_vector([1,2],3))
        reject('boolean_top_k_not_integer',lambda:index.query_vector(index.vectors[0],True))
    record('all_corrupt_and_invalid_cases_rejected',all(r['rejected'] for r in negative),negative)
    record('task1_to_4_input_snapshots_unchanged',snapshot_inputs()==before)
    lock=json.loads((ROOT/'data/manifests/task1_task2_baseline_lock.json').read_text('utf-8'))
    record('10_frozen_files_and_4_historical_prefixes_unchanged',
        all(digest((ROOT/r['path']).read_bytes())==r['sha256'] for r in lock['files']) and
        all(digest((ROOT/r['path']).read_bytes()[:r['original_size_bytes']])==r['original_prefix_sha256'] for r in lock['append_only_files']))
    local=json.loads((ROOT/'data/manifests/local_data_files.json').read_text('utf-8'))['files']
    record('all_61_local_corpus_files_unchanged',len(local)==61 and all(digest((ROOT/r['path']).read_bytes())==r['sha256'] for r in local))
    for name in ('dataset_manifest.json','human_review_receipt.json','owner_approval_receipt.json','retrieval_test.jsonl'):
        old=subprocess.check_output(['git','show',BASE+':data/eval/'+name],cwd=ROOT)
        record('task4_baseline_bytes_'+name,(ROOT/'data/eval'/name).read_bytes()==old)
    if args.original_root:
        original_files=json.loads(args.original_snapshot.read_text('utf-8'))
        record('original_project_178_static_files_unchanged',len(original_files)==178 and all(
            digest((args.original_root/name).read_bytes())==sha for name,sha in original_files.items()))
        record('original_project_has_no_root_git',not (args.original_root/'.git').exists())
    record('telemetry_uses_local_disabled_implementation', 'chroma_product_telemetry_impl=\'dense_telemetry.DisabledTelemetry\'' in (ROOT/'scripts/dense_index.py').read_text('utf-8'))
    result={'captured_at':datetime.now(timezone.utc).isoformat(),'status':'PASS' if all(r['passed'] for r in checks) else 'FAIL',
        'passed':sum(r['passed'] for r in checks),'total':len(checks),'checks':checks,
        'negative_cases_rejected':sum(r['rejected'] for r in negative),'negative_cases_total':len(negative),
        'baseline_commit':BASE,'index_manifest_sha256':digest((args.index/'index_manifest.json').read_bytes()),
        'build_timing':original['timing'],'rebuild_timing':rebuild_manifest['timing'],
        'rebuild_directory':rebuild_path.relative_to(ROOT).as_posix(),'max_rebuild_vector_difference':difference,
        'model_runtime':original['model_runtime'],'environment':original['environment'],
        'actual_corpus_reencodings_this_command':1,'locked_test_queries_parsed_or_scored':False,
        'retrieval_quality_metrics_computed':False,'smoke_query_count':len(smoke),
        'implementation_sha256':{name:digest((ROOT/'scripts'/name).read_bytes()) for name in
            ('dense_index.py','dense_telemetry.py','build_dense_index.py','query_dense_index.py','verify_task5_delivery.py','recheck_task5.ps1')}}
    write_json(ROOT/'reports/evidence/task5_dense_smoke.json',{'captured_at':result['captured_at'],
        'scope':'Ad hoc index usability queries; not taken from evaluation files and not scored for quality',
        'top_k':3,'queries':smoke,'full_source_text_published':False})
    write_json(ROOT/'reports/acceptance/task5_delivery_gate.json',result)
    print(json.dumps({k:result[k] for k in ('status','passed','total','negative_cases_rejected','negative_cases_total','max_rebuild_vector_difference')}))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        message=str(exc).replace(str(ROOT),'<project>')
        write_json(ROOT/'reports/acceptance/task5_delivery_gate.json',{
            'captured_at':datetime.now(timezone.utc).isoformat(),'status':'FAIL',
            'errors':[type(exc).__name__+': '+message],
            'retrieval_quality_metrics_computed':False,'locked_test_queries_parsed_or_scored':False})
        print(json.dumps({'status':'FAIL','error':message},ensure_ascii=False))
        raise SystemExit(1)
