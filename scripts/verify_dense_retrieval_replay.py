"""Replay saved development evidence and reject isolated corrupt copies; no model calls."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone

from dense_retrieval_eval import file_record, replay
from eval_dataset import ROOT, digest

DEVELOPMENT=ROOT/'reports/retrieval/dense_b0/dev'
CORE=('dense_retrieval_eval.py','run_dense_retrieval.py','recompute_dense_retrieval.py')


def read_json(path):return json.loads(Path(path).read_text('utf-8'))


def write_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def read_rows(path):return [json.loads(line) for line in Path(path).read_text('utf-8').splitlines() if line.strip()]


def write_rows(path,rows):
    Path(path).write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8')


def inventory(directory):
    return {p.relative_to(directory).as_posix():digest(p.read_bytes())
            for p in sorted(directory.rglob('*')) if p.is_file()}


def state(path):
    path=Path(path)
    return {'exists':path.exists(),'sha256':digest(path.read_bytes()) if path.is_file() else None}


def verify():
    if read_json(DEVELOPMENT/'run_manifest.json').get('split')!='dev':
        raise ValueError('Only the saved development run may be used by this regression')
    baseline=inventory(DEVELOPMENT)
    fixture_root=ROOT/'.tmp'/('task7-replay-'+uuid.uuid4().hex)
    fixture_root.mkdir(parents=True)
    checks={};errors={};commands=[]

    def check(name,passed,detail=None):
        checks[name]=bool(passed)
        if not passed:errors[name]=detail or 'Assertion was false'

    original_summary=replay(DEVELOPMENT)
    check('original_development_replays',original_summary['split']=='dev'
          and original_summary['quality']['questions']==40)

    def mutate_json(name,operation):
        def mutate(folder):
            path=folder/name;value=read_json(path);operation(value);write_json(path,value)
        return mutate

    def mutate_rows(name,operation):
        def mutate(folder):
            path=folder/name;value=read_rows(path);operation(value);write_rows(path,value)
        return mutate

    def manifest(field,value):return mutate_json('run_manifest.json',lambda m:m.update({field:value}))

    def resign(folder):
        path=folder/'run_manifest.json';value=read_json(path)
        for name in list(value['artifacts']):
            if (folder/name).is_file():value['artifacts'][name]=file_record(folder/name)
        write_json(path,value)

    cases=[
        ('manifest_status',manifest('status','FAILED'),True),
        ('manifest_schema',manifest('manifest_version','unknown'),True),
        ('purpose',manifest('purpose','parameter_selection'),True),
        ('parameter_selection',manifest('used_for_parameter_selection',True),True),
        ('gold_in_retrieval',manifest('gold_passed_to_retrieval',True),True),
        ('generation_requests',manifest('llm_generation_requests',1),True),
        ('index_unchanged_claim',manifest('formal_index_artifacts_unchanged',False),True),
        ('query_request_count',manifest('query_request_count',119),True),
        ('warmup_request_count',manifest('warmup_request_count',2),True),
        ('index_version',manifest('index_version','synthetic-other-index'),True),
        ('index_hash',manifest('index_manifest_sha256','0'*64),True),
        ('vector_fingerprint',manifest('index_vector_fingerprint','0'*64),True),
        ('corpus_hash',manifest('corpus_sha256','0'*64),True),
        ('corpus_version',manifest('corpus_version','synthetic-other-corpus'),True),
        ('dataset_version',manifest('dataset_version','synthetic-other-eval'),True),
        ('unknown_source_commit',manifest('source_commit','f'*40),True),
        ('model_artifact',mutate_json('run_manifest.json',lambda m:m['model_artifact'].update(digest='0'*64)),True),
        ('model_runtime_digest',mutate_json('run_manifest.json',lambda m:m['model_runtime_after'].update(digest='0'*64)),True),
        ('gpu_runtime',mutate_json('run_manifest.json',lambda m:m['model_runtime_before'].update(size_vram=1)),True),
        ('boolean_gpu_runtime',mutate_json('run_manifest.json',lambda m:m['model_runtime_before'].update(size_vram=False)),True),
        ('startup_nan',manifest('startup_loading_seconds',float('nan')),True),
        ('wall_time_negative',manifest('whole_run_wall_seconds',-1),True),
        ('missing_warmup',manifest('warmups',[]),True),
        ('warmup_nan',mutate_json('run_manifest.json',lambda m:m['warmups'][0]['timing'].update(query_embedding_seconds=float('nan'))),True),
        ('unexpected_dev_authorization',manifest('authorization',{'path':'synthetic'}),True),
        ('configuration',mutate_json('run_manifest.json',lambda m:m['config'].update(top_k=5)),True),
        ('input_snapshot_hash',mutate_json('run_manifest.json',lambda m:m['input_snapshots']['data/eval/retrieval_dev.jsonl'].update(sha256='0'*64)),True),
        ('missing_input_snapshot',mutate_json('run_manifest.json',lambda m:m['input_snapshots'].pop('config/dense_index.json')),True),
        ('source_record_hash',mutate_json('source_map.json',lambda rows:rows[0].update(record_sha256='0'*64)),True),
        ('source_url_mismatch',mutate_json('source_map.json',lambda rows:rows[0].update(source_url='https://example.invalid/forged')),True),
        ('source_extra_body',mutate_json('source_map.json',lambda rows:rows[0].update(content_zh='invented forbidden body')),True),
        ('source_duplicate',mutate_json('source_map.json',lambda rows:rows.__setitem__(1,dict(rows[0]))),True),
        ('prediction_query_hash',mutate_rows('predictions.jsonl',lambda rows:rows[0].update(question_sha256='0'*64)),True),
        ('prediction_query',mutate_rows('predictions.jsonl',lambda rows:rows[0].update(query='invented unbound query')),True),
        ('prediction_boolean_rank',mutate_rows('predictions.jsonl',lambda rows:rows[0]['results'][0].update(rank=True)),True),
        ('prediction_top10_depth',mutate_rows('predictions.jsonl',lambda rows:rows[0]['results'].pop()),True),
        ('prediction_source_metadata',mutate_rows('predictions.jsonl',lambda rows:rows[0]['results'][0].update(source_url='https://example.invalid/forged')),True),
        ('timing_total_omits_stages',mutate_rows('predictions.jsonl',lambda rows:rows[0]['measurements'][0].update(total_seconds=0)),True),
        ('timing_nonfinite',mutate_rows('predictions.jsonl',lambda rows:rows[0]['measurements'][0].update(vector_search_seconds=float('inf'))),True),
        ('timing_stage_missing',mutate_rows('predictions.jsonl',lambda rows:rows[0]['measurements'][0].pop('normalization_seconds')),True),
        ('requests_missing_sample',mutate_rows('requests.jsonl',lambda rows:rows.pop()),True),
        ('requests_duplicate_sample',mutate_rows('requests.jsonl',lambda rows:rows.append(dict(rows[0]))),True),
        ('requests_question_mismatch',mutate_rows('requests.jsonl',lambda rows:rows[0].update(question_id='SYNTHETIC_UNKNOWN')),True),
        ('requests_measurement_mismatch',mutate_rows('requests.jsonl',lambda rows:rows[0]['measurement'].update(total_seconds=999)),True),
        ('summary_metric',mutate_json('summary.json',lambda m:m['quality']['metrics'].update({'Recall@5':-1})),True),
        ('summary_latency',mutate_json('summary.json',lambda m:m['latency']['stages']['total_seconds'].update(p95=-1)),True),
        ('error_analysis',mutate_json('error_analysis.json',lambda m:m.update(miss_top5=-1)),True),
        ('run_started_identity',mutate_json('run_started.json',lambda m:m.update(run_id='0'*32)),True),
        ('artifact_hash_without_resigning',mutate_rows('requests.jsonl',lambda rows:rows.pop()),False),
        ('manifest_artifact_hash',mutate_json('run_manifest.json',lambda m:m['artifacts']['predictions.jsonl'].update(sha256='0'*64)),False),
        ('artifact_inventory_missing',mutate_json('run_manifest.json',lambda m:m['artifacts'].pop('error_analysis.json')),True),
    ]
    for name,mutation,update_hashes in cases:
        folder=fixture_root/name
        shutil.copytree(DEVELOPMENT,folder)
        resign(folder)
        try:
            clean=replay(folder)
            check('clean_copy_'+name,clean==original_summary)
        except Exception as exc:
            check('clean_copy_'+name,False,type(exc).__name__+': '+str(exc))
            continue
        mutation(folder)
        if update_hashes:resign(folder)
        try:replay(folder)
        except (ValueError,TypeError,KeyError,json.JSONDecodeError,subprocess.CalledProcessError) as exc:
            check('reject_'+name,True)
        else:check('reject_'+name,False,'Corrupt isolated development copy was accepted')

    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')

    def invoke(arguments):
        result=subprocess.run([sys.executable,'-B',*arguments],cwd=ROOT,env=env,
                              capture_output=True,text=True,encoding='utf-8',timeout=60)
        commands.append({'script':arguments[0],'arguments':arguments[1:],
                         'returncode':result.returncode})
        return result

    forbidden_run=ROOT/'reports/retrieval'/('unauthorized-contract-'+uuid.uuid4().hex)
    usage=forbidden_run.parent/'test_usage.jsonl';before_usage=state(usage)
    result=invoke(['scripts/run_dense_retrieval.py','--mode','test','--run-dir',str(forbidden_run)])
    check('unauthorized_test_exits_nonzero',result.returncode!=0)
    check('unauthorized_test_rejected_for_missing_authorization',
          'Locked test requires a preregistered authorization' in result.stderr,
          'Expected missing-authorization gate was not reached')
    check('unauthorized_test_does_not_create_run_directory',not forbidden_run.exists())
    check('unauthorized_test_does_not_append_usage_ledger',state(usage)==before_usage)
    result=invoke(['scripts/run_dense_retrieval.py','--mode','dev','--run-dir',str(DEVELOPMENT)])
    check('existing_dev_directory_exits_nonzero',result.returncode!=0)
    check('existing_dev_directory_rejected_for_preservation',
          'preserve previous attempts' in result.stderr,'Expected no-overwrite gate was not reached')
    result=invoke(['scripts/recompute_dense_retrieval.py','--run-dir',str(DEVELOPMENT),
                   '--output',str(DEVELOPMENT/'summary.json')])
    check('existing_recompute_output_exits_nonzero',result.returncode!=0)
    check('existing_recompute_output_rejected_for_preservation',
          'Use a new JSON output' in result.stderr,'Expected no-overwrite gate was not reached')
    check('original_development_artifact_bytes_unchanged',inventory(DEVELOPMENT)==baseline)
    check('usage_ledger_still_unchanged',state(usage)==before_usage)
    return {'status':'PASS' if all(checks.values()) else 'FAIL','check_count':len(checks),
        'passed_checks':sum(checks.values()),'checks':checks,
        'failed_checks':[k for k,v in checks.items() if not v],'errors':errors,
        'generated_at':datetime.now(timezone.utc).isoformat(),
        'source_sha256':{name:digest((ROOT/'scripts'/name).read_bytes()) for name in CORE},
        'input_development_manifest':file_record(DEVELOPMENT/'run_manifest.json'),
        'fixture_directory':fixture_root.relative_to(ROOT).as_posix(),'corrupt_copy_cases':len(cases),
        'commands':commands,'model_requests':0,'real_test_embedding_or_scoring_requests':0,
        'real_test_questions_inspected_by_agent':False,'original_data_or_index_modified':False,
        'scope':'Saved dev replay and isolated copies only; runner integrity gates may parse frozen evaluation metadata; no official test inference or benchmark tuning'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',required=True)
    args=parser.parse_args();report=(ROOT/args.report).resolve()
    if report.suffix!='.json' or not any(report.is_relative_to(ROOT/p) for p in ('reports','.tmp')):
        raise ValueError('Use a new JSON report under reports/ or .tmp/')
    if report.exists():raise ValueError('Refusing to overwrite an existing replay regression report')
    result=verify();report.parent.mkdir(parents=True,exist_ok=True)
    with report.open('x',encoding='utf-8',newline='\n') as handle:
        json.dump(result,handle,ensure_ascii=False,indent=2,allow_nan=False);handle.write('\n')
    print(json.dumps({'status':result['status'],'check_count':result['check_count'],
        'passed_checks':result['passed_checks'],'failed_checks':result['failed_checks'],
        'report':report.relative_to(ROOT).as_posix()}))
    raise SystemExit(0 if result['status']=='PASS' else 1)


if __name__=='__main__':main()
