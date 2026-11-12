"""Task7 defect regressions: isolated development fixtures, no model requests."""
from __future__ import annotations
import argparse,copy,contextlib,io,json,shutil,sys,uuid
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from eval_dataset import ROOT,digest,load_jsonl,write_json
import dense_retrieval_eval as e
import dense_retrieval_contracts as c
import run_dense_retrieval as runner
import verify_task7_delivery as gate

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();report=args.report.resolve()
    if report.exists() or not report.is_relative_to(ROOT/'reports') or report.suffix!='.json':raise ValueError('Use new reports JSON')
    temp=ROOT/'.tmp'/('task7-supplement-'+uuid.uuid4().hex);temp.mkdir()
    dev=ROOT/'reports/retrieval/dense_b0/dev';checks={}
    def check(name,value):checks[name]=bool(value)
    def rejects(f):
        try:f()
        except (ValueError,TypeError,KeyError,OSError):return True
        return False
    manifest=json.loads((dev/'run_manifest.json').read_text('utf-8'));cfg=e.load_config()
    original=e.replay(dev)
    check('historical_development_replays_after_authorized_source_fixes',original['quality']['questions']==40)
    check('new_execution_still_requires_current_committed_source',rejects(lambda:e.require_committed_sources(manifest['source_commit'])))
    check('authorization_dependency_now_in_source_policy','scripts/run_retrieval_metrics.py' in e.SOURCES)
    check('new_contract_module_in_source_policy','scripts/dense_retrieval_contracts.py' in e.SOURCES)
    current=e.snapshots();actual=e.file_record
    def changed(path):
        r=actual(path)
        return {**r,'sha256':'0'*64} if r['path']=='scripts/run_retrieval_metrics.py' else r
    with patch.object(e,'file_record',side_effect=changed):
        check('execution_detects_changed_authorization_dependency',rejects(lambda:e.require_matching_snapshots(current)))
    cases=[('bool_warmup',lambda m:m['warmups'][0].update(repetition=True)),
      ('wrong_model_name',lambda m:m['model_runtime_before'].update(name='wrong')),
      ('zero_model_context',lambda m:m['model_runtime_after'].update(context_length=0)),
      ('bool_model_context',lambda m:m['model_runtime_after'].update(context_length=True)),
      ('wrong_runner',lambda m:m['model_runtime_before'].update(runner='wrong')),
      ('negative_model_size',lambda m:m['model_runtime_after'].update(size=-1)),
      ('time_reversed',lambda m:m.update(completed_at='2000-01-01T00:00:00+00:00')),
      ('time_invalid',lambda m:m.update(completed_at='not-a-date')),
      ('time_no_zone',lambda m:m.update(completed_at='2026-11-12T09:00:00')),
      ('extra_manifest',lambda m:m.update(content_zh='SYNTHETIC unapproved body')),
      ('extra_runtime',lambda m:m['model_runtime_before'].update(content_zh='SYNTHETIC body')),
      ('extra_environment',lambda m:m['environment'].update(content_zh='SYNTHETIC body')),
      ('bool_cpu_count',lambda m:m['environment'].update(logical_cpus=True)),
      ('wrong_packages',lambda m:m['environment']['packages'].update(numpy='wrong')),
      ('bool_inline_cache',lambda m:m['config'].update(cache=0)),
      ('zero_warmup_total',lambda m:m['warmups'][0].update(total_seconds=0)),
      ('zero_whole_wall',lambda m:m.update(whole_run_wall_seconds=0)),
      ('oversize_warmup_stage',lambda m:m['warmups'][0]['timing'].update(query_embedding_seconds=999)),
      ('forged_source_provenance',lambda m:m['input_snapshots']['scripts/dense_retrieval_eval.py'].update(sha256='0'*64))]
    for name,mutate in cases:
        folder=temp/name;shutil.copytree(dev,folder);m=copy.deepcopy(manifest);mutate(m)
        for filename in m['artifacts']:m['artifacts'][filename]=e.file_record(folder/filename)
        write_json(folder/'run_manifest.json',m)
        check('reject_'+name,rejects(lambda:e.replay(folder)))
    for name in ('extra_started','recorded_failure'):
        folder=temp/name;shutil.copytree(dev,folder);m=copy.deepcopy(manifest)
        path=folder/('run_started.json' if name=='extra_started' else 'failure.json')
        value=json.loads(path.read_text('utf-8')) if path.exists() else {'status':'FAILED'}
        value['content_zh']='SYNTHETIC unapproved body';write_json(path,value)
        for filename in m['artifacts']:m['artifacts'][filename]=e.file_record(folder/filename)
        write_json(folder/'run_manifest.json',m)
        check('reject_'+name,rejects(lambda:e.replay(folder)))
    questions=load_jsonl(ROOT/'data/eval/retrieval_dev.jsonl');pred=load_jsonl(dev/'predictions.jsonl');sources=json.loads((dev/'source_map.json').read_text('utf-8'))
    for name,mutate in [('http_outside_embedding',lambda m:m['embedding_observation'].update(elapsed_seconds=999)),
      ('server_load_outside_total',lambda m:m['embedding_observation'].update(server_total_duration_ns=1,server_load_duration_ns=999)),
      ('server_outside_http',lambda m:m['embedding_observation'].update(server_total_duration_ns=10**15)),
      ('zero_measured_wall',lambda m:m.update({k:0 for k in e.TIMINGS})),
      ('bool_observation_inputs',lambda m:m['embedding_observation'].update(inputs=True))]:
        changed_pred=copy.deepcopy(pred);mutate(changed_pred[0]['measurements'][0])
        check('reject_'+name,rejects(lambda:e.validate_predictions(questions,changed_pred,cfg,sources,'dev',manifest['run_id'])))
    bad_sources=copy.deepcopy(sources);bad_sources[0]['law_number']=True
    check('reject_bool_law_metadata',rejects(lambda:e.validate_predictions(questions,pred,cfg,bad_sources,'dev',manifest['run_id'])))
    base=ROOT/'reports/retrieval/dense_b0';grant=json.loads((base/'test_authorization.json').read_text('utf-8'))
    release=json.loads((ROOT/'data/eval/dataset_manifest.json').read_text('utf-8'))
    test_manifest=json.loads((base/'test/run_manifest.json').read_text('utf-8'))
    def grant_check(value):return c.grant_metadata(value,release,cfg,digest(e.CONFIG.read_bytes()),'reports/retrieval/dense_b0/test',test_manifest['source_commit'],test_manifest['started_at'])
    check('original_pretest_authorization_still_valid',grant_check(grant) is None)
    for name,mutate in [('version',lambda g:g.update(authorization_version='wrong')),('dataset',lambda g:g.update(dataset_version='wrong')),
      ('inline_config',lambda g:g['config'].update(cache=0)),('lock_time',lambda g:g.update(test_locked_at='wrong')),
      ('postdated',lambda g:g.update(prepared_at='2099-01-01T00:00:00+00:00')),('receipt_count',lambda g:g.update(development_verification=[])),
      ('extra_body',lambda g:g.update(content_zh='SYNTHETIC body')),('run_path',lambda g:g.update(allowed_run_directory='reports/wrong'))]:
        g=copy.deepcopy(grant);mutate(g);check('reject_grant_'+name,rejects(lambda:grant_check(g)))
    events=load_jsonl(base/'test_usage.jsonl');auth=e.file_record(base/'test_authorization.json')
    check('original_selected_usage_valid',bool(c.usage_matches(events,test_manifest,'reports/retrieval/dense_b0/test',auth,release)))
    other=copy.deepcopy(events)
    for event in other:event.update(run_id='1'*32,run_directory='reports/retrieval/previous/test')
    check('other_completed_run_does_not_invalidate_selected_run',bool(c.usage_matches(other+events,test_manifest,'reports/retrieval/dense_b0/test',auth,release)))
    failed={**other[0],'event':'FAILED'}
    check('other_failed_run_preserved_and_selected_run_valid',bool(c.usage_matches([other[0],failed]+events,test_manifest,'reports/retrieval/dense_b0/test',auth,release)))
    check('missing_selected_terminal_rejected',not c.usage_matches(events[:1],test_manifest,'reports/retrieval/dense_b0/test',auth,release))
    check('duplicated_selected_terminal_rejected',not c.usage_matches(events+[events[1]],test_manifest,'reports/retrieval/dense_b0/test',auth,release))
    # Lifecycle injection uses invented questions and a ROOT below ignored .tmp.
    for name,fail_failure_file in [('start_write',False),('start_and_failure_write',True)]:
        sandbox=temp/name;sandbox.mkdir();(sandbox/'config').mkdir();write_json(sandbox/'config/dense_index.json',{})
        output=sandbox/'reports/retrieval/new/test';fake_dev=sandbox/'reports/dev/run_manifest.json'
        write_json(fake_dev,{'completed_at':'2025-01-01T00:00:00+00:00'})
        ticket={**grant,'prepared_at':'2025-02-01T00:00:00+00:00','input_snapshots':{},'allowed_run_directory':'reports/retrieval/new/test',
                'development_manifest':{'path':'reports/dev/run_manifest.json'},'development_summary':{'path':'reports/dev/summary.json'}}
        ticket_path=sandbox/'authorization.json'
        artifact=lambda p:{'path':Path(p).relative_to(sandbox).as_posix(),'size_bytes':1,'sha256':'a'*64}
        ticket.update(development_manifest=artifact(fake_dev),development_summary=artifact(fake_dev.with_name('summary.json')),development_verification=[])
        write_json(ticket_path,ticket)
        def writer(path,value):
            if Path(path).name=='run_started.json' or (fail_failure_file and Path(path).name=='failure.json'):raise OSError('SYNTHETIC start-write failure')
            return write_json(path,value)
        with contextlib.ExitStack() as stack:
            for key,value in {'ROOT':sandbox,'EVAL':sandbox/'data/eval'}.items():stack.enter_context(patch.object(runner,key,value))
            for key,value in {'load_config':cfg,'require_original_release':release,'snapshots':{},'replay':{'split':'dev'},'file_record':artifact}.items():
                stack.enter_context(patch.object(runner,key,side_effect=value) if callable(value) else patch.object(runner,key,return_value=value))
            stack.enter_context(patch.object(runner,'require_committed_sources'))
            stack.enter_context(patch.object(runner,'require_matching_snapshots'))
            stack.enter_context(patch.object(runner,'authorize_test'))
            stack.enter_context(patch.object(runner.contracts,'grant_metadata'))
            stack.enter_context(patch.object(runner.contracts,'verification_receipts',return_value=[]))
            stack.enter_context(patch.object(runner.subprocess,'check_output',return_value=grant['source_commit']))
            stack.enter_context(patch.object(runner,'load_jsonl',return_value=[{'question_id':f'X{i}','question':'SYNTHETIC question'} for i in range(50)]))
            stack.enter_context(patch.object(runner,'write_json',side_effect=writer))
            with contextlib.redirect_stderr(io.StringIO()):
                try:runner.evaluate(SimpleNamespace(mode='test',run_dir=output,authorization=ticket_path));error=None
                except Exception as exc:error=exc
        logs=load_jsonl(output.parent/'test_usage.jsonl') if (output.parent/'test_usage.jsonl').exists() else []
        check(name+'_preserves_primary_error',isinstance(error,OSError) and 'SYNTHETIC start-write' in str(error))
        check(name+'_records_failed_terminal',[v['event'] for v in logs]==['STARTED','FAILED'])
        check(name+'_never_complete',not (output/'run_manifest.json').exists())
        if not fail_failure_file:check(name+'_records_failure_file',(output/'failure.json').exists())
    import dense_index
    sandbox=temp/'cleanup';sandbox.mkdir();(sandbox/'config').mkdir();write_json(sandbox/'config/dense_index.json',{})
    class FailedIndex:
        closed=0
        @property
        def rows(self):raise ValueError('SYNTHETIC primary source failure')
        def close(self):
            self.closed+=1
            raise RuntimeError('SYNTHETIC cleanup failure')
    failed_index=FailedIndex();output=sandbox/'reports/retrieval/new/dev'
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(runner,'ROOT',sandbox));stack.enter_context(patch.object(runner,'EVAL',sandbox/'data/eval'))
        for key,value in {'load_config':cfg,'require_original_release':release,'snapshots':{},'file_record':lambda p:{'path':'synthetic','sha256':'a'*64,'size_bytes':1}}.items():
            stack.enter_context(patch.object(runner,key,side_effect=value) if callable(value) else patch.object(runner,key,return_value=value))
        stack.enter_context(patch.object(runner,'require_committed_sources'))
        stack.enter_context(patch.object(runner.subprocess,'check_output',return_value=grant['source_commit']))
        stack.enter_context(patch.object(runner,'load_jsonl',return_value=[{'question_id':f'X{i}','question':'SYNTHETIC question'} for i in range(40)]))
        stack.enter_context(patch.object(dense_index,'DenseIndex',return_value=failed_index))
        stack.enter_context(patch.object(dense_index,'PinnedEmbedder',return_value=SimpleNamespace()))
        with contextlib.redirect_stderr(io.StringIO()):
            try:runner.evaluate(SimpleNamespace(mode='dev',run_dir=output,authorization=None));error=None
            except Exception as exc:error=exc
    check('cleanup_does_not_replace_primary_exception',isinstance(error,ValueError) and 'primary source' in str(error))
    check('cleanup_attempted_once_after_primary_failure',failed_index.closed==1)
    check('primary_failure_evidence_survives_cleanup_error','primary source' in json.loads((output/'failure.json').read_text('utf-8'))['error'])
    fake_receipt=temp/'incomplete-PASS.json'
    write_json(fake_receipt,{'status':'PASS','checks':{'invented':True},'checks_total':1,'checks_passed':1,
                            'source_sha256':{'verify_dense_metric_arithmetic.py':'a'*64}})
    check('incomplete_PASS_receipt_rejected',rejects(lambda:list(c.verification_receipts([e.file_record(fake_receipt)],grant['source_commit'],e.file_record))))
    # Multiple legitimate snapshot sizes are supported without mutating any baseline.
    before=json.loads((ROOT/'.runtime/task7-audit/before.json').read_text('utf-8'))
    before['tracked']['scripts/dense_retrieval_contracts.py']=digest((ROOT/'scripts/dense_retrieval_contracts.py').read_bytes())
    alternate=ROOT/'.runtime/task7-audit/expanded-preservation.json';write_json(alternate,before)
    result=gate.verify(base/'dev',base/'test',base/'test_authorization.json',base/'test_usage.jsonl',alternate)
    check('expanded_committed_baseline_accepted',result['status']=='PASS')
    baseline=json.loads((ROOT/'.runtime/task7-audit/before.json').read_text('utf-8'))
    old={p:sha for p,sha in baseline['tracked'].items() if p.startswith(('data/eval/','reports/')) and p not in gate.HISTORICAL_REPORT_EXCEPTIONS}
    check('all_original_evaluation_and_delivery_evidence_unchanged',all(digest((ROOT/p).read_bytes())==sha for p,sha in old.items()))
    result={'captured_at':datetime.now(timezone.utc).isoformat(),'status':'PASS' if all(checks.values()) else 'FAIL',
      'passed':sum(checks.values()),'total':len(checks),'checks':checks,'failed':[k for k,v in checks.items() if not v],
      'actual_model_requests':0,'formal_test_experiments_started':0,'test_individual_predictions_read':False,
      'scope':'Isolated development mutations, synthetic authorizations/lifecycle and replay of original evidence; no new test measurement',
      'source_sha256':{n:digest((ROOT/'scripts'/n).read_bytes()) for n in ('dense_retrieval_contracts.py','dense_retrieval_eval.py','run_dense_retrieval.py','verify_task7_delivery.py','verify_task7_supplement.py')}}
    write_json(report,result);print(json.dumps({k:result[k] for k in ('status','passed','total','failed')}))
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
