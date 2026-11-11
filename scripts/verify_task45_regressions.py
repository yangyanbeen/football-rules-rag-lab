"""Regression cases for the six reproduced task 4/5 delivery defects."""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from dense_index import (CONFIG, DEFAULT_INDEX, DenseIndex, PinnedEmbedder, _CLIENT_REFERENCES,
                         collection_metadata, inventory, load_config, open_collection, safe_output)
from eval_dataset import EVAL, REVIEW_LEDGER, ROOT, digest, write_json
from freeze_eval_dataset import freeze
from validate_eval_dataset import validate
from validate_eval_receipt import validate_receipt

BASE='3e41191c145da963fb24057bb1b39354287ebc5a'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    report=args.report.resolve()
    if not report.is_relative_to(ROOT/'reports') or report.suffix!='.json':
        raise ValueError('Use a report JSON under reports/')
    folder=ROOT/'.tmp'/('task45-regression-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
    folder.mkdir(parents=True)
    checks=[]
    def record(name, passed):checks.append({'check':name,'passed':bool(passed)})
    def rejects(callback):
        try:callback()
        except ValueError:return True
        return False
    historical_names=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE,'reports','data/eval',
        'data/manifests/dense_index_manifest.json','data/manifests/dense_chunk_ids.json'],cwd=ROOT,text=True).splitlines()
    historical={name:digest((ROOT/name).read_bytes()) for name in historical_names}
    original_index={**inventory(DEFAULT_INDEX),'index_manifest.json':digest((DEFAULT_INDEX/'index_manifest.json').read_bytes())}

    public=validate_receipt()
    record('real_public_receipt_13_checks',public['status']=='PASS_PUBLIC_RECEIPT' and public['passed']==public['total']==13)
    record('public_receipt_does_not_claim_private_reading_proof',public['private_human_reading_independently_proven'] is False)
    checkout=folder/'public-checkout'
    (checkout/'scripts').mkdir(parents=True)
    for name in ('eval_dataset.py','validate_eval_receipt.py'):shutil.copy2(ROOT/'scripts'/name,checkout/'scripts'/name)
    shutil.copytree(EVAL,checkout/'data/eval')
    proc=subprocess.run([sys.executable,str(checkout/'scripts/validate_eval_receipt.py')],cwd=checkout,
        capture_output=True,text=True,encoding='utf-8',timeout=30)
    record('published_only_checkout_validation_without_corpus_ledger_or_models',proc.returncode==0 and
        json.loads(proc.stdout)['status']=='PASS_PUBLIC_RECEIPT' and not (checkout/'data/processed').exists()
        and not (checkout/'.runtime').exists())

    missing=folder/'missing-receipt'
    shutil.copytree(EVAL,missing,ignore=lambda _,names:['human_review_receipt.json'] if 'human_review_receipt.json' in names else [])
    record('missing_public_receipt_detected',validate_receipt(missing)['status']=='FAIL')
    before={p.name:digest(p.read_bytes()) for p in missing.iterdir() if p.is_file()}
    record('refreeze_missing_receipt_rejected_without_writes',rejects(lambda:freeze(missing,REVIEW_LEDGER))
        and before=={p.name:digest(p.read_bytes()) for p in missing.iterdir() if p.is_file()})
    cases=[
        ('duplicate_question',lambda r:r['records'][1].update(question_id=r['records'][0]['question_id'])),
        ('wrong_annotation',lambda r:r['records'][0].update(annotation_sha256='0'*64)),
        ('ai_signoff',lambda r:r['records'][0].update(reviewer_type='ai')),
        ('nonapproved_decision',lambda r:r['records'][0].update(decision='changes_requested')),
        ('private_field',lambda r:r['records'][0].update(reviewer_name='SYNTHETIC FIXTURE ONLY')),
        ('naive_time',lambda r:r['records'][0].update(reviewed_at='2026-11-11T12:00:00')),
        ('invalid_time_type',lambda r:r['records'][0].update(reviewed_at=None)),
        ('future_review',lambda r:r['records'][0].update(reviewed_at='2099-01-01T00:00:00+00:00')),
        ('wrong_version',lambda r:r.update(dataset_version='incorrect')),
        ('wrong_ledger_hash',lambda r:r.update(private_ledger_sha256='f'*64)),
        ('wrong_test_hash',lambda r:r.update(test_sha256='e'*64)),
    ]
    for name,mutate in cases:
        target=folder/('receipt-'+name);shutil.copytree(EVAL,target)
        receipt_path=target/'human_review_receipt.json'
        receipt=json.loads(receipt_path.read_text('utf-8'));mutate(receipt);write_json(receipt_path,receipt)
        manifest_path=target/'dataset_manifest.json'
        manifest=json.loads(manifest_path.read_text('utf-8'))
        manifest['human_review']['receipt_sha256']=digest(receipt_path.read_bytes());write_json(manifest_path,manifest)
        record('rehashed_public_receipt_rejects_'+name,validate_receipt(target)['status']=='FAIL')
    record('published_metadata_cannot_replace_real_private_ledger',validate(phase='delivery',ledger=folder/'absent-ledger.jsonl')['status']=='FAIL')

    first,second=DenseIndex(),DenseIndex()
    second.close();second.close()
    record('other_shared_instance_remains_queryable',first.query_vector(first.vectors[0],1)[0]['chunk_id']==first.rows[0]['chunk_id'])
    first.close();first.close()
    record('shared_instances_close_idempotently',not _CLIENT_REFERENCES)
    record('closed_index_query_rejected',rejects(lambda:first.query('足球')))
    record('closed_index_vector_query_rejected',rejects(lambda:first.query_vector(first.vectors[0],1)))
    target=folder/'missing-collection';shutil.copytree(DEFAULT_INDEX,target)
    cfg=copy.deepcopy(load_config());cfg['storage']['collection']='missing-collection'
    from chromadb.api.shared_system_client import SharedSystemClient
    try:open_collection(target,cfg);failed=False
    except Exception:failed=True
    record('failed_collection_open_releases_its_system',failed and str(target/'chroma') not in SharedSystemClient._identifier_to_system
        and str(target/'chroma') not in _CLIENT_REFERENCES)
    with DenseIndex() as index:
        cfg=copy.deepcopy(load_config());cfg['storage']['collection']='missing-collection'
        try:open_collection(DEFAULT_INDEX,cfg);failed=False
        except Exception:failed=True
        record('failed_shared_open_keeps_other_client_alive',failed and index.query_vector(index.vectors[0],1)[0]['chunk_id']==index.rows[0]['chunk_id'])

    with DenseIndex() as index:
        row=index.rows[0];meta=collection_metadata(row);vector=index.vectors[0]
        packets={
            'partial':{'ids':[[row['chunk_id']]],'distances':[[0.0]],'metadatas':[[meta]]},
            'duplicate':{'ids':[[row['chunk_id']]*3],'distances':[[0.0]*3],'metadatas':[[meta]*3]},
            'misaligned':{'ids':[[row['chunk_id']]*3],'distances':[[0.0]],'metadatas':[[meta]*3]},
            'missing_fields':{'ids':[[row['chunk_id']]]},
        }
        for name,packet in packets.items():
            index.collection=SimpleNamespace(query=lambda _packet=packet,**kwargs:_packet)
            record('query_packet_rejects_'+name,rejects(lambda:index.query_vector(vector,3)))
        index.collection=SimpleNamespace(query=lambda **kwargs:{'ids':[[row['chunk_id']]],'distances':[[0.1]],'metadatas':[[meta]]})
        record('query_packet_rejects_incorrect_finite_distance',rejects(lambda:index.query_vector(vector,1)))
    record('unqualified_external_embedder_rejected',rejects(lambda:DenseIndex(embedder=SimpleNamespace(encode=lambda texts:np.ones((1,1024))))))
    fake=PinnedEmbedder.__new__(PinnedEmbedder);fake.cfg=copy.deepcopy(load_config());fake.cfg['model']['digest']='0'*64
    record('different_pinned_embedder_configuration_rejected',rejects(lambda:DenseIndex(embedder=fake)))
    cfg=load_config()
    for section,field,value in [('embedding','api','/unsupported'),('text','query_template','unsupported-prefix'),
                                ('embedding','num_gpu',False),('top','expected_records',99.0)]:
        changed=copy.deepcopy(cfg)
        (changed if section=='top' else changed[section])[field]=value
        path=folder/(field+'-config.json');write_json(path,changed)
        record('unsupported_configuration_rejected_'+field,rejects(lambda:load_config(path)))
    record('nested_index_output_rejected_before_write',rejects(lambda:safe_output(DEFAULT_INDEX/'new-child-index')))
    record('original_index_files_unchanged',original_index=={**inventory(DEFAULT_INDEX),
        'index_manifest.json':digest((DEFAULT_INDEX/'index_manifest.json').read_bytes())})
    record('all_historical_eval_reports_and_public_index_metadata_unchanged',historical=={name:digest((ROOT/name).read_bytes()) for name in historical_names})
    record('original_human_validator_source_unchanged',(ROOT/'scripts/validate_eval_dataset.py').read_bytes()==subprocess.check_output(
        ['git','show',BASE+':scripts/validate_eval_dataset.py'],cwd=ROOT))
    record('no_client_reference_leaks_after_all_cases',not _CLIENT_REFERENCES)
    result={'captured_at':datetime.now(timezone.utc).isoformat(),'status':'PASS' if all(r['passed'] for r in checks) else 'FAIL',
        'passed':sum(r['passed'] for r in checks),'total':len(checks),'checks':checks,'reference_commit':BASE,
        'actual_human_reviews_created':False,'real_dataset_quality_metrics_computed':False,
        'historical_files_preserved':len(historical),
        'implementation_sha256':{name:digest((ROOT/'scripts'/name).read_bytes()) for name in
            ('dense_index.py','freeze_eval_dataset.py','validate_eval_receipt.py','verify_task45_regressions.py')}}
    write_json(report,result)
    print(json.dumps({k:result[k] for k in ('status','passed','total','historical_files_preserved')}))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
